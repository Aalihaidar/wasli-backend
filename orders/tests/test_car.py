import pytest

from orders.car import (
    CAR_FIELDS,
    CarDetails,
    clean_car_details,
    clean_car_field,
    missing_car_fields,
    normalise_plate,
)

GOOD = {
    "parking_note": "Parking B2 near the lift",
    "plate": "A 12345",
    "model": "Toyota Camry",
    "colour": "White",
}


def test_the_four_fields_in_the_order_the_bot_asks() -> None:
    assert CAR_FIELDS == ("parking_note", "plate", "model", "colour")


def test_a_plate_is_trimmed_upper_case_with_one_space() -> None:
    assert normalise_plate("  a   12345 ") == "A 12345"
    assert clean_car_field("plate", " dubai  k 123 ") == "DUBAI K 123"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("parking_note", "ab"),
        ("parking_note", "x" * 201),
        ("plate", "A"),
        ("plate", "A" * 13),
        ("model", "T"),
        ("model", "T" * 41),
        ("colour", "W"),
        ("colour", "W" * 31),
        ("colour", "   "),
        ("colour", ""),
        ("colour", None),
    ],
)
def test_a_value_the_field_does_not_allow_is_missing(
    field: str, value: str | None
) -> None:
    assert clean_car_field(field, value) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("parking_note", "abc"),
        ("parking_note", "x" * 200),
        ("plate", "A1"),
        ("plate", "A" * 12),
        ("model", "T" * 40),
        ("colour", "W" * 30),
    ],
)
def test_the_limits_are_inclusive(field: str, value: str) -> None:
    assert clean_car_field(field, value) is not None


def test_spaces_inside_a_value_are_collapsed() -> None:
    assert clean_car_field("model", "Toyota   Camry ") == "Toyota Camry"


def test_an_unknown_field_is_a_bug() -> None:
    with pytest.raises(ValueError, match="Unknown car field"):
        clean_car_field("owner", "x")


def test_all_four_valid_details_are_cleaned_together() -> None:
    assert clean_car_details({**GOOD, "plate": "a  12345"}) == CarDetails(
        parking_note="Parking B2 near the lift",
        plate="A 12345",
        model="Toyota Camry",
        colour="White",
    )


def test_one_bad_detail_means_no_details() -> None:
    assert clean_car_details({**GOOD, "colour": ""}) is None
    assert clean_car_details({}) is None


def test_the_missing_fields_are_listed_in_the_order_asked() -> None:
    assert missing_car_fields(GOOD) == ()
    assert missing_car_fields({**GOOD, "colour": "", "plate": "A"}) == (
        "plate",
        "colour",
    )
    assert missing_car_fields({}) == CAR_FIELDS
