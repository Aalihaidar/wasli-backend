import pytest
from django.test import Client
from django.urls import reverse

from chat.models import Conversation, Message, Sender
from chat.services import add_message
from chat.tests.factories import make_conversation
from customers.tests.factories import PASSWORD
from restaurants.tests.factories import make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client() -> Client:
    User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
    client = Client()
    assert client.login(username="owner", password=PASSWORD)
    return client


def test_the_pages_load(admin_client: Client) -> None:
    conversation = make_conversation(
        location_lat=25.2001, location_lng=55.2701, location_source="gps"
    )
    add_message(conversation, Sender.BOT, text="Welcome to Cafe One")

    pages = [
        reverse("admin:chat_conversation_changelist"),
        reverse("admin:chat_conversation_change", args=[conversation.pk]),
    ]

    for page in pages:
        assert admin_client.get(page).status_code == 200, page


def test_the_messages_are_listed_in_order(admin_client: Client) -> None:
    conversation = make_conversation()
    add_message(conversation, Sender.BOT, text="First question")
    add_message(conversation, Sender.CUSTOMER, text="Two karak please")

    response = admin_client.get(
        reverse("admin:chat_conversation_change", args=[conversation.pk])
    )
    page = response.content.decode()

    assert page.index("First question") < page.index("Two karak please")


def test_a_conversation_cannot_be_added_or_edited_by_hand(admin_client: Client) -> None:
    conversation = make_conversation()

    assert admin_client.get(reverse("admin:chat_conversation_add")).status_code == 403
    change = reverse("admin:chat_conversation_change", args=[conversation.pk])
    # Read-only: the page may show the record but a POST changes nothing.
    admin_client.post(change, {"state": "placed", "locale": "ar"})
    conversation.refresh_from_db()
    assert conversation.state == "ordering"
    assert conversation.locale == "en"


def test_a_message_cannot_be_changed_from_its_conversation(
    admin_client: Client,
) -> None:
    conversation = make_conversation()
    message = add_message(conversation, Sender.BOT, text="Original")
    change = reverse("admin:chat_conversation_change", args=[conversation.pk])

    admin_client.post(
        change,
        {
            "messages-TOTAL_FORMS": "1",
            "messages-INITIAL_FORMS": "1",
            "messages-0-id": str(message.pk),
            "messages-0-text": "Changed",
            "messages-0-DELETE": "on",
        },
    )

    message.refresh_from_db()
    assert message.text == "Original"
    assert Message.objects.filter(pk=message.pk).exists()


def test_the_coordinates_are_not_shown(admin_client: Client) -> None:
    conversation = make_conversation(
        location_lat=25.2001,
        location_lng=55.2701,
        location_accuracy_m=12.5,
        location_source="gps",
    )

    page = admin_client.get(
        reverse("admin:chat_conversation_change", args=[conversation.pk])
    ).content.decode()

    assert "25.2001" not in page
    assert "55.2701" not in page
    assert "GPS" in page  # where the position came from is shown


def test_a_test_conversation_can_be_deleted_with_its_messages(
    admin_client: Client,
) -> None:
    conversation = make_conversation()
    add_message(conversation, Sender.BOT, text="Welcome")

    response = admin_client.post(
        reverse("admin:chat_conversation_delete", args=[conversation.pk]),
        {"post": "yes"},
    )

    assert response.status_code == 302
    assert not Conversation.objects.filter(pk=conversation.pk).exists()
    assert Message.objects.count() == 0


def test_the_list_can_be_searched_and_filtered(admin_client: Client) -> None:
    make_conversation(make_restaurant("cafe-a"))
    make_conversation(make_restaurant("cafe-b"), state="review")
    url = reverse("admin:chat_conversation_changelist")

    found = admin_client.get(url, {"q": "cafe-a"}).context["cl"].result_list
    assert [c.restaurant.slug for c in found] == ["cafe-a"]
    filtered = admin_client.get(url, {"state": "review"}).context["cl"].result_list
    assert [c.restaurant.slug for c in filtered] == ["cafe-b"]
