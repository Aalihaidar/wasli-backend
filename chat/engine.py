"""The conversation engine: what the bot does with each thing a customer sends.

One customer input is one *turn*. A turn runs in a single transaction that holds the
conversation's row lock, so two taps at once never interleave, a retry with the same
``client_message_id`` returns the first result instead of running again, and a failure leaves no
half-written conversation. The turn stores the customer's message, decides what to do (the
assistant only helps to understand what the customer meant), updates the conversation and writes
the bot's replies. Every word the bot says comes from ``chat/texts.py``; every price from the
order service.

This module covers the start of a conversation and the ordering step up to the order summary and
the customer's confirmation. The steps after it (the car question, the note, the review and
placing the order) are added with their own endpoints; until then a conversation that has moved on
accepts only a language change and a restart.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from assistant.availability import ai_available, record_failure
from assistant.errors import AssistantError
from assistant.menu import build_prompt_menu
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
    PromptMenu,
    QuestionKind,
)
from core.locales import Locale
from core.order_types import SUPPORTED_ORDER_TYPES
from customers.models import Customer
from menu.models import Option, OptionGroup
from orders.errors import OrderError, OrderProblem, ProblemCode
from orders.models import MAX_LINES
from orders.pricing import PricedOrder, price_lines
from restaurants.models import Restaurant, RestaurantMenuImage

from .errors import ConversationExpired, InvalidActionForState, UnsupportedOrderType
from .lines import Line, apply_actions, new_line, renumber
from .models import (
    IDLE_EXPIRY,
    Conversation,
    ConversationState,
    Message,
    MessageKind,
    Sender,
)
from .services import add_message
from .summary import summary_payload
from .texts import pick, say

# A provider failure of these kinds turns the assistant off for a few minutes. A badly formed
# answer (``invalid_output``) does not: the provider is up, it just did not understand.
_OUTAGE = {Outcome.ERROR, Outcome.TIMEOUT, Outcome.RATE_LIMITED}
# What a provider answers when it cannot read the clip itself (a corrupt or unsupported file):
# the clip is the problem, so the customer is asked to say it again and the assistant stays on.
_UNREADABLE_AUDIO = {"http_400", "http_413", "http_415", "http_422"}
# What the bot quotes of a thing the customer asked for that is not on the menu.
_UNMATCHED_SHOWN = 3
_UNMATCHED_CHARS = 60
_MAX_NOTE_CHARS = 200

# The actions of the contract, and the states each is allowed in. A conversation past
# ``ordering`` takes only a language change and a restart until its own steps are built.
_ORDERING_ACTIONS = {"confirm", "edit", "choose", "set_lines"}
_ANY_OPEN_STATE_ACTIONS = {"set_locale", "restart"}


def get_assistant() -> Assistant:
    """The assistant layer for a turn (a test replaces this with a scripted fake)."""
    return Assistant()


# --- what a turn takes and gives --------------------------------------------------------------


@dataclass(frozen=True)
class Action:
    """A button the customer tapped, or the app's own request (the item picker)."""

    name: str
    field_name: str = ""
    value: str = ""
    locale: str = ""
    lines: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Reply:
    """One bot message, before it is stored."""

    text: str
    kind: str = MessageKind.TEXT
    payload: dict[str, Any] = field(default_factory=dict)
    image: str = ""


class Opened(NamedTuple):
    conversation: Conversation
    messages: list[Message]
    created: bool


class Sent(NamedTuple):
    conversation: Conversation
    messages: list[Message]


def _quick_replies(*buttons: dict[str, str]) -> dict[str, Any]:
    return {"quick_replies": list(buttons)}


# --- reading the order ------------------------------------------------------------------------


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


def _is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


class _Menu:
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
    restaurant: Restaurant, stored: list[Line], menu: _Menu, locale: str
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
    menu: _Menu,
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
            entry["option_ids"] = [o for o in entry["option_ids"] if _is_uuid(o)]
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
    menu: _Menu,
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


# --- one turn ---------------------------------------------------------------------------------


