"""Serializer building blocks shared by the apps."""

from rest_framework import serializers


class OmitWhenNone:
    """Leaves the property out of the response, never ``null``, when it has no value: the
    contract has no nullable references and a missing value is an optional property
    (docs/api-conventions.md). A missing related object counts as no value."""

    def get_attribute(self, instance: object) -> object:
        value = super().get_attribute(instance)  # type: ignore[misc]
        if value is None:
            raise serializers.SkipField()
        return value
