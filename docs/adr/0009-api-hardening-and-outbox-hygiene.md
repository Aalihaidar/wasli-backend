# ADR 0009: API hardening baseline and outbox hygiene

- Status: accepted
- Date: 2026-11-10

## Context

Every endpoint that follows (the chat, the voice upload, the staff orders with a customer's car and position) would
inherit the same gaps: no way to match a failure the app shows to a log line, answers that a browser or a proxy may
keep, no cap on the size of a request body, and an access log that prints the full request line. The nearby search
carries the customer's position in its query string, so that last gap would have put positions in the logs. Separately,
the messaging outbox stores plain verification codes, and nothing deleted them or stopped it from running in production.

A review of a sibling project's baseline (a public repository of the owner's) showed a small, tested way to close the
first three; this record adopts the parts that fit.

## Decision

**Request id.** Every response under `/api/v1/` carries `X-Request-ID`, errors included. A client may send its own; it is
kept only when it is 8 to 64 letters, digits or hyphens, otherwise a UUID is generated, so a client cannot put its own text
into a log line. The id is in every log line (`[{request_id}]`), and browser apps may read and send it (CORS). It holds no
personal data.

**No-store.** Every response under `/api/v1/` sends `Cache-Control: no-store`, success and error alike. It is a
middleware, so a response that never reaches a view has it too.

**Body size.** A request body over `REQUEST_BODY_MAX_BYTES` (64 KB) is refused with `400 request_too_large` before any view
reads it. A path may have its own limit in `REQUEST_BODY_LIMITS`: a voice upload (`/conversations/{id}/voice`) may be 6 MB
(one clip of at most 5 MB plus the multipart framing) and a larger one is `400 audio_too_large`, the code the contract
already has. The check is on `Content-Length`. The CORS headers are added before it, so a browser app can read the error.

**Access log.** The production entrypoint gives Gunicorn an access-log format with the method, the path (`%(U)s`, never the
query string), the status, the size, the time in milliseconds and the request id the API sends back. A `GUNICORN_CMD_ARGS`
set on the platform replaces it, so it is not set on Render.

**Outbox hygiene.**

- Outbox messages are deleted after `OUTBOX_RETENTION_HOURS` (24). Every send deletes the older ones, because no scheduler
  runs on the free staging service; `python manage.py purge_outbox` does it on demand.
- `MESSAGING_BACKEND` has a second value, `disabled`, which sends nothing and fails on every send. Production uses it until
  Resend and an SMS provider exist.
- A system check, `messaging.E001`, fails (`manage.py check`, `migrate`, the deploy check) when `ENVIRONMENT=production` and
  the backend is the outbox. This tightens ADR 0006: the refusal no longer waits for the first send.

## Consequences

- `wasli-production` must set `ENVIRONMENT=production` and `MESSAGING_BACKEND=disabled`, or it does not start.
- The apps cannot cache API answers through HTTP and must send audio no larger than the cap.
- `request_too_large` is a new error code in the contract; the other additions are headers.
- A verification code is readable in the staging admin for at most a day.
- Per-user rate limits (the reference also has them) are left for the throttling step of D3.
