import pytest
from django.core.exceptions import ValidationError

from users.identifiers import (
    identify,
    normalize_email,
    normalize_phone,
    normalize_username,
    validate_username,
)


class TestNormalize:
    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_blank_becomes_none(self, value: str | None) -> None:
        assert normalize_username(value) is None
        assert normalize_email(value) is None
        assert normalize_phone(value) is None

    def test_username_and_email_are_trimmed_and_lowercased(self) -> None:
        assert normalize_username("  Sara.Ahmed ") == "sara.ahmed"
        assert normalize_email(" Sara@Example.COM ") == "sara@example.com"

    @pytest.mark.parametrize(
        "value",
        [
            "+971501234567",
            "00971501234567",
            "0501234567",
            "050 123 4567",
            "(050) 123-4567",
        ],
    )
    def test_phone_is_stored_in_international_form(self, value: str) -> None:
        assert normalize_phone(value) == "+971501234567"

    def test_phone_keeps_a_foreign_country_code(self) -> None:
        assert normalize_phone("+44 20 7946 0958") == "+442079460958"

    @pytest.mark.parametrize("value", ["12345", "abc", "+971", "0000000000"])
    def test_invalid_phone_is_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError):
            normalize_phone(value)


class TestValidateUsername:
    @pytest.mark.parametrize("value", ["sara", "Sara.Ahmed", "a_b-c", "abc", "a" * 30])
    def test_accepts(self, value: str) -> None:
        validate_username(value)

    @pytest.mark.parametrize(
        "value", ["ab", "a" * 31, "1sara", "_sara", "-sara", "sa ra", "sa@ra", ""]
    )
    def test_rejects(self, value: str) -> None:
        with pytest.raises(ValidationError):
            validate_username(value)


class TestIdentify:
    def test_at_sign_means_email(self) -> None:
        assert identify(" Sara@Example.com ") == ("email", "sara@example.com")

    @pytest.mark.parametrize("value", ["050 123 4567", "+971501234567", "0501234567"])
    def test_a_valid_number_means_phone(self, value: str) -> None:
        assert identify(value) == ("phone", "+971501234567")

    def test_anything_else_means_username(self) -> None:
        assert identify("Cashier.One") == ("username", "cashier.one")

    @pytest.mark.parametrize("value", ["", "   ", "12345", "+971"])
    def test_a_value_that_can_match_no_account_is_none(self, value: str) -> None:
        assert identify(value) is None
