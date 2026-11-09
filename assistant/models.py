from typing import ClassVar

from django.db import models

from core.models import BaseModel


class Purpose(models.TextChoices):
    PARSE_ORDER = "parse_order", "Parse an order"
    CLASSIFY_REPLY = "classify_reply", "Classify a reply"
    EXTRACT_CAR = "extract_car", "Extract the car details"
    TRANSCRIBE = "transcribe", "Transcribe a voice note"
    MENU_DRAFT = "menu_draft", "Draft a menu from photos"


class InputKind(models.TextChoices):
    TEXT = "text", "Text"
    AUDIO = "audio", "Audio"


class Outcome(models.TextChoices):
    OK = "ok", "OK"
    INVALID_OUTPUT = "invalid_output", "Invalid output"
    ERROR = "error", "Error"
    TIMEOUT = "timeout", "Timeout"
    RATE_LIMITED = "rate_limited", "Rate limited"
    BUDGET_EXCEEDED = "budget_exceeded", "Daily budget exceeded"


class AICallLog(BaseModel):
    """One call to the assistant provider: which provider and model, what for, how long it
    took and how it ended.

    It never holds what the customer wrote or said, what the provider answered, or any phone
    number or position: only the facts above. The daily budget guard counts these rows, so
    they are never deleted by hand (the admin has no delete).
    """

    # Empty for calls made outside a customer's conversation, such as the developer spike.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistant_calls",
    )
    # A test conversation can be deleted in the admin; its log rows stay.
    conversation = models.ForeignKey(
        "chat.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_calls",
    )
    provider = models.CharField(max_length=30)
    model = models.CharField(max_length=100, blank=True)
    purpose = models.CharField(max_length=20, choices=Purpose)
    input_kind = models.CharField(max_length=10, choices=InputKind)
    latency_ms = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome)
    # A short stable code for a failure, never the provider's message.
    error_code = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "assistant call"
        indexes: ClassVar[list[models.Index]] = [
            # The daily budget guard counts the day's calls.
            models.Index(fields=["created_at"], name="assistant_call_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.purpose} {self.outcome}"
