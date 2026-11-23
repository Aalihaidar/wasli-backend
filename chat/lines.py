"""Editing the order lines of a conversation.

A line is the dict ``{line, item_id, quantity, option_ids, note}`` stored on the conversation
(ids as strings). The assistant proposes changes as actions addressed to a ``line`` number; this
module applies them to a copy of the lines. It never prices anything and never trusts an id: a
proposal that names an item the restaurant does not show or a line that is not there is dropped
and counted, and the order service re-checks every line before anything is shown or placed.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any

from assistant.types import ActionType, OrderAction
from orders.models import MAX_LINES, MAX_QUANTITY

Line = dict[str, Any]


@dataclass
class Applied:
    lines: list[Line]
    # Proposals that named an item or a line that does not exist: dropped.
    dropped: int = 0
    # An ``add`` that would have made more than ``MAX_LINES`` lines.
    too_many: bool = False
    # Whether the lines differ from what they were.
    changed: bool = False


def new_line(
    item_id: str,
    quantity: int = 1,
    option_ids: Iterable[str] = (),
    note: str = "",
) -> Line:
    return {
        "line": 0,
        "item_id": str(item_id),
        "quantity": quantity,
        "option_ids": [str(option) for option in option_ids],
        "note": note,
    }


def renumber(lines: list[Line]) -> list[Line]:
    """Number the lines 1, 2, 3... in order, so the numbers shown to the customer and the
    numbers the assistant addresses are always the same."""
    for number, line in enumerate(lines, start=1):
        line["line"] = number
    return lines


def _copy(lines: Iterable[Line]) -> list[Line]:
    return [
        {**line, "option_ids": list(line.get("option_ids") or [])} for line in lines
    ]


def _same_choice(a: Line, b: Line) -> bool:
    return (
        a["item_id"] == b["item_id"]
        and sorted(a["option_ids"]) == sorted(b["option_ids"])
        and (a.get("note") or "") == (b.get("note") or "")
    )


def apply_actions(
    current: Iterable[Line],
    actions: Iterable[OrderAction],
    valid_item_ids: Collection[str],
) -> Applied:
    """Apply the assistant's actions, in order, to a copy of ``current``.

    ``valid_item_ids`` are the items this restaurant shows its customers. Adding an item that is
    already on the order with the same options and note adds to its quantity.
    """
    lines = _copy(current)
    before = [
        (line["item_id"], line["quantity"], line["option_ids"], line.get("note"))
        for line in lines
    ]
    result = Applied(lines=lines)

    def find(number: int | None) -> Line | None:
        return next((line for line in lines if line["line"] == number), None)

    for action in actions:
        if action.type is ActionType.CLEAR:
            lines.clear()
        elif action.type is ActionType.ADD:
            item_id = str(action.item_id)
            if item_id not in valid_item_ids:
                result.dropped += 1
                continue
            added = new_line(
                item_id,
                action.quantity or 1,
                action.option_ids,
                action.note or "",
            )
            same = next((line for line in lines if _same_choice(line, added)), None)
            if same is not None:
                same["quantity"] = min(
                    same["quantity"] + added["quantity"], MAX_QUANTITY
                )
            elif len(lines) >= MAX_LINES:
                result.too_many = True
            else:
                lines.append(added)
                renumber(lines)
        else:
            target = find(action.line)
            if target is None:
                result.dropped += 1
            elif action.type is ActionType.REMOVE:
                lines.remove(target)
                renumber(lines)
            elif action.type is ActionType.SET_QUANTITY:
                target["quantity"] = action.quantity or target["quantity"]
            elif action.type is ActionType.SET_OPTIONS:
                target["option_ids"] = [str(option) for option in action.option_ids]
            elif action.type is ActionType.SET_NOTE:
                target["note"] = action.note or ""

    renumber(lines)
    after = [
        (line["item_id"], line["quantity"], line["option_ids"], line.get("note"))
        for line in lines
    ]
    result.changed = before != after
    return result
