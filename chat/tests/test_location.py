"""``PUT /conversations/{id}/location``: the phone's position, kept until the order is placed."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from chat.models import Conversation, ConversationState
from chat.tests.helpers import make_world, open_chat, put_location, signed_in

pytestmark = pytest.mark.django_db


def _chat() -> tuple[APIClient, str]:
    make_world()
    _, api = signed_in()
    return api, open_chat(api).json()["conversation"]["id"]


class TestSendingThePosition:
    def test_the_position_is_kept_and_nothing_is_said_in_the_chat(self) -> None:
        api, cid = _chat()

        response = put_location(api, cid, 25.2005, 55.2705, accuracy_m=15, source="gps")

        assert response.status_code == 204 and response.content == b""
        conversation = Conversation.objects.get(pk=cid)
        assert (conversation.location_lat, conversation.location_lng) == (
            25.2005,
            55.2705,
        )
        assert conversation.location_accuracy_m == 15
        assert conversation.location_source == "gps"
        assert conversation.location_captured_at is not None
        assert conversation.messages.count() == 2  # the welcome and the question only

    def test_the_latest_position_wins(self) -> None:
        api, cid = _chat()
        put_location(api, cid, 25.1, 55.1, accuracy_m=50, source="gps")

        put_location(api, cid, 25.2, 55.2, accuracy_m=None, source="simulated")

        conversation = Conversation.objects.get(pk=cid)
        assert (conversation.location_lat, conversation.location_lng) == (25.2, 55.2)
        assert conversation.location_accuracy_m is None
        assert conversation.location_source == "simulated"

    def test_the_accuracy_is_optional_and_may_be_zero(self) -> None:
        api, cid = _chat()

        assert put_location(api, cid, accuracy_m=None).status_code == 204
        assert put_location(api, cid, accuracy_m=0).status_code == 204

    def test_it_is_accepted_in_every_open_step(self) -> None:
        api, cid = _chat()
        for state in ("ordering", "ask_car", "ask_note", "review"):
            Conversation.objects.filter(pk=cid).update(state=state)
            assert put_location(api, cid).status_code == 204, state

    def test_the_position_is_never_in_what_the_api_sends_back(self) -> None:
        api, cid = _chat()
        put_location(api, cid, 25.20051, 55.27051)

        body = api.get(f"/api/v1/conversations/{cid}/messages").content.decode()

        assert "25.20051" not in body and "55.27051" not in body

    @pytest.mark.parametrize(
        ("lat", "lng", "accuracy"),
        [
            (90.1, 55.0, 5),
            (-90.1, 55.0, 5),
            (25.0, 180.1, 5),
            (25.0, -180.1, 5),
            (25.0, 55.0, -1),
        ],
    )
    def test_a_position_out_of_range_is_invalid_location(
        self, lat: float, lng: float, accuracy: float
    ) -> None:
        api, cid = _chat()

        response = put_location(api, cid, lat, lng, accuracy_m=accuracy)

        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "invalid_location"
        assert Conversation.objects.get(pk=cid).location_lat is None

    def test_the_edges_of_the_range_are_valid(self) -> None:
        api, cid = _chat()

        assert put_location(api, cid, 90, 180).status_code == 204
        assert put_location(api, cid, -90, -180).status_code == 204

    @pytest.mark.parametrize(
        "body",
        [
            {"lng": 55.0, "source": "gps"},
            {"lat": 25.0, "source": "gps"},
            {"lat": 25.0, "lng": 55.0},
            {"lat": 25.0, "lng": 55.0, "source": "none"},
            {"lat": "north", "lng": 55.0, "source": "gps"},
        ],
    )
    def test_an_incomplete_or_wrong_body_is_a_validation_error(
        self, body: dict[str, object]
    ) -> None:
        api, cid = _chat()

        response = api.put(f"/api/v1/conversations/{cid}/location", body, format="json")

        assert response.status_code == 400


class TestWhoMayUseIt:
    def test_a_customer_token_is_required(self) -> None:
        _, cid = _chat()

        response = APIClient().put(
            f"/api/v1/conversations/{cid}/location",
            {"lat": 25.0, "lng": 55.0, "source": "gps"},
            format="json",
        )

        assert response.status_code == 401

    def test_another_customers_conversation_is_a_404(self) -> None:
        _, cid = _chat()
        _, intruder = signed_in("intruder-location@example.com")

        response = put_location(intruder, cid)

        assert response.status_code == 404
        assert Conversation.objects.get(pk=cid).location_lat is None

    def test_an_unknown_conversation_is_a_404(self) -> None:
        _, api = signed_in()

        assert put_location(api, str(uuid.uuid4())).status_code == 404

    def test_a_placed_conversation_takes_no_more_positions(self) -> None:
        api, cid = _chat()
        Conversation.objects.filter(pk=cid).update(state=ConversationState.PLACED)

        response = put_location(api, cid)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_action_for_state"

    def test_an_expired_conversation_takes_no_position(self) -> None:
        api, cid = _chat()
        Conversation.objects.filter(pk=cid).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = put_location(api, cid)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "conversation_expired"