class _Turn:
    """Everything one turn needs, and what the bot does in each step of ordering."""

    def __init__(self, conversation: Conversation, assistant: Assistant) -> None:
        self.conversation = conversation
        self.restaurant = conversation.restaurant
        self.assistant = assistant
        self.menu = _Menu(self.restaurant)
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
                    **_quick_replies(
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
            payload=_quick_replies(*buttons),
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
        return Reply(text, payload=_quick_replies(*buttons))

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

    def _failed(self, error: AssistantError, unavailable: str) -> Reply:
        """The bot's answer when the assistant could not be used for this input."""
        if error.outcome in _OUTAGE:
            record_failure()
            return self.reply(unavailable)
        if error.outcome == Outcome.BUDGET_EXCEEDED:
            # Nothing was sent: the day's budget is used up, so the picker is offered.
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

    def on_voice(self, audio: AudioInput) -> list[Reply]:
        """A spoken message goes to the assistant like a typed one, and what it heard is kept
        on the customer's message as the transcript. The clip itself is dropped with this call."""
        if not ai_available():
            return [self.reply("voice_unavailable")]
        try:
            result = self._ask_assistant(audio)
        except AssistantError as error:
            if error.code in _UNREADABLE_AUDIO:
                return [self.reply("could_not_hear")]
            return [self._failed(error, "voice_unavailable")]
        heard = (result.transcript or "").strip()
        if self.customer_row is not None:
            self.customer_row.transcript = heard
            self.customer_row.save(update_fields=["transcript", "updated_at"])
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
        conversation.return_to_review = False
        conversation.state = ConversationState.ASK_CAR
        return [self.reply("car_question")]

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
        if not _is_uuid(value) or not _is_uuid(question.get("group_id")):
            return False
        return Option.objects.filter(
            pk=value, group_id=question["group_id"], is_available=True
        ).exists()

    def choice_label(self, value: str) -> str:
        """What the customer's tap is shown as in the history: the name of what they chose."""
        if value in self.menu.item_ids:
            return self.menu.item_name(value, self.locale)
        if _is_uuid(value):
            option = Option.objects.filter(pk=value).first()
            if option is not None:
                return pick(option.name_en, option.name_ar_display, self.locale)
        return ""


def _add_action(item_id: str) -> OrderAction:
    return OrderAction(type=ActionType.ADD, item_id=item_id, quantity=1)


# --- the turn around it -----------------------------------------------------------------------


def _owned(
    customer: Customer, conversation_id: uuid.UUID, *, lock: bool
) -> Conversation:
    """The customer's own conversation. Another customer's, or an unknown id, is a 404."""
    query = Conversation.objects.select_related("restaurant", "customer")
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        return query.get(pk=conversation_id, customer=customer)
    except Conversation.DoesNotExist:
        raise NotFound from None


def _store(conversation: Conversation, reply: Reply) -> Message:
    return add_message(
        conversation,
        Sender.BOT,
        MessageKind(reply.kind),
        text=reply.text,
        image=reply.image,
        payload=reply.payload,
    )


def _replayed(conversation: Conversation, first: Message) -> list[Message]:
    """What a request produced the first time: the customer's message and the bot's replies
    that follow it, up to the customer's next message."""
    following = Message.objects.filter(conversation=conversation, seq__gt=first.seq)
    next_customer = (
        following.filter(sender=Sender.CUSTOMER)
        .order_by("seq")
        .values_list("seq", flat=True)
    ).first()
    if next_customer is not None:
        following = following.filter(seq__lt=next_customer)
    return [first, *following.order_by("seq")]


def _run_turn(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    *,
    allowed: Callable[[Conversation], None],
    customer_message: Callable[[_Turn], tuple[str, dict[str, Any]]],
    handler: Callable[[_Turn], list[Reply]],
    used_voice: bool = False,
) -> Sent:
    with transaction.atomic():
        conversation = _owned(customer, conversation_id, lock=True)
        earlier = Message.objects.filter(
            conversation=conversation, client_message_id=client_message_id
        ).first()
        if earlier is not None:
            return Sent(conversation, _replayed(conversation, earlier))

        if conversation.state == ConversationState.PLACED:
            raise InvalidActionForState
        if conversation.is_expired():
            raise ConversationExpired
        allowed(conversation)

        turn = _Turn(conversation, get_assistant())
        text, payload = customer_message(turn)
        stored = [
            add_message(
                conversation,
                Sender.CUSTOMER,
                MessageKind.TEXT,
                text=text,
                used_voice=used_voice,
                payload=payload,
                client_message_id=client_message_id,
            )
        ]
        turn.customer_row = stored[0]
        now = timezone.now()
        conversation.last_activity_at = now
        conversation.expires_at = now + IDLE_EXPIRY
        try:
            replies = handler(turn)
        except OrderError as error:
            if ProblemCode.RESTAURANT_UNAVAILABLE not in error.codes:
                raise
            replies = [turn.reply("restaurant_unavailable")]
        stored.extend(_store(conversation, reply) for reply in replies)
        conversation.save()
        return Sent(conversation, stored)


def send_text(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    text: str,
) -> Sent:
    """The customer typed ``text``. In ``ordering`` the assistant reads it as an order change."""

    def allowed(conversation: Conversation) -> None:
        if conversation.state != ConversationState.ORDERING:
            raise InvalidActionForState

    return _run_turn(
        customer,
        conversation_id,
        client_message_id,
        allowed=allowed,
        customer_message=lambda turn: (text, {}),
        handler=lambda turn: turn.on_text(text),
    )


def send_voice(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    audio: AudioInput,
) -> Sent:
    """The customer spoke. The clip is understood like a typed message in ``ordering``; the
    customer's message holds what was heard (``transcript``) and never the audio."""

    def allowed(conversation: Conversation) -> None:
        if conversation.state != ConversationState.ORDERING:
            raise InvalidActionForState

    return _run_turn(
        customer,
        conversation_id,
        client_message_id,
        allowed=allowed,
        customer_message=lambda turn: ("", {}),
        handler=lambda turn: turn.on_voice(audio),
        used_voice=True,
    )


def send_action(
    customer: Customer,
    conversation_id: uuid.UUID,
    client_message_id: uuid.UUID,
    action: Action,
) -> Sent:
    """The customer tapped a button, or the app sent its own request (the item picker)."""

    def allowed(conversation: Conversation) -> None:
        in_ordering = conversation.state == ConversationState.ORDERING
        if action.name in _ORDERING_ACTIONS and not in_ordering:
            raise InvalidActionForState
        if action.name not in _ORDERING_ACTIONS | _ANY_OPEN_STATE_ACTIONS:
            # ``edit_field`` and ``skip_note`` belong to steps that are not built yet.
            raise InvalidActionForState

    def customer_message(turn: _Turn) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {"action": action.name}
        label = ""
        if action.name == "confirm":
            label = turn.say("confirm_label")
        elif action.name == "edit":
            label = turn.say("edit_label")
        elif action.name == "restart":
            label = turn.say("restart_label")
        elif action.name == "set_lines":
            label = turn.say("picked_items")
        elif action.name == "set_locale":
            label = say("locale_label", action.locale)
            payload["locale"] = action.locale
        elif action.name == "choose":
            label = turn.choice_label(action.value)
            payload["value"] = action.value
        return label, payload

    return _run_turn(
        customer,
        conversation_id,
        client_message_id,
        allowed=allowed,
        customer_message=customer_message,
        handler=lambda turn: turn.on_action(action),
    )


def list_messages(
    customer: Customer, conversation_id: uuid.UUID, after_seq: int = 0
) -> Sent:
    """The messages after ``after_seq``, oldest first (what the app polls)."""
    conversation = _owned(customer, conversation_id, lock=False)
    messages = Message.objects.filter(
        conversation=conversation, seq__gt=after_seq
    ).order_by("seq")
    return Sent(conversation, list(messages))


# --- starting a conversation ------------------------------------------------------------------


def _welcome(restaurant: Restaurant, locale: str) -> str:
    custom = (
        restaurant.welcome_message_ar or restaurant.welcome_message_en
        if locale == Locale.AR.value
        else restaurant.welcome_message_en
    )
    if custom.strip():
        return custom.strip()
    return say(
        "welcome",
        locale,
        restaurant=pick(restaurant.name_en, restaurant.name_ar_display, locale),
    )


@transaction.atomic
def open_conversation(
    customer: Customer,
    restaurant: Restaurant,
    *,
    locale: str,
    start_new: bool = False,
    order_type: str = "car",
) -> Opened:
    """The customer's current conversation with a restaurant, or a new one.

    The newest conversation is returned (with its whole history) while it is placed or has not
    expired; a new one is made when there is none, the last one expired unplaced, or
    ``start_new`` is true. A new conversation already holds the welcome, one message per menu
    image and the first question.
    """
    if order_type not in SUPPORTED_ORDER_TYPES:
        raise UnsupportedOrderType
    # Two requests at once for the same customer take turns, so they never make two.
    Customer.objects.select_for_update().get(pk=customer.pk)
    latest = (
        Conversation.objects.for_restaurant(restaurant)
        .filter(customer=customer)
        .order_by("-created_at")
        .first()
    )
    if (
        latest is not None
        and not start_new
        and (latest.state == ConversationState.PLACED or not latest.is_expired())
    ):
        history = list(latest.messages.order_by("seq"))
        return Opened(latest, history, created=False)

    conversation = Conversation.objects.create(
        restaurant=restaurant,
        customer=customer,
        locale=locale,
        order_type=order_type,
    )
    replies = [Reply(_welcome(restaurant, locale))]
    replies.extend(
        Reply(
            pick(image.caption_en, image.caption_ar_display, locale),
            MessageKind.IMAGE,
            image=image.image.name or "",
        )
        for image in RestaurantMenuImage.objects.for_restaurant(restaurant)
    )
    replies.append(Reply(say("what_to_order", locale)))
    messages = [_store(conversation, reply) for reply in replies]
    return Opened(conversation, messages, created=True)


__all__ = [
    "Action",
    "Opened",
    "Sent",
    "list_messages",
    "open_conversation",
    "reconcile",
    "send_action",
    "send_text",
    "send_voice",
]
