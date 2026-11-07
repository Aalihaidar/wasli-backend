# Project steps

The checklist of everything to do in this repository, from a fresh copy of the template to a project that is ready for its first endpoint. Tick a step (`- [x]`) as soon as it is done, in the same pull request that completes it. The detailed instructions behind each step are in the [README](../README.md) and in [`github-setup.md`](github-setup.md).

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
- [x] Settings → Advanced Security (dependency graph, Dependabot alerts and updates; the repository is private, so private vulnerability reporting, CodeQL and secret scanning are not offered)
- [x] Add the `gitleaks` secret scanner to pre-commit (replaces GitHub secret scanning on a private repository)
- [ ] Import the three rulesets (`protect-main`, `protect-develop`, `protect-tags`), only after **CI passed** has run once and `main` exists (not available while the repository is private on the free plan)
- [x] Decide on image publishing: set `PUBLISH_IMAGE` (`ghcr` or `dockerhub`) or leave it unset
- [ ] Verify the protection (direct pushes rejected, a topic branch cannot target `main`, only merge commits offered); blocked until the rulesets can be imported

## 7. Ready for the first endpoint

- [x] Copy `.env.example` to `.env` and adjust it if needed
- [x] Choose the authentication approach and record it in `docs/api-conventions.md`
- [x] Set the pagination class and page size in `REST_FRAMEWORK`
- [ ] Set `CORS_ALLOWED_ORIGINS` for the web client (development and production)
- [ ] Create the first app, with its model, serializer, view, URL under `/api/v1/` and tests
- [ ] Generate and commit the API contract (`bash scripts/schema.sh generate`), which switches on the three API CI jobs
- [ ] Add both the backend and the client owners to `/openapi/` and `/.spectral.yaml` in `.github/CODEOWNERS`
- [ ] Publish the first release: raise the `version` in `pyproject.toml`, merge `develop` into `main` through a release pull request, then publish the draft release

## 8. Later

- [ ] After the first presentation to restaurant managers, choose the hosting for the pilot (the owner decides whether it costs anything), keeping the split: `develop` is staging with its own database and service, `main` is production with its own
- [ ] Review the Dependabot pull requests weekly and promote `develop` to `main`

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
- [x] Add the Wasli settings, read from the environment (demo mode, location check, screen-online requirement, assistant provider, Gemini key and model, assistant timeout and daily request limit, seed switch, platform admin credentials, and an `ENVIRONMENT` name, `staging` or `production`, that shows in the logs), with invented placeholders in `.env.example` and the same names in `docker-compose.yml`; the testing settings use the fake provider
- [x] Configure DRF: customer and staff authentication classes, `IsAuthenticated` by default with explicit public views, throttle classes and rates, the shared pagination class and page size, and `409` in the documented error codes with its enum override (the staff token class, defaults, throttling, pagination and `409` are done; the customer authentication class is added with the `customers` step in section 10)
- [x] Add `google-genai` (`uv add`)
- [ ] **Needs the owner:** update the Notion pages (Conclusion, Plan & Strategy, Backend, Demo, API contract, Backend build guide, Frontend pages) with the decisions of 2026-11-07, replacing the old text, from the owner's own account
- [x] Settings cleanup: remove `DEMO_MODE`, `RUN_SEED_DEMO`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and the demo wording in the settings, `.env.example`, `docker-compose.yml`, the comments and the tests (`LOCATION_CHECK`, `REQUIRE_SCREEN_ONLINE` and `ENVIRONMENT` stay); the entrypoint keeps only the migrations, and the platform superuser is created by hand with `createsuperuser`
- [x] Update `docs/api-conventions.md`: the roles (platform team, restaurant `admin`, `cashier`, customer), restaurant accounts sign in with a username (the login accepts a username, an email or a phone number), and the three polling lists are the documented pagination exception
- [ ] Set `CORS_ALLOWED_ORIGINS` per environment: local development now, then the staging and the production site origins from the frontend team (they need a staging and a production deploy of each of the two sites). Local development is done in `.env.example`; the two Render origin lists are still placeholders
- [x] Create the Render web service `wasli-staging` (Docker, `docker/Dockerfile.prod`, Frankfurt, Free, health check `/healthz`, Auto-Deploy off: it deploys from `develop` only when started by hand from the Render dashboard) with the staging Neon string and its environment variables
- [ ] Create the Render web service `wasli-production` (same settings, Auto-Deploy off: it deploys from `main` only when started by hand, and its first deploy waits for the release pull request below) with the production Neon string and its own environment variables. Production stays closed (no restaurants, no customers) until the pilot; no customer can sign up there until its messaging services are chosen (section 14). Both free services share the workspace's free instance hours and 5 GB of monthly traffic, and both sleep when idle
- [ ] Merge the D0 pull request into `develop`, deploy staging by hand and confirm `GET /healthz` returns 200 with the migrations in the log (staging done on 2026-11-07: live at `https://wasli-staging.onrender.com`, `/healthz` and the admin login return 200); then promote `develop` to `main` through a release pull request, deploy production by hand and confirm the same
- [ ] **D0 done:** staging (from `develop`) and production (from `main`) are deployed on Render with their own Neon projects, `/healthz` is green on both, **CI passed** is green on `develop`

## 10. D1: data model, read endpoints and the assistant spike

