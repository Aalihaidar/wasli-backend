"""The pure parts of the engine: editing lines and the bot's sentences."""

import re
import uuid

import pytest

from assistant.types import ActionType, OrderAction
from chat.lines import apply_actions, new_line, renumber
from chat.texts import _TEXTS, pick, say
from orders.models import MAX_LINES, MAX_QUANTITY

ITEM = str(uuid.uuid4())
OTHER = str(uuid.uuid4())
VALID = {ITEM, OTHER}


def _lines(*items: str) -> list[dict]:  # type: ignore[type-arg]
    return renumber([new_line(item) for item in items])


class TestApplyActions:
    def test_adding_an_unknown_item_is_dropped_and_counted(self) -> None:
        result = apply_actions(
            [], [OrderAction(type=ActionType.ADD, item_id=str(uuid.uuid4()))], VALID
        )

        assert result.lines == [] and result.dropped == 1 and not result.changed

    def test_adding_the_same_choice_adds_the_quantity_up_to_the_cap(self) -> None:
        lines = _lines(ITEM)
        lines[0]["quantity"] = MAX_QUANTITY - 1

        result = apply_actions(
            lines, [OrderAction(type=ActionType.ADD, item_id=ITEM, quantity=5)], VALID
        )

        assert len(result.lines) == 1
        assert result.lines[0]["quantity"] == MAX_QUANTITY

    def test_the_same_item_with_other_options_is_another_line(self) -> None:
        option = str(uuid.uuid4())
        result = apply_actions(
            _lines(ITEM),
            [OrderAction(type=ActionType.ADD, item_id=ITEM, option_ids=[option])],
            VALID,
        )

        assert [line["line"] for line in result.lines] == [1, 2]
        assert result.changed

    def test_the_input_is_never_changed(self) -> None:
        lines = _lines(ITEM)

        apply_actions(lines, [OrderAction(type=ActionType.CLEAR)], VALID)

        assert len(lines) == 1

    def test_removing_renumbers(self) -> None:
        result = apply_actions(
            _lines(ITEM, OTHER, ITEM + "x"),
            [OrderAction(type=ActionType.REMOVE, line=1)],
            VALID,
        )

        assert [(line["line"], line["item_id"]) for line in result.lines] == [
            (1, OTHER),
            (2, ITEM + "x"),
        ]

    def test_set_options_and_note_replace_what_was_there(self) -> None:
        option = str(uuid.uuid4())
        lines = _lines(ITEM)
        lines[0]["note"] = "old"

        result = apply_actions(
            lines,
            [
                OrderAction(type=ActionType.SET_OPTIONS, line=1, option_ids=[option]),
                OrderAction(type=ActionType.SET_NOTE, line=1, note=None),
            ],
            VALID,
        )

        assert result.lines[0]["option_ids"] == [option]
        assert result.lines[0]["note"] == ""

    def test_the_twenty_first_line_is_refused(self) -> None:
        lines = _lines(*(str(uuid.uuid4()) for _ in range(MAX_LINES)))

        result = apply_actions(
            lines, [OrderAction(type=ActionType.ADD, item_id=ITEM)], VALID
        )

        assert len(result.lines) == MAX_LINES and result.too_many

    def test_nothing_proposed_means_nothing_changed(self) -> None:
        result = apply_actions(_lines(ITEM), [], VALID)

        assert not result.changed and result.dropped == 0


class TestTexts:
    @pytest.mark.parametrize("key", sorted(_TEXTS))
    def test_every_text_exists_in_both_languages_with_the_same_blanks(
        self, key: str
    ) -> None:
        texts = _TEXTS[key]
        assert set(texts) == {"en", "ar"}
        blanks = {
            lang: set(re.findall(r"{(\w+)}", text)) for lang, text in texts.items()
        }
        assert blanks["en"] == blanks["ar"]
        assert all(text.strip() for text in texts.values())

    def test_a_name_with_braces_cannot_break_a_sentence(self) -> None:
        assert say("unavailable", "en", items="{items} {0}") == (
            "Not available right now: {items} {0}."
        )

    def test_an_unknown_language_falls_back_to_english(self) -> None:
        assert say("what_to_order", "fr") == "What would you like to order?"

    def test_a_name_is_picked_by_language(self) -> None:
        assert pick("Tea", "شاي", "ar") == "شاي"
        assert pick("Tea", "شاي", "en") == "Tea"
