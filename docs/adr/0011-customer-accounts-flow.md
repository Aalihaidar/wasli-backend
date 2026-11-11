# ADR 0011: The customer-account flow

- Status: accepted
- Date: 2026-11-10

## Context

[ADR 0006](0006-customer-accounts-and-messaging-outbox.md) decided that customers always sign up and verify a code.
Building it needs choices that are costly to change once two apps are built on the contract: what a code looks like and
how long it lives, what an answer may reveal about who has an account, and how an abandoned sign-up is recovered. The
owner agreed every proposal below on 2026-11-10, as both the backend and the frontend owner.

## Decision

**The endpoints** (all under `/api/v1/customers/`, no trailing slash): `signup`, `verify`, `resend-code`, `login`,
`logout`, `me`, `me/contact`, `me/contact/verify`, `password-reset` and `password-reset/confirm`. Their shapes are in
`openapi/schema.yaml`. Sign-up takes a name, **an email or a phone number**, a password and a language. Sign-in takes an
email or a phone number: a customer has no username.

**The code.** Six digits, valid 10 minutes, 5 wrong attempts, then the code is dead and a new one is needed. A new code
for the same purpose replaces the open one. A contact gets one code a minute and five an hour per purpose
(`429 throttled` with `Retry-After`). Only a keyed hash is stored (an HMAC with the secret key and the row's id), because a
plain hash of six digits falls in a second. The plain code exists only in the message that was sent, which is written in
the customer's language, and never in a log.

**What an answer reveals.**

- Signing up with the contact of a verified account is `409 account_exists`. This tells a visitor that the contact is
  registered; the agreed contract asks for it so the app can say "sign in instead", and the sign-up throttle limits how fast
  it can be probed.
- Everywhere else nothing is revealed: `verify` answers `code_invalid` for an unknown contact, `resend-code` and
  `password-reset` answer the same `202` whether or not an account exists and send nothing when none does, and the reset
  limits are counted per contact whether or not the account exists. A wrong password and an unknown contact give the same
  `401`; `account_not_verified` is shown only to someone who knows the password.

**A sign-up that was never verified** is restarted by signing up again with the same contact: the name, the password and the
language are replaced and a new code is sent. A contact whose account is verified, or that belongs to a staff or platform
account, is `account_exists`. This way an abandoned attempt never locks a person out of their own contact.

**Sessions.** The token is returned only by `verify` and `login` and sent as `Authorization: Customer <token>`. It has no
expiry in the first version; `logout` revokes that device's token, and a password reset revokes every token of the
customer. A blocked or deactivated customer is `403 permission_denied`.

**The added contact.** A customer adds the contact they lack (an email for a phone sign-up, a phone number for an email
sign-up). It is saved only after its own code is verified, and changing a contact the account already has is not offered
(`409 contact_already_set`).

**Passwords** follow Django's validators (at least 8 characters, not common, not entirely numeric, not like the contact or
the name); the codes of the refusal (`password_too_short` and so on) are the error `code`s. A weak new password at a reset
does not spend the code.

**Throttles.** Each public call has its own scope per client address (sign-up 10 an hour, verify 20 a minute, resend 20 an
hour, sign-in 10 a minute, reset 10 an hour, reset confirmation 10 a minute), and ten sign-in tries for one contact in 15
minutes are refused for that contact. They are counted in the process cache, so each worker counts for itself.

**Error codes added to the contract:** `account_exists`, `contact_already_set` and `no_pending_contact` (`409`),
`account_not_verified` (`403`), `too_many_attempts` (`429`), and `code_invalid` and `code_expired` (`400`).

## Consequences

- No customer can sign up on production until a real messaging backend exists: with `MESSAGING_BACKEND=disabled` a sign-up
  fails and saves nothing (the account is created and the message sent in one transaction).
- Whoever can read a contact's messages can take over an unverified sign-up for it; that is the nature of proving a contact by
  a code, and the code expires.
- Whether a customer who signed up with an email must also verify a phone number before the first order is still open.
- Per-worker counters allow a few more tries than the stated limits when several workers run; a shared cache would make
  them exact.
