# ADR 0027: The optional Ready step

- Status: accepted
- Date: 2026-11-27

## Context

After the restaurant accepts an order, staff prepare it and bring it to the car. Until now the customer heard nothing between
"accepted, ready in about 10 minutes" and the order arriving. The state table already listed `accepted` to `ready` as an optional
step for the last milestone, and the order has a `ready_at` column and a `ready` status. The owner asked for it on 2026-11-27 if it
helps the project.

## Decision

- **One endpoint:** `POST /staff/orders/{id}/ready`, no body, needs `orders.decide`, answers `200` with the updated `StaffOrder`.
  It is `mark_order_ready` in `orders/services.py`: the order is locked, must be `accepted` (a placed, rejected or already ready
  order is `409 order_invalid_transition`), gets `status = ready` and `ready_at`, and one `OrderEvent` records the two states and the
  member. An order of another restaurant or an unknown id is `404`. `updated_at` moves like every other change, so the screens find
  the order through the polling list.
- **The customer is told in the same transaction**, by a `result` message with `status: ready` and a sentence in the
  conversation's language ("Your order #7 is ready. We are bringing it to your car."). Its payload holds only `order_id`, `number`
  and `status`: `eta_minutes` and the rejection fields belong to the other two answers. The shape needs no new message kind.
- **`ready_at` joins `StaffOrder`** as a nullable timestamp (null until the order is ready). The customer's own order keeps its shape:
  its `status` reads `ready`.
- **Existing clients keep working.** `status` and `result` are already extensible lists in the contract, the customer app shows an
  unknown status with the message's own text, and the restaurant app can ignore the new endpoint until it adds the button.
- **Not built:** the later steps of the table (`delivered`, `not_found`, `no_show`) and any alert or push for the customer.

## Consequences

- The restaurant app gets a third button on an accepted order and the customer app a third card; both are optional.
- A ready order cannot be rejected or accepted again (the existing `409`).
- Adding `delivered` later follows the same pattern: one function, one endpoint, one text, one payload with the status.
