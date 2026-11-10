"""What goes into the assistant layer and what comes back.

Inputs are plain frozen dataclasses. Outputs are pydantic models: a provider's JSON is only
trusted after it has been validated against them, and a value that does not fit (an unknown
intent, a quantity of 500, a missing ``item_id``) is an ``invalid_output`` failure, never data.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, TypeVar, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import limits

# --- inputs ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class AudioInput:
    """One voice clip. It is sent to the provider and never stored."""

    data: bytes
    mime_type: str


MessageInput = str | AudioInput


@dataclass(frozen=True)
class PromptOption:
    id: str
    name_en: str
    name_ar: str
    is_default: bool = False
    is_available: bool = True


@dataclass(frozen=True)
class PromptGroup:
    id: str
    name_en: str
    name_ar: str
    min_select: int
    max_select: int
    options: tuple[PromptOption, ...] = ()


@dataclass(frozen=True)
class PromptItem:
    """A menu item as the assistant sees it: names, aliases and options, never a price."""

    id: str
    name_en: str
    name_ar: str
    aliases: tuple[str, ...] = ()
    is_available: bool = True
    option_groups: tuple[PromptGroup, ...] = ()


@dataclass(frozen=True)
class PromptMenu:
    items: tuple[PromptItem, ...]


@dataclass(frozen=True)
class CurrentLine:
    """A line of the order being built, addressed by its ``line`` number."""

    line: int
    item_id: str
    quantity: int
    option_ids: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class CarFields:
    parking_note: str | None = None
    plate: str | None = None
    model: str | None = None
    colour: str | None = None


# --- outputs ---------------------------------------------------------------------------------


class Language(StrEnum):
    AR = "ar"
    EN = "en"


class OrderIntent(StrEnum):
    ORDER_CHANGE = "order_change"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    UNCLEAR = "unclear"


class ReplyIntent(StrEnum):
    CONFIRM = "confirm"
    EDIT = "edit"
    CANCEL = "cancel"
    UNCLEAR = "unclear"


class ReplyField(StrEnum):
    ITEMS = "items"
    CAR = "car"
    NOTE = "note"


class ActionType(StrEnum):
    ADD = "add"
    REMOVE = "remove"
    SET_QUANTITY = "set_quantity"
    SET_OPTIONS = "set_options"
    SET_NOTE = "set_note"
    CLEAR = "clear"


class QuestionKind(StrEnum):
    CHOOSE_ITEM = "choose_item"
    CHOOSE_OPTION = "choose_option"


class _Output(BaseModel):
    # An unknown field is a provider that did not follow the schema.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _a_null_list_is_an_empty_list(cls, data: Any) -> Any:
        """Providers answer ``null`` for a list they have nothing to put in."""
        if not isinstance(data, dict):
            return data
        lists = {
            name
            for name, info in cls.model_fields.items()
            if get_origin(info.annotation) is list
        }
        return {
            key: ([] if value is None and key in lists else value)
            for key, value in data.items()
        }


class OrderAction(_Output):
    type: ActionType
    item_id: str | None = Field(default=None, max_length=64)
    line: int | None = Field(default=None, ge=1, le=limits.MAX_LINES)
    quantity: int | None = Field(default=None, ge=1, le=limits.MAX_QUANTITY)
    option_ids: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=limits.MAX_NOTE_CHARS)

    @model_validator(mode="after")
    def _has_what_its_type_needs(self) -> OrderAction:
        if self.type is ActionType.ADD:
            if not self.item_id:
                raise ValueError("add needs item_id")
        elif self.type is not ActionType.CLEAR and self.line is None:
            raise ValueError(f"{self.type.value} needs line")
        if self.type is ActionType.SET_QUANTITY and self.quantity is None:
            raise ValueError("set_quantity needs quantity")
        return self


class OrderQuestion(_Output):
    kind: QuestionKind
    mention: str | None = Field(default=None, max_length=limits.MAX_TEXT_FIELD_CHARS)
    item_ids: list[str] = Field(default_factory=list, max_length=10)
    line: int | None = Field(default=None, ge=1, le=limits.MAX_LINES)
    group_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _has_what_its_kind_needs(self) -> OrderQuestion:
        if self.kind is QuestionKind.CHOOSE_ITEM and len(self.item_ids) < 2:
            raise ValueError("choose_item needs at least two item_ids")
        if self.kind is QuestionKind.CHOOSE_OPTION and (
            self.line is None or not self.group_id
        ):
            raise ValueError("choose_option needs line and group_id")
        return self


class ParseOrderResult(_Output):
    transcript: str | None = Field(default=None, max_length=limits.MAX_TEXT_CHARS * 2)
    language: Language
    intent: OrderIntent
    actions: list[OrderAction] = Field(
        default_factory=list, max_length=limits.MAX_ACTIONS
    )
    questions: list[OrderQuestion] = Field(default_factory=list, max_length=5)
    unmatched: list[str] = Field(default_factory=list, max_length=limits.MAX_UNMATCHED)

    @model_validator(mode="after")
    def _confirm_has_no_actions(self) -> ParseOrderResult:
        # "confirm" is only for a clear yes to the current summary; with actions it is a change.
        if self.intent is OrderIntent.CONFIRM and self.actions:
            raise ValueError("confirm cannot come with actions")
        return self


class ClassifyReplyResult(_Output):
    transcript: str | None = Field(default=None, max_length=limits.MAX_TEXT_CHARS * 2)
    language: Language | None = None
    intent: ReplyIntent
    field: ReplyField | None = None


class CarDetailsResult(_Output):
    transcript: str | None = Field(default=None, max_length=limits.MAX_TEXT_CHARS * 2)
    language: Language | None = None
    parking_note: str | None = Field(
        default=None, max_length=limits.MAX_TEXT_FIELD_CHARS
    )
    plate: str | None = Field(default=None, max_length=limits.MAX_TEXT_FIELD_CHARS)
    model: str | None = Field(default=None, max_length=limits.MAX_TEXT_FIELD_CHARS)
    colour: str | None = Field(default=None, max_length=limits.MAX_TEXT_FIELD_CHARS)


class TranscribeResult(_Output):
    transcript: str | None = Field(default=None, max_length=limits.MAX_TEXT_CHARS * 2)
    language: Language | None = None


# --- what an adapter returns ------------------------------------------------------------------

_T = TypeVar("_T", bound=BaseModel)


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Completion(Generic[_T]):  # noqa: UP046
    """A validated result with what the call cost, so the layer can log it."""

    value: _T
    model: str = ""
    usage: Usage = field(default_factory=Usage)


JsonObject = dict[str, Any]
