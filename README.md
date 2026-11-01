# Wasli Backend

Backend API for Wasli, which lets customers parked at a restaurant order from
the car through a chat with the restaurant.

[![CI](https://github.com/Aalihaidar/wasli-backend/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Aalihaidar/wasli-backend/actions/workflows/ci.yml)

> **Status:** in development.

## Stack

| Component | Version |
| --- | --- |
| Python | 3.14.8 |
| Django | 6.0.9 |
| uv | 0.13.5 |
| PostgreSQL | 18 |
| Redis | 8 |
| Dev container image | `alihaidar199527/django-devcontainer:python-3.14.8.6` |

Application libraries and their exact versions are pinned in `pyproject.toml` and
`uv.lock`.

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

`develop` and `main` are protected: work happens on topic branches and pull requests
into `develop`; only `develop` opens a pull request into `main` (the release). The git hooks
(Conventional Commits, no commits or pushes on `develop`/`main`) are installed with the container;
the single required check is **CI passed**.

- Branches, hooks, SSH keys, CI and releases: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)
- GitHub settings, Actions permissions, environments, security and rulesets: [`docs/github-setup.md`](docs/github-setup.md)
- The dev image is pinned in `docker-compose.yml`; Dependabot proposes updates as pull requests.
- CI builds and smoke-tests the production image on every pull request and pushes nothing. To publish it, set the repository variable `PUBLISH_IMAGE` (`ghcr` or `dockerhub`), see [`docs/github-setup.md`](docs/github-setup.md) section 3.

## Template

Created from [`alihaidar0/django-template`](https://github.com/alihaidar0/django-template)
release [`v2026.11.01`](https://github.com/alihaidar0/django-template/releases/tag/v2026.11.01).

## License

See [LICENSE](LICENSE) © 2026 Ali Haidar
