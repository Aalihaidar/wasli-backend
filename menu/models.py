from typing import Any, ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction

from core.locales import ARABIC_OPTIONAL_HELP, ArabicFallbackMixin, arabic_or_english
from core.tenancy import RestaurantOwnedModel, align_with_parent

MAX_ALIASES = 20
MAX_ALIAS_LENGTH = 60
# A menu has up to three levels: a category, its subcategories and their subcategories.
MAX_CATEGORY_DEPTH = 3


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


class MenuCategory(ArabicFallbackMixin, RestaurantOwnedModel):
    """A heading of the menu. A category may sit inside another one (a subcategory), up to
    ``MAX_CATEGORY_DEPTH`` levels, and holds items at any level."""

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        help_text=(
            "Optional. Choose a category to make this one its subcategory. A menu has "
            "up to three levels: category, subcategory and sub-subcategory."
        ),
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(
        max_length=150, blank=True, help_text=ARABIC_OPTIONAL_HELP
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "name_en")
        verbose_name_plural = "menu categories"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("id")),
                name="menu_category_not_its_own_parent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.restaurant}: {self.path}"

    def _chain(self) -> list[MenuCategory]:
        """This category and its parents, from itself up to the top. It stops after
        ``MAX_CATEGORY_DEPTH + 1`` steps and at a repeat, so a bad loop can never run on."""
        chain: list[MenuCategory] = [self]
        node = self.parent
        while node is not None and len(chain) <= MAX_CATEGORY_DEPTH:
            if any(node.pk == seen.pk for seen in chain):
                break
            chain.append(node)
            node = node.parent
        return chain

    @property
    def depth(self) -> int:
        """1 for a top-level category, 2 for a subcategory, 3 for a sub-subcategory."""
        return len(self._chain())

    @property
    def path(self) -> str:
        """The names from the top category down to this one: ``Burgers > Grilled``."""
        return " > ".join(c.name_en for c in reversed(self._chain()))

    def _subtree_height(self) -> int:
        """1 for a category with no subcategory, 2 when it has subcategories, and so on."""
        if self._state.adding:
            return 1
        height, level = 1, [self.pk]
        while level and height <= MAX_CATEGORY_DEPTH:
            level = list(
                MenuCategory.objects.filter(parent_id__in=level).values_list(
                    "pk", flat=True
                )
            )
            if level:
                height += 1
        return height

    def clean(self) -> None:
        super().clean()
        self._normalise()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._normalise()
        super().save(*args, **kwargs)

    def _normalise(self) -> None:
        parent = self.parent
        if parent is None:
            return
        align_with_parent(self, parent, "parent")
        parents = parent._chain()
        if not self._state.adding and any(self.pk == c.pk for c in parents):
            raise ValidationError(
                {
                    "parent": "A category cannot be inside itself or inside one of its "
                    "own subcategories."
                }
            )
        if len(parents) + self._subtree_height() > MAX_CATEGORY_DEPTH:
            raise ValidationError(
                {
                    "parent": "A menu has at most three levels: category, subcategory "
                    "and sub-subcategory."
                }
            )


class MenuItem(ArabicFallbackMixin, RestaurantOwnedModel):
    """A dish or drink. The price is in minor units (fils); the client never sends one."""

    category = models.ForeignKey(
        MenuCategory, on_delete=models.PROTECT, related_name="items"
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(
        max_length=150, blank=True, help_text=ARABIC_OPTIONAL_HELP
    )
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True, help_text=ARABIC_OPTIONAL_HELP)
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

    @property
    def description_ar_display(self) -> str:
        return arabic_or_english(self.description_ar, self.description_en)

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


class OptionGroup(ArabicFallbackMixin, RestaurantOwnedModel):
    """A choice attached to an item (size, milk, extras). ``min_select`` 1 or more makes it
    required; ``max_select`` is how many options the customer may pick."""

    item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, related_name="option_groups"
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(
        max_length=150, blank=True, help_text=ARABIC_OPTIONAL_HELP
    )
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


class Option(ArabicFallbackMixin, RestaurantOwnedModel):
    """One choice inside an option group. The price change is added to the item's price and
    may be negative. Default options fill a required group the customer did not mention."""

    group = models.ForeignKey(
        OptionGroup, on_delete=models.CASCADE, related_name="options"
    )
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(
        max_length=150, blank=True, help_text=ARABIC_OPTIONAL_HELP
    )
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
