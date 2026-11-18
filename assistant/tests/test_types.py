"""A provider's JSON is only trusted after it fits these models."""

import pytest
from pydantic import ValidationError

from assistant.types import (
    CarDetailsResult,
    ClassifyReplyResult,
    OrderAction,
    OrderQuestion,
    ParseOrderResult,
)

PARSE = {
    "transcript": None,
    "language": "en",
    "intent": "order_change",
    "actions": [
        {
            "type": "add",
            "item_id": "item-1",
            "quantity": 2,
            "option_ids": ["opt-1"],
            "note": "less sugar",
        },
        {"type": "set_quantity", "line": 1, "quantity": 3},
        {"type": "remove", "line": 2},
    ],
    "questions": [
        {"kind": "choose_item", "mention": "burger", "item_ids": ["a", "b"]},
        {"kind": "choose_option", "line": 1, "group_id": "grp-1"},
    ],
    "unmatched": ["pizza"],
}


class TestParseOrder:
    def test_the_example_of_the_spec_is_valid(self) -> None:
        result = ParseOrderResult.model_validate(PARSE)

        assert [a.type.value for a in result.actions] == [
            "add",
            "set_quantity",
            "remove",
        ]
        assert result.questions[0].item_ids == ["a", "b"]
        assert result.unmatched == ["pizza"]

    def test_null_lists_are_empty_lists(self) -> None:
        result = ParseOrderResult.model_validate(
            {**PARSE, "actions": None, "questions": None, "unmatched": None}
        )

        assert (result.actions, result.questions, result.unmatched) == ([], [], [])

    @pytest.mark.parametrize(
        "change",
        [
            {"intent": "maybe"},
            {"language": "fr"},
            {"extra_field": 1},
            {"actions": [{"type": "add", "quantity": 2}]},  # add needs item_id
            {"actions": [{"type": "remove"}]},  # remove needs line
            {"actions": [{"type": "set_quantity", "line": 1}]},  # needs quantity
            {"actions": [{"type": "add", "item_id": "x", "quantity": 500}]},
            {"actions": [{"type": "add", "item_id": "x", "quantity": 0}]},
            {"actions": [{"type": "teleport", "item_id": "x"}]},
            {"questions": [{"kind": "choose_item", "item_ids": ["only-one"]}]},
            {"questions": [{"kind": "choose_option", "line": 1}]},
            {"unmatched": ["x"] * 11},
        ],
    )
    def test_anything_that_does_not_fit_is_refused(
        self, change: dict[str, object]
    ) -> None:
        with pytest.raises(ValidationError):
            ParseOrderResult.model_validate({**PARSE, **change})

    def test_confirm_never_comes_with_actions(self) -> None:
        with pytest.raises(ValidationError):
            ParseOrderResult.model_validate({**PARSE, "intent": "confirm"})

    def test_a_plain_confirm_is_valid(self) -> None:
        result = ParseOrderResult.model_validate(
            {
                "language": "ar",
                "intent": "confirm",
                "actions": [],
                "questions": [],
                "unmatched": [],
            }
        )

        assert result.intent.value == "confirm"

    def test_a_note_is_capped(self) -> None:
        with pytest.raises(ValidationError):
            OrderAction(type="add", item_id="x", note="n" * 201)  # type: ignore[arg-type]

    def test_clear_needs_nothing_else(self) -> None:
        assert OrderAction(type="clear").line is None  # type: ignore[arg-type]

    def test_a_question_about_two_items_needs_both(self) -> None:
        question = OrderQuestion(kind="choose_item", item_ids=["a", "b"])  # type: ignore[arg-type]

        assert question.mention is None


class TestOtherResults:
    def test_a_car_answer_may_leave_every_field_empty(self) -> None:
        result = CarDetailsResult.model_validate({"plate": None})

        assert result.plate is None and result.colour is None

    def test_a_car_field_is_capped(self) -> None:
        with pytest.raises(ValidationError):
            CarDetailsResult.model_validate({"parking_note": "x" * 301})

    def test_a_reply_has_an_intent_and_maybe_a_field(self) -> None:
        result = ClassifyReplyResult.model_validate({"intent": "edit", "field": "car"})

        assert result.field is not None and result.field.value == "car"

    def test_a_reply_with_an_unknown_field_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ClassifyReplyResult.model_validate({"intent": "edit", "field": "price"})

    def test_whitespace_around_text_is_stripped(self) -> None:
        assert (
            CarDetailsResult.model_validate({"plate": "  A 12345 "}).plate == "A 12345"
        )
