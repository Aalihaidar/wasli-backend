"""Reading the order: every line of a conversation checked against this restaurant's menu.

``reconcile`` repairs what can be repaired without asking (a finished item or option is dropped
and reported, a note that is too long is cut) and keeps a line that still needs a required option
as *incomplete*, so the bot can ask. Prices come from the order service, never from here.
"""

import uuid
from dataclasses import dataclass, field

from assistant.menu import build_prompt_menu
from assistant.types import PromptMenu
from menu.models import Option, OptionGroup
from orders.errors import OrderError, OrderProblem, ProblemCode
from orders.pricing import PricedOrder, price_lines
from restaurants.models import Restaurant

from .lines import Line, renumber
from .texts import pick

_MAX_NOTE_CHARS = 200


@dataclass
class Reconciled:
    """The stored lines after every line was checked against the menu."""

    lines: list[Line]
    # Priced lines (those that are complete) and the numbers they carry in ``lines``.
    priced: PricedOrder | None = None
    priced_numbers: list[int] = field(default_factory=list)
    # Names of items or options dropped because they are finished or unavailable.
    unavailable: list[str] = field(default_factory=list)
    # Lines kept but waiting for an option the customer has to choose.
    incomplete: list[tuple[Line, OrderProblem]] = field(default_factory=list)


def is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


class Menu:
    """The restaurant's visible items, for names and for the ids the assistant may use."""

    def __init__(self, restaurant: Restaurant) -> None:
        self.prompt: PromptMenu = build_prompt_menu(restaurant)
        self.names = {
            item.id: (item.name_en, item.name_ar or item.name_en)
            for item in self.prompt.items
        }
        self.item_ids: set[str] = set(self.names)

    def item_name(self, item_id: str, locale: str) -> str:
        english, arabic = self.names.get(str(item_id), ("", ""))
        return pick(english, arabic, locale)


def reconcile(
    restaurant: Restaurant, stored: list[Line], menu: Menu, locale: str
) -> Reconciled:
    """Check every line, repairing what can be repaired without asking.

    An item or option that is finished, an id that is not on this menu or a bad quantity is
    dropped (and an unavailable one is reported); a note that is too long is cut; too many
    options of a group are trimmed. A line that needs a required option the customer has not
    chosen is kept as *incomplete* so the bot can ask. Raises ``OrderError`` only when the whole
    restaurant cannot take orders.
    """
    work = [{**line, "option_ids": list(line["option_ids"])} for line in stored]
    unavailable: list[str] = []
    incomplete: list[tuple[Line, OrderProblem]] = []
    priced: PricedOrder | None = None
    active: list[Line] = []

    for _attempt in range(len(work) * 3 + 3):
        waiting = [entry for entry, _ in incomplete]
        active = [e for e in work if not any(e is w for w in waiting)]
        if not active:
            priced = None
            break
        try:
            priced = price_lines(restaurant, active)
            break
        except OrderError as error:
            if error.codes & {
                ProblemCode.RESTAURANT_UNAVAILABLE,
                ProblemCode.TOO_MANY_LINES,
                ProblemCode.EMPTY_ORDER,
            }:
                raise
            by_position = dict(enumerate(active, start=1))
            repaired = False
            for problem in error.problems:
                entry = by_position.get(problem.line or 0)
                if entry is not None and _repair(
                    entry, problem, work, incomplete, unavailable, menu, locale
                ):
                    repaired = True
            if not repaired:
                raise
    else:  # pragma: no cover - every pass repairs at least one problem or raises
        raise OrderError([])

    renumber(work)
    numbers = [entry["line"] for entry in active] if priced is not None else []
    return Reconciled(
        lines=work,
        priced=priced,
        priced_numbers=numbers,
        unavailable=unavailable,
        incomplete=incomplete,
    )


def _drop(work: list[Line], entry: Line) -> None:
    work[:] = [other for other in work if other is not entry]


def _repair(
    entry: Line,
    problem: OrderProblem,
    work: list[Line],
    incomplete: list[tuple[Line, OrderProblem]],
    unavailable: list[str],
    menu: Menu,
    locale: str,
) -> bool:
    """Fix or drop one problem line. Returns whether anything changed."""
    code = problem.code
    if code in {
        ProblemCode.UNKNOWN_ITEM,
        ProblemCode.INVALID_QUANTITY,
        ProblemCode.INVALID_PRICE,
    }:
        _drop(work, entry)
        return True
    if code is ProblemCode.ITEM_UNAVAILABLE:
        unavailable.append(menu.item_name(entry["item_id"], locale))
        _drop(work, entry)
        return True
    if code is ProblemCode.NOTE_TOO_LONG:
        entry["note"] = str(entry.get("note") or "").strip()[:_MAX_NOTE_CHARS]
        return True
    if code is ProblemCode.UNKNOWN_OPTION:
        before = len(entry["option_ids"])
        if problem.option_id is not None:
            entry["option_ids"] = [
                o for o in entry["option_ids"] if o != str(problem.option_id)
            ]
        else:
            entry["option_ids"] = [o for o in entry["option_ids"] if is_uuid(o)]
        return len(entry["option_ids"]) != before
    if code is ProblemCode.OPTION_UNAVAILABLE:
        option = (
            Option.objects.filter(pk=problem.option_id).first()
            if problem.option_id is not None
            else None
        )
        if option is not None:
            unavailable.append(pick(option.name_en, option.name_ar_display, locale))
        entry["option_ids"] = [
            o for o in entry["option_ids"] if o != str(problem.option_id)
        ]
        return True
    if code is ProblemCode.OPTION_RULE:
        return _repair_option_rule(
            entry, problem, work, incomplete, unavailable, menu, locale
        )
    return False


def _repair_option_rule(
    entry: Line,
    problem: OrderProblem,
    work: list[Line],
    incomplete: list[tuple[Line, OrderProblem]],
    unavailable: list[str],
    menu: Menu,
    locale: str,
) -> bool:
    group = (
        OptionGroup.objects.filter(pk=problem.group_id)
        .prefetch_related("options")
        .first()
        if problem.group_id is not None
        else None
    )
    if group is None:
        _drop(work, entry)
        return True
    options = list(group.options.all())
    in_group = [o for o in entry["option_ids"] if o in {str(x.pk) for x in options}]
    if len(in_group) > group.max_select:
        keep = set(in_group[: group.max_select])
        entry["option_ids"] = [
            o for o in entry["option_ids"] if o not in set(in_group) or o in keep
        ]
        return True
    free = [o for o in options if o.is_available and str(o.pk) not in in_group]
    if len(free) < group.min_select - len(in_group):
        # The customer cannot complete this choice: treat the whole item as unavailable.
        unavailable.append(menu.item_name(entry["item_id"], locale))
        _drop(work, entry)
        return True
    incomplete.append((entry, problem))
    return True
