# ADR 0005: Images on Cloudflare R2

- Status: accepted, not built yet (`docs/steps.md`, section 10)
- Date: 2026-11-07

## Context

Logos, menu images and item photos are uploaded in the Django admin. The web services have ephemeral disks, so files
written there disappear at the next deploy. The apps need absolute URLs.

## Decision

- Uploaded images go to object storage on Cloudflare R2 (S3 compatible, through `django-storages`), one bucket and one
  key pair per environment.
- The API returns absolute URLs built from a public base URL. Staging uses the `r2.dev` address until a domain exists;
  production needs a custom domain on Cloudflare for the CDN.
- Static files stay on WhiteNoise.
- Tests use a fake storage and never reach the network.

## Consequences

- Until the storage is switched on, image fields use the default file storage and the API returns the URL of that
  storage.
- Keys exist only in the environment of each service.
