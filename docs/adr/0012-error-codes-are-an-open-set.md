# ADR 0012: Error codes are an open set

- Status: accepted
- Date: 2026-11-11

## Context

Every error response has one body, `{"type", "errors": [{"code", "detail", "attr"}]}`, and the apps branch on `code`. The
codes of one HTTP status (`409`, `429`, ...) are one list shared by every operation that can answer that status, so the
contract stays small and a generated client has one error model.

Each feature adds codes. The customer accounts added `account_exists`, `contact_already_set`, `no_pending_contact`
(`409`), `account_not_verified` (`403`) and `too_many_attempts` (`429`). Declared as a closed `enum`, every new code
changed the response contract of every operation that shares the list, so the contract check (oasdiff) failed with
`response-property-enum-value-added` on endpoints that cannot even return the code. A generated client with a closed enum
would also throw on a code it does not know.

## Decision

- Every `ErrorCode<status>Enum` in the schema is declared `x-extensible-enum`, by a post-processing hook
  (`config/openapi_hooks.py`). The description still lists every code with its label.
- A client treats an unknown code as a generic failure of its HTTP status. A generated client reads the code as a string.
- Adding a code is not a breaking change. Removing or renaming a code, or changing the status it comes with, still is, and
  needs the `breaking change` label.
- Other enums (a language, a channel, an order status, a reject reason) stay closed: their values are part of the
  behaviour, not a growing list of failures.

## Consequences

- The switch from closed to extensible is itself flagged once by the contract check (`response-property-became-not-enum`),
  because the base still has closed lists. The pull request that introduces it carries the `breaking change` label, which
  is the owner's approval; before the first release nothing is pinned to it.
- After that, a new error code needs no label and no frontend release.
- The apps must not exhaustively switch over error codes without a default branch.
