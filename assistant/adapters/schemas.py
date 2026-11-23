"""The JSON shapes the providers are asked to answer in.

Written by hand, with no defaults and no unions, in the small subset of JSON Schema that Gemini's
schema mode accepts. The Groq adapter puts the same shapes in its prompt. Whatever a provider
answers is validated again with the pydantic models of ``assistant.types``.
"""

from typing import Any

_STRING = {"type": "string"}
_NULLABLE_STRING = {"type": "string", "nullable": True}
_NULLABLE_INT = {"type": "integer", "nullable": True}
_LANGUAGE = {"type": "string", "enum": ["ar", "en"]}
_NULLABLE_LANGUAGE = {"type": "string", "enum": ["ar", "en"], "nullable": True}

# Gemini's schema mode takes a subset of OpenAPI. These are written by hand, with no defaults and
# no unions, because that subset rejects what pydantic would generate.
PARSE_ORDER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "transcript": _NULLABLE_STRING,
        "language": _LANGUAGE,
        "intent": {
            "type": "string",
            "enum": ["order_change", "confirm", "cancel", "unclear"],
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "add",
                            "remove",
                            "set_quantity",
                            "set_options",
                            "set_note",
                            "clear",
                        ],
                    },
                    "item_id": _NULLABLE_STRING,
                    "line": _NULLABLE_INT,
                    "quantity": _NULLABLE_INT,
                    "option_ids": {"type": "array", "items": _STRING},
                    "note": _NULLABLE_STRING,
                },
                "required": ["type"],
            },
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["choose_item", "choose_option"],
                    },
                    "mention": _NULLABLE_STRING,
                    "item_ids": {"type": "array", "items": _STRING},
                    "line": _NULLABLE_INT,
                    "group_id": _NULLABLE_STRING,
                },
                "required": ["kind"],
            },
        },
        "unmatched": {"type": "array", "items": _STRING},
    },
    "required": ["language", "intent", "actions", "questions", "unmatched"],
}
CLASSIFY_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "transcript": _NULLABLE_STRING,
        "language": _NULLABLE_LANGUAGE,
        "intent": {"type": "string", "enum": ["confirm", "edit", "cancel", "unclear"]},
        "field": {
            "type": "string",
            "enum": ["items", "car", "note"],
            "nullable": True,
        },
    },
    "required": ["intent"],
}
CAR_DETAILS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "transcript": _NULLABLE_STRING,
        "language": _NULLABLE_LANGUAGE,
        "parking_note": _NULLABLE_STRING,
        "plate": _NULLABLE_STRING,
        "model": _NULLABLE_STRING,
        "colour": _NULLABLE_STRING,
    },
    "required": ["parking_note", "plate", "model", "colour"],
}
TRANSCRIBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"transcript": _NULLABLE_STRING, "language": _NULLABLE_LANGUAGE},
    "required": ["transcript"],
}
