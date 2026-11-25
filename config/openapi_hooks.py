"""Post-processing of the generated OpenAPI document (``SPECTACULAR_SETTINGS``).

The error ``code`` lists are an open set: every feature that can fail in a new way adds a code,
and all the error responses share the same lists. Declared as a closed ``enum``, each new code
would be a breaking change to every existing endpoint (a client's generated enum would refuse
it), and the API-contract CI check rightly fails. Declared as ``x-extensible-enum`` they may
grow: a client treats a code it does not know as a generic failure of the HTTP status. The
description of each list still names every code.
"""

import re
from typing import Any

# ErrorCode401Enum, ErrorCode409Enum, ... (config.api_errors and the package's own).
ERROR_CODE_LIST = re.compile(r"ErrorCode\d{3}Enum")
# Other lists the product will add values to (a new kind of message, a new step of the
# conversation, a new way to serve an order): the apps treat a value they do not know as unknown.
EXTENSIBLE_LISTS = frozenset(
    {
        "MessageKindEnum",
        "ConversationStateEnum",
        "OrderTypeEnum",
        "OrderStatusEnum",
        "StaffRoleEnum",
        "StaffPermissionEnum",
    }
)


def make_error_codes_extensible(
    result: dict[str, Any], generator: Any, request: Any, public: bool
) -> dict[str, Any]:
    """Turn every ``ErrorCode<status>Enum`` and the lists in ``EXTENSIBLE_LISTS`` into an
    ``x-extensible-enum``."""
    for name, schema in result.get("components", {}).get("schemas", {}).items():
        extensible = ERROR_CODE_LIST.fullmatch(name) or name in EXTENSIBLE_LISTS
        if extensible and "enum" in schema:
            schema["x-extensible-enum"] = schema.pop("enum")
    return result
