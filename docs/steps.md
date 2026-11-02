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

- [ ] Copy `.env.example` to `.env` and adjust it if needed
- [x] Choose the authentication approach and record it in `docs/api-conventions.md`
- [ ] Set the pagination class and page size in `REST_FRAMEWORK`
- [ ] Set `CORS_ALLOWED_ORIGINS` for the web client (development and production)
- [ ] Create the first app, with its model, serializer, view, URL under `/api/v1/` and tests
- [ ] Generate and commit the API contract (`bash scripts/schema.sh generate`), which switches on the three API CI jobs
- [ ] Add both the backend and the client owners to `/openapi/` and `/.spectral.yaml` in `.github/CODEOWNERS`
- [ ] Publish the first release: raise the `version` in `pyproject.toml`, merge `develop` into `main` through a release pull request, then publish the draft release

## 8. Later

- [ ] Choose the hosting target and add a deployment workflow with its `staging` and `production` environments
- [ ] Review the Dependabot pull requests weekly and promote `develop` to `main`
