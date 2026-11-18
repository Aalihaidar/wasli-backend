# ADR 0003: Staging from `develop`, production from `main`, deploys by hand

- Status: accepted
- Date: 2026-11-06

## Context

The first version is shown to restaurant managers on staging while the final product runs on production. A merge must
never migrate a database by surprise, and the first version runs on free plans.

## Decision

- `develop` is staging and `main` is production. Each has its own PostgreSQL project (Neon) and its own web service
  (Render). `ENVIRONMENT` (`local`, `staging` or `production`) names the deployment; everything that differs between
  environments sits behind settings, never behind separate code paths.
- Auto-Deploy is off on both services: the owner deploys by hand after a group of pull requests is merged. Production's
  first deploy waits for the release pull request.
- Local development uses the staging database; the tests create their own `test_` database there. Data on staging is
  development data and may be reset when the owner agrees. Production data is never touched from development.
- Staging uses free plans only. A paid upgrade is the owner's decision.
- Promoting `develop` to `main` happens only when needed (a release, production needs the code, or the owner asks), with
  a merge commit.
- Connection strings and keys live only in the environment of each service and in the git-ignored `.env`.

## Consequences

- A merged pull request is not live until someone deploys it, so a new migration reaches staging only at a deploy.
- Free instances sleep when idle and the first request after a pause is slow.
- Features that must not run in production check `ENVIRONMENT` (the messaging outbox, the API docs, test-order deletion
  in the admin).
