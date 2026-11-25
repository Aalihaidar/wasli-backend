# Wasli Backend

Backend API for Wasli, which lets customers parked at a restaurant order from
the car through a chat with the restaurant.

[![CI](https://github.com/Aalihaidar/wasli-backend/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Aalihaidar/wasli-backend/actions/workflows/ci.yml)

> **Status (2026-11-18):** in development, milestone D1 of the first version, closing. Staging is
> live at <https://wasli-staging.onrender.com>. Built: the data models, admin and tests of the
> eight Wasli apps, the three public read endpoints, the ten customer-account endpoints
> (sign-up with a verification code, sign-in, password reset), image storage on Cloudflare R2,
> the assistant adapters, the API hardening baseline and the committed API contract. Since then:
> the order service and the text chat (D2: open a conversation, send a message, read messages,
> the order summary, voice, the car question, the note, the review, the position and the placed
> order, and the car question one item at a time while the assistant is down). Next: the staff endpoints (D3). The checklist is
> [`docs/steps.md`](docs/steps.md); the design is in
> [`docs/project-overview.md`](docs/project-overview.md).

## Stack

| Component | Version |
| --- | --- |
| Python | 3.15.2 (production image), 3.15.2 (dev container) |
| Django | 6.0.10 |
| Django REST framework | with drf-spectacular and drf-standardized-errors |
| uv | 0.13.9 (production image), 0.13.8 (dev container) |
| PostgreSQL | 18 |
| Redis | 8 |
| Dev container image | `alihaidar199527/django-devcontainer:python-3.15.2.3` |

Application libraries and their exact versions are pinned in `pyproject.toml` and
`uv.lock`.

## The apps

| App | What it holds |
| --- | --- |
| `users` | The one account table: sign-in with a username, an email or a phone number |
| `core` | Shared base model, money and distance helpers, permission codes, restaurant scoping, the public `config` endpoint |
| `restaurants` | Restaurants (with an optional service distance), menu images and staff memberships (roles `admin` and `cashier`), the public restaurant endpoints, the staff sign-in and the member's own profile |
| `menu` | Categories, items, option groups and options |
| `customers` | Customers, their sessions and cars, restaurant blocks, the customer token authentication, sign-up with a verification code, sign-in and password reset |
| `messaging` | The outbox of emails and SMS (shown in the admin on local and staging, refused in production) and the delivery interface |
| `chat` | Conversations and messages |
| `orders` | Orders, order lines and the status history |
| `assistant` | The adapters to the understanding provider (Groq as the main one, Gemini as the second, a fake one for tests), the prompts, the key and quota counters and the log of calls |

The staff order endpoints (the orders list, accept and reject) are not built yet. The drafts of the privacy policy and the terms of use are in [`docs/legal/`](docs/legal/README.md).

## The API

The contract is [`openapi/schema.yaml`](openapi/schema.yaml), generated with
`bash scripts/schema.sh generate` and never edited by hand. Built so far, all under `/api/v1/`:

- `GET /config`, `GET /restaurants/nearby` and `GET /restaurants/{slug}`: public, no token.
- Ten endpoints under `/customers/` (`signup`, `verify`, `resend-code`, `login`, `logout`, `me`,
  `me/contact`, `me/contact/verify`, `password-reset`, `password-reset/confirm`).
- The chat, with the customer token: `POST /restaurants/{slug}/conversations` (open the current
  conversation or a new one), `GET /conversations/{id}/messages?after_seq=` (polled) and
  `POST /conversations/{id}/messages` (text, or a button: `confirm`, `edit`, `edit_field`,
  `choose`, `skip_note`, `set_lines`, `set_locale`, `restart`) and `POST /conversations/{id}/voice`
  (one WAV clip taken in every open step, read in memory and never stored), `PUT /conversations/{id}/location` (the phone's position) and
  `GET /orders/{id}` (the customer's own order). The chat now runs from the welcome to the placed order. The bot writes every message; the assistant only
  understands ([ADR 0019](docs/adr/0019-the-conversation-engine.md), providers in
  [`docs/groq-setup.md`](docs/groq-setup.md) and [`docs/gemini-setup.md`](docs/gemini-setup.md)).
- The staff sign-in, for the restaurant app: `POST /auth/login` (a token only for an active member of a restaurant),
  `POST /auth/logout`, `POST /auth/password` (the temporary password) and `GET /staff/me`, with the staff token
  (`Authorization: Token <token>`; [ADR 0024](docs/adr/0024-the-staff-sign-in.md)).

On local and staging, staff signed in through the admin can open Swagger UI at `/api/docs/`;
production serves nothing there. The two Flutter repositories pin the contract by commit until
the first release is published. After a change to `openapi/schema.yaml`, tell them the commit
to pin. The conventions are in [`docs/api-conventions.md`](docs/api-conventions.md) and the
decisions in [`docs/adr/`](docs/adr/README.md).

Management commands: `check_media [--fetch]` (checks the image storage), `purge_outbox`
(deletes old outbox messages) and `assistant_spike` (tries the assistant on sample input; never
in production).

## Environments

- **Staging** deploys from `develop` to Render (free plan, Frankfurt) with its own Neon
  database. **Production** will deploy from `main` with its own service and database.
  Auto-Deploy is off: the owner starts each deploy by hand after a group of pull requests
  is merged.
- Local development uses the staging database through `DATABASE_URL` in `.env` (never
  committed); there is no local database.
- There is no seed command. The platform team enters restaurants, menus and staff accounts
  in the Django admin, and creates the superuser with `python manage.py createsuperuser`.
- New settings are listed in `.env.example` and `docker-compose.yml`; real keys live only
  in `.env` and in the Render environment variables.

## Getting started

Install Docker Desktop and VS Code with the Dev Containers extension, then:

```bash
git clone git@github.com:Aalihaidar/wasli-backend.git
code wasli-backend
```

Click **Reopen in Container**. The first start installs the dependencies and the git
hooks (`uv sync --locked`, `pre-commit install`); the Celery worker starts by itself. Then:

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Celery Beat starts by itself once the migrations are applied. With `DATABASE_URL` pointing at an external
database it stays idle unless `BEAT_ON_EXTERNAL_DATABASE=true` is set in `.env`.

| Service | URL |
| --- | --- |
| Django | <http://localhost:8000> |
| Mailpit | <http://localhost:8025> |
| Flower | <http://localhost:5556> (`celery -A config flower --port=5555`; host port 5556) |

## Development

Work happens on topic branches and pull requests into `develop`; `develop` opens a pull
request into `main` only when needed (a release, or production needs the new code). The git
hooks (Conventional Commits, no commits or pushes on `develop`/`main`) are installed with
the container; the single required check is **CI passed**. The three rulesets
(`protect-main`, `protect-develop`, `protect-tags`) are enforced while the repository is
public; GitHub does not enforce them on a private repository on the free plan, and the
local hooks are the guard then (see "Changing the repository's visibility" in
[`docs/github-setup.md`](docs/github-setup.md)).

- Branches, hooks, SSH keys, CI and releases: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)
- GitHub settings, Actions permissions, environments, security and rulesets: [`docs/github-setup.md`](docs/github-setup.md)
- Entering a restaurant, its menu, images and staff accounts in the Django admin: [`docs/data-entry.md`](docs/data-entry.md)
- The dev image is pinned in `docker-compose.yml`; Dependabot proposes updates as pull requests.
- CI builds and smoke-tests the production image on every pull request and pushes nothing. To publish it, set the repository variable `PUBLISH_IMAGE` (`ghcr` or `dockerhub`), see [`docs/github-setup.md`](docs/github-setup.md) section 3.

## Template

Created from [`alihaidar0/django-template`](https://github.com/alihaidar0/django-template)
release [`v2026.11.01`](https://github.com/alihaidar0/django-template/releases/tag/v2026.11.01)
and synced with release
[`v2026.11.17`](https://github.com/alihaidar0/django-template/releases/tag/v2026.11.17).

## License

See [LICENSE](LICENSE) © 2026 Ali Haidar
