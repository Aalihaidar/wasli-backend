"""The restaurant's answer to an order, posted into the customer's chat.

The message is a bot message of kind ``result``. Its text is written here in the conversation's
language; its ``payload`` is what the app reads: ``order_id``, ``number`` and ``status`` always,
``eta_minutes`` only when accepted, ``rejection_reason_code`` and ``rejection_note`` only when
rejected, nothing more when the order is ready. A property that does not apply is absent, never ``null``, and the note is absent when
the restaurant gave none.
"""

from typing import Any

from orders.models import Order, OrderStatus, RejectionReason

from .models import Message, MessageKind, Sender
from .services import add_message
from .texts import say


def post_order_result(order: Order) -> Message:
    """Add the ``result`` message for an order that was just accepted, rejected or made ready.

    Call it inside the transaction that changed the order, so the customer never sees a
    decision without its message or the other way round."""
    conversation = order.conversation
    locale = conversation.locale
    payload: dict[str, Any] = {
        "order_id": str(order.pk),
        "number": order.number,
        "status": order.status,
    }
    if order.status == OrderStatus.READY:
        text = say("result_ready", locale, number=order.number)
    elif order.status == OrderStatus.ACCEPTED:
        payload["eta_minutes"] = order.eta_minutes
        text = say(
            "result_accepted", locale, number=order.number, minutes=order.eta_minutes
        )
    else:
        payload["rejection_reason_code"] = order.rejection_reason_code
        reason = say(f"reject_{order.rejection_reason_code}", locale)
        if order.rejection_note:
            payload["rejection_note"] = order.rejection_note
            reason = f"{reason} {order.rejection_note}"
        elif order.rejection_reason_code == RejectionReason.OTHER:
            reason = ""
        text = say(
            "result_rejected", locale, number=order.number, reason=reason
        ).strip()
    return add_message(
        conversation, Sender.BOT, MessageKind.RESULT, text=text, payload=payload
    )
