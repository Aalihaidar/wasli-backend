import pytest

from core.money import CURRENCY, format_minor


def test_currency_is_aed() -> None:
    assert CURRENCY == "AED"


@pytest.mark.parametrize(
    ("amount_minor", "expected"),
    [
        (0, "0.00"),
        (5, "0.05"),
        (100, "1.00"),
        (1250, "12.50"),
        (123456, "1234.56"),
        (-150, "-1.50"),
        (-5, "-0.05"),
    ],
)
def test_format_minor(amount_minor: int, expected: str) -> None:
    assert format_minor(amount_minor) == expected
