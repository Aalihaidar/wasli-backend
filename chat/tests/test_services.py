import uuid

import pytest

from chat.models import Conversation, Message, MessageKind, Sender
from chat.services import add_message
from chat.tests.factories import make_conversation

pytestmark = pytest.mark.django_db


class TestAddMessage:
    def test_the_first_message_is_number_one(self) -> None:
        conversation = make_conversation()

        message = add_message(conversation, Sender.BOT, text="Welcome")

        assert message.seq == 1
        assert message.text == "Welcome"
        assert message.conversation_id == conversation.pk
        assert message.restaurant_id == conversation.restaurant_id

    def test_numbers_follow_each_other_without_gaps(self) -> None:
        conversation = make_conversation()

        messages = [
            add_message(conversation, Sender.BOT, text=str(i)) for i in range(4)
        ]

        assert [m.seq for m in messages] == [1, 2, 3, 4]
        assert [m.seq for m in conversation.messages.all()] == [1, 2, 3, 4]

    def test_the_conversation_remembers_the_newest_number(self) -> None:
        conversation = make_conversation()

        add_message(conversation, Sender.BOT)
        add_message(conversation, Sender.CUSTOMER)

        assert conversation.last_seq == 2
        stored = Conversation.objects.get(pk=conversation.pk)
        assert stored.last_seq == 2

    def test_a_stale_copy_of_the_conversation_still_gets_the_next_number(self) -> None:
        conversation = make_conversation()
        stale = Conversation.objects.get(pk=conversation.pk)
        add_message(conversation, Sender.BOT)

        message = add_message(stale, Sender.BOT)

        assert message.seq == 2

    def test_each_conversation_counts_on_its_own(self) -> None:
        first, second = make_conversation(), make_conversation()

        add_message(first, Sender.BOT)
        add_message(first, Sender.BOT)
        message = add_message(second, Sender.BOT)

        assert message.seq == 1

    def test_it_stores_what_it_is_given(self) -> None:
        conversation = make_conversation()
        client_id = uuid.uuid4()

        message = add_message(
            conversation,
            Sender.CUSTOMER,
            MessageKind.TEXT,
            text="",
            transcript="two karak",
            used_voice=True,
            payload={"note": "x"},
            client_message_id=client_id,
        )
        message.refresh_from_db()

        assert message.sender == Sender.CUSTOMER
        assert message.used_voice is True
        assert message.transcript == "two karak"
        assert message.payload == {"note": "x"}
        assert message.client_message_id == client_id

    def test_a_menu_image_message_carries_the_stored_file_name(self) -> None:
        conversation = make_conversation()

        message = add_message(
            conversation,
            Sender.BOT,
            MessageKind.IMAGE,
            image="restaurants/menu/drinks.jpg",
            text="Drinks",
        )

        assert message.kind == MessageKind.IMAGE
        assert message.image.name == "restaurants/menu/drinks.jpg"

    def test_a_repeated_client_message_id_is_refused(self) -> None:
        conversation = make_conversation()
        client_id = uuid.uuid4()
        add_message(conversation, Sender.CUSTOMER, client_message_id=client_id)

        with pytest.raises(Exception, match="unique_client_message_id"):
            add_message(conversation, Sender.CUSTOMER, client_message_id=client_id)

        # The failed attempt took no number: the next message is still number two.
        assert Message.objects.filter(conversation=conversation).count() == 1
        assert Conversation.objects.get(pk=conversation.pk).last_seq == 1
