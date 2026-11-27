"""Error codes are an open set: their lists are ``x-extensible-enum`` so a new code is not a
breaking change (config/openapi_hooks.py)."""

import re
from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

from config.api_errors import ErrorCode403Enum, ErrorCode409Enum, ErrorCode429Enum
from config.openapi_hooks import (
    ERROR_CODE_LIST,
    EXTENSIBLE_LISTS,
    make_error_codes_extensible,
)


def document(**schemas: dict[str, Any]) -> dict[str, Any]:
    return {"components": {"schemas": schemas}}


class TestTheHook:
    def test_an_error_code_list_becomes_extensible(self) -> None:
        result = make_error_codes_extensible(
            document(
                ErrorCode409Enum={
                    "type": "string",
                    "enum": ["a", "b"],
                    "description": "d",
                }
            ),
            None,
            None,
            True,
        )

        schema = result["components"]["schemas"]["ErrorCode409Enum"]
        assert "enum" not in schema
        assert schema["x-extensible-enum"] == ["a", "b"]
        assert schema["type"] == "string" and schema["description"] == "d"

    def test_other_enums_stay_closed(self) -> None:
        result = make_error_codes_extensible(
            document(
                LocaleEnum={"type": "string", "enum": ["en", "ar"]},
                ErrorResponse409={"type": "object"},
                ClientErrorEnum={"type": "string", "enum": ["client_error"]},
            ),
            None,
            None,
            True,
        )

        schemas = result["components"]["schemas"]
        assert schemas["LocaleEnum"]["enum"] == ["en", "ar"]
        assert schemas["ClientErrorEnum"]["enum"] == ["client_error"]
        assert "x-extensible-enum" not in schemas["LocaleEnum"]

    def test_the_lists_that_grow_become_extensible_too(self) -> None:
        result = make_error_codes_extensible(
            document(
                **{
                    name: {"type": "string", "enum": ["a", "b"]}
                    for name in EXTENSIBLE_LISTS
                }
            ),
            None,
            None,
            True,
        )

        for name in EXTENSIBLE_LISTS:
            schema = result["components"]["schemas"][name]
            assert "enum" not in schema and schema["x-extensible-enum"] == ["a", "b"]

    def test_a_document_without_components_is_left_alone(self) -> None:
        assert make_error_codes_extensible({"paths": {}}, None, None, True) == {
            "paths": {}
        }

    @pytest.mark.parametrize(
        ("name", "matches"),
        [
            ("ErrorCode401Enum", True),
            ("ErrorCode429Enum", True),
            ("ErrorCode40Enum", False),
            ("ErrorCodeEnum", False),
            ("MyErrorCode409Enum", False),
        ],
    )
    def test_only_the_error_code_lists_are_matched(
        self, name: str, matches: bool
    ) -> None:
        assert bool(ERROR_CODE_LIST.fullmatch(name)) is matches


