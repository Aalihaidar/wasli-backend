"""The storage system check and the ``check_media`` command."""

from io import StringIO
from typing import Any
from unittest import mock

import pytest
from django.core.files.storage import default_storage
from django.core.management import CommandError, call_command

from core.checks import check_media_storage_is_durable


class TestDurabilityCheck:
    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_the_disk_is_a_warning_outside_local_development(
        self, settings: Any, environment: str
    ) -> None:
        settings.ENVIRONMENT = environment
        settings.MEDIA_STORAGE = "filesystem"

        [warning] = check_media_storage_is_durable(None)

        assert warning.id == "core.W001"
        assert "MEDIA_STORAGE=r2" in (warning.hint or "")

    @pytest.mark.parametrize(
        ("environment", "storage"),
        [
            ("local", "filesystem"),
            ("local", "r2"),
            ("staging", "r2"),
            ("production", "r2"),
        ],
    )
    def test_everything_else_passes(
        self, settings: Any, environment: str, storage: str
    ) -> None:
        settings.ENVIRONMENT = environment
        settings.MEDIA_STORAGE = storage

        assert check_media_storage_is_durable(None) == []


class TestCheckMediaCommand:
    def test_it_writes_prints_the_url_and_cleans_up(self) -> None:
        out = StringIO()

        call_command("check_media", stdout=out)

        text = out.getvalue()
        assert "Public URL:" in text
        assert "The image storage works." in text
        _, files = default_storage.listdir("healthcheck")
        assert files == []

    def test_it_cleans_up_even_when_the_fetch_fails(self) -> None:
        with (
            mock.patch(
                "core.management.commands.check_media.urllib.request.urlopen"
            ) as get,
            mock.patch.object(
                default_storage.__class__,
                "url",
                return_value="https://pub-1.r2.dev/x.txt",
            ),
        ):
            get.side_effect = OSError("blocked")
            with pytest.raises(CommandError, match="public access"):
                call_command("check_media", "--fetch", stdout=StringIO())

        _, files = default_storage.listdir("healthcheck")
        assert files == []

    def test_fetch_reads_the_file_back(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"wasli storage check"
        out = StringIO()
        with (
            mock.patch(
                "core.management.commands.check_media.urllib.request.urlopen",
                return_value=response,
            ),
            mock.patch.object(
                default_storage.__class__,
                "url",
                return_value="https://pub-1.r2.dev/x.txt",
            ),
        ):
            call_command("check_media", "--fetch", stdout=out)

        assert "Read back over HTTP: ok" in out.getvalue()

    def test_fetch_names_itself_because_cloudflare_refuses_the_default_agent(
        self,
    ) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"wasli storage check"
        with (
            mock.patch(
                "core.management.commands.check_media.urllib.request.urlopen",
                return_value=response,
            ) as get,
            mock.patch.object(
                default_storage.__class__,
                "url",
                return_value="https://pub-1.r2.dev/x.txt",
            ),
        ):
            call_command("check_media", "--fetch", stdout=StringIO())

        sent = get.call_args.args[0]
        assert sent.get_header("User-agent") == "wasli-check-media/1.0"

    def test_fetch_refuses_a_non_https_address(self) -> None:
        with (
            mock.patch.object(
                default_storage.__class__,
                "url",
                return_value="/media/healthcheck/x.txt",
            ),
            pytest.raises(CommandError, match="not an https address"),
        ):
            call_command("check_media", "--fetch", stdout=StringIO())

    def test_fetch_refuses_different_content(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"something else"
        with (
            mock.patch(
                "core.management.commands.check_media.urllib.request.urlopen",
                return_value=response,
            ),
            mock.patch.object(
                default_storage.__class__,
                "url",
                return_value="https://pub-1.r2.dev/x.txt",
            ),
            pytest.raises(CommandError, match="not the one stored"),
        ):
            call_command("check_media", "--fetch", stdout=StringIO())
