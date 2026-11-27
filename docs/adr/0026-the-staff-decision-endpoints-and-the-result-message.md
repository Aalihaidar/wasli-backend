# ADR 0026: The staff decision endpoints and the result message

- Status: accepted
- Date: 2026-11-26

## Context

The restaurant screen answers a placed order, and the customer must see the answer in the same chat. The shapes were agreed with
the restaurant app (API request #94) and with the customer app (the `result` message). The state machine was built in
[ADR 0025](0025-the-order-state-machine-and-the-staff-orders-list.md); this record covers the endpoints that call it and the
message they post.

## Decision

- **Two endpoints** under `orders.decide`: `POST /staff/orders/{id}/accept` with `{eta_minutes}` and
  `POST /staff/orders/{id}/reject` with `{reason_code, note?}`. Both answer `200` with the updated `StaffOrder`, so the screen
  replaces the order it holds. An order of another restaurant, or an unknown id, is `404`; an order that is not waiting is
  `409 order_invalid_transition`; a wrong wait, reason or note is a `400` that names the field. The screen's per-account
  default throttle applies; no stricter scope is added because a screen answers a few orders an hour.
- **The decision and the message are one transaction.** `accept_order` and `reject_order` call `chat.result.post_order_result`
  inside the transaction that changes the order, so there is never a decision without its message or the other way round
  (a test makes the posting fail and checks that the order stays placed).
- **The message** is a bot message of kind `result`, written in the conversation's language (`chat/texts.py`, Arabic and
  English, a sentence per reason). Its `payload` is `order_id`, `number` and `status`; `eta_minutes` only when accepted;
  `rejection_reason_code` and, only when the restaurant wrote a note, `rejection_note` when rejected. A property that does not apply
  is absent, never `null`. There is no `reason_text`: the app shows the message's `text`.
- **The rejection reason is declared in place everywhere** as a string with `x-extensible-enum` (the answer, the customer's own
  order and the request), never as a named enum or a `$ref`, because the generated Dart client reads the named nullable form badly.
  The customer's `GET /orders/{id}` moves from a plain string to this form: no value changes, the list is now declared.
- The customer's `conversation.order.status` is read from the order, so it follows the decision with no extra step.

## Consequences

- A new rejection reason needs a text in `chat/texts.py` (a test would fail without it) and a value in the list; the apps treat an
  unknown code as unknown.
- The customer app learns of the answer by polling the messages, as for every other bot message; there is no push yet.
