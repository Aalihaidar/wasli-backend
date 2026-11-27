"""What can go wrong when an order is priced or placed.

The order service never writes text for a customer: it raises an ``OrderError`` that lists
machine-readable problems, and the conversation engine turns them into a bot message in the
conversation's language (or into an HTTP error where the contract says so).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ProblemCode(StrEnum):
    # The order itself.
    EMPTY_ORDER = "empty_order"
    TOO_MANY_LINES = "too_many_lines"
    RESTAURANT_UNAVAILABLE = "restaurant_unavailable"
    # One line.
    INVALID_QUANTITY = "invalid_quantity"
    NOTE_TOO_LONG = "note_too_long"
    UNKNOWN_ITEM = "unknown_item"
    ITEM_UNAVAILABLE = "item_unavailable"
    UNKNOWN_OPTION = "unknown_option"
    OPTION_UNAVAILABLE = "option_unavailable"
    # A group needs more or fewer choices than were given (``group_id`` names it).
    OPTION_RULE = "option_rule"
    INVALID_PRICE = "invalid_price"
    # Placing the order.
    CAR_DETAILS_INCOMPLETE = "car_details_incomplete"
    UNSUPPORTED_ORDER_TYPE = "unsupported_order_type"
    OUTSIDE_SERVICE_DISTANCE = "outside_service_distance"
    WRONG_STATE = "wrong_state"
    CONVERSATION_EXPIRED = "conversation_expired"
    ALREADY_PLACED = "already_placed"


@dataclass(frozen=True)
class OrderProblem:
    code: ProblemCode
    # The 1-based number of the line, when the problem belongs to one.
    line: int | None = None
    item_id: UUID | None = None
    option_id: UUID | None = None
    group_id: UUID | None = None
    # For ``car_details_incomplete``: the car fields that are missing or invalid.
    fields: tuple[str, ...] = ()


class OrderError(Exception):
    """One or more problems that stop an order. Nothing was written when it is raised."""

    def __init__(self, problems: Sequence[OrderProblem]) -> None:
        self.problems: tuple[OrderProblem, ...] = tuple(problems)
        codes = ", ".join(p.code.value for p in self.problems)
        super().__init__(codes)

    @property
    def codes(self) -> set[ProblemCode]:
        return {problem.code for problem in self.problems}
