"""One turn of the ordering step: what the bot does with an order typed, spoken or tapped.

``OrderingTurn`` holds what every step of a turn needs (the conversation, the menu, the assistant,
the bot's texts) and the ordering step itself: the assistant's actions applied to the lines, the
order summary, the questions, Confirm and the item picker. The later steps (the car, the note, the
review and placing the order) extend it in ``chat/steps.py``.
"""

from typing import Any

from assistant.availability import ai_available, record_failure
from assistant.errors import AssistantError
from assistant.models import Outcome
from assistant.services import Assistant
from assistant.types import (
    ActionType,
    AudioInput,
    CurrentLine,
    MessageInput,
    OrderAction,
    OrderIntent,
    ParseOrderResult,
    QuestionKind,
)
from menu.models import Option, OptionGroup
from orders.models import MAX_LINES

from .errors import InvalidActionForState
from .lines import apply_actions, new_line, renumber
from .models import Conversation, ConversationState, Message, MessageKind
from .reconcile import Menu, Reconciled, is_uuid, reconcile
from .replies import Action, Reply, quick_replies
from .summary import summary_payload
from .texts import pick, say

# A provider failure of these kinds turns the assistant off for a few minutes. A badly formed
# answer (``invalid_output``) does not: the provider is up, it just did not understand.
_OUTAGE = {Outcome.ERROR, Outcome.TIMEOUT, Outcome.RATE_LIMITED}
# What a provider answers when it cannot read the clip itself (a corrupt or unsupported file):
# the clip is the problem, so the customer is asked to say it again and the assistant stays on.
UNREADABLE_AUDIO = {"http_400", "http_413", "http_415", "http_422"}
# What the bot quotes of a thing the customer asked for that is not on the menu.
_UNMATCHED_SHOWN = 3
_UNMATCHED_CHARS = 60


