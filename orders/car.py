"""The four car details of an order and the rules every answer must meet.

The conversation engine merges what the customer says into these fields and the order service
checks them again before placing the order, so one set of rules serves both. Nothing here
invents a value: a field that is missing or does not fit is reported, and the bot asks again.
"""

from collections.abc import Mapping
from dataclasses import dataclass

# The fields of the car question, in the order the bot asks for what is missing.
CAR_FIELDS = ("parking_note", "plate", "model", "colour")

# Inclusive lengths, after trimming and collapsing spaces.
_LENGTHS: Mapping[str, tuple[int, int]] = {
    "parking_note": (3, 200),
    "plate": (2, 12),
    "model": (2, 40),
    "colour": (2, 30),
}


@dataclass(frozen=True)
class CarDetails:
    parking_note: str
    plate: str
    model: str
    colour: str


def normalise_plate(value: str) -> str:
    """Trimmed, upper case, with the spaces between its parts collapsed to one."""
    return " ".join(value.split()).upper()


def clean_car_field(field: str, value: str | None) -> str | None:
    """The cleaned value of one car field, or ``None`` when it is empty or has a length the
    field does not allow (so the bot asks for it again)."""
    if field not in _LENGTHS:
        raise ValueError(f"Unknown car field: {field}")
    if not value:
        return None
    cleaned = " ".join(value.split())
    if field == "plate":
        cleaned = normalise_plate(cleaned)
    low, high = _LENGTHS[field]
    return cleaned if low <= len(cleaned) <= high else None


def clean_car_details(values: Mapping[str, str | None]) -> CarDetails | None:
    """All four details cleaned, or ``None`` when any is missing or invalid."""
    cleaned = {field: clean_car_field(field, values.get(field)) for field in CAR_FIELDS}
    if any(value is None for value in cleaned.values()):
        return None
    return CarDetails(
        parking_note=cleaned["parking_note"] or "",
        plate=cleaned["plate"] or "",
        model=cleaned["model"] or "",
        colour=cleaned["colour"] or "",
    )


def missing_car_fields(values: Mapping[str, str | None]) -> tuple[str, ...]:
    """The car fields that are missing or invalid, in the order the bot asks for them."""
    return tuple(
        field
        for field in CAR_FIELDS
        if clean_car_field(field, values.get(field)) is None
    )
