"""The steps after ordering: the car, the note, the review and placing the order.

``Turn`` extends the ordering turn with what the bot does in ``ask_car``, ``ask_note`` and
``review``. The assistant only helps to understand (the car details inside one free answer, what a
reply to the final summary means); the server merges and validates every answer, asks only for what
is missing, writes every word and, at the final confirmation, places the order through the order
service. A missing or unreadable answer is always handled in the chat, never as an HTTP error.
"""

from assistant.availability import ai_available
from assistant.errors import AssistantError
from assistant.types import (
    AudioInput,
    CarDetailsResult,
    CarFields,
    MessageInput,
    ReplyField,
    ReplyIntent,
)
from orders.car import (
    CAR_FIELDS,
    car_field_limits,
    clean_car_field,
    missing_car_fields,
)
from orders.errors import OrderError, ProblemCode
from orders.services import place_order

from .errors import ConversationExpired, InvalidActionForState, UnsupportedOrderType
from .models import ConversationState, MessageKind
from .ordering import UNREADABLE_AUDIO, OrderingTurn
from .reconcile import Reconciled, reconcile
from .replies import Action, Reply, quick_replies
from .summary import summary_payload

# Where each car detail lives on the conversation.
_CAR_ATTRS = {
    "parking_note": "parking_note",
    "plate": "vehicle_plate",
    "model": "vehicle_model",
    "colour": "vehicle_colour",
}
# The note is stored as typed (the assistant never reads it); at most this long.
MAX_ORDER_NOTE_CHARS = 300


