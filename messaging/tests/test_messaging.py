from datetime import timedelta
from io import StringIO

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from customers.tests.factories import PASSWORD
from messaging.backends import (
    DisabledBackend,
    OutboxBackend,
    OutgoingMessage,
    get_backend,
    purge_old_messages,
)
from messaging.checks import check_outbox_not_in_production
from messaging.models import Channel, OutboxMessage, Purpose
from messaging.services import send_message
from users.models import User

pytestmark = pytest.mark.django_db


def make_message(**extra: str) -> OutboxMessage:
    values = {
        "channel": Channel.EMAIL,
        "recipient": "sara@example.com",
        "subject": "Your code",
        "body": "Your Wasli code is 123456.",
        "purpose": Purpose.VERIFICATION,
        **extra,
    }
    return OutboxMessage.objects.create(**values)


class TestModel:
    def test_an_email_address_is_stored_in_lower_case(self) -> None:
        assert (
            make_message(recipient=" Sara@Example.COM ").recipient == "sara@example.com"
        )

    def test_a_phone_number_is_stored_in_international_format(self) -> None:
        message = make_message(channel=Channel.SMS, recipient="050 123 4567")

        assert message.recipient == "+971501234567"

    @pytest.mark.parametrize(
        ("channel", "recipient"),
        [(Channel.EMAIL, "not-an-address"), (Channel.SMS, "12"), (Channel.SMS, "")],
    )
    def test_a_bad_recipient_is_refused(self, channel: Channel, recipient: str) -> None:
        with pytest.raises(ValidationError):
            make_message(channel=channel, recipient=recipient)

    def test_the_newest_message_comes_first(self) -> None:
        first = make_message(body="one")
        second = make_message(body="two")

        assert list(OutboxMessage.objects.all()) == [second, first]


class TestOutboxBackend:
    def test_it_stores_the_message(self, settings: object) -> None:
        OutboxBackend().send(
            OutgoingMessage(
                channel="sms",
                recipient="0501234567",
                body="Code 654321",
                purpose="verification",
            )
        )

        row = OutboxMessage.objects.get()
        assert (row.channel, row.recipient, row.body) == (
            "sms",
            "+971501234567",
            "Code 654321",
        )

    @pytest.mark.parametrize("environment", ["local", "staging"])
    def test_it_runs_on_local_and_staging(
        self, settings: object, environment: str
    ) -> None:
        settings.ENVIRONMENT = environment  # type: ignore[attr-defined]

        assert isinstance(OutboxBackend(), OutboxBackend)

    def test_it_refuses_to_run_in_production(self, settings: object) -> None:
        settings.ENVIRONMENT = "production"  # type: ignore[attr-defined]

        with pytest.raises(ImproperlyConfigured, match="production"):
            OutboxBackend()

    def test_nothing_is_stored_when_it_refuses(self, settings: object) -> None:
        settings.ENVIRONMENT = "production"  # type: ignore[attr-defined]

        with pytest.raises(ImproperlyConfigured):
            send_message(
                Channel.EMAIL, "sara@example.com", "Code 1", Purpose.VERIFICATION
            )

        assert not OutboxMessage.objects.exists()

    def test_an_invalid_recipient_stores_nothing(self) -> None:
        with pytest.raises(ValidationError):
            send_message(Channel.EMAIL, "nope", "Code 1", Purpose.VERIFICATION)

        assert not OutboxMessage.objects.exists()


class TestSelection:
    def test_the_setting_chooses_the_backend(self, settings: object) -> None:
        settings.MESSAGING_BACKEND = "outbox"  # type: ignore[attr-defined]

        assert isinstance(get_backend(), OutboxBackend)

    def test_an_unknown_backend_is_a_configuration_error(
        self, settings: object
    ) -> None:
        settings.MESSAGING_BACKEND = "carrier-pigeon"  # type: ignore[attr-defined]

        with pytest.raises(ImproperlyConfigured, match="carrier-pigeon"):
            get_backend()


class TestService:
    def test_send_message_goes_through_the_backend(self) -> None:
        send_message(
            Channel.EMAIL,
            "Sara@Example.com",
            "Your code is 111222.",
            Purpose.PASSWORD_RESET,
            subject="Reset",
        )

        row = OutboxMessage.objects.get()
        assert row.recipient == "sara@example.com"
        assert row.subject == "Reset"
        assert row.purpose == "password_reset"