- [x] `core`: the abstract base model (UUID key, `created_at`, `updated_at`), the money and haversine helpers (with location validation and the distance band), and the permission codes (`orders.view`, `orders.decide`, `menu.edit`, `members.manage`, `restaurant.settings`, `reports.view`) with the `admin` and `cashier` role map, all unit-tested
- [ ] `core`: the restaurant-scoped queryset and the DRF permission class that checks the caller's membership for a permission code, never a role name (built with `StaffMembership` in the `restaurants` step)
- [ ] `restaurants`: `ParkingLot`, `Restaurant` (with `is_demo`, an informational flag shown as an admin column and filter, no effect on behaviour), `RestaurantMenuImage` and `StaffMembership` (role `admin` or `cashier`; its user must have a username, so every restaurant account signs in with a username; the last admin of a restaurant cannot be deactivated or demoted), with their admin and tests
- [ ] `menu`: `MenuCategory`, `MenuItem` (with aliases), `OptionGroup` and `Option`, with their admin and tests
- [ ] `customers`: `Customer` (linked one-to-one to its `User`, required: every customer signs up), `CustomerSession` (only the token hash is stored), `Vehicle` and `CustomerBlock`, the `Authorization: Customer <token>` authentication class and its schema extension, with tests
- [ ] `chat`: `Conversation` and `Message` with their admin and tests
- [ ] `orders`: `Order`, `OrderItem` and `OrderEvent` (read-only admin) and `assistant`: the assistant call log (provider, model, purpose, latency, outcome, never the content), with tests
- [ ] Tenancy and permission tests: staff of restaurant A can never read or change restaurant B's data, and a cashier cannot do what only an admin can
- [x] Platform team: the owner's superuser account (email sign-in, never a shared account), created by hand with `createsuperuser` in the dev container against the staging Neon project on 2026-11-07; there is no seed command
- [ ] Platform team: the second named superuser, for the owner's brother, added later the same way (production's superusers are created by the owner at launch)
- [ ] **Needs the owner:** the real restaurant's details, location, parking lot, items, prices, options, photos and menu images, entered through the Django admin on staging once the admin and the media storage exist; never invent a menu
- [ ] `messaging`: `OutboxMessage` (channel `email` or `sms`, recipient, subject, body, purpose, created_at) with a read-only admin, the delivery interface and its `outbox` backend, chosen by `MESSAGING_BACKEND`; the outbox backend refuses to start when `ENVIRONMENT=production`; tests
- [ ] Open the API request issue for customer accounts (sign-up, verification, resend, sign-in, sign-out, `me`, adding the missing contact, password reset) and agree it with the frontend team before building it
- [ ] Customer accounts: sign-up with a name, an email or a phone number and a password, a six-digit verification code (stored hashed, 10 minutes, five attempts, resend limit) sent through the messaging interface, verify (issues the customer token), resend, sign-in, sign-out, `GET /api/v1/customers/me`, adding the missing contact from the account settings (an email for a phone sign-up, a phone number for an email sign-up) with a code sent to it (changing an existing contact is not offered), and password reset, all throttled, with tests (an unverified account cannot sign in; another account's code never works). The endpoint shapes are agreed first in an API request issue
- [ ] Media storage: `django-storages` with Cloudflare R2 (S3 API); image fields uploaded in the admin for logo, cover, menu images and item photos (instead of URL text fields); absolute URLs in the API from a public base URL; one bucket and one key pair per environment; settings in `.env.example` and `docker-compose.yml`; tested with a fake storage
- [ ] **Needs the owner:** an R2 bucket and an access key for staging on the existing Cloudflare account, with the public `r2.dev` address enabled until a domain exists
- [ ] `GET /api/v1/config` (location check, screen-online requirement, assistant availability, languages), with tests
- [ ] `GET /api/v1/restaurants/nearby` (distance, `is_open`, `nearest` hint) and `GET /api/v1/restaurants/{slug}` (menu images and structured menu), with tests
- [ ] Generate and commit `openapi/schema.yaml` (`bash scripts/schema.sh generate`) with the `api-change` label, and add the backend and client owners to `/openapi/` and `/.spectral.yaml` in `.github/CODEOWNERS`
- [ ] Adapter interface and Gemini adapter, then a developer-only spike command for order parsing, car-details extraction and transcription in Arabic, English and mixed input
- [ ] **Needs the owner:** a Gemini key for a project made for Wasli, and the WAV clips the frontend records in Chrome on Android and Safari on iPhone
- [ ] Run the spike and report the model chosen, its free daily quota, the latency per call and which audio formats worked
- [ ] Publish release `v0.1.0` (raise the version, release pull request, publish the draft) and tell the frontend team which release to pin
- [ ] **D1 done:** the real restaurant is entered through the admin on staging with its images on R2, the endpoints work there, a customer can sign up and verify with the code read in the admin outbox, `v0.1.0` is published and the spike is reported

## 11. D2: the conversation engine

- [ ] `assistant`: fake adapter with recorded outputs (used by every test), prompts, call logging, and the availability flag (false for 5 minutes after a provider failure)
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
- [ ] Logs: one line per request with timing, one line per assistant call with purpose, latency and outcome, never customer text, audio or position
- [ ] README: run locally, run the tests, deploy, environment variables, entering a restaurant and its menu in the admin
- [ ] Publish release `v1.0.0`
- [ ] **D4 done:** staging is complete and safe to show

## 14. Before the pilot: restaurant admin, customer accounts and audit (after D3, not started)

- [ ] Restaurant-admin API, each endpoint checking its permission code: menu and prices (items, options, photos, availability), members (add, edit, change role, deactivate and reactivate, reset password with a temporary password; no hard delete), restaurant settings, reports
- [ ] Guardrails tested: an admin manages only their own restaurant, cannot grant more than their own role, cannot deactivate or demote the last admin; a deactivated member keeps their history and can be reactivated; a new member must change the temporary password
- [ ] Decide with the owner whether a customer who signed up with an email must also verify a phone number before the first order
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