class TestTheGeneratedContract:
    @pytest.fixture(scope="class")
    def schemas(self) -> dict[str, Any]:
        # drf-spectacular is only partly typed
        generated = SchemaGenerator().get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
        return dict(generated["components"]["schemas"])

    def test_no_error_code_list_is_closed(self, schemas: dict[str, Any]) -> None:
        lists = {
            n: s for n, s in schemas.items() if re.fullmatch(r"ErrorCode\d{3}Enum", n)
        }

        assert {"ErrorCode401Enum", "ErrorCode409Enum", "ErrorCode429Enum"} <= set(
            lists
        )
        for name, schema in lists.items():
            assert "enum" not in schema, f"{name} is a closed enum"
            assert schema["x-extensible-enum"], f"{name} lists no code"

    def test_every_code_is_still_named_in_its_list(
        self, schemas: dict[str, Any]
    ) -> None:
        expected: dict[str, Any] = {
            "ErrorCode403Enum": ErrorCode403Enum,
            "ErrorCode409Enum": ErrorCode409Enum,
            "ErrorCode429Enum": ErrorCode429Enum,
        }

        for name, codes in expected.items():
            assert set(schemas[name]["x-extensible-enum"]) == {c.value for c in codes}
            for code in codes:
                assert f"`{code.value}`" in schemas[name]["description"]

    def test_real_enums_stay_closed(self, schemas: dict[str, Any]) -> None:
        assert schemas["LocaleEnum"]["enum"] == ["en", "ar"]

    def test_the_chat_lists_are_extensible(self, schemas: dict[str, Any]) -> None:
        assert set(schemas["MessageKindEnum"]["x-extensible-enum"]) >= {
            "text",
            "image",
            "order_summary",
        }
        assert "ask_car" in schemas["ConversationStateEnum"]["x-extensible-enum"]
        assert schemas["OrderTypeEnum"]["x-extensible-enum"][0] == "car"
        for name in ("MessageKindEnum", "ConversationStateEnum", "OrderTypeEnum"):
            assert "enum" not in schemas[name]

    def test_the_staff_lists_are_extensible(self, schemas: dict[str, Any]) -> None:
        assert set(schemas["StaffRoleEnum"]["x-extensible-enum"]) == {
            "admin",
            "cashier",
        }
        assert {"orders.view", "orders.decide"} <= set(
            schemas["StaffPermissionEnum"]["x-extensible-enum"]
        )
        for name in ("StaffRoleEnum", "StaffPermissionEnum"):
            assert "enum" not in schemas[name]

    def test_the_staff_me_reference_to_the_restaurant_is_a_bare_reference(
        self, schemas: dict[str, Any]
    ) -> None:
        """No `allOf` around a nested object (the generated clients read it badly), and the
        service distance is an optional property, never a nullable one."""
        me = schemas["StaffMe"]["properties"]
        restaurant = schemas["StaffRestaurant"]

        assert me["restaurant"] == {"$ref": "#/components/schemas/StaffRestaurant"}
        assert "service_radius_m" not in restaurant["required"]
        assert "nullable" not in restaurant["properties"]["service_radius_m"]

    def test_the_staff_order_declares_its_lists_and_optional_parts(
        self, schemas: dict[str, Any]
    ) -> None:
        order = schemas["StaffOrder"]
        properties = order["properties"]

        # Optional properties are absent, never null, and nested objects are bare references.
        for name in ("vehicle", "parking_note", "customer_location"):
            assert name not in order["required"]
        assert properties["vehicle"] == {"$ref": "#/components/schemas/StaffVehicle"}
        assert properties["customer_location"] == {
            "$ref": "#/components/schemas/StaffLocation"
        }
        # The reason is an inline nullable string with an extensible list: no $ref, no allOf.
        reason = properties["rejection_reason_code"]
        assert "$ref" not in reason and "allOf" not in reason
        assert reason["type"] == "string" and reason["nullable"] is True
        assert reason["x-extensible-enum"] == [
            "item_unavailable",
            "too_busy",
            "closing_soon",
            "too_far",
            "location_unclear",
            "other",
        ]
        # Fields that are empty until the restaurant answers are required and nullable.
        for name in ("eta_minutes", "decided_at", "rejection_note", "distance_m"):
            assert name in order["required"]
            assert properties[name]["nullable"] is True
        assert "x-extensible-enum" in schemas["DistanceBandEnum"]
        assert "enum" not in schemas["DistanceBandEnum"]
        location_source = schemas["StaffLocation"]["properties"]["source"]
        assert location_source["x-extensible-enum"] == ["gps", "simulated", "none"]
        assert "$ref" not in location_source

    def test_the_customer_position_request_keeps_its_own_closed_list(
        self, schemas: dict[str, Any]
    ) -> None:
        """The staff location source is declared in place so that it never merges with the
        customer's request, whose list is closed and has no ``none``."""
        source = schemas["LocationRequest"]["properties"]["source"]

        assert source["allOf"] == [{"$ref": "#/components/schemas/SourceEnum"}]
        assert schemas["SourceEnum"]["enum"] == ["gps", "simulated"]