class Turn(OrderingTurn):
    # --- what the bot says --------------------------------------------------------------------

    def _car_values(self) -> dict[str, str]:
        return {
            field: getattr(self.conversation, attr)
            for field, attr in _CAR_ATTRS.items()
        }

    def _car_fields(self) -> CarFields:
        values = self._car_values()
        return CarFields(**{field: values[field] or None for field in CAR_FIELDS})

    def _car_labels(self, fields: tuple[str, ...]) -> str:
        return ", ".join(self.say(f"car_label_{field}") for field in fields)

    def _car_prompt(self) -> Reply:
        """The car question: all of it the first time, only what is missing afterwards, and the
        four current values when the customer is editing them from the review. While the
        assistant is down, or once the one-at-a-time questions have started, one item is asked."""
        if self.conversation.pending_field or not ai_available():
            return self._fallback_prompt()
        if self.conversation.return_to_review:
            values = "\n".join(
                f"{self.say('car_value_' + field)}: {value}"
                for field, value in self._car_values().items()
                if value
            )
            return self.reply("car_show", values=values)
        missing = missing_car_fields(self._car_values())
        if len(missing) == len(CAR_FIELDS):
            return self.reply("car_question")
        return self.reply("car_still_need", items=self._car_labels(missing))

    def _note_prompt(self) -> Reply:
        conversation = self.conversation
        if conversation.return_to_review and conversation.order_note:
            return Reply(
                self.say("note_edit", note=conversation.order_note),
                payload=quick_replies(
                    {"label": self.say("keep_label"), "action": "skip_note"}
                ),
            )
        return Reply(
            self.say("note_question"),
            payload=quick_replies(
                {"label": self.say("skip_label"), "action": "skip_note"}
            ),
        )

    def _review_message(self, rec: Reconciled) -> Reply:
        conversation = self.conversation
        assert rec.priced is not None  # noqa: S101 - the caller checked
        has_position = conversation.location_lat is not None
        return Reply(
            self.say("review_question"),
            MessageKind.REVIEW,
            {
                "summary": summary_payload(rec.priced, rec.priced_numbers, self.locale),
                "parking_note": conversation.parking_note,
                "vehicle_plate": conversation.vehicle_plate,
                "vehicle_model": conversation.vehicle_model,
                "vehicle_colour": conversation.vehicle_colour,
                "order_note": conversation.order_note,
                "location_shared": has_position,
                "location_source": conversation.location_source
                if has_position
                else "none",
                **quick_replies(
                    {"label": self.say("yes_send_label"), "action": "confirm"},
                    {"label": self.say("edit_label"), "action": "edit"},
                ),
            },
        )

    def _edit_prompt(self) -> Reply:
        return Reply(
            self.say("review_edit_prompt"),
            payload=quick_replies(
                {
                    "label": self.say("edit_order_label"),
                    "action": "edit_field",
                    "field": "items",
                },
                {
                    "label": self.say("edit_car_label"),
                    "action": "edit_field",
                    "field": "car",
                },
                {
                    "label": self.say("edit_note_label"),
                    "action": "edit_field",
                    "field": "note",
                },
            ),
        )

    # --- moving between the steps -------------------------------------------------------------

    def _enter_car(self, *, editing: bool) -> None:
        """Open the car question afresh (any one-at-a-time questions start again)."""
        conversation = self.conversation
        conversation.state = ConversationState.ASK_CAR
        conversation.return_to_review = editing
        conversation.pending_field = ""

    def to_car_question(self) -> list[Reply]:
        self._enter_car(editing=False)
        return [self._car_prompt()]

    def begin_car_edit(self) -> list[Reply]:
        self._enter_car(editing=True)
        return [self._car_prompt()]

    def to_note(self) -> list[Reply]:
        conversation = self.conversation
        conversation.state = ConversationState.ASK_NOTE
        conversation.return_to_review = False
        return [self._note_prompt()]

    def begin_note_edit(self) -> list[Reply]:
        conversation = self.conversation
        conversation.state = ConversationState.ASK_NOTE
        conversation.return_to_review = True
        return [self._note_prompt()]

    def begin_items_edit(self) -> list[Reply]:
        """Back to the order. The next Confirm goes straight to the review."""
        conversation = self.conversation
        conversation.state = ConversationState.ORDERING
        conversation.return_to_review = True
        conversation.pending_question = None
        return [self.reply("edit_prompt"), *self.present([])]

    def to_review(self) -> list[Reply]:
        """The whole order for the final confirmation. If a line no longer stands (an item became
        unavailable), the customer goes back to the order and is told."""
        conversation = self.conversation
        rec = reconcile(self.restaurant, conversation.lines, self.menu, self.locale)
        if rec.unavailable or rec.incomplete or rec.priced is None:
            conversation.state = ConversationState.ORDERING
            conversation.return_to_review = True
            return self.present([], None, rec)
        conversation.lines = rec.lines
        conversation.pending_question = None
        conversation.state = ConversationState.REVIEW
        conversation.return_to_review = False
        return [self._review_message(rec)]

    # --- the car ------------------------------------------------------------------------------

    def _merge_car(self, result: CarDetailsResult) -> bool:
        """Put what the customer said into the conversation, changing only what they mentioned.
        A value that does not meet the rules is ignored (and counts as missing). Returns whether
        anything changed."""
        changed = False
        for field, attr in _CAR_ATTRS.items():
            cleaned = clean_car_field(field, getattr(result, field))
            if cleaned and cleaned != getattr(self.conversation, attr):
                setattr(self.conversation, attr, cleaned)
                changed = True
        return changed

    def _car_answer(self, message: MessageInput) -> list[Reply]:
        conversation = self.conversation
        editing = conversation.return_to_review
        if conversation.pending_field or not ai_available():
            return self._fallback_answer(message)
        asked = list(CAR_FIELDS if editing else missing_car_fields(self._car_values()))
        try:
            result = self.assistant.extract_car_details(
                self._car_fields(),
                asked,
                message,
                self.locale,
                restaurant=self.restaurant,
                conversation=conversation,
            )
        except AssistantError as error:
            if isinstance(message, AudioInput) and error.code in UNREADABLE_AUDIO:
                return [self.reply("could_not_hear")]
            if self._went_down(error):
                return self._fallback_answer(message)
            return [self.reply("not_understood")]
        if isinstance(message, AudioInput) and not self.hear(result.transcript):
            return [self.reply("could_not_hear")]

        changed = self._merge_car(result)
        missing = missing_car_fields(self._car_values())
        if missing:
            key = "car_still_need" if changed else "car_not_caught"
            return [self.reply(key, items=self._car_labels(missing))]
        if editing:
            if not changed:
                return [self.reply("car_no_change"), self._car_prompt()]
            return self.to_review()
        return self.to_note()

    # --- the car, one item at a time (the assistant is down) -----------------------------------

    def _ask_text(self, field: str) -> str:
        """The question for one car item. When editing from the review, the current value is shown."""
        text = self.say(f"car_ask_{field}")
        current = getattr(self.conversation, _CAR_ATTRS[field])
        if self.conversation.return_to_review and current:
            text = f"{text}\n{self.say('car_current', value=current)}"
        return text

    def _fallback_prompt(self) -> Reply:
        """The question for the item being asked. The first time it also says why, and starts at
        the first item that is missing (all four when editing)."""
        conversation = self.conversation
        starting = not conversation.pending_field
        if starting:
            missing = missing_car_fields(self._car_values())
            first = (
                CAR_FIELDS[0]
                if conversation.return_to_review or not missing
                else missing[0]
            )
            conversation.pending_field = first
        text = self._ask_text(conversation.pending_field)
        if starting:
            text = f"{self.say('car_fallback_intro')}\n{text}"
        return Reply(text)

    def _fallback_answer(self, message: MessageInput) -> list[Reply]:
        """An answer to the car question while the assistant cannot read it. The typed text goes
        straight into the item being asked, checked by the same rules as the order service; a
        spoken one cannot be read. A message that arrives before the first question is not used
        as an answer, because it may hold several items."""
        conversation = self.conversation
        starting = not conversation.pending_field
        if isinstance(message, AudioInput):
            return [self.reply("car_voice_unavailable"), self._fallback_prompt()]
        if starting:
            return [self._fallback_prompt()]
        field = conversation.pending_field
        cleaned = clean_car_field(field, message)
        if cleaned is None:
            low, high = car_field_limits(field)
            hint = self.say(
                "car_invalid", item=self.say(f"car_value_{field}"), low=low, high=high
            )
            return [Reply(f"{hint}\n{self._ask_text(field)}")]
        setattr(conversation, _CAR_ATTRS[field], cleaned)

        editing = conversation.return_to_review
        if editing:
            position = CAR_FIELDS.index(field) + 1
            following = CAR_FIELDS[position] if position < len(CAR_FIELDS) else None
        else:
            missing = missing_car_fields(self._car_values())
            following = missing[0] if missing else None
        if following:
            conversation.pending_field = following
            return [Reply(self._ask_text(following))]
        conversation.pending_field = ""
        return self.to_review() if editing else self.to_note()

    # --- the note -----------------------------------------------------------------------------

    def _note_answer(self, text: str) -> list[Reply]:
        note = " ".join(text.split())
        if len(note) > MAX_ORDER_NOTE_CHARS:
            return [self.reply("note_too_long", limit=MAX_ORDER_NOTE_CHARS)]
        self.conversation.order_note = note
        return self.to_review()

    def _note_voice(self, audio: AudioInput) -> list[Reply]:
        if not ai_available():
            return [self.reply("voice_unavailable")]
        try:
            result = self.assistant.transcribe(
                audio,
                self.locale,
                restaurant=self.restaurant,
                conversation=self.conversation,
            )
        except AssistantError as error:
            if error.code in UNREADABLE_AUDIO:
                return [self.reply("could_not_hear")]
            return [self._failed(error, "voice_unavailable")]
        heard = self.hear(result.transcript)
        if not heard:
            return [self.reply("could_not_hear")]
        return self._note_answer(heard)

    def _skip_note(self) -> list[Reply]:
        """No note, or, when editing from the review, keep the note as it is."""
        conversation = self.conversation
        if not conversation.return_to_review:
            conversation.order_note = ""
        return self.to_review()

    # --- the review ---------------------------------------------------------------------------

    def _review_answer(self, message: MessageInput) -> list[Reply]:
        """A free-text or spoken reply to the final summary: what does it mean?"""
        if not ai_available():
            return [self.reply("use_buttons"), *self.to_review()]
        try:
            result = self.assistant.classify_reply(
                message,
                self.locale,
                restaurant=self.restaurant,
                conversation=self.conversation,
            )
        except AssistantError as error:
            if isinstance(message, AudioInput) and error.code in UNREADABLE_AUDIO:
                return [self.reply("could_not_hear"), *self.to_review()]
            return [self._failed(error, "use_buttons"), *self.to_review()]
        if isinstance(message, AudioInput) and not self.hear(result.transcript):
            return [self.reply("could_not_hear"), *self.to_review()]

        if result.intent is ReplyIntent.CONFIRM:
            return self.place()
        if result.intent is ReplyIntent.CANCEL:
            self._clear_everything()
            return [self.reply("cleared")]
        if result.intent is ReplyIntent.EDIT:
            return self._edit(result.field.value if result.field else "", message)
        return [self.reply("not_understood"), *self.to_review()]

    def _edit(self, field: str, message: MessageInput | None = None) -> list[Reply]:
        """Open one part of the order for editing. A free-text reply that already holds the
        change to the car ("the colour is black") is read as the answer, so the customer does
        not say it twice."""
        if field == ReplyField.ITEMS.value:
            return self.begin_items_edit()
        if field == ReplyField.NOTE.value:
            return self.begin_note_edit()
        if field == ReplyField.CAR.value:
            replies = self.begin_car_edit()
            if message is None or self.conversation.pending_field:
                return replies
            return self._car_answer(message)
        return [self._edit_prompt()]

    # --- placing the order --------------------------------------------------------------------

    def place(self) -> list[Reply]:
        """The final confirmation: the order service checks everything again and creates the
        order. A customer whose phone must be verified first gets a ``403`` and nothing is stored
        (the whole turn is rolled back)."""
        conversation = self.conversation
        conversation.save()  # the order service reads the row
        try:
            order = place_order(conversation)
        except OrderError as error:
            return self._placing_failed(error)
        conversation.refresh_from_db()
        return [self.reply("placed", number=order.number)]

    def _placing_failed(self, error: OrderError) -> list[Reply]:
        codes = error.codes
        conversation = self.conversation
        if ProblemCode.CONVERSATION_EXPIRED in codes:
            raise ConversationExpired
        if codes & {ProblemCode.ALREADY_PLACED, ProblemCode.WRONG_STATE}:
            raise InvalidActionForState
        if ProblemCode.UNSUPPORTED_ORDER_TYPE in codes:
            raise UnsupportedOrderType
        if ProblemCode.RESTAURANT_UNAVAILABLE in codes:
            return [self.reply("restaurant_unavailable")]
        if ProblemCode.OUTSIDE_SERVICE_DISTANCE in codes:
            return [self.reply("outside_service_distance"), *self.to_review()]
        if ProblemCode.CAR_DETAILS_INCOMPLETE in codes:
            self._enter_car(editing=False)
            return [self._car_prompt()]
        # The order itself no longer stands: an item or option is gone, or it is empty.
        conversation.state = ConversationState.ORDERING
        conversation.return_to_review = True
        return self.present([])

    # --- what the customer sends, by step -----------------------------------------------------

    def on_text(self, text: str) -> list[Reply]:
        state = self.conversation.state
        if state == ConversationState.ASK_CAR:
            return self._car_answer(text)
        if state == ConversationState.ASK_NOTE:
            return self._note_answer(text)
        if state == ConversationState.REVIEW:
            return self._review_answer(text)
        return super().on_text(text)

    def on_voice(self, audio: AudioInput) -> list[Reply]:
        state = self.conversation.state
        if state == ConversationState.ASK_CAR:
            return self._car_answer(audio)
        if state == ConversationState.ASK_NOTE:
            return self._note_voice(audio)
        if state == ConversationState.REVIEW:
            return self._review_answer(audio)
        return super().on_voice(audio)

    def on_action(self, action: Action) -> list[Reply]:
        conversation = self.conversation
        state = conversation.state
        if action.name == "set_locale":
            conversation.locale = action.locale
            return self._repeat_current_question()
        if action.name == "restart" or state == ConversationState.ORDERING:
            return super().on_action(action)
        if action.name == "skip_note" and state == ConversationState.ASK_NOTE:
            return self._skip_note()
        if state == ConversationState.REVIEW:
            if action.name == "confirm":
                return self.place()
            if action.name == "edit":
                return [self._edit_prompt()]
            if action.name == "edit_field":
                return self._edit(action.field_name)
        raise InvalidActionForState  # pragma: no cover - checked before the turn

    def _repeat_current_question(self) -> list[Reply]:
        """After a language change, the question the customer is on, in the new language."""
        state = self.conversation.state
        if state == ConversationState.ASK_CAR:
            return [self._car_prompt()]
        if state == ConversationState.ASK_NOTE:
            return [self._note_prompt()]
        if state == ConversationState.REVIEW:
            return self.to_review()
        return self.present([])
