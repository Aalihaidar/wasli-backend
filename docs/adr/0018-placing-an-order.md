# ADR 0018: How an order is priced and placed

- Status: accepted
- Date: 2026-11-22

## Context

The conversation engine proposes order lines from what a customer typed or said, and the customer confirms them. Neither
the assistant nor the app can be trusted with a price or with what exists on the menu, and an order is created at the
moment of the final confirmation, so the rules for what is accepted have to live in one place with tests.

## Decision

- **The server prices every order from the database** (`orders/pricing.py`). A line is an item id, a quantity, option ids
  and a note, never a price. An item must belong to this restaurant, be available and sit in a visible category (a hidden
  category hides its branch, [ADR 0016](0016-nested-menu-categories.md)). A quantity is 1 to 20, a note at most 200
  characters, an order at most 20 lines. The unit price is the item's price plus the price change of every chosen option; it
  may not end below zero. Prices include VAT, so the total equals the subtotal.
- **Option rules.** A chosen option must belong to the item and be available, and each group gets between `min_select` and
  `max_select` choices. A required group the customer did not mention is filled with its default options; if it still has
  too few or too many, the bot asks. A required group whose only choice was named but is finished is not silently replaced
  by the default.
- **Problems are data, not text.** The service raises an `OrderError` with a list of coded problems and the line, item,
  option or group each belongs to, all at once. The engine turns them into a bot message in the conversation's language.
  The service never writes text for a customer.
- **Placing is one transaction** (`orders/services.py`). The phone check comes first, before any read or write, so a refusal
  leaves nothing behind. Then the conversation and the restaurant row are locked and everything is checked again: the
  conversation is in the review state, has not expired, has no order yet and has a supported order type; the lines price;
  the four car details are valid. The order takes the next number of the restaurant, keeps copies of the lines (names, the
  Arabic name falling back to the English one, prices, options), the car, the note, the position and the distance to the
  restaurant, writes the first event, saves the car for the customer's next conversation and marks the conversation placed.
  Any problem rolls everything back, including the order number.
- **The service distance never refuses an order by default.** `LOCATION_CHECK` `warn` and `off` only record the distance.
  With `enforce`, an order is refused when the restaurant sets a service distance and the customer is farther than it. An
  order without a position, and a restaurant with no service distance, are never refused for their distance (assumption
  of mine, to confirm before `enforce` is switched on in the pilot).
- **Not in this record:** blocked customers (the platform-wide ban and the restaurant's blocks), the order state machine
  (accept, reject), and the HTTP error codes. They come with the staff endpoints and the conversation endpoints.

## Consequences

- The engine and the endpoints call one function and show the result; there is no second path that creates an order.
- Every rule above has a test, and a rule that changes is changed here and in the tests together.
- The engine must add its bot message inside the same transaction, so a failure there also leaves no order.
