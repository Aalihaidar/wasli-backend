# Wasli Backend

Backend API for Wasli, which lets customers parked at a restaurant order from
the car through a chat with the restaurant.

[![CI](https://github.com/Aalihaidar/wasli-backend/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Aalihaidar/wasli-backend/actions/workflows/ci.yml)

> **Status (2026-11-09):** in development, milestone D1 of the first version. Staging is
> live at <https://wasli-staging.onrender.com>. The data models, admin and tests of the
> seven Wasli apps are built; the order service, the conversation engine, messaging,
> customer sign-up, image storage, the assistant adapters and the API endpoints come
> next. The checklist is [`docs/steps.md`](docs/steps.md); the design is in
> [`docs/project-overview.md`](docs/project-overview.md).

## Stack

| Component | Version |
| --- | --- |
| Python | 3.14.9 (production image), 3.14.8 (dev container) |
| Django | 6.0.9 |
| Django REST framework | with drf-spectacular and drf-standardized-errors |
| uv | 0.13.7 (production image), 0.13.5 (dev container) |
| PostgreSQL | 18 |
| Redis | 8 |
| Dev container image | `alihaidar199527/django-devcontainer:python-3.14.8.6` |

Application libraries and their exact versions are pinned in `pyproject.toml` and
`uv.lock`.

## The apps

| App | What it holds |
| --- | --- |
| `users` | The one account table: sign-in with a username, an email or a phone number |
| `core` | Shared base model, money and distance helpers, permission codes, restaurant scoping |
| `restaurants` | Parking lots, restaurants, menu images and staff memberships (roles `admin` and `cashier`) |
| `menu` | Categories, items, option groups and options |
| `customers` | Customers, their sessions and cars, restaurant blocks, the customer token authentication |
| `chat` | Conversations and messages |
| `orders` | Orders, order lines and the status history |
| `assistant` | The log of calls to the assistant provider |

The conversation engine, the `messaging` app and the API endpoints are not built yet.

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
the container; the single required check is **CI passed**. GitHub rulesets cannot be
enabled while the repository is private on the free plan, so the local hooks are the guard.

- Branches, hooks, SSH keys, CI and releases: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)
- GitHub settings, Actions permissions, environments, security and rulesets: [`docs/github-setup.md`](docs/github-setup.md)
- The dev image is pinned in `docker-compose.yml`; Dependabot proposes updates as pull requests.
- CI builds and smoke-tests the production image on every pull request and pushes nothing. To publish it, set the repository variable `PUBLISH_IMAGE` (`ghcr` or `dockerhub`), see [`docs/github-setup.md`](docs/github-setup.md) section 3.

## Template

Created from [`alihaidar0/django-template`](https://github.com/alihaidar0/django-template)
release [`v2026.11.01`](https://github.com/alihaidar0/django-template/releases/tag/v2026.11.01).

## License

See [LICENSE](LICENSE) © 2026 Ali Haidar
