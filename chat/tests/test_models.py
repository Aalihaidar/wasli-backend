import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from chat.models import (
    IDLE_EXPIRY,
    Conversation,
    ConversationState,
    Message,
    MessageKind,
    Sender,
)
from chat.tests.factories import make_conversation
from customers.tests.factories import make_customer
from restaurants.tests.factories import make_restaurant

pytestmark = pytest.mark.django_db


class TestConversation:
    def test_defaults(self) -> None:
        before = timezone.now()
        conversation = make_conversation()

        assert conversation.pk.version == 4
        assert conversation.state == ConversationState.ORDERING
        assert conversation.locale == "en"
        assert conversation.lines == []
        assert conversation.pending_question is None
        assert conversation.pending_field == ""
        assert conversation.return_to_review is False
        assert conversation.location_lat is None
        assert conversation.location_source == "none"
        assert conversation.last_seq == 0
        assert conversation.closed_at is None
        assert before <= conversation.last_activity_at <= timezone.now()
        assert (
            before + IDLE_EXPIRY
            <= conversation.expires_at
            <= timezone.now() + IDLE_EXPIRY
        )

    def test_the_text_names_the_restaurant_customer_and_state(self) -> None:
        conversation = make_conversation(make_restaurant("cafe-a"))

        assert "Cafe A" in str(conversation)
        assert "Sara Example" in str(conversation)
        assert "ordering" in str(conversation)

    def test_it_expires_after_its_expiry_time(self) -> None:
        now = timezone.now()
        conversation = make_conversation(expires_at=now + timedelta(minutes=5))

        assert conversation.is_expired(now) is False
        assert conversation.is_expired(now + timedelta(minutes=5)) is True
        assert conversation.is_expired(now + timedelta(hours=1)) is True

    def test_the_state_and_locale_are_from_their_lists(self) -> None:
        conversation = make_conversation()
        conversation.state = "shipping"
        conversation.locale = "fr"

        with pytest.raises(ValidationError) as error:
            conversation.full_clean()
        assert {"state", "locale"} <= set(error.value.message_dict)

    def test_the_lines_are_a_list_of_objects(self) -> None:
        conversation = make_conversation()

        for bad in ({"line": 1}, ["karak"], "karak"):
            conversation.lines = bad
            with pytest.raises(ValidationError) as error:
                conversation.full_clean()
            assert "lines" in error.value.message_dict
            with pytest.raises(ValidationError):
                conversation.save()

    def test_the_lines_keep_what_the_engine_stores(self) -> None:
        lines = [
            {
                "line": 1,
                "item_id": str(uuid.uuid4()),
                "quantity": 2,
                "option_ids": [],
                "note": "less sugar",
            }
        ]
        conversation = make_conversation(lines=lines)
        conversation.refresh_from_db()

        assert conversation.lines == lines

    def test_a_pending_question_is_an_object_or_nothing(self) -> None:
        conversation = make_conversation(
            pending_question={"kind": "choose_item", "mention": "burger"}
        )
        conversation.refresh_from_db()
        assert conversation.pending_question == {
            "kind": "choose_item",
            "mention": "burger",
        }

        conversation.pending_question = ["burger"]
        with pytest.raises(ValidationError) as error:
            conversation.full_clean()
        assert "pending_question" in error.value.message_dict

    def test_the_car_field_asked_alone_is_one_of_the_four(self) -> None:
        conversation = make_conversation(pending_field="plate")
        conversation.pending_field = "wheel"

        with pytest.raises(ValidationError) as error:
            conversation.full_clean()
        assert "pending_field" in error.value.message_dict

    def test_a_position_needs_both_coordinates(self) -> None:
        with pytest.raises(ValidationError):
            make_conversation(location_lat=25.2)
        with pytest.raises(IntegrityError), transaction.atomic():
            Conversation.objects.bulk_create(
                [
                    Conversation(
                        restaurant=make_restaurant("cafe-b"),
                        customer=make_customer("omar@example.com", "Omar"),
                        location_lng=55.2,
                    )
                ]
            )

    def test_a_position_is_kept_with_its_accuracy_and_source(self) -> None:
        now = timezone.now()
        conversation = make_conversation(
            location_lat=25.2001,
            location_lng=55.2701,
            location_accuracy_m=12.5,
            location_source="gps",
            location_captured_at=now,
        )
        conversation.refresh_from_db()

        assert (conversation.location_lat, conversation.location_lng) == (
            25.2001,
            55.2701,
        )
        assert conversation.location_accuracy_m == 12.5
        assert conversation.location_source == "gps"

    def test_a_position_stays_on_earth(self) -> None:
        conversation = make_conversation()

        for field, value in (
            ("location_lat", 90.5),
            ("location_lat", -91),
            ("location_lng", 180.5),
            ("location_accuracy_m", -1),
        ):
            fresh = make_conversation(restaurant=conversation.restaurant)
            fresh.location_lat = fresh.location_lng = 0
            setattr(fresh, field, value)
            with pytest.raises(ValidationError) as error:
                fresh.full_clean()
            assert field in error.value.message_dict

    def test_the_position_source_is_one_of_three(self) -> None:
        conversation = make_conversation()
        conversation.location_source = "wifi"

        with pytest.raises(ValidationError) as error:
            conversation.full_clean()
        assert "location_source" in error.value.message_dict

    def test_a_restaurant_with_conversations_cannot_be_deleted(self) -> None:
        conversation = make_conversation()

        with pytest.raises(ProtectedError):
            conversation.restaurant.delete()

    def test_a_customer_with_conversations_cannot_be_deleted(self) -> None:
        conversation = make_conversation()

        with pytest.raises(ProtectedError):
            conversation.customer.delete()

    def test_a_restaurant_only_sees_its_own_conversations(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        in_a = make_conversation(a)
        make_conversation(b)

        assert list(Conversation.objects.for_restaurant(a)) == [in_a]

    def test_the_customer_reaches_their_conversations(self) -> None:
        conversation = make_conversation()

        assert list(conversation.customer.conversations.all()) == [conversation]


class TestMessage:
    def test_defaults(self) -> None:
        conversation = make_conversation()
        message = Message.objects.create(
            conversation=conversation, seq=1, sender=Sender.BOT
        )

        assert message.pk.version == 4
        assert message.kind == MessageKind.TEXT
        assert message.text == ""
        assert message.transcript == ""
        assert message.used_voice is False
        assert not message.image
        assert message.payload == {}
        assert message.client_message_id is None
        assert str(message) == "#1 bot text"

    def test_it_belongs_to_its_conversations_restaurant(self) -> None:
        conversation = make_conversation()
        message = Message.objects.create(
            conversation=conversation, seq=1, sender=Sender.CUSTOMER
        )

        assert message.restaurant_id == conversation.restaurant_id

    def test_it_cannot_name_another_restaurant(self) -> None:
        conversation = make_conversation(make_restaurant("cafe-a"))
        other = make_restaurant("cafe-b")

        with pytest.raises(ValidationError) as error:
            Message.objects.create(
                conversation=conversation,
                restaurant=other,
                seq=1,
                sender=Sender.BOT,
            )
        assert "conversation" in error.value.message_dict

    def test_messages_come_in_seq_order(self) -> None:
        conversation = make_conversation()
        for seq in (3, 1, 2):
            Message.objects.create(
                conversation=conversation, seq=seq, sender=Sender.BOT
            )

        assert [m.seq for m in conversation.messages.all()] == [1, 2, 3]

    def test_a_seq_is_used_once_per_conversation(self) -> None:
        conversation = make_conversation()
        Message.objects.create(conversation=conversation, seq=1, sender=Sender.BOT)

        with pytest.raises(IntegrityError), transaction.atomic():
            Message.objects.create(
                conversation=conversation, seq=1, sender=Sender.CUSTOMER
            )

    def test_two_conversations_each_start_at_one(self) -> None:
        for _ in range(2):
            Message.objects.create(
                conversation=make_conversation(), seq=1, sender=Sender.BOT
            )

        assert Message.objects.filter(seq=1).count() == 2

    def test_a_client_message_id_is_used_once_per_conversation(self) -> None:
        conversation = make_conversation()
        client_id = uuid.uuid4()
        Message.objects.create(
            conversation=conversation,
            seq=1,
            sender=Sender.CUSTOMER,
            client_message_id=client_id,
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                seq=2,
                sender=Sender.CUSTOMER,
                client_message_id=client_id,
            )

    def test_the_same_client_message_id_can_appear_in_another_conversation(
        self,
    ) -> None:
        client_id = uuid.uuid4()
        for _ in range(2):
            Message.objects.create(
                conversation=make_conversation(),
                seq=1,
                sender=Sender.CUSTOMER,
                client_message_id=client_id,
            )

        assert Message.objects.filter(client_message_id=client_id).count() == 2

    def test_bot_messages_need_no_client_message_id(self) -> None:
        conversation = make_conversation()
        for seq in (1, 2, 3):
            Message.objects.create(
                conversation=conversation, seq=seq, sender=Sender.BOT
            )

        assert conversation.messages.filter(client_message_id__isnull=True).count() == 3

    def test_sender_and_kind_are_from_their_lists(self) -> None:
        message = Message(
            conversation=make_conversation(), seq=1, sender="robot", kind="video"
        )

        with pytest.raises(ValidationError) as error:
            message.full_clean()
        assert {"sender", "kind"} <= set(error.value.message_dict)

    def test_every_kind_the_contract_names_exists(self) -> None:
        assert {kind.value for kind in MessageKind} == {
            "text",
            "image",
            "order_summary",
            "review",
            "result",
        }

    def test_the_payload_is_an_object(self) -> None:
        conversation = make_conversation()
        message = Message.objects.create(
            conversation=conversation,
            seq=1,
            sender=Sender.BOT,
            kind=MessageKind.ORDER_SUMMARY,
            payload={"quick_replies": [{"label": "Confirm", "action": "confirm"}]},
        )
        message.refresh_from_db()
        assert message.payload["quick_replies"][0]["action"] == "confirm"

        with pytest.raises(ValidationError):
            Message.objects.create(
                conversation=conversation, seq=2, sender=Sender.BOT, payload=["x"]
            )

    def test_a_voice_message_keeps_its_transcript_not_the_audio(self) -> None:
        message = Message.objects.create(
            conversation=make_conversation(),
            seq=1,
            sender=Sender.CUSTOMER,
            used_voice=True,
            transcript="two karak, one large",
        )
        message.refresh_from_db()

        assert message.used_voice is True
        assert message.transcript == "two karak, one large"

    def test_an_image_message_names_a_stored_menu_image(self) -> None:
        message = Message.objects.create(
            conversation=make_conversation(),
            seq=1,
            sender=Sender.BOT,
            kind=MessageKind.IMAGE,
            image="restaurants/menu/drinks.jpg",
            text="Drinks",
        )
        message.refresh_from_db()

        assert message.image.name == "restaurants/menu/drinks.jpg"

    def test_deleting_a_conversation_removes_its_messages(self) -> None:
        conversation = make_conversation()
        Message.objects.create(conversation=conversation, seq=1, sender=Sender.BOT)

        conversation.delete()

        assert Message.objects.count() == 0

    def test_a_restaurant_only_sees_its_own_messages(self) -> None:
        a, b = make_restaurant("cafe-a"), make_restaurant("cafe-b")
        in_a = Message.objects.create(
            conversation=make_conversation(a), seq=1, sender=Sender.BOT
        )
        Message.objects.create(
            conversation=make_conversation(b), seq=1, sender=Sender.BOT
        )

        assert list(Message.objects.for_restaurant(a)) == [in_a]
