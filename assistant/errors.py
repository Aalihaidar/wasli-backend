"""How a call to a provider can fail, as short stable codes.

An error never carries the provider's message or anything the customer said or sent: the
message could echo it, and nothing of the content may reach a log (``AICallLog`` has no field
for it either).
"""

from django.core.exceptions import ImproperlyConfigured

from .models import Outcome


class AssistantError(Exception):
    """The provider could not understand the input. The conversation falls back to its
    no-assistant path (item picker, one car question at a time)."""

    outcome: str = Outcome.ERROR
    code: str = "provider_error"

    def __init__(self, code: str | None = None) -> None:
        self.code = code or type(self).code
        super().__init__(self.code)


class AssistantTimeout(AssistantError):
    outcome = Outcome.TIMEOUT
    code = "timeout"


class AssistantRateLimited(AssistantError):
    outcome = Outcome.RATE_LIMITED
    code = "rate_limited"


class AssistantBudgetExceeded(AssistantError):
    """The day's budget for this provider is used up; nothing was sent to it."""

    outcome = Outcome.BUDGET_EXCEEDED
    code = "budget_exceeded"


class AssistantInvalidOutput(AssistantError):
    outcome = Outcome.INVALID_OUTPUT
    code = "invalid_output"


class AssistantInputError(ValueError):
    """The input is over a cap (too long, too large, a type the provider does not take). The
    caller checks first and never sends it; this is a programming error, not a provider failure."""


class AssistantNotConfigured(ImproperlyConfigured):
    """The chosen provider is missing a setting."""
