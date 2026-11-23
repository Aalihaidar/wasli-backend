# ADR 0022: The car, the note, the review and placing the order

- Status: accepted
- Date: 2026-11-24

## Context

After the order is confirmed, the chat asks for the car and the parking spot in one question, then for an optional note, shows
the whole order once more and sends it after a final confirmation. The customer answers in free text or by voice, the answers
must be checked by the server, an edit from the review must not make the customer repeat everything, and placing the order must
be exactly one transaction with the same guarantees as any other turn ([ADR 0019](0019-the-conversation-engine.md),
[ADR 0018](0018-placing-an-order.md)).

## Decision

- **The car (`ask_car`).** One question asks for the parking name and where the car is, the number, the model and the colour. The
  assistant only sorts the answer into the four fields (`extract_car_details`); the server merges it, changing only what the
  customer mentioned, and checks each field with `orders/car.py` (a value that does not meet the rules counts as missing). The bot
  then asks only for what is missing ("Thank you. I still need the car number, the car model."), and says it did not catch an
  answer that held nothing. When all four are valid the conversation moves to the note. A spoken answer works the same way and
  keeps its transcript on the customer's message.
- **The note (`ask_note`).** Stored as typed (spaces collapsed, at most 300 characters; longer is asked again in the chat) and
  never read by the assistant. A spoken note is transcribed and then handled as text. Skip means no note.
- **The review (`review`).** A `review` message carries the summary with prices, the four car values, the note, whether the
  position was shared and where it came from (`gps` or `simulated`), never the coordinates, and the buttons Yes, send and Edit.
  Edit offers Order, Car and parking and Note (`edit_field`). A free-text or spoken reply is classified (`classify_reply`) as a
  yes (places the order), an edit (with the part when the customer said which), a cancel (clears the order, the car and the note
  and goes back to `ordering`) or unclear (asked again with the buttons). A reply that already holds a change to the car ("make
  the colour black") is read as the answer, so the customer does not say it twice (two assistant calls, the most the spec
  allows); for the order and the note the part is opened and the customer says the change.
- **Editing from the review** sets `return_to_review`: a changed order returns to the review at its next Confirm, a car edit
  shows the four current values and merges only the change, a note edit shows the note and the answer replaces it (Keep leaves
  it). Nothing changed is said ("I did not catch a change") and asked again.
- **Placing.** The final confirmation (the button, or a clear yes) calls the order service in the same transaction as the turn.
  The phone check is the first thing it does: a customer who must verify a phone gets `403 phone_not_verified`, and because the
  turn is one transaction the customer's message, the state and the order number are all rolled back, so nothing is stored and a
  retry starts clean. Other refusals are answered in the chat: an item or option that is gone sends the customer back to the
  order (and tells them what), incomplete car details back to the car question, a position outside the service distance (only
  with `LOCATION_CHECK=enforce`) a message and the review again, a restaurant that stopped taking orders a message. On success
  the bot says "Your order #N was sent" and the conversation carries `order` (`id`, `number`, `status`), absent until then
  (never `null`; `core.serializers.OmitWhenNone`).
- **The position.** `PUT /conversations/{id}/location` (`lat`, `lng`, optional `accuracy_m`, `source` `gps` or `simulated`) keeps
  the latest position on the conversation in any open step and answers `204`. Out of range is `400 invalid_location`; a placed
  or expired conversation is `409`. It is copied to the order at the final confirmation and is never sent back to the app, logged
  or given to the assistant.
- **The order for the customer.** `GET /orders/{id}` shows only the customer's own order (a `404` for anyone else): number,
  `status`, `order_type`, `placed_at`, the wait or the rejection reason and note, and the totals. It never shows the car or the
  position. The order `status` is an `x-extensible-enum` like the other lists that grow.
- **What each step takes.** Text and voice are taken in every open step; the buttons per step are: ordering (`confirm`, `edit`,
  `choose`, `set_lines`), the car (none), the note (`skip_note`), the review (`confirm`, `edit`, `edit_field`); `set_locale`
  and `restart` work everywhere and repeat the current question. Anything else is `409 invalid_action_for_state`.
- **Voice limit.** A clip may now be 60 seconds (5 MB); an order is about 10 seconds, so the limit is generous on purpose.
- **Code layout.** The old engine file is split: `chat/engine.py` runs a turn and holds the public functions, `chat/ordering.py` the
  ordering step, `chat/steps.py` the car, the note, the review and placing, `chat/reconcile.py` the checking of the order against
  the menu, `chat/replies.py` the button and the bot message.

## Consequences

- While the assistant is down the car question cannot be read: the bot says it cannot read the answer right now (the buttons and
  the item picker still work). The four questions asked one at a time are the fallback still to build.
- A customer who edits the car by voice may cost three assistant calls in a turn (the clip classified, then read for the car);
  the budget and the per-key limits count them.
- The review and the placed message are plain bot messages; the staff's answer (`result`) comes with the staff endpoints.
