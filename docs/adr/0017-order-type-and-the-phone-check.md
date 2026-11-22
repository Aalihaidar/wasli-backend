# ADR 0017: The order type and the phone check before the first order

- Status: accepted
- Date: 2026-11-21

## Context

Two contract changes were agreed with the customer app and the restaurant app on 2026-11-14 (API request issue #52) and
have to be in place before the conversation endpoints freeze:

- an **order type** (`car`, `dine_in`, `delivery`), because the product will serve more than cars later and a field added
  after the apps are released is a breaking change;
- a **phone check**: a customer who signed up with an email must verify a phone number before the first order (owner,
  2026-11-12).

The owner also wants to test the whole flow from the customer app on staging first (sign-up, chat, order, car details,
location, final confirmation). On staging there is no SMS provider: a phone code lands in the messaging outbox, which the
owner reads in the Django admin and hands to the tester.

## Decision

- **Order type.** `Conversation.order_type` and `Order.order_type` hold `car`, `dine_in` or `delivery`, default `car`. The
  order's earlier field `fulfilment_type` was renamed to `order_type` (a rename migration, no data change) so the database
  and the contract use one name. The API accepts only `car` for now: any other value is `400 unsupported_order_type`
  (`core.order_types.SUPPORTED_ORDER_TYPES`). In the contract it is a string declared `x-extensible-enum`, so adding a value
  later is not a breaking change.
- **Phone check.** `customers.services.ensure_phone_verified_for_order(customer)` raises `403 phone_not_verified` when the
  setting `REQUIRE_VERIFIED_PHONE` is on and the customer's phone is not verified. The order service calls it at the final
  confirmation (the `confirm` action in the `review` state). It changes nothing and stores nothing, so a retry with the same
  `client_message_id` is refused again, or goes through once the phone is verified. The customer adds the phone with the
  existing `POST /customers/me/contact` and `POST /customers/me/contact/verify`; no new endpoint.
- **The setting** `REQUIRE_VERIFIED_PHONE` is `false` in the code, so local development and the tests need no phone code.
  The owner decided on 2026-11-22 to turn it **on for staging** (a Render variable) for the pilot, and it is on in
  production. Where it is on, the owner reads the phone code in the messaging outbox in the admin and gives it to the
  person testing, until an SMS provider exists. The code path and the error code exist and are tested, so the apps can
  build the phone step against the real contract.

## Consequences

- The rule is one setting, not a separate code path: staging and production run the same code (ADR 0003).
- With the setting on, an email-only customer cannot place an order until a phone is verified, and every phone code is
  read in the admin outbox by the owner (the outbox keeps a message 24 hours, a code is valid 10 minutes). A tester can
  use a made-up number in international format, because the owner reads the code, not the phone.
- Production must have the setting on and a real SMS backend before the first real customer (`docs/steps.md`, section 14).
- `unsupported_order_type` and the `order_type` request field come with the conversation endpoint; this record covers the
  model, the error code and the gate.
- A restaurant that serves only some order types (`order_types` per restaurant) is a later decision.
