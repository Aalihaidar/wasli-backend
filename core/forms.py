from typing import Any

from django import forms

from core.money import MINOR_UNITS_PER_AED, format_minor


class MinorUnitsField(forms.DecimalField):
    """Form field that shows an amount in AED ("12.50") and stores it in minor units (1250).

    The model keeps integers in fils (``*_minor``); people type AED. Up to two decimals are
    accepted and anything finer is refused, so nothing is rounded silently.
    """

    def __init__(self, *, allow_negative: bool = False, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 2)
        if not allow_negative:
            kwargs.setdefault("min_value", 0)
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool):
            return format_minor(value)
        return value

    def clean(self, value: Any) -> int | None:
        amount = super().clean(value)
        if amount is None:
            return None
        return int(amount * MINOR_UNITS_PER_AED)

    def has_changed(self, initial: Any, data: Any) -> bool:
        if self.disabled:
            return False
        try:
            new = self.clean(data)
        except forms.ValidationError:
            return True
        return bool(initial != new)
