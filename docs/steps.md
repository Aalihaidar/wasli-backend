# Project steps

The checklist of everything to do in this repository, from a fresh copy of the template to a project that is ready for its first endpoint (sections 1 to 8), then the Wasli milestones D0 to D4 and what comes after (sections 9 to 15). Tick a step (`- [x]`) as soon as it is done, in the same pull request that completes it. The detailed instructions behind each step are in the [README](../README.md) and in [`github-setup.md`](github-setup.md).

## 1. Repository and local environment

- [x] Create the repository from the template (default branch `develop`, `main` created by the Bootstrap main workflow)
- [x] Clone it and reopen it in the dev container
- [x] Set the remote `origin` to the project repository
- [x] Set the repository-local Git identity (`user.name`, `user.email`)
- [x] Check in Actions that **Bootstrap main** and **Labels** ran green, and that the labels from `.github/labels.yml` exist
- [x] Keep local tooling files out of the repository (`.gitignore` entries merged into `develop`)

## 2. Create the Django project

- [x] `uv init --bare`
- [x] Add the production dependencies (`uv add django djangorestframework …`, see README 2.3)
- [x] Add the dev and test dependencies (`uv add --dev pytest pytest-django …`, see README 2.3)
- [x] `bash scripts/init-django.sh` (settings split, Celery, health check, error schema, custom user model, tool configuration)
- [x] Add project fields to `users/models.py` before the first migration, if any are known (regenerate `users/migrations/0001_initial.py`)
- [x] `pre-commit install`
- [x] `python manage.py migrate`
- [x] `python manage.py runserver 0.0.0.0:8000`
- [x] Set the API title in `SPECTACULAR_SETTINGS` (`config/settings/base.py`) to the project name

## 3. First run check

- [x] `GET /healthz` returns 200
- [x] Create a superuser (`pmsu`) and sign in at `/admin/`
- [x] `pytest` runs (exit 5, "no tests ran", is normal on a new project)
- [x] `mypy .` reports no issues
- [x] `pre-commit run --all-files` passes every hook
- [x] PostgreSQL answers (`psql "$DATABASE_URL" -c "select version();"`)
- [x] Redis answers (`redis-cli -h redis ping`)
- [x] The Celery worker answers (`celery -A config inspect ping`)
- [x] A test email reaches Mailpit (`python manage.py sendtestemail you@example.com`)
- [x] Flower lists the worker (`celery -A config flower --port=5555`, host port 5556)
- [x] `ssh -T git@<host in the origin URL>` greets the right account
- [x] The branch guard works: `pre-commit run no-commit-to-branch` fails on `develop`

## 4. Freeze the toolchain and write the README

- [x] `bash scripts/pin-image.sh` (pins the dev image to an exact build)
- [x] `bash scripts/init-readme.sh --description "…"` (replaces the template guide with the project README)
- [x] Update `.github/CODEOWNERS` with the project owners
- [x] Review `LICENSE`, `.github/SECURITY.md` and `.github/CONTRIBUTING.md` (they still describe the template)
- [x] Replace the template links and badges that point to the template repository
- [x] Add the project's own rules (identifiers, money and currency formats, authentication, domain naming) to `docs/api-conventions.md`

## 5. First pull request

- [x] Create a topic branch (for example `chore/initial-setup`)
- [x] Commit the generated project with a Conventional Commit message
- [x] Push the branch and open a pull request into `develop`
- [x] **CI passed** is green (first time the required check exists)
- [x] Merge with **Create a merge commit**
- [x] Promote `develop` to `main` with a release pull request (source branch `develop`, merge commit)

## 6. GitHub repository settings

