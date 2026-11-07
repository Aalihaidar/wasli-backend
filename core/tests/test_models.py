import uuid

from django.db import models

from core.models import BaseModel


def test_base_model_is_abstract() -> None:
    assert BaseModel._meta.abstract is True


def test_base_model_has_a_uuid_primary_key() -> None:
    pk = BaseModel._meta.pk

    assert isinstance(pk, models.UUIDField)
    assert pk.name == "id"
    assert pk.default is uuid.uuid4
    assert pk.editable is False


def test_base_model_has_utc_timestamps() -> None:
    created = BaseModel._meta.get_field("created_at")
    updated = BaseModel._meta.get_field("updated_at")

    assert isinstance(created, models.DateTimeField)
    assert created.auto_now_add is True
    assert isinstance(updated, models.DateTimeField)
    assert updated.auto_now is True
