from django.urls import path
from drf_spectacular.generators import SchemaGenerator

from customers.tests.test_authentication import CustomerView


def test_the_customer_token_is_documented_in_the_contract() -> None:
    generator = SchemaGenerator(patterns=[path("x/", CustomerView.as_view())])  # type: ignore[no-untyped-call]

    schema = generator.get_schema(request=None, public=True)  # type: ignore[no-untyped-call]

    scheme = schema["components"]["securitySchemes"]["customerAuth"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "header"
    assert scheme["name"] == "Authorization"
    assert "Customer <token>" in scheme["description"]
    operation = schema["paths"]["/x/"]["get"]
    assert {"customerAuth": []} in operation["security"]
