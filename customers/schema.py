"""Documents ``Authorization: Customer <token>`` in the OpenAPI contract."""

from typing import Any

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CustomerTokenScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "customers.authentication.CustomerTokenAuthentication"
    name = "customerAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": (
                "Customer token, sent as `Customer <token>`. It is returned once, "
                "when a sign-up is verified or a customer signs in."
            ),
        }