- [x] Settings → General (default branch, merge methods, features, automatic branch deletion, release immutability)
- [x] Settings → Actions → General (allowed actions, pin to full commit SHA, workflow permissions)
- [x] Settings → Advanced Security (dependency graph, Dependabot alerts and updates; private vulnerability reporting, CodeQL and secret scanning are offered only while the repository is public)
- [x] Add the `gitleaks` secret scanner to pre-commit (the guard that works whether the repository is public or private)
- [x] Import the three rulesets (`protect-main`, `protect-develop`, `protect-tags`) after **CI passed** had run once and `main` existed (enforced while the repository is public; GitHub does not enforce them on a private repository on the free plan)
- [ ] While the repository is public: turn on private vulnerability reporting, CodeQL (Actions and Python), secret scanning and push protection, and set the repository description and topics (`docs/github-setup.md`, "Changing the repository's visibility")
- [x] Decide on image publishing: set `PUBLISH_IMAGE` (`ghcr` or `dockerhub`) or leave it unset
- [ ] Verify the protection (direct pushes rejected, a topic branch cannot target `main`, only merge commits offered); the rulesets are in place, so this needs a test push, run once by the owner

## 7. Ready for the first endpoint

- [x] Copy `.env.example` to `.env` and adjust it if needed
- [x] Choose the authentication approach and record it in `docs/api-conventions.md`
- [x] Set the pagination class and page size in `REST_FRAMEWORK`
- [ ] Set `CORS_ALLOWED_ORIGINS` for the web client (development and production)
- [x] Create the first app, with its model, serializer, view, URL under `/api/v1/` and tests
- [x] Generate and commit the API contract (`bash scripts/schema.sh generate`), which switches on the three API CI jobs
- [x] Add both the backend and the client owners to `/openapi/` and `/.spectral.yaml` in `.github/CODEOWNERS` (the owner is both; `@Aalihaidar` owns both paths)
- [ ] Publish the first release: raise the `version` in `pyproject.toml`, merge `develop` into `main` through a release pull request, then publish the draft release

## 8. Later

- [ ] After the first presentation to restaurant managers, choose the hosting for the pilot (the owner decides whether it costs anything), keeping the split: `develop` is staging with its own database and service, `main` is production with its own
- [ ] Review the Dependabot pull requests weekly; promote `develop` to `main` only when needed (a release or milestone is ready, or production needs the new code), not after every merge

## How the Wasli steps are organised

