from core.order_types import SUPPORTED_ORDER_TYPES, OrderType


def test_the_three_order_types_of_the_contract() -> None:
    assert {t.value for t in OrderType} == {"car", "dine_in", "delivery"}


def test_only_a_car_order_is_accepted_for_now() -> None:
    assert frozenset({"car"}) == SUPPORTED_ORDER_TYPES