class OrderingTurn:
    """Everything one turn needs, and what the bot does in each step of ordering."""

    def __init__(self, conversation: Conversation, assistant: Assistant) -> None:
        self.conversation = conversation
        self.restaurant = conversation.restaurant
        self.assistant = assistant
        self.menu = Menu(self.restaurant)
        # The customer's message of this turn, once it is stored (a voice turn adds its
        # transcript to it).
        self.customer_row: Message | None = None

    @property
    def locale(self) -> str:
        return self.conversation.locale

    def say(self, key: str, **names: object) -> str:
        return say(key, self.locale, **names)

    def reply(self, key: str, **names: object) -> Reply:
        return Reply(self.say(key, **names))

    # -- the order summary and the questions that can stand in its place ---------------------

    def present(
        self,
        notices: list[str],
        offered_choice: dict[str, Any] | None = None,
        reconciled: Reconciled | None = None,
    ) -> list[Reply]:
        """Say what changed and then show the order, or ask what is still missing."""
        conversation = self.conversation
        rec = reconciled or reconcile(
            self.restaurant, conversation.lines, self.menu, self.locale
        )
        conversation.lines = rec.lines
        replies = [Reply(notice) for notice in notices]
        if rec.unavailable:
            replies.append(
                self.reply(
                    "unavailable", items=", ".join(dict.fromkeys(rec.unavailable))
                )
            )

        question = self._option_question(rec) or self._item_question(offered_choice)
        if question is not None:
            replies.append(question)
            return replies
        conversation.pending_question = None

        if rec.priced is None:
            replies.append(self.reply("what_to_order"))
            return replies
        replies.append(
            Reply(
                self.say("summary_question"),
                MessageKind.ORDER_SUMMARY,
                {
                    "summary": summary_payload(
                        rec.priced, rec.priced_numbers, self.locale
                    ),
                    **quick_replies(
                        {"label": self.say("confirm_label"), "action": "confirm"},
                        {"label": self.say("edit_label"), "action": "edit"},
                    ),
                },
            )
        )
        return replies

    def _option_question(self, rec: Reconciled) -> Reply | None:
        """Ask for the next required option, derived from the lines themselves."""
        if not rec.incomplete:
            return None
        entry, problem = rec.incomplete[0]
        assert problem.group_id is not None  # noqa: S101
        group = (
            OptionGroup.objects.filter(pk=problem.group_id)
            .prefetch_related("options")
            .get()
        )
        chosen = set(entry["option_ids"])
        buttons = [
            {
                "label": pick(option.name_en, option.name_ar_display, self.locale),
                "action": "choose",
                "value": str(option.pk),
            }
            for option in group.options.all()
            if option.is_available and str(option.pk) not in chosen
        ]
        self.conversation.pending_question = {
            "kind": QuestionKind.CHOOSE_OPTION.value,
            "line": entry["line"],
            "group_id": str(group.pk),
        }
        return Reply(
            self.say(
                "choose_option",
                group=pick(group.name_en, group.name_ar_display, self.locale),
                item=self.menu.item_name(entry["item_id"], self.locale),
            ),
            payload=quick_replies(*buttons),
        )

    def _item_question(self, offered: dict[str, Any] | None) -> Reply | None:
        """Ask which of several items the customer meant (the assistant found it unclear)."""
        if not offered or offered.get("kind") != QuestionKind.CHOOSE_ITEM.value:
            return None
        item_ids = [i for i in offered.get("item_ids", []) if i in self.menu.item_ids]
        if len(item_ids) < 2:
            return None
        mention = str(offered.get("mention") or "")[:_UNMATCHED_CHARS]
        self.conversation.pending_question = {
            "kind": QuestionKind.CHOOSE_ITEM.value,
            "item_ids": item_ids,
            "mention": mention,
        }
        text = (
            self.say("choose_item", mention=mention)
            if mention
            else self.say("choose_item_plain")
        )
        buttons = [
            {
                "label": self.menu.item_name(item_id, self.locale),
                "action": "choose",
                "value": item_id,
            }
            for item_id in item_ids
        ]
        return Reply(text, payload=quick_replies(*buttons))

    # -- text ---------------------------------------------------------------------------------

    def _current_lines(self) -> list[CurrentLine]:
        return [
            CurrentLine(
                line=line["line"],
                item_id=line["item_id"],
                quantity=line["quantity"],
                option_ids=tuple(line["option_ids"]),
                note=line.get("note") or "",
            )
            for line in self.conversation.lines
        ]

    def _ask_assistant(self, message: MessageInput) -> ParseOrderResult:
        conversation = self.conversation
        return self.assistant.parse_order(
            self.menu.prompt,
            self._current_lines(),
            conversation.pending_question,
            message,
            self.locale,
            restaurant=self.restaurant,
            conversation=conversation,
        )

    def _went_down(self, error: AssistantError) -> bool:
        """Whether the assistant cannot be used now: an outage (remembered for a few minutes) or
        a used-up budget (nothing was sent). Any other failure is a badly formed answer."""
        if error.outcome in _OUTAGE:
            record_failure()
            return True
        return error.outcome == Outcome.BUDGET_EXCEEDED

    def _failed(self, error: AssistantError, unavailable: str) -> Reply:
        """The bot's answer when the assistant could not be used for this input."""
        if self._went_down(error):
            return self.reply(unavailable)
        return self.reply("not_understood")

    def on_text(self, text: str) -> list[Reply]:
        if not ai_available():
            return [self.reply("assistant_down")]
        try:
            result = self._ask_assistant(text)
        except AssistantError as error:
            return [self._failed(error, "assistant_down")]
        return self.on_parsed(result)

    def hear(self, transcript: str | None) -> str:
        """Keep what the assistant heard on the customer's message and return it."""
        heard = (transcript or "").strip()
        if self.customer_row is not None:
            self.customer_row.transcript = heard
            self.customer_row.save(update_fields=["transcript", "updated_at"])
        return heard

    def on_voice(self, audio: AudioInput) -> list[Reply]:
        """A spoken message goes to the assistant like a typed one, and what it heard is kept
        on the customer's message as the transcript. The clip itself is dropped with this call."""
        if not ai_available():
            return [self.reply("voice_unavailable")]
        try:
            result = self._ask_assistant(audio)
        except AssistantError as error:
            if error.code in UNREADABLE_AUDIO:
                return [self.reply("could_not_hear")]
            return [self._failed(error, "voice_unavailable")]
        heard = self.hear(result.transcript)
        if not heard:
            return [self.reply("could_not_hear")]
        return self.on_parsed(result)

    def on_parsed(self, result: ParseOrderResult) -> list[Reply]:
        conversation = self.conversation
        if result.intent is OrderIntent.CANCEL:
            conversation.lines = []
            conversation.pending_question = None
            return [self.reply("cleared")]
        if result.intent is OrderIntent.CONFIRM:
            return self.confirm()

        applied = apply_actions(conversation.lines, result.actions, self.menu.item_ids)
        conversation.lines = applied.lines

        notices: list[str] = []
        unmatched = [
            " ".join(item.split())[:_UNMATCHED_CHARS]
            for item in result.unmatched
            if item.strip()
        ][:_UNMATCHED_SHOWN]
        if unmatched:
            notices.append(self.say("unmatched", items=", ".join(unmatched)))
        if applied.too_many:
            notices.append(self.say("too_many_lines", limit=MAX_LINES))

        offered = next(
            (
                {
                    "kind": QuestionKind.CHOOSE_ITEM.value,
                    "item_ids": question.item_ids,
                    "mention": question.mention,
                }
                for question in result.questions
                if question.kind is QuestionKind.CHOOSE_ITEM
                and sum(i in self.menu.item_ids for i in question.item_ids) >= 2
            ),
            None,
        )
        if not (applied.changed or unmatched or applied.too_many or offered):
            notices.append(self.say("not_understood"))
            # Nothing changed: a question the customer has not answered is still open.
            pending = conversation.pending_question
            if pending and pending.get("kind") == QuestionKind.CHOOSE_ITEM.value:
                offered = pending
        return self.present(notices, offered)

    # -- buttons ------------------------------------------------------------------------------

    def confirm(self) -> list[Reply]:
        """Move on to the car question when the order is complete and every line still stands;
        otherwise say what changed or ask what is missing."""
        conversation = self.conversation
        if not conversation.lines:
            return [self.reply("empty_order")]
        rec = reconcile(self.restaurant, conversation.lines, self.menu, self.locale)
        if rec.unavailable or rec.incomplete or rec.priced is None:
            pending = conversation.pending_question
            offered = pending if pending and "item_ids" in pending else None
            return self.present([], offered, rec)
        conversation.lines = rec.lines
        conversation.pending_question = None
        if conversation.return_to_review:
            return self.to_review()
        return self.to_car_question()

    # The steps after ordering are in chat/steps.py, which extends this class.
    def to_car_question(self) -> list[Reply]:
        raise NotImplementedError

    def to_review(self) -> list[Reply]:
        raise NotImplementedError

    def on_action(self, action: Action) -> list[Reply]:
        conversation = self.conversation
        if action.name == "confirm":
            return self.confirm()
        if action.name == "edit":
            return [self.reply("edit_prompt")]
        if action.name == "choose":
            return self._choose(action.value)
        if action.name == "set_lines":
            conversation.lines = renumber(
                [
                    new_line(
                        str(line["item_id"]),
                        line["quantity"],
                        [str(o) for o in line.get("option_ids", [])],
                        line.get("note", ""),
                    )
                    for line in action.lines
                ][:MAX_LINES]
            )
            conversation.pending_question = None
            if not conversation.lines:
                return [self.reply("empty_order")]
            return self.present([])
        if action.name == "set_locale":
            conversation.locale = action.locale
            if conversation.state == ConversationState.ORDERING:
                return self.present([])
            return [self.reply("car_question")]
        if action.name == "restart":
            self._clear_everything()
            return [self.reply("restarted")]
        raise InvalidActionForState  # pragma: no cover - checked before the turn

    def _clear_everything(self) -> None:
        conversation = self.conversation
        conversation.lines = []
        conversation.pending_question = None
        conversation.pending_field = ""
        conversation.return_to_review = False
        conversation.parking_note = ""
        conversation.vehicle_plate = ""
        conversation.vehicle_model = ""
        conversation.vehicle_colour = ""
        conversation.order_note = ""
        conversation.state = ConversationState.ORDERING

    def _choose(self, value: str) -> list[Reply]:
        """The customer tapped one of the buttons of a question the bot asked."""
        conversation = self.conversation
        question = conversation.pending_question or {}
        kind = question.get("kind")
        if kind == QuestionKind.CHOOSE_ITEM.value:
            if value in question.get("item_ids", []) and value in self.menu.item_ids:
                added = apply_actions(
                    conversation.lines,
                    [_add_action(value)],
                    self.menu.item_ids,
                )
                conversation.lines = added.lines
                conversation.pending_question = None
                return self.present([])
        elif kind == QuestionKind.CHOOSE_OPTION.value:
            line = next(
                (x for x in conversation.lines if x["line"] == question.get("line")),
                None,
            )
            if line is not None and self._option_belongs(question, value):
                line["option_ids"] = [*line["option_ids"], value]
                conversation.pending_question = None
                return self.present([])
        conversation.pending_question = None
        return self.present([self.say("stale_choice")])

    @staticmethod
    def _option_belongs(question: dict[str, Any], value: str) -> bool:
        if not is_uuid(value) or not is_uuid(question.get("group_id")):
            return False
        return Option.objects.filter(
            pk=value, group_id=question["group_id"], is_available=True
        ).exists()

    def choice_label(self, value: str) -> str:
        """What the customer's tap is shown as in the history: the name of what they chose."""
        if value in self.menu.item_ids:
            return self.menu.item_name(value, self.locale)
        if is_uuid(value):
            option = Option.objects.filter(pk=value).first()
            if option is not None:
                return pick(option.name_en, option.name_ar_display, self.locale)
        return ""


def _add_action(item_id: str) -> OrderAction:
    return OrderAction(type=ActionType.ADD, item_id=item_id, quantity=1)
