import pytest
from django import forms

from core.forms import MinorUnitsField


class TestMinorUnitsField:
    @pytest.mark.parametrize(
        ("typed", "minor"),
        [
            ("12.50", 1250),
            ("12.5", 1250),
            ("12", 1200),
            ("0.05", 5),
            ("0", 0),
            ("0.00", 0),
            ("1234.56", 123456),
        ],
    )
    def test_aed_becomes_minor_units(self, typed: str, minor: int) -> None:
        assert MinorUnitsField().clean(typed) == minor

    @pytest.mark.parametrize("typed", ["12.555", "12.001", "abc", "1e3x", "-1"])
    def test_a_bad_amount_is_refused(self, typed: str) -> None:
        with pytest.raises(forms.ValidationError):
            MinorUnitsField().clean(typed)

    def test_a_negative_amount_needs_allow_negative(self) -> None:
        assert MinorUnitsField(allow_negative=True).clean("-1.50") == -150

    def test_an_empty_optional_amount_is_none(self) -> None:
        assert MinorUnitsField(required=False).clean("") is None

    def test_an_empty_required_amount_is_refused(self) -> None:
        with pytest.raises(forms.ValidationError):
            MinorUnitsField().clean("")

    @pytest.mark.parametrize(
        ("minor", "shown"), [(1250, "12.50"), (5, "0.05"), (-150, "-1.50"), (0, "0.00")]
    )
    def test_minor_units_are_shown_in_aed(self, minor: int, shown: str) -> None:
        assert MinorUnitsField(allow_negative=True).prepare_value(minor) == shown

    def test_an_unchanged_amount_is_not_a_change(self) -> None:
        field = MinorUnitsField()

        assert field.has_changed(1250, "12.50") is False
        assert field.has_changed(1250, "12.5") is False
        assert field.has_changed(1250, "13.00") is True
        assert field.has_changed(1250, "oops") is True
