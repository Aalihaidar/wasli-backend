"""Where uploaded images live: the local disk, or a Cloudflare R2 bucket.

Images are uploaded in the Django admin (logos, covers, menu images, item photos). The web
services have an ephemeral disk, so staging and production keep them in an R2 bucket (S3
compatible), one bucket and one key pair per environment. The API returns absolute URLs built
from the bucket's public address (``R2_PUBLIC_BASE_URL``), which is the ``r2.dev`` address on
staging until a domain exists and a custom domain on Cloudflare in production.

``MEDIA_STORAGE`` chooses: ``filesystem`` (the default, for local development) or ``r2``.
Choosing ``r2`` without all of its settings stops start-up, instead of failing at the first
upload.
"""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

R2_SETTINGS = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_BASE_URL",
)

FILESYSTEM_BACKEND = "django.core.files.storage.FileSystemStorage"
R2_BACKEND = "storages.backends.s3.S3Storage"


def public_host(base_url: str) -> str:
    """The host of the public base URL, which must be an ``https`` address with no path.

    ``https://pub-0123abcd.r2.dev`` gives ``pub-0123abcd.r2.dev``. Anything else would make
    the API return URLs that do not point at the bucket.
    """
    parts = urlsplit(base_url.strip())
    if parts.scheme != "https" or not parts.netloc:
        raise ImproperlyConfigured(
            "R2_PUBLIC_BASE_URL must be an https address such as https://pub-1234.r2.dev "
            f"(got {base_url!r})."
        )
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ImproperlyConfigured(
            "R2_PUBLIC_BASE_URL must be the bucket's address only, with no path."
        )
    return parts.netloc


def r2_storage(environ: Mapping[str, str]) -> dict[str, Any]:
    """The ``STORAGES["default"]`` entry for the R2 bucket named by the environment."""
    values = {name: environ.get(name, "").strip() for name in R2_SETTINGS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ImproperlyConfigured(
            "MEDIA_STORAGE=r2 needs these settings: " + ", ".join(missing) + "."
        )
    return {
        "BACKEND": R2_BACKEND,
        "OPTIONS": {
            "bucket_name": values["R2_BUCKET_NAME"],
            "endpoint_url": f"https://{values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            "access_key": values["R2_ACCESS_KEY_ID"],
            "secret_key": values["R2_SECRET_ACCESS_KEY"],
            "region_name": "auto",
            "signature_version": "s3v4",
            # The bucket is public: URLs are plain addresses, not signed links.
            "custom_domain": public_host(values["R2_PUBLIC_BASE_URL"]),
            "url_protocol": "https:",
            "querystring_auth": False,
            "default_acl": None,
            # A new upload never replaces a file, so a stored name never changes content and
            # may be cached for a long time.
            "file_overwrite": False,
            "object_parameters": {
                "CacheControl": "public, max-age=31536000, immutable"
            },
        },
    }


def media_storage(choice: str, environ: Mapping[str, str]) -> dict[str, Any]:
    """The default storage for ``MEDIA_STORAGE`` (``filesystem`` or ``r2``)."""
    if choice == "r2":
        return r2_storage(environ)
    return {"BACKEND": FILESYSTEM_BACKEND}


def public_media_sources(storage: Mapping[str, Any]) -> list[str]:
    """The origins uploaded images are loaded from, for the CSP ``img-src``: the bucket's public
    address with R2, nothing for the local disk (it is the site's own origin)."""
    host = storage.get("OPTIONS", {}).get("custom_domain")
    return [f"https://{host}"] if host else []