class TestAdmin:
    @pytest.fixture
    def admin_client(self) -> Client:
        User.objects.create_superuser("owner", PASSWORD, email="owner@example.com")
        client = Client()
        assert client.login(username="owner", password=PASSWORD)
        return client

    def test_the_owner_can_read_the_code(self, admin_client: Client) -> None:
        message = make_message()

        listing = admin_client.get(reverse("admin:messaging_outboxmessage_changelist"))
        detail = admin_client.get(
            reverse("admin:messaging_outboxmessage_change", args=[message.pk])
        )

        assert listing.status_code == 200
        assert "sara@example.com" in listing.content.decode()
        assert "123456" in detail.content.decode()

    def test_a_message_cannot_be_added_or_changed(self, admin_client: Client) -> None:
        message = make_message()

        assert (
            admin_client.get(reverse("admin:messaging_outboxmessage_add")).status_code
            == 403
        )
        admin_client.post(
            reverse("admin:messaging_outboxmessage_change", args=[message.pk]),
            {"body": "changed"},
        )
        message.refresh_from_db()
        assert message.body == "Your Wasli code is 123456."

    def test_a_message_can_be_deleted_outside_production(
        self, admin_client: Client
    ) -> None:
        message = make_message()

        admin_client.post(
            reverse("admin:messaging_outboxmessage_delete", args=[message.pk]),
            {"post": "yes"},
        )

        assert not OutboxMessage.objects.filter(pk=message.pk).exists()

    def test_a_message_is_never_deleted_in_production(
        self, admin_client: Client, settings: object
    ) -> None:
        settings.ENVIRONMENT = "production"  # type: ignore[attr-defined]
        message = make_message()
        url = reverse("admin:messaging_outboxmessage_delete", args=[message.pk])

        assert admin_client.get(url).status_code == 403
        admin_client.post(url, {"post": "yes"})
        assert OutboxMessage.objects.filter(pk=message.pk).exists()


class TestDisabledBackend:
    def test_the_setting_can_choose_it(self, settings: object) -> None:
        settings.MESSAGING_BACKEND = "disabled"  # type: ignore[attr-defined]

        assert isinstance(get_backend(), DisabledBackend)

    @pytest.mark.parametrize("environment", ["local", "staging", "production"])
    def test_every_send_fails_loudly_and_stores_nothing(
        self, settings: object, environment: str
    ) -> None:
        settings.MESSAGING_BACKEND = "disabled"  # type: ignore[attr-defined]
        settings.ENVIRONMENT = environment  # type: ignore[attr-defined]

        with pytest.raises(ImproperlyConfigured, match="disabled"):
            send_message(
                Channel.EMAIL, "sara@example.com", "Code 1", Purpose.VERIFICATION
            )

        assert not OutboxMessage.objects.exists()


class TestProductionCheck:
    def test_the_outbox_in_production_is_a_system_error(self, settings: object) -> None:
        settings.ENVIRONMENT = "production"  # type: ignore[attr-defined]
        settings.MESSAGING_BACKEND = "outbox"  # type: ignore[attr-defined]

        [error] = check_outbox_not_in_production(None)

        assert error.id == "messaging.E001"
        assert "disabled" in (error.hint or "")

    @pytest.mark.parametrize(
        ("environment", "backend"),
        [
            ("production", "disabled"),
            ("staging", "outbox"),
            ("local", "outbox"),
            ("local", "disabled"),
        ],
    )
    def test_every_other_combination_passes(
        self, settings: object, environment: str, backend: str
    ) -> None:
        settings.ENVIRONMENT = environment  # type: ignore[attr-defined]
        settings.MESSAGING_BACKEND = backend  # type: ignore[attr-defined]

        assert check_outbox_not_in_production(None) == []

    def test_the_check_is_registered_with_django(self, settings: object) -> None:
        from django.core.management import CommandError

        settings.ENVIRONMENT = "production"  # type: ignore[attr-defined]
        settings.MESSAGING_BACKEND = "outbox"  # type: ignore[attr-defined]

        with pytest.raises(CommandError, match=r"messaging\.E001"):
            call_command("check", tags=["security"])


class TestRetention:
    def age(self, message: OutboxMessage, hours: int) -> None:
        OutboxMessage.objects.filter(pk=message.pk).update(
            created_at=timezone.now() - timedelta(hours=hours)
        )

    def test_old_messages_are_deleted_and_recent_ones_kept(
        self, settings: object
    ) -> None:
        settings.OUTBOX_RETENTION_HOURS = 24  # type: ignore[attr-defined]
        old, recent = make_message(body="old"), make_message(body="recent")
        self.age(old, 25)
        self.age(recent, 23)

        assert purge_old_messages() == 1

        assert list(OutboxMessage.objects.all()) == [recent]

    def test_the_retention_is_a_setting(self, settings: object) -> None:
        settings.OUTBOX_RETENTION_HOURS = 2  # type: ignore[attr-defined]
        message = make_message()
        self.age(message, 3)

        assert purge_old_messages() == 1

    def test_each_send_tidies_the_table(self, settings: object) -> None:
        settings.OUTBOX_RETENTION_HOURS = 24  # type: ignore[attr-defined]
        old = make_message(body="old code 111111")
        self.age(old, 48)

        send_message(
            Channel.EMAIL, "sara@example.com", "new code", Purpose.VERIFICATION
        )

        assert list(OutboxMessage.objects.values_list("body", flat=True)) == [
            "new code"
        ]

    def test_the_command_purges_on_demand(self, settings: object) -> None:
        settings.OUTBOX_RETENTION_HOURS = 24  # type: ignore[attr-defined]
        self.age(make_message(), 30)
        out = StringIO()

        call_command("purge_outbox", stdout=out)

        assert "Deleted 1 outbox message(s)." in out.getvalue()
        assert not OutboxMessage.objects.exists()
