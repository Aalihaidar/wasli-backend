# ADR 0001: One account table for everybody

- Status: accepted
- Date: 2026-11-05

## Context

Four kinds of people use Wasli: the platform team, restaurant admins, cashiers and customers. Separate account tables
would duplicate sign-in, password and token handling and make "one person is both" impossible to prevent in one place.
Customers want to sign in with what they remember (an email or a phone number); restaurant staff share a screen and
need short, typeable names.

## Decision

`users.User` is the only account table. It has three optional identifiers, `username`, `email` and `phone`, each unique
when set and stored as `NULL` when empty (never an empty string). A database check requires at least one.
`USERNAME_FIELD` is `username`.

- `username`: lower case, letters, digits, `.`, `_` and `-`, 3 to 30 characters, starting with a letter, so it can never
  look like a phone number or an email address.
- `email` is stored in lower case; `phone` in international format (default region AE) after normalisation.
- One authentication backend (`users/backends.py`) takes one value plus the password: a value with `@` is an email, a
  value that parses as a phone number is a phone, anything else is a username (case-insensitive).
- Every restaurant account (admin or cashier) has a username; the platform team signs in with an email.
- A `Customer` profile is linked one-to-one to a user. A user is staff or a customer, never both.

## Consequences

- The login endpoint keeps one `username` field that accepts any of the three values.
- Customers and staff use different token headers (`Authorization: Customer <token>` and `Authorization: Token <token>`),
  so a token of one kind never opens the endpoints of the other.
- Phone and email verification dates live on the user.