The sections below take the project from the finished scaffold to the complete first version on staging (milestones D0 to D4), then list what comes after. Follow them in order and say so before skipping ahead. Each group of steps is one topic branch and one pull request into `develop`, with its tests, and ticks its steps in the same pull request. Steps that need something from the project owner (accounts, the real restaurant's data, recorded clips) say so. The product and API details are in the project notes and `openapi/schema.yaml`, which wins for endpoints.

## 9. D0: users, apps, settings and first deploy

- [x] **Needs the owner:** a Neon account and a Render account (both done)
- [ ] Keep staging on free plans: no payment method on Render, Neon or Google AI Studio, and billing stays off on the Gemini project; Cloudflare R2 runs on the owner's existing account within its free allowance (check each provider's page: the free plans of Render and Neon stop or suspend at their limits instead of charging). Production's plans are decided at launch. A small paid upgrade is the owner's call, only if something hurts a meeting
- [x] Create two Neon projects in Frankfurt on the newest PostgreSQL, each with the free plan's autoscaling compute (0.25 to 2 CU) and its direct connection string with `sslmode=require` (the host without `-pooler`): `wasli-staging` (for `develop`, and also for local development and tests) and `wasli-production` (for `main`). Separate projects keep each one's free compute hours apart, and the free plan allows several projects (check Neon's current limits). There is no local database: the dev container's `db` service stays unused
- [x] Copy `.env.example` to `.env`, set `DATABASE_URL` to the `wasli-staging` string and adjust the rest. Connection strings live only in `.env` (git-ignored) and in the Render environment variables, never in the repository
- [x] Check that `pytest` works against `wasli-staging` (it creates and drops its own `test_` database there) and that local work, tests and the staging service together stay inside that project's free compute hours (`pytest` runs against `wasli-staging` and passes; checked in the Neon dashboard on 2026-11-07: 0.21 compute CU-hours and 32.75 MB used since the project was created, the compute sleeps when idle; the autoscaling range stays at the free plan's 0.25 to 2 CU for now (owner's choice): if the free hours run low, lower the maximum to 0.25 CU. `/healthz` does not query the database, so Render's health checks do not wake Neon; recheck the usage graph after the first staging deploy)
- [x] Rebuild `users.User` with three sign-in identifiers, `username`, `email` and `phone` (international format), plus `phone_verified_at`, `email_verified_at` and `must_change_password`: each identifier unique and stored as NULL when empty, never as an empty string; at least one required; `username` is `USERNAME_FIELD`, starts with a letter and cannot contain `@`. Add an authentication backend that takes one value plus the password and finds the account by email, phone or username. Update the manager, admin and tests, delete `users/migrations/0001_initial.py`, regenerate it and reset the `wasli-staging` database (never production)
- [x] Create the apps `core`, `restaurants`, `menu`, `customers`, `chat`, `orders` and `assistant`, and register them with `rest_framework.authtoken` in `INSTALLED_APPS`
- [x] Add the Wasli settings, read from the environment (location check, screen-online requirement, assistant provider, Gemini key and model, assistant timeout and daily request limit, and an `ENVIRONMENT` name, `local`, `staging` or `production`, that shows in the logs), with invented placeholders in `.env.example` and the same names in `docker-compose.yml`; the testing settings use the fake provider (the demo and seed settings of the first draft were removed by the settings cleanup below)
- [x] Configure DRF: customer and staff authentication classes, `IsAuthenticated` by default with explicit public views, throttle classes and rates, the shared pagination class and page size, and `409` in the documented error codes with its enum override (the staff token class, defaults, throttling, pagination and `409` are done; the customer authentication class came with the `customers` step in section 10)
- [x] Add `google-genai` (`uv add`)
- [x] **Needs the owner:** update the Notion pages (Conclusion, Plan & Strategy, Backend, Demo, API contract, Backend build guide, Frontend pages) with the decisions of 2026-11-07, replacing the old text, from the owner's own account (done on 2026-11-09; the Demo page is now titled "Staging (first version)")
- [x] Settings cleanup: remove `DEMO_MODE`, `RUN_SEED_DEMO`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and the demo wording in the settings, `.env.example`, `docker-compose.yml`, the comments and the tests (`LOCATION_CHECK`, `REQUIRE_SCREEN_ONLINE` and `ENVIRONMENT` stay); the entrypoint keeps only the migrations, and the platform superuser is created by hand with `createsuperuser`
- [x] Update `docs/api-conventions.md`: the roles (platform team, restaurant `admin`, `cashier`, customer), restaurant accounts sign in with a username (the login accepts a username, an email or a phone number), and the three polling lists are the documented pagination exception
- [ ] Set `CORS_ALLOWED_ORIGINS` per environment: local development now, then the staging and the production site origins from the frontend team (they need a staging and a production deploy of each of the two sites). Local development is done in `.env.example`. The staging site origins are decided (2026-11-10): the Cloudflare Pages projects `wasli-customer-staging` and `wasli-restaurant-staging`, so `https://wasli-customer-staging.pages.dev` and `https://wasli-restaurant-staging.pages.dev`; they must be set on the staging Render service and match the CORS rule of the staging R2 bucket (the frontend creates the projects with exactly these names and checks the real addresses). Production's origins are still to be chosen
- [x] Create the Render web service `wasli-staging` (Docker, `docker/Dockerfile.prod`, Frankfurt, Free, health check `/healthz`, Auto-Deploy off: it deploys from `develop` only when started by hand from the Render dashboard) with the staging Neon string and its environment variables
- [ ] Create the Render web service `wasli-production` (same settings, Auto-Deploy off: it deploys from `main` only when started by hand, and its first deploy waits for the release pull request below) with the production Neon string and its own environment variables. Production stays closed (no restaurants, no customers) until the pilot, and its variables must include `ENVIRONMENT=production` and `MESSAGING_BACKEND=disabled` (the start-up check refuses the outbox there); no customer can sign up there until its messaging services are chosen (section 14). Both free services share the workspace's free instance hours and 5 GB of monthly traffic, and both sleep when idle
- [ ] Merge the D0 pull request into `develop`, deploy staging by hand and confirm `GET /healthz` returns 200 with the migrations in the log (staging done on 2026-11-07: live at `https://wasli-staging.onrender.com`, `/healthz` and the admin login return 200); then promote `develop` to `main` through a release pull request, deploy production by hand and confirm the same
- [ ] **D0 done:** staging (from `develop`) and production (from `main`) are deployed on Render with their own Neon projects, `/healthz` is green on both, **CI passed** is green on `develop`

## 10. D1: data model, read endpoints and the assistant spike

- [x] `core`: the abstract base model (UUID key, `created_at`, `updated_at`), the money and haversine helpers (with location validation and the distance band), and the permission codes (`orders.view`, `orders.decide`, `menu.edit`, `members.manage`, `restaurant.settings`, `reports.view`) with the `admin` and `cashier` role map, all unit-tested
- [x] `core`: the restaurant-scoped queryset (`for_restaurant`) and, in `restaurants`, the DRF permission class that checks the caller's membership for a permission code, never a role name
- [x] `restaurants`: `ParkingLot`, `Restaurant` (with `is_demo`, an informational flag shown as an admin column and filter, no effect on behaviour), `RestaurantMenuImage` and `StaffMembership` (role `admin` or `cashier`; its user must have a username, so every restaurant account signs in with a username; the last admin of a restaurant cannot be deactivated or demoted), with their admin and tests
- [x] `menu`: `MenuCategory`, `MenuItem` (with aliases), `OptionGroup` and `Option`, with their admin and tests (prices are typed in AED in the admin and stored in fils; a child row always belongs to its parent's restaurant)
- [x] `customers`: `Customer` (linked one-to-one to its `User`, required: every customer signs up), `CustomerSession` (only the token hash is stored), `Vehicle` and `CustomerBlock`, the `Authorization: Customer <token>` authentication class and its schema extension, with tests
- [x] `chat`: `Conversation` and `Message` with their admin and tests (the conversation holds the order lines, the pending question, the car details, the note and the position; a message's `seq` is taken under a row lock by `chat/services.py`; the admin is read-only and leaves out the coordinates)
- [x] `orders`: `Order`, `OrderItem` and `OrderEvent` (read-only admin) and `assistant`: the assistant call log (provider, model, purpose, latency, outcome, never the content), with tests (an order keeps copies of the car, the note, the position and every line's names and price; a rejected order always has a reason and the reason `other` a note, enforced in the database; the admin is read-only and hides the coordinates, and a test order can be deleted there on local and staging but never in production; the call log has no field that could hold content)
- [x] Tenancy and permission tests: staff of restaurant A can never read or change restaurant B's data, and a cashier cannot do what only an admin can (every restaurant-owned table is checked for scoping, protected deletion and parents of another restaurant, and a new tenant table fails the suite until it is added; each endpoint adds its own isolation test when it is built)
- [x] Swagger UI: `/api/docs/` and `/api/schema/` on local and staging only and only for staff accounts signed in through the admin (anyone else gets a 404, production serves nothing), the UI bundled with the app (`drf-spectacular-sidecar`, no CDN), with tests
- [x] Platform team: the owner's superuser account (email sign-in, never a shared account), created by hand with `createsuperuser` in the dev container against the staging Neon project on 2026-11-07; there is no seed command
- [ ] Platform team: the second named superuser, for the owner's brother, added later the same way (production's superusers are created by the owner at launch)
- [ ] **Needs the owner:** the real restaurant's details, location, parking lot, items, prices, options, photos and menu images, entered through the Django admin on staging once the admin and the media storage exist; never invent a menu
- [x] `messaging`: `OutboxMessage` (channel `email` or `sms`, recipient, subject, body, purpose, created_at) with a read-only admin, the delivery interface and its `outbox` backend, chosen by `MESSAGING_BACKEND`; the outbox backend refuses to start when `ENVIRONMENT=production`; tests
- [x] Open the API request issue for customer accounts (sign-up, verification, resend, sign-in, sign-out, `me`, adding the missing contact, password reset) and agree it with the frontend team before building it (agreed on 2026-11-10 with every proposal accepted; the decisions are in [ADR 0011](adr/0011-customer-accounts-flow.md), and the issue stays as a written record)
- [x] Customer accounts: sign-up with a name, an email or a phone number and a password, a six-digit verification code (stored hashed, 10 minutes, five attempts, resend limit) sent through the messaging interface, verify (issues the customer token), resend, sign-in, sign-out, `GET /api/v1/customers/me`, adding the missing contact from the account settings (an email for a phone sign-up, a phone number for an email sign-up) with a code sent to it (changing an existing contact is not offered), and password reset, all throttled, with tests (an unverified account cannot sign in; another account's code never works). The endpoint shapes are agreed first in an API request issue (`customers/accounts.py`, `customers/verification.py`, ten endpoints under `/api/v1/customers/`, the `VerificationCode` model, per-scope throttles, the new error codes `account_exists`, `contact_already_set`, `no_pending_contact`, `account_not_verified` and `too_many_attempts`, and the first customer part of `openapi/schema.yaml`)
- [x] Media storage: `django-storages` with Cloudflare R2 (S3 API); image fields uploaded in the admin for logo, cover, menu images and item photos (the fields exist on the models and use the default file storage until this step switches it to R2); absolute URLs in the API from a public base URL; one bucket and one key pair per environment; settings in `.env.example` and `docker-compose.yml`; tested with a fake storage (`MEDIA_STORAGE=filesystem|r2`, the five `R2_*` variables, `check_media`, the warning `core.W001`; the owner's setup steps are in `docs/r2-setup.md`)
- [x] **Needs the owner:** an R2 bucket and an access key for staging on the existing Cloudflare account, with the public `r2.dev` address enabled until a domain exists (done on 2026-11-10: bucket `wasli-staging-media`, a key limited to it, the six variables set locally and on the staging service; `check_media --fetch` passed)
- [x] `GET /api/v1/config` (location check, screen-online requirement, assistant availability, languages, polling interval), with tests; `ai_enabled` is true for the fake provider, and for Gemini when its key and model are set (the daily budget and the outage window come with the assistant layer in D3)
- [x] `nearest` on `GET /api/v1/restaurants/nearby` is an optional property, absent when there is none, and the API conventions forbid nullable object references (agreed with the customer app on 2026-11-14)
- [x] `GET /api/v1/restaurants/nearby` (distance, `is_open`, `nearest` hint) and `GET /api/v1/restaurants/{slug}` (menu images and structured menu), with tests; `is_open` is true while the restaurant's site polled in the last 60 seconds, `nearby` is not paginated (polling list), `nearby` is a reserved slug, and a restaurant that is inactive or whose subscription is suspended is not listed and its page is a 404
- [x] Gunicorn access log without the query string: the production entrypoint logs the method, the path, the status, the size, the time and the request id, never the full request line, because `GET /restaurants/nearby` carries the customer's position in its query string; tested. Remove `GUNICORN_CMD_ARGS` from the Render variables if it is set there, because it replaces these defaults
- [x] Generate and commit `openapi/schema.yaml` (`bash scripts/schema.sh generate`) with the `api-change` label (the three public endpoints; Swagger on staging shows it)
- [x] The backend and client owners on `/openapi/` and `/.spectral.yaml` in `.github/CODEOWNERS`: the owner is both, and `@Aalihaidar` already owns both paths
- [x] Decision records: `docs/adr/` with an index and the first eight records (accounts, roles and tenancy, environments and deploys, no demo mode, R2 images, customer accounts and the outbox, API shape, public visibility); a new decision that is costly to change gets a record in the same pull request
- [x] API hardening baseline: `X-Request-ID` on every API response and in every log line, `Cache-Control: no-store` on `/api/v1/`, a request body cap (64 KB, 6 MB for a voice upload) refused with `request_too_large` or `audio_too_large` before any view, CORS exposing and allowing the request id; tested ([ADR 0009](adr/0009-api-hardening-and-outbox-hygiene.md))
- [x] Outbox hygiene: messages deleted after 24 hours (on every send and with `python manage.py purge_outbox`), the `disabled` messaging backend, and the system check `messaging.E001` that fails when `ENVIRONMENT=production` uses the outbox; tested
- [x] Django admin polish (built in, no new dependency): Wasli branding and colours for the light and dark theme, the environment in the header, sections in working order, counters on the first page, image thumbnails, the items of a category edited on its page with prices in AED, and coloured status labels; the option of a third-party theme is recorded in [ADR 0013](adr/0013-django-admin-appearance.md)
- [x] Adapter interface and Gemini adapter, then a developer-only spike command for order parsing, car-details extraction and transcription in Arabic, English and mixed input (`assistant/adapters/`, `python manage.py assistant_spike`, [ADR 0010](adr/0010-the-assistant-layer.md); written and tested against a stand-in client, not yet run against the real provider)
- [ ] **Needs the owner:** a Gemini key for a project made for Wasli, and the WAV clips the frontend records in Chrome on Android and Safari on iPhone
- [ ] Run the spike and report the model chosen, its free daily quota, the latency per call and which audio formats worked
- [ ] **Needs the owner (frontend gate):** measure the first load of the Flutter web customer site as soon as its start screen and a chat shell are deployed on staging. Scan a QR code to the site with a real mid-range Android phone over mobile data, and with an iPhone in Safari, with an empty cache and with a warm one, and record the download size and the time until the screen is usable. Proposed target: usable within about 4 seconds on 4G with an empty cache (the owner confirms or changes it). If the result is clearly too slow, replace only the customer web site with a small web-only app and keep Flutter for the restaurant site and the later apps; the backend and the contract do not change either way
- [ ] Release `v0.1.0` (raise the version, release pull request): the owner keeps it as a draft until the whole backend is finished (decided 2026-11-14), so both frontend repositories (`wasli-customer-flutter`, `wasli-restaurant-flutter`) pin the contract by commit meanwhile; after a merge that changes `openapi/schema.yaml`, tell the frontend team the `develop` commit to pin
- [ ] **D1 done:** the real restaurant is entered through the admin on staging with its images on R2, the endpoints work there, a customer can sign up and verify with the code read in the admin outbox, the `v0.1.0` contract is on `develop` (the release itself stays a draft) and the spike is reported

## 11. D2: the conversation engine

- [x] `assistant`: fake adapter with recorded outputs (used by every test), prompts and call logging (one `AICallLog` row per call, never the content)
- [ ] `assistant`: the availability flag (`ai_available` false for 5 minutes after a provider failure)
- [ ] `orders/services.py`: validation and pricing from the database (availability, option rules, default options, limits of 20 lines and quantity 20), unit-tested
- [ ] `chat/texts.py`: every bot text in Arabic and English, with a test that each text has both
- [ ] `chat/engine.py`: welcome, menu images and first question, then the ordering loop (item actions applied, ids validated, unmatched items, choice questions and `choose`, empty order, cancel and `restart`)
- [ ] Engine: the car question (one question, merge-only answers, server validation, ask only for what is missing), the note question and skip, the review with the three edit paths and the return to the review, `set_locale`
- [ ] Engine: duplicate `client_message_id` returns the earlier result, conversation expiry, one order per conversation
- [ ] Order creation in one transaction (lock the restaurant row, next number, snapshots, distances, location rule, vehicle saved, bot message)
- [ ] Voice paths (audio into the car answer and the note, transcript stored, empty transcript repeats the question, size and length limits) and the fallbacks (car details one at a time, `set_lines`, assistant unavailable)
- [ ] Endpoints: create or get a conversation, messages (text and actions), messages after a sequence number, voice, location and `GET /orders/{id}`, with the customer-scoping tests (another customer's conversation is a 404)
- [ ] Engine, pricing, parsing, voice, fallback, session and location tests pass; API smoke test from nearby to a placed order
- [ ] Regenerate and commit `openapi/schema.yaml`, publish release `v0.2.0` and tell the frontend team
- [ ] **D2 done:** on the deployed API a customer goes from the welcome to a placed order by text and by voice, with edits at both confirmations

## 12. D3: the restaurant side (show it to restaurant managers after this)

- [ ] Staff endpoints: login (restaurant accounts use a username), logout and `GET /staff/me`
- [ ] `GET /staff/orders?since=` (returns `server_time`, marks the screen online) with both-language item names, distance and distance band
- [ ] Order state machine in `orders/services.py` (accept with 5, 10 or 15 minutes, reject with every reason and a required note for `other`, every other transition a 409), each transition writing an `OrderEvent`
- [ ] Accept and reject endpoints that post the `result` message into the customer's chat
- [ ] Daily request budget guard for the assistant layer and the assistant flag in `/config`
- [ ] Throttling on every open endpoint, stricter on messages, voice and session creation
- [ ] State-machine and tenancy tests pass
- [ ] Regenerate and commit `openapi/schema.yaml`, publish release `v0.3.0` and tell the frontend team
- [ ] **D3 done:** the full flow works with both deployed sites on staging, the tenancy test passes and reject works with every reason; show it to restaurant managers

## 13. D4: polish

- [ ] Second, fake restaurant (`is_demo` set) in another parking lot, entered in the admin on staging only, to prove many restaurants work
- [ ] Optional `ready` step and its chat message
- [ ] Logs: one line per request with timing (the access-log line with the time and the request id exists since the API hardening step), one line per assistant call with purpose, latency and outcome, never customer text, audio or position
- [ ] README: run locally, run the tests, deploy, environment variables, entering a restaurant and its menu in the admin
- [ ] Publish release `v1.0.0`
- [ ] **D4 done:** staging is complete and safe to show

## 14. Before the pilot: restaurant admin, customer accounts and audit (after D3, not started)

- [ ] Restaurant-admin API, each endpoint checking its permission code: menu and prices (items, options, photos, availability), members (add, edit, change role, deactivate and reactivate, reset password with a temporary password; no hard delete), restaurant settings, reports
- [ ] Guardrails tested: an admin manages only their own restaurant, cannot grant more than their own role, cannot deactivate or demote the last admin; a deactivated member keeps their history and can be reactivated; a new member must change the temporary password
- [x] Decide with the owner whether a customer who signed up with an email must also verify a phone number before the first order (decided 2026-11-12: it must, at the pilot)
- [ ] Phone check before the first order: agree the refusal status and error code in an API request issue, then build the gate in the order service (it reuses `POST /customers/me/contact` and `POST /customers/me/contact/verify`) with tests
- [ ] Audit log of price, menu and member changes (who, what, when)
- [ ] Two-factor sign-in for the platform team
- [ ] Per-device staff tokens, so signing out on one device does not sign out the others
- [ ] **Needs the owner:** a domain, added to Cloudflare (the image CDN on a custom domain and the sender domain of Resend both need it)
- [ ] Choose the SMS provider for the UAE (price, delivery, sender-ID rules) and create the Resend account
- [ ] Email backend (Resend) and SMS backend behind the messaging interface, chosen per environment by `MESSAGING_BACKEND`; a daily limit on messages sent to cap cost; tests that production refuses the outbox backend
- [ ] Production R2 bucket on a custom domain behind the Cloudflare CDN, and staging moved to a custom domain too; optional cache rule for static files once the API sits behind the Cloudflare proxy
- [ ] Update the API contract, regenerate `openapi/schema.yaml` and tell the frontend team

## 15. Later (not started)

- [ ] Speech benchmark on real recordings (with consent) and a choice of provider
- [ ] Privacy policy and terms, subscription price and trade licence (business tasks for the owner)
- [ ] Pilot MVP: statuses ready, delivered, can't find car, no-show and cancel, blocks and the platform-wide ban, location enforcement, cash or card choice
- [ ] Platform admin tools: onboarding, QR codes, subscriptions, orders per restaurant per month
- [ ] Paid always-on hosting, managed database with backups, monitoring
- [ ] Launch: realtime stream, push and WhatsApp notifications, saved vehicles, reports
