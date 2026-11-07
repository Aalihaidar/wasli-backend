"""Money helpers. Amounts are integers in minor units (fils, 100 per AED), never floats."""

CURRENCY = "AED"
MINOR_UNITS_PER_AED = 100


def format_minor(amount_minor: int) -> str:
    """Return an amount in minor units as a decimal string with two digits: 1250 -> "12.50".

    The currency code is added by the caller (every bot text is written in the customer's
    language). Integer arithmetic only, so there is no rounding to get wrong.
    """
    sign = "-" if amount_minor < 0 else ""
    units, minor = divmod(abs(amount_minor), MINOR_UNITS_PER_AED)
    return f"{sign}{units}.{minor:02d}"
