from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

from core.tenancy import RestaurantOwnedModel, align_with_parent

MAX_ALIASES = 20
MAX_ALIAS_LENGTH = 60


def clean_aliases(value: object) -> list[str]:
    """Normalise a list of alternative names ("karak" for "Karak tea"): trimmed, no empties,
    no duplicates ignoring case, at most ``MAX_ALIASES`` of at most ``MAX_ALIAS_LENGTH``."""
    if not isinstance(value, list):
        raise ValidationError("Aliases must be a list of names.")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            raise ValidationError("Every alias must be text.")
        alias = " ".join(raw.split())
        if not alias:
            continue
        if len(alias) > MAX_ALIAS_LENGTH:
            raise ValidationError(
                f"An alias can have at most {MAX_ALIAS_LENGTH} characters."
            )
        key = alias.casefold()
        if key not in seen:
            seen.add(key)
            cleaned.append(alias)
    if len(cleaned) > MAX_ALIASES:
        raise ValidationError(f"At most {MAX_ALIASES} aliases per item.")
    return cleaned


class MenuCategory(RestaurantOwnedModel):
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(max_length=150)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "name_en")
        verbose_name_plural = "menu categories"

    def __str__(self) -> str:
        return f"{self.restaurant}: {self.name_en}"


class MenuItem(RestaurantOwnedModel):
    """A dish or drink. The price is in minor units (fils); the client never sends one."""

    category = models.ForeignKey(
        MenuCategory, on_delete=models.PROTECT, related_name="items"
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(max_length=150)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    price_minor = models.PositiveIntegerField(help_text="In fils: 1250 is 12.50 AED.")
    image = models.ImageField(upload_to="menu/items/", blank=True)
    # Unavailable items stay on the menu but cannot be ordered.
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    # Other names customers use ("karak"); the assistant matches input against them.
    aliases = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("category__sort_order", "sort_order", "name_en")

    def __str__(self) -> str:
        return self.name_en

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        if self.category_id is not None:
            align_with_parent(self, self.category, "category")
        self.aliases = clean_aliases(self.aliases)


class OptionGroup(RestaurantOwnedModel):
    """A choice attached to an item (size, milk, extras). ``min_select`` 1 or more makes it
    required; ``max_select`` is how many options the customer may pick."""

    item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, related_name="option_groups"
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(max_length=150)
    min_select = models.PositiveSmallIntegerField(default=0)
    max_select = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name_en")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=models.Q(max_select__gte=models.F("min_select")),
                name="option_group_max_at_least_min",
            ),
            models.CheckConstraint(
                condition=models.Q(max_select__gte=1),
                name="option_group_max_at_least_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item}: {self.name_en}"

    def clean(self) -> None:
        super().clean()
        self._normalise()
        if self.max_select < self.min_select:
            raise ValidationError(
                {"max_select": "The maximum cannot be below the minimum."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        if self.item_id is not None:
            align_with_parent(self, self.item, "item")


class Option(RestaurantOwnedModel):
    """One choice inside an option group. The price change is added to the item's price and
    may be negative. Default options fill a required group the customer did not mention."""

    group = models.ForeignKey(
        OptionGroup, on_delete=models.CASCADE, related_name="options"
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(max_length=150)
    price_delta_minor = models.IntegerField(
        default=0, help_text="In fils, added to the item's price: 200 is +2.00 AED."
    )
    is_available = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name_en")

    def __str__(self) -> str:
        return f"{self.group}: {self.name_en}"

    def clean(self) -> None:
        super().clean()
        self._check_rules()

    def save(self, *args: Any, **kwargs: Any) -> None:
        with transaction.atomic():
            self._check_rules()
            super().save(*args, **kwargs)

    def _check_rules(self) -> None:
        if self.group_id is None:
            return
        align_with_parent(self, self.group, "group")
        if not self.is_default:
            return
        if not self.is_available:
            raise ValidationError(
                {"is_default": "An unavailable option cannot be the default."}
            )
        other_defaults = (
            Option.objects.filter(group_id=self.group_id, is_default=True)
            .exclude(pk=self.pk)
            .count()
        )
        if other_defaults + 1 > self.group.max_select:
            raise ValidationError(
                {
                    "is_default": (
                        f"This group allows {self.group.max_select} option(s), "
                        "so it cannot have more default options."
                    )
                }
            )
