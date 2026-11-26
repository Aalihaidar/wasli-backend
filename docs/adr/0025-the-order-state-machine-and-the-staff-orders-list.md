# ADR 0025: The restaurant's answer to an order and the staff orders list

- Status: accepted
- Date: 2026-11-25

## Context

The restaurant screen polls for new orders and answers each one: accept with a wait of 5, 10 or 15 minutes, or reject with one of
six reasons. The shapes were agreed with the restaurant app in the API request #94 (its Rounds 2 to 4). This record covers the
second slice: the state machine and the list. The endpoints that call the state machine, and the `result` message the customer
receives, are the third slice.

## Decision

- **A placed order is answered once.** `accept_order` and `reject_order` (`orders/services.py`) lock the order row
  (`select_for_update`), require `status == placed` and write the new fields and one `OrderEvent` (`actor_type=staff`, the
  member's user id) in one transaction. Any other state is `409 order_invalid_transition` (`OrderInvalidTransition`), so two screens
  answering together are serialised and the second one learns the real state. An order of another restaurant, or an unknown id, is
  `404`, never `403`. A wrong wait, an unknown reason, a missing note for `other` and a note over 200 characters are `400` field
  errors checked before the order is read.
- **`updated_at` moves on every change** because the fields are saved with `save(update_fields=[..., "updated_at"])`, never with
  `update()` (which would skip `auto_now`). The screens find a changed order by it. The timestamps keep microseconds.
- **The list** is `GET /staff/orders?since=` (`orders/staff_views.py`), needs `orders.view` through `require_permission`, and is not
  paginated (a polling list, `docs/api-conventions.md`). It answers `{server_time, orders}`. `server_time` is taken before the read.
  The read starts `CHANGE_OVERLAP` (10 seconds) before `since`: a change is saved a moment before it is committed, so one that commits
  just after the last `server_time` could carry an earlier `updated_at` and never be sent. The price is that an order can arrive
  again with the same `updated_at`; the app merges by id and keeps the latest. Without `since` the window is the last 24 hours. A
  `since` that is not a timestamp or lies in the future is `400 invalid_since`.
- **Every successful call marks the restaurant's screen online** (`restaurants.services.mark_screen_online`: one column written with
  `update()`, so nothing else of the restaurant, no `updated_at` and no signal, is touched every few seconds). A refused call (no
  token, no permission, a bad `since`) does not.
- **One `StaffOrder` shape** (`orders/staff_serializers.py`) serves the list, accept, reject and the later Ready step. `vehicle` and
  `parking_note` belong to a car order and `customer_location` exists only when the customer shared a position: each is absent,
  never `null`. `decided_at` is a property (`accepted_at` or `rejected_at`), not a column. No customer name, email or phone is
  returned. Item and option names come in both languages (the order's own copy).
- **Lists that grow are extensible.** `status`, `order_type` and `distance_band` are named `x-extensible-enum` lists. The rejection
  reason and `customer_location.source` are declared **in place** as strings with `x-extensible-enum`: the first because a named
  enum with a nullable wrapper is read badly by the generated Dart client, the second because a named list for the staff location
  made the schema merge it with the customer's position request, whose own list is closed and has no `none` (a regression test
  keeps the two apart).
- **No `GET /staff/orders/{id}`.** After a conflict or a network failure the app polls with its last `server_time`; the changed order
  is in the answer.

## Consequences

- The list has no row limit: a restaurant that was offline for days and sends an old `since` gets every order changed since. The
  default window and a normal poll keep it small; a cap can be added if a real restaurant needs it.
- Marking the screen online writes one row every poll (about once every 3 seconds per open screen): negligible for a few
  restaurants, to be reviewed with the realtime work after the pilot.
- The overlap means a poll normally repeats the orders changed in the last 10 seconds.
- The rejection reason of the customer's own order (`GET /orders/{id}`) is still a plain string; it takes the same inline form with
  the `result` message in the next slice, after the customer app has checked it.
