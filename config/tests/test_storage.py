"""Where uploaded images are kept: the choice, the R2 options and the public URLs."""

from pathlib import Path
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import InMemoryStorage, default_storage
from storages.backends.s3 import S3Storage

from config.storage import media_storage, public_host, public_media_sources, r2_storage

R2_ENV = {
    "R2_ACCOUNT_ID": "0123456789abcdef",
    "R2_ACCESS_KEY_ID": "invented-access-key-id",
    "R2_SECRET_ACCESS_KEY": "invented-secret-access-key",
    "R2_BUCKET_NAME": "wasli-test-media",
    "R2_PUBLIC_BASE_URL": "https://pub-1234abcd.r2.dev",
}


def test_tests_keep_images_in_memory_whatever_the_environment_says() -> None:
    """A developer's .env may point at the staging bucket; a test must never reach it."""
    assert isinstance(default_storage._wrapped, InMemoryStorage)  # type: ignore[attr-defined]


def test_the_local_disk_is_the_default() -> None:
    assert media_storage("filesystem", {}) == {
        "BACKEND": "django.core.files.storage.FileSystemStorage"
    }


class TestR2Options:
    def test_the_bucket_comes_from_the_environment(self) -> None:
        storage = media_storage("r2", R2_ENV)

        assert storage["BACKEND"] == "storages.backends.s3.S3Storage"
        options = storage["OPTIONS"]
        assert options["bucket_name"] == "wasli-test-media"
        assert (
            options["endpoint_url"]
            == "https://0123456789abcdef.r2.cloudflarestorage.com"
        )
        assert options["access_key"] == "invented-access-key-id"
        assert options["secret_key"] == "invented-secret-access-key"
        assert options["region_name"] == "auto"

    def test_urls_are_plain_public_addresses(self) -> None:
        options = r2_storage(R2_ENV)["OPTIONS"]

        assert options["custom_domain"] == "pub-1234abcd.r2.dev"
        assert options["url_protocol"] == "https:"
        assert options["querystring_auth"] is False

    def test_a_new_upload_never_replaces_a_file(self) -> None:
        options = r2_storage(R2_ENV)["OPTIONS"]

        assert options["file_overwrite"] is False
        assert "immutable" in options["object_parameters"]["CacheControl"]

    def test_the_storage_builds_the_public_url_without_the_network(self) -> None:
        storage = S3Storage(**r2_storage(R2_ENV)["OPTIONS"])

        assert (
            storage.url("restaurants/logos/cafe.png")
            == "https://pub-1234abcd.r2.dev/restaurants/logos/cafe.png"
        )

    @pytest.mark.parametrize("missing", sorted(R2_ENV))
    def test_a_missing_setting_stops_start_up_and_names_it(self, missing: str) -> None:
        environ = {k: v for k, v in R2_ENV.items() if k != missing}

        with pytest.raises(ImproperlyConfigured, match=missing):
            r2_storage(environ)

    def test_an_empty_setting_counts_as_missing(self) -> None:
        with pytest.raises(ImproperlyConfigured, match="R2_BUCKET_NAME"):
            r2_storage({**R2_ENV, "R2_BUCKET_NAME": "  "})

    def test_the_error_never_contains_a_secret(self) -> None:
        environ = {k: v for k, v in R2_ENV.items() if k != "R2_BUCKET_NAME"}

        with pytest.raises(ImproperlyConfigured) as error:
            r2_storage(environ)

        assert "invented-secret-access-key" not in str(error.value)
        assert "invented-access-key-id" not in str(error.value)


class TestPublicHost:
    @pytest.mark.parametrize(
        ("url", "host"),
        [
            ("https://pub-1234abcd.r2.dev", "pub-1234abcd.r2.dev"),
            ("https://pub-1234abcd.r2.dev/", "pub-1234abcd.r2.dev"),
            (" https://media.example.com ", "media.example.com"),
        ],
    )
    def test_the_host_is_taken_from_an_https_address(self, url: str, host: str) -> None:
        assert public_host(url) == host

    @pytest.mark.parametrize(
        "url",
        [
            "http://pub-1234abcd.r2.dev",
            "pub-1234abcd.r2.dev",
            "https://pub-1234abcd.r2.dev/media",
            "https://pub-1234abcd.r2.dev/?x=1",
            "ftp://example.com",
            "",
        ],
    )
    def test_anything_else_is_refused(self, url: str) -> None:
        with pytest.raises(ImproperlyConfigured):
            public_host(url)


def test_an_unknown_media_storage_value_stops_start_up(monkeypatch: Any) -> None:
    from config.env import env_choice

    monkeypatch.setenv("MEDIA_STORAGE", "s3")

    with pytest.raises(ImproperlyConfigured, match="MEDIA_STORAGE"):
        env_choice("MEDIA_STORAGE", "filesystem", {"filesystem", "r2"})


class TestPublicMediaSources:
    def test_the_bucket_is_an_image_source_with_r2(self) -> None:
        assert public_media_sources(r2_storage(R2_ENV)) == [
            "https://pub-1234abcd.r2.dev"
        ]

    def test_the_local_disk_adds_nothing(self) -> None:
        assert public_media_sources(media_storage("filesystem", {})) == []

    def test_the_production_policy_allows_the_bucket_for_images(
        self, tmp_path: Path
    ) -> None:
        """The admin's thumbnails and the apps' pictures come from the bucket, so the policy
        (report-only now, enforced later) must name it. Run in a fresh interpreter: the settings
        are read once, when Django starts."""
        import os
        import subprocess
        import sys

        def img_src(mode: str) -> str:
            env = {
                "PATH": os.environ["PATH"],
                "HOME": str(tmp_path),
                "SECRET_KEY": "x-test-secret-key-for-this-check-only-0123456789",
                "DATABASE_URL": f"sqlite:///{tmp_path}/policy-check.db",
                "MEDIA_STORAGE": mode,
                **R2_ENV,
            }
            out = subprocess.run(
                [
                    sys.executable,
                    "-W",
                    "ignore",
                    "-c",
                    "import config.settings.production as p; print(p.SECURE_CSP_REPORT_ONLY['img-src'])",
                ],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            return out.stdout

        assert "https://pub-1234abcd.r2.dev" in img_src("r2")
        assert "r2.dev" not in img_src("filesystem")
