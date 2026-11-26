# Architecture decision records

One short file per decision that is costly to change later. Each states the context, the decision and its
consequences. A decision that changes gets a new record that supersedes the old one; the old file stays and its status
says so.

The product and the API contract are described in `docs/project-overview.md` and `openapi/schema.yaml`. These records
explain **why** the code is the way it is, so a new developer or the frontend team does not have to ask.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-one-account-table.md) | One account table for everybody, with a username, an email or a phone number | accepted |
| [0002](0002-roles-permissions-and-tenancy.md) | Roles, permission codes and restaurant isolation | accepted |
| [0003](0003-environments-and-deploys.md) | Staging from `develop`, production from `main`, deploys by hand | accepted |
| [0004](0004-no-demo-mode-and-no-seed.md) | No demo mode and no seed: data is entered in the Django admin | accepted |
| [0005](0005-images-on-cloudflare-r2.md) | Images on Cloudflare R2, static files on WhiteNoise | accepted, built |
| [0006](0006-customer-accounts-and-messaging-outbox.md) | Customer accounts with a verification code, and the messaging outbox | accepted, built |
| [0007](0007-api-shape-conventions.md) | API shape: polling lists, paths without a trailing slash, public endpoints | accepted |
| [0008](0008-public-visibility-and-flags.md) | What a customer can see: `is_open`, suspended restaurants and `ai_enabled` | accepted |
| [0009](0009-api-hardening-and-outbox-hygiene.md) | API hardening baseline (request id, no-store, body cap) and outbox hygiene | accepted |
| [0010](0010-the-assistant-layer.md) | The assistant layer: one adapter interface, validated outputs, no content in logs | accepted |
| [0011](0011-customer-accounts-flow.md) | The customer-account flow: codes, limits, what an answer reveals | accepted |
| [0012](0012-error-codes-are-an-open-set.md) | Error codes are an open set: extensible lists, not closed enums | accepted |
| [0013](0013-django-admin-appearance.md) | How the Django admin looks: built-in polish now, a third-party theme later (options and costs) | accepted |
| [0014](0014-optional-arabic-names.md) | Arabic names are optional, the English text stands in when they are empty | accepted, built |
| [0015](0015-service-distance-replaces-the-parking-lot.md) | A restaurant's service distance replaces the parking lot (changes the range rule of 0008) | accepted, built |
| [0016](0016-nested-menu-categories.md) | Menu categories can nest, up to three levels (category, subcategory, sub-subcategory) | accepted, built |
| [0017](0017-order-type-and-the-phone-check.md) | The order type on conversations and orders, and the phone check before the first order (a setting, off on staging until the pilot) | accepted, model and gate built |
| [0018](0018-placing-an-order.md) | How an order is priced and placed: what the server checks, the order of the steps, and what never refuses an order | accepted, built |
| [0019](0019-the-conversation-engine.md) | How the conversation engine runs a turn: one transaction per input, replays, the assistant proposes and the server decides, errors only for state | accepted, ordering step built |
| [0020](0020-groq-is-the-main-assistant-provider.md) | Groq is the main assistant provider (Whisper and a text model, numbered keys used in order), Gemini the second; how limits are counted | accepted, built |
| [0021](0021-voice-is-read-in-memory-and-never-stored.md) | A voice clip is read in memory and never stored: the voice endpoint, WAV only for now, and what happens when it cannot be understood | accepted, built |
| [0022](0022-the-car-the-note-the-review-and-placing.md) | The car, the note, the review and placing the order: merge-only answers, the review edit paths, the phone check as a rolled-back 403, the position and the customer's order; addendum: the car question one item at a time while the assistant is down | accepted, built |
| [0023](0023-image-folders-follow-the-admin.md) | Uploaded images go to one folder per restaurant laid out like the admin, in lowercase kebab case, with a picture for every menu category level | accepted, built |
| [0024](0024-the-staff-sign-in.md) | The staff sign-in: a token only for an active member, one token per account, a refusal that never says which accounts exist, the temporary password and `GET /staff/me` | accepted, built |
| [0025](0025-the-order-state-machine-and-the-staff-orders-list.md) | The restaurant's answer to an order (accept or reject once, `409` otherwise, `updated_at` on every change) and the staff polling list with its overlap, the screen marked online and one `StaffOrder` shape | accepted, built (the endpoints and the result message come next) |

## Writing a record

Copy the shape of an existing one: status, date, context, decision, consequences. Keep it to what a reader needs; link
the code and the contract instead of repeating them. Do not put secrets, personal data or private account details in a
record. Add the new file to the table above in the same pull request as the change it explains.
