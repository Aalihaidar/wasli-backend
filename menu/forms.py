import re
from typing import Any

from django import forms

from core.forms import MinorUnitsField

from .models import MenuItem, Option, clean_aliases


class AliasesField(forms.CharField):
    """Aliases typed one per line (commas also separate them), stored as a list."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", forms.Textarea(attrs={"rows": 3}))
        kwargs.setdefault(
            "help_text", "Other names customers use, one per line (for example: karak)."
        )
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return "\n".join(str(alias) for alias in value)
        return value

    def to_python(self, value: Any) -> list[str]:  # type: ignore[override]
        text = super().to_python(value) or ""
        return clean_aliases(re.split(r"[\n,]", text))

    def has_changed(self, initial: Any, data: Any) -> bool:
        if self.disabled:
            return False
        try:
            return list(initial or []) != self.to_python(data)
        except forms.ValidationError:
            return True


class MenuItemAdminForm(forms.ModelForm):  # type: ignore[type-arg]
    price_minor = MinorUnitsField(label="Price (AED)", help_text="For example 12.50")
    aliases = AliasesField()

    class Meta:
        model = MenuItem
        fields = (
            "category",
            "name_en",
            "name_ar",
            "description_en",
            "description_ar",
            "price_minor",
            "image",
            "is_available",
            "sort_order",
            "aliases",
        )


class OptionAdminForm(forms.ModelForm):  # type: ignore[type-arg]
    price_delta_minor = MinorUnitsField(
        label="Price change (AED)",
        allow_negative=True,
        initial=0,
        help_text="Added to the item's price, for example 2.00 or -1.00",
    )

    class Meta:
        model = Option
        fields = (
            "group",
            "name_en",
            "name_ar",
            "price_delta_minor",
            "is_available",
            "is_default",
            "sort_order",
        )
