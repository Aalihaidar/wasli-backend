# ADR 0007: API shape conventions

- Status: accepted
- Date: 2026-11-10 (the polling exception was agreed on 2026-11-05)

## Context

Two apps generate their client from `openapi/schema.yaml`. Small differences between endpoints (a trailing slash, a
list that sometimes is not paginated) become special cases in every generated client.

## Decision

- Every list is paginated with one class (`core.pagination.StandardPagination`), except the three polling lists
  (`GET /restaurants/nearby`, `GET /conversations/{id}/messages?after_seq=` and `GET /staff/orders?since=`), which keep
  the shapes in the contract because the sites call them every few seconds.
- Paths have no trailing slash: `/api/v1/config`, `/api/v1/restaurants/{slug}`. A request with one is a `404`.
- The public endpoints (`config`, `restaurants/nearby`, `restaurants/{slug}`) read no token, so a stale token never
  turns a public call into a `401`.
- Every error raised in a view has the one body of `drf-standardized-errors`; clients branch on `code`, never on
  `detail`.
- Money is an integer in minor units named `*_minor`; the API never sends formatted prices. Times are UTC ISO 8601.
- A customer's position is never written to a log. The nearby search reads it from the query string, so no request log
  may record a query string: the request log of Django records only the path, and the production entrypoint gives
  Gunicorn an access-log format that prints the path (`%(U)s`) and never the full request line.

## Consequences

- A `/` typed after a path is not redirected for any method, so the apps must call the exact path.
- The Swagger page and the committed schema describe the same operations; the schema is regenerated in the same pull
  request as the endpoint.
