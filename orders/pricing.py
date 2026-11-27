"""Validation and pricing of an order's lines, from the database only.

The server is the authority on what can be ordered and what it costs: a line names a menu item
and the options chosen, never a price. Whatever the assistant or the app proposed, an item that
is not this restaurant's, that is finished, or whose option rules are not met is reported as a
problem and nothing is priced.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db.models import Prefetch

from core.money import CURRENCY
from menu.models import MenuItem, Option, OptionGroup
from menu.services import visible_categories
from restaurants.models import Restaurant
from restaurants.services import public_restaurants

from .errors import OrderError, OrderProblem, ProblemCode
from .models import MAX_LINES, MAX_QUANTITY

MAX_LINE_NOTE_CHARS = 200


@dataclass(frozen=True)
class PricedOption:
    id: UUID
    name_en: str
    name_ar: str
    price_delta_minor: int


@dataclass(frozen=True)
class PricedLine:
    line: int
    item_id: UUID
    name_en: str
    name_ar: str
    options: tuple[PricedOption, ...]
    quantity: int
    note: str
    unit_price_minor: int
    line_total_minor: int

    @property
    def option_ids(self) -> list[UUID]:
        return [option.id for option in self.options]


@dataclass(frozen=True)
class PricedOrder:
    lines: tuple[PricedLine, ...]
    subtotal_minor: int
    total_minor: int
    currency: str = CURRENCY


def _as_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _quantity(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= MAX_QUANTITY else None


def _dedupe(values: Sequence[object]) -> list[UUID | None]:
    """The option ids in the order given, each once; an id that is not a UUID stays as
    ``None`` so it is reported as an unknown option."""
    seen: set[UUID | None] = set()
    unique: list[UUID | None] = []
    for value in values:
        option_id = _as_uuid(value)
        if option_id is not None and option_id in seen:
            continue
        seen.add(option_id)
        unique.append(option_id)
    return unique


def price_lines(
    restaurant: Restaurant, lines: Sequence[Mapping[str, Any]]
) -> PricedOrder:
    """Check every line against this restaurant's menu and price the order.

    A line is ``{item_id, quantity, option_ids, note}``. A required option group the customer
    did not mention is filled with its default options; a group that still has too few or too
    many choices is a problem (the bot asks). Raises ``OrderError`` listing every problem found,
    so the bot can ask about all of them at once; returns the priced order otherwise. Reads
    only: nothing is written.
    """
    if not public_restaurants().filter(pk=restaurant.pk).exists():
        raise OrderError([OrderProblem(ProblemCode.RESTAURANT_UNAVAILABLE)])
    if not lines:
        raise OrderError([OrderProblem(ProblemCode.EMPTY_ORDER)])
    if len(lines) > MAX_LINES:
        raise OrderError([OrderProblem(ProblemCode.TOO_MANY_LINES)])

    item_ids = {
        item_id
        for line in lines
        if (item_id := _as_uuid(line.get("item_id"))) is not None
    }
    items = {
        item.pk: item
        for item in MenuItem.objects.for_restaurant(restaurant)
        .filter(pk__in=item_ids)
        .prefetch_related(
            Prefetch(
                "option_groups",
                queryset=OptionGroup.objects.prefetch_related(
                    Prefetch("options", queryset=Option.objects.all())
                ),
            )
        )
    }
    visible = {category.pk for category in visible_categories(restaurant)}

    problems: list[OrderProblem] = []
    priced: list[PricedLine] = []
    for number, raw in enumerate(lines, start=1):
        line = _price_line(number, raw, items, visible, problems)
        if line is not None:
            priced.append(line)
    if problems:
        raise OrderError(problems)

    subtotal = sum(line.line_total_minor for line in priced)
    return PricedOrder(
        lines=tuple(priced), subtotal_minor=subtotal, total_minor=subtotal
    )


def _price_line(
    number: int,
    raw: Mapping[str, Any],
    items: Mapping[UUID, MenuItem],
    visible: set[UUID],
    problems: list[OrderProblem],
) -> PricedLine | None:
    before = len(problems)
    item_id = _as_uuid(raw.get("item_id"))
    item = items.get(item_id) if item_id is not None else None
    if item is None:
        problems.append(
            OrderProblem(ProblemCode.UNKNOWN_ITEM, line=number, item_id=item_id)
        )
        return None

    quantity = _quantity(raw.get("quantity"))
    if quantity is None:
        problems.append(
            OrderProblem(ProblemCode.INVALID_QUANTITY, line=number, item_id=item.pk)
        )
    note = raw.get("note")
    note = note.strip() if isinstance(note, str) else ""
    if len(note) > MAX_LINE_NOTE_CHARS:
        problems.append(
            OrderProblem(ProblemCode.NOTE_TOO_LONG, line=number, item_id=item.pk)
        )
    if not item.is_available or item.category_id not in visible:
        problems.append(
            OrderProblem(ProblemCode.ITEM_UNAVAILABLE, line=number, item_id=item.pk)
        )
        return None

    options = _choose_options(number, item, raw.get("option_ids"), problems)
    unit_price = item.price_minor + sum(o.price_delta_minor for o in options)
    if unit_price < 0:
        problems.append(
            OrderProblem(ProblemCode.INVALID_PRICE, line=number, item_id=item.pk)
        )
    if len(problems) > before or quantity is None:
        return None
    return PricedLine(
        line=number,
        item_id=item.pk,
        name_en=item.name_en,
        name_ar=item.name_ar_display,
        options=tuple(options),
        quantity=quantity,
        note=note,
        unit_price_minor=unit_price,
        line_total_minor=unit_price * quantity,
    )


def _choose_options(
    number: int, item: MenuItem, raw_ids: object, problems: list[OrderProblem]
) -> list[PricedOption]:
    """The options of one line, with each group's rules applied."""
    groups = list(item.option_groups.all())
    by_id = {
        option.pk: (group, option) for group in groups for option in group.options.all()
    }
    given = _dedupe(raw_ids) if isinstance(raw_ids, list | tuple) else []

    chosen: dict[UUID, list[Option]] = {group.pk: [] for group in groups}
    mentioned: set[UUID] = set()
    for option_id in given:
        found = by_id.get(option_id) if option_id is not None else None
        if found is None:
            problems.append(
                OrderProblem(
                    ProblemCode.UNKNOWN_OPTION,
                    line=number,
                    item_id=item.pk,
                    option_id=option_id,
                )
            )
            continue
        group, option = found
        mentioned.add(group.pk)
        if not option.is_available:
            problems.append(
                OrderProblem(
                    ProblemCode.OPTION_UNAVAILABLE,
                    line=number,
                    item_id=item.pk,
                    option_id=option.pk,
                    group_id=group.pk,
                )
            )
            continue
        chosen[group.pk].append(option)

    result: list[PricedOption] = []
    for group in groups:
        picks = chosen[group.pk]
        if not picks and group.pk not in mentioned and group.min_select >= 1:
            defaults = [
                o for o in group.options.all() if o.is_default and o.is_available
            ]
            picks = defaults[: group.max_select]
        if group.pk in mentioned and not picks:
            # The customer named only options that cannot be had: already reported.
            continue
        if not group.min_select <= len(picks) <= group.max_select:
            problems.append(
                OrderProblem(
                    ProblemCode.OPTION_RULE,
                    line=number,
                    item_id=item.pk,
                    group_id=group.pk,
                )
            )
            continue
        result.extend(
            PricedOption(
                id=option.pk,
                name_en=option.name_en,
                name_ar=option.name_ar_display,
                price_delta_minor=option.price_delta_minor,
            )
            for option in picks
        )
    return result
