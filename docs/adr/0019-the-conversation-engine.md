# ADR 0019: How the conversation engine runs a turn

- Status: accepted
- Date: 2026-11-22

## Context

The customer's chat is where an order is built. The assistant can only understand what was said; the backend must decide
what happens next, write every word the customer reads, and stay correct when the app retries a request, two taps arrive
together, or the assistant is slow or down. The contract with the customer app is in the API request issue for the chat
endpoints, and the steps after the order summary (car, note, review, placing) are built in later pull requests.

## Decision

- **One input is one turn, in one transaction** (`chat/engine.py`). The turn locks the conversation row, stores the
  customer's message, decides, updates the conversation and writes the bot's replies. Two taps at once take turns, and a
  failure leaves no half-written conversation. The assistant call happens inside the turn, so a conversation is served one
  message at a time, which is what a chat needs; the wait is bounded by `AI_TIMEOUT_SECONDS`.
- **A retry never runs twice.** Every message carries a `client_message_id`; a repeat returns what the first request
  produced (the customer's message and the replies up to the customer's next message), with the same `201`, and does not
  call the assistant again.
- **A button is a message too.** A tap is stored as a customer message holding the label of the button (and the action in
  its payload), so the history reads like a conversation and a tap can be replayed.
- **All text comes from `chat/texts.py`**, in the conversation's language, filled with names that are data and never
  templates. The assistant never writes a reply and never sees a price. Every price in the summary comes from the order
  service (`orders/pricing.py`).
- **The assistant proposes, the server decides.** Item ids from the assistant are checked against the items this
  restaurant shows; an unknown or other restaurant's id is dropped. Lines are renumbered after every change so the numbers
  the customer sees and the numbers the assistant addresses are the same. Repairs happen without asking when they can: a
  finished item or option is dropped and reported, a note that is too long is cut. A required option the customer did not
  choose is asked as a question with buttons, derived from the lines themselves (the assistant's own option questions are
  ignored); a question about which of several items was meant is taken from the assistant when its ids are on the menu.
  At most one question is open at a time.
- **A missing or unreadable answer is not an HTTP error.** Something the bot cannot use is answered in the chat. A
  provider failure (an error, a timeout, a rate limit) is answered in the chat and turns `ai_available` off for five
  minutes (`assistant/availability.py`, remembered in the cache, so per worker); a badly formed answer does not, because the
  provider is up. While it is off, typed orders are not sent and the app offers the item picker (`set_lines`), which uses
  the same checks.
- **Only a state-dependent action is an error.** An action that is not allowed at this step is `409
  invalid_action_for_state`, a conversation past its expiry is `409 conversation_expired`, another customer's conversation
  is `404`. A conversation that has moved past ordering takes only a language change and a restart until its own steps
  exist.
- **Extensible lists.** The message `kind`, the conversation `state` and the `order_type` are declared
  `x-extensible-enum` like the error codes ([ADR 0012](0012-error-codes-are-an-open-set.md)): the apps treat a value they
  do not know as unknown, so the next kind of message is not a breaking change.
- **Limits.** A text is at most 500 characters, counted as Unicode code points after trimming. Messages are throttled per
  customer (`chat_message`, 40 a minute) and opening a conversation more strictly (`chat_open`, 30 an hour); polling is not
  counted against the message limit.

## Consequences

- A slow provider holds a conversation's row lock and a database connection for up to the timeout. That is acceptable for
  one customer's chat on the free hosting; a queue is the answer if it ever is not.
- The five-minute window is per Gunicorn worker, so one worker may learn of an outage a little before another. The cost is
  one more customer waiting for one timeout.
- The newest conversation of a customer with a restaurant is returned while it is placed or has not expired. The older
  rule of three hours after placing is not applied, so "Order again" is always `start_new: true`.
