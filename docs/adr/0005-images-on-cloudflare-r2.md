# ADR 0005: Images on Cloudflare R2

- Status: accepted, built (the bucket itself is created by the owner, see [`../r2-setup.md`](../r2-setup.md))
- Date: 2026-11-07 (built 2026-11-10)

## Context

Logos, menu images and item photos are uploaded in the Django admin. The web services have ephemeral disks, so files
written there disappear at the next deploy. The apps need absolute URLs.

## Decision

- Uploaded images go to object storage on Cloudflare R2 (S3 compatible, through `django-storages`), one bucket and one
  key pair per environment. `MEDIA_STORAGE` chooses `filesystem` (local development, the default) or `r2`; the bucket is
  read from `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` and `R2_PUBLIC_BASE_URL`
  (`config/storage.py`). Choosing `r2` with a setting missing stops start-up and names it.
- The API returns absolute URLs built from the bucket's public address: the file is public and the URL is the plain
  address, never a signed link. Staging uses the `r2.dev` address until a domain exists; production needs a custom domain
  on Cloudflare for the CDN. `R2_PUBLIC_BASE_URL` must be an `https` address with no path.
- A new upload never replaces a file, so a stored name never changes content and is served with a long cache lifetime.
- The bucket has a CORS rule for the two sites, because Flutter web loads images with the browser's fetch.
- A system check (`core.W001`) warns when staging or production keeps images on the local disk, and
  `python manage.py check_media --fetch` proves a bucket works (write, public URL, read back, delete).
- Static files stay on WhiteNoise.
- Tests keep images in memory whatever the environment says, because a developer's `.env` may point at the staging bucket.

## Consequences

- The owner creates a bucket and a key per environment ([`../r2-setup.md`](../r2-setup.md)); keys exist only in the
  environment of each service and in the git-ignored `.env`.
- An image uploaded on local development goes to the staging bucket when `.env` says so, like the database does.
- `r2.dev` is rate limited and not meant for production traffic, so production waits for a domain.
