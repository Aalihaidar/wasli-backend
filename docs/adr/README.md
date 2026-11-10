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
| [0005](0005-images-on-cloudflare-r2.md) | Images on Cloudflare R2, static files on WhiteNoise | accepted, not built yet |
| [0006](0006-customer-accounts-and-messaging-outbox.md) | Customer accounts with a verification code, and the messaging outbox | accepted, outbox built |
| [0007](0007-api-shape-conventions.md) | API shape: polling lists, paths without a trailing slash, public endpoints | accepted |
| [0008](0008-public-visibility-and-flags.md) | What a customer can see: `is_open`, suspended restaurants and `ai_enabled` | accepted |
| [0009](0009-api-hardening-and-outbox-hygiene.md) | API hardening baseline (request id, no-store, body cap) and outbox hygiene | accepted |

## Writing a record

Copy the shape of an existing one: status, date, context, decision, consequences. Keep it to what a reader needs; link
the code and the contract instead of repeating them. Do not put secrets, personal data or private account details in a
record. Add the new file to the table above in the same pull request as the change it explains.
