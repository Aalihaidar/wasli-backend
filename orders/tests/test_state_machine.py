"""The restaurant's answer to a placed order: accept with 5, 10 or 15 minutes, reject with one
of six reasons, and nothing else. Every other transition is a 409, every change writes an
``OrderEvent`` and moves ``updated_at``, and one restaurant can never answer another's order."""

import uuid

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from orders.models import ActorType, Order, OrderEvent, OrderStatus, RejectionReason
from orders.services import OrderInvalidTransition, accept_order, reject_order
from orders.tests.factories import make_order
from restaurants.models import Restaurant
from restaurants.tests.factories import make_member, make_restaurant
from users.models import User

pytestmark = pytest.mark.django_db


class Setup:
    """A restaurant, its cashier and one placed order."""

    def __init__(self, slug: str = "cafe-one") -> None:
        self.restaurant: Restaurant = make_restaurant(slug)
        self.actor: User = make_member(self.restaurant, f"{slug}-cashier").user
        self.order = make_order(self.restaurant)

    def accept(self, eta: int = 10) -> Order:
        return accept_order(
            order_id=self.order.pk,
            restaurant=self.restaurant,
            actor=self.actor,
            eta_minutes=eta,
        )

    def reject(self, reason: str = "too_busy", note: str = "") -> Order:
        return reject_order(
            order_id=self.order.pk,
            restaurant=self.restaurant,
            actor=self.actor,
            reason_code=reason,
            note=note,
        )

    def fresh(self) -> Order:
        return Order.objects.get(pk=self.order.pk)

    def events(self) -> list[OrderEvent]:
        return list(OrderEvent.objects.filter(order=self.order).order_by("created_at"))


def codes(error: ValidationError) -> dict[str, list[str]]:
    return {
        field: [detail.code for detail in details]
        for field, details in error.detail.items()
    }


class TestAccept:
    @pytest.mark.parametrize("minutes", [5, 10, 15])
    def test_a_placed_order_is_accepted_with_the_wait(self, minutes: int) -> None:
        setup = Setup()

        order = setup.accept(minutes)

        stored = setup.fresh()
        assert order.pk == stored.pk
        assert stored.status == OrderStatus.ACCEPTED
        assert stored.eta_minutes == minutes
        assert stored.accepted_at is not None
        assert stored.rejected_at is None
        assert stored.rejection_reason_code == ""
        assert stored.decided_at == stored.accepted_at

    def test_the_change_moves_updated_at_so_the_screens_find_it(self) -> None:
        setup = Setup()
        before = setup.fresh().updated_at

        setup.accept()

        after = setup.fresh().updated_at
        assert after > before
        assert after.microsecond != 0 or after.second != before.second

    def test_the_event_names_the_staff_member(self) -> None:
        setup = Setup()

        setup.accept()

        placed_or_not = [e for e in setup.events() if e.to_status == "accepted"]
        assert len(placed_or_not) == 1
        event = placed_or_not[0]
        assert (event.from_status, event.to_status) == ("placed", "accepted")
        assert event.actor_type == ActorType.STAFF
        assert event.actor_id == setup.actor.pk
        assert event.restaurant_id == setup.restaurant.pk

    @pytest.mark.parametrize("minutes", [0, 7, 20, -5])
    def test_another_wait_is_refused_and_nothing_changes(self, minutes: int) -> None:
        setup = Setup()

        with pytest.raises(ValidationError) as refused:
            setup.accept(minutes)

        assert codes(refused.value) == {"eta_minutes": ["invalid_choice"]}
        assert setup.fresh().status == OrderStatus.PLACED
        assert setup.events() == []

    def test_a_placed_order_has_no_decision_time(self) -> None:
        assert Setup().fresh().decided_at is None


