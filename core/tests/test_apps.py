import pytest
from django.apps import apps

WASLI_APPS = [
    "users",
    "core",
    "restaurants",
    "menu",
    "customers",
    "chat",
    "orders",
    "assistant",
]


@pytest.mark.parametrize("label", [*WASLI_APPS, "authtoken"])
def test_app_is_installed(label: str) -> None:
    # get_app_config raises LookupError for an app that is not installed.
    assert apps.get_app_config(label).label == label
