"""The HTTP errors of the chat endpoints, each with the stable ``code`` the apps branch on.

Only what the contract calls an error is here. A missing or invalid answer inside the chat (an
item that is not on the menu, a car colour, a voice clip nobody could understand) is never an
HTTP error: the bot answers it in the conversation.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class _Coded(APIException):  # type: ignore[misc]
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail=detail or self.default_detail, code=self.default_code)


class InvalidActionForState(_Coded):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invalid_action_for_state"
    default_detail = "This action is not allowed at this step of the conversation."


class ConversationExpired(_Coded):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conversation_expired"
    default_detail = "This conversation has expired. Start a new one."


class UnsupportedOrderType(_Coded):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "unsupported_order_type"
    default_detail = "This order type is not available yet."