class TestReject:
    @pytest.mark.parametrize(
        "reason", [r for r in RejectionReason.values if r != "other"]
    )
    def test_every_reason_works_without_a_note(self, reason: str) -> None:
        setup = Setup()

        setup.reject(reason)

        stored = setup.fresh()
        assert stored.status == OrderStatus.REJECTED
        assert stored.rejection_reason_code == reason
        assert stored.rejection_note == ""
        assert stored.rejected_at is not None
        assert stored.accepted_at is None
        assert stored.eta_minutes is None
        assert stored.decided_at == stored.rejected_at

    def test_a_note_is_kept_trimmed(self) -> None:
        setup = Setup()

        setup.reject("too_far", "  Please come closer.  ")

        assert setup.fresh().rejection_note == "Please come closer."

    def test_other_needs_a_note(self) -> None:
        setup = Setup()

        setup.reject("other", "The grill is closed for cleaning.")

        stored = setup.fresh()
        assert stored.rejection_reason_code == "other"
        assert stored.rejection_note == "The grill is closed for cleaning."

    @pytest.mark.parametrize("note", ["", "   ", "\n"])
    def test_other_without_a_note_is_refused(self, note: str) -> None:
        setup = Setup()

        with pytest.raises(ValidationError) as refused:
            setup.reject("other", note)

        assert codes(refused.value) == {"note": ["required"]}
        assert setup.fresh().status == OrderStatus.PLACED

    def test_a_note_of_200_characters_passes_and_201_does_not(self) -> None:
        setup = Setup()
        with pytest.raises(ValidationError) as refused:
            setup.reject("too_busy", "x" * 201)
        assert codes(refused.value) == {"note": ["max_length"]}

        setup.reject("too_busy", "x" * 200)

        assert len(setup.fresh().rejection_note) == 200

    def test_an_unknown_reason_is_refused(self) -> None:
        setup = Setup()

        with pytest.raises(ValidationError) as refused:
            setup.reject("because")

        assert codes(refused.value) == {"reason_code": ["invalid_choice"]}
        assert setup.events() == []

    def test_the_event_names_the_staff_member(self) -> None:
        setup = Setup()

        setup.reject("closing_soon")

        event = next(e for e in setup.events() if e.to_status == "rejected")
        assert (event.from_status, event.to_status) == ("placed", "rejected")
        assert (event.actor_type, event.actor_id) == (ActorType.STAFF, setup.actor.pk)


class TestEveryOtherTransition:
    @pytest.mark.parametrize(
        "status", [s for s in OrderStatus.values if s != OrderStatus.PLACED]
    )
    @pytest.mark.parametrize("action", ["accept", "reject"])
    def test_an_order_that_is_not_placed_cannot_be_answered(
        self, status: str, action: str
    ) -> None:
        setup = Setup()
        extra = {"rejection_reason_code": "too_busy"} if status == "rejected" else {}
        Order.objects.filter(pk=setup.order.pk).update(status=status, **extra)
        before = setup.fresh()

        with pytest.raises(OrderInvalidTransition) as refused:
            setup.accept() if action == "accept" else setup.reject()

        assert refused.value.status_code == 409
        assert refused.value.detail.code == "order_invalid_transition"
        after = setup.fresh()
        assert (after.status, after.updated_at) == (before.status, before.updated_at)
        assert setup.events() == []

    def test_an_order_is_answered_only_once(self) -> None:
        setup = Setup()
        setup.accept(5)

        with pytest.raises(OrderInvalidTransition):
            setup.reject("too_busy")
        with pytest.raises(OrderInvalidTransition):
            setup.accept(15)

        stored = setup.fresh()
        assert (stored.status, stored.eta_minutes) == (OrderStatus.ACCEPTED, 5)
        assert len(setup.events()) == 1


class TestTenancy:
    def test_another_restaurants_order_is_not_found_and_stays_untouched(self) -> None:
        mine, theirs = Setup("cafe-a"), Setup("cafe-b")

        with pytest.raises(NotFound):
            accept_order(
                order_id=theirs.order.pk,
                restaurant=mine.restaurant,
                actor=mine.actor,
                eta_minutes=10,
            )
        with pytest.raises(NotFound):
            reject_order(
                order_id=theirs.order.pk,
                restaurant=mine.restaurant,
                actor=mine.actor,
                reason_code="too_busy",
            )

        assert theirs.fresh().status == OrderStatus.PLACED
        assert theirs.events() == []

    def test_an_unknown_order_is_not_found(self) -> None:
        setup = Setup()

        with pytest.raises(NotFound):
            accept_order(
                order_id=uuid.uuid4(),
                restaurant=setup.restaurant,
                actor=setup.actor,
                eta_minutes=10,
            )

    def test_answering_one_order_leaves_the_restaurants_others_alone(self) -> None:
        setup = Setup()
        other = make_order(setup.restaurant)

        setup.accept()

        assert Order.objects.get(pk=other.pk).status == OrderStatus.PLACED
