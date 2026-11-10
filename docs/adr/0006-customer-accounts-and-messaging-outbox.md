# ADR 0006: Customer accounts with a verification code, and the messaging outbox

- Status: accepted; the outbox and the account endpoints are built (the flow is in [ADR 0011](0011-customer-accounts-flow.md))
- Date: 2026-11-07

## Context

Customers order from their cars and a restaurant needs to trust that an order comes from a real person. The anonymous
customer session of the first plan is gone. A verification code has to be readable somewhere on local and staging
before a real email or SMS provider exists.

## Decision

- Customers always sign up with a name, an email or a phone number and a password, then verify a six-digit code sent to
  that contact (valid 10 minutes, five attempts, a limited resend). The token is returned once, by the verification and by
  sign-in. The exact endpoint shapes are agreed in an API request issue before they are built.
- Every outgoing email or SMS goes through `messaging.services.send_message`; no view calls a provider directly. The
  backend is chosen by `MESSAGING_BACKEND`.
- The `outbox` backend stores the message in `messaging.OutboxMessage`, shown read-only in the Django admin, so the
  owner reads the code there. Because the stored body holds the plain code, the backend refuses to be created when
  `ENVIRONMENT` is `production`.
- Production will send email with Resend and SMS with a provider chosen later. Both wait for a domain.

## Consequences

- No customer can sign up on production until its messaging backends exist; production stays closed until the pilot.
- The refusal happens when the backend is created, at the first send, and not when the process starts, so production can be
  deployed closed before a real backend exists. A start-up system check is a possible tightening.
- Whether a customer who signed up with an email must also verify a phone number before the first order is still open.
