# Setting up the R2 bucket for images

Uploaded images (logos, covers, menu images, item photos) live in a Cloudflare R2 bucket, one bucket and one key pair
per environment ([ADR 0005](adr/0005-images-on-cloudflare-r2.md)). Do this once for staging and once for production.
The code reads the bucket from environment variables; nothing here is ever committed.

## How the buckets are laid out

The Cloudflare account may hold other projects, so every Wasli bucket and key is separate and named for what it is:

| | Staging | Production |
| --- | --- | --- |
| Bucket | `wasli-staging-media` | `wasli-production-media` |
| Key | Object Read & Write, limited to the staging bucket | Object Read & Write, limited to the production bucket |
| Public address | the `r2.dev` address | a custom domain on Cloudflare |
| Values live in | the local `.env` and the staging Render service | the production Render service only |

- Another app uses its own bucket, so its images never reach Wasli's bucket and a Wasli key cannot touch another app.
- Never use an account-wide or "Admin" key for the backend.
- Production values are never put in a developer's `.env`: local development uses the staging bucket, like the database.
- Inside a bucket the code keeps order itself: `restaurants/logos/`, `restaurants/covers/`, `restaurants/menu/`,
  `menu/items/` and `chat/messages/`.
- Staging status (2026-11-10): the staging bucket exists with public access and its CORS rule, and its keys are set in the
  local `.env` and on the staging Render service. The production bucket is created at launch.

## 1. Create the bucket

1. In the Cloudflare dashboard open **R2 Object Storage** and choose **Create bucket**.
2. Name it for its environment, for example `wasli-staging-media` (production: `wasli-production-media`). Keep the
   default location.

## 2. Make the files public

1. Open the bucket, then **Settings**, then **Public access**.
2. Staging: enable the **R2.dev subdomain** and copy the address, which looks like `https://pub-<hash>.r2.dev`. That is
   `R2_PUBLIC_BASE_URL`. Cloudflare limits this address and does not recommend it for production.
3. Production: connect a **custom domain** on Cloudflare instead (it needs a domain, which does not exist yet) and use
   `https://<that domain>` as `R2_PUBLIC_BASE_URL`.

## 3. Allow the sites to read the images

Flutter web loads images with the browser's fetch, which needs a CORS rule. Open the bucket **Settings**, then
**CORS Policy**, and add one rule with the exact origins of the two sites of that environment (the same values as
`CORS_ALLOWED_ORIGINS`; the example is staging's, and `http://localhost:8080` lets the app on a developer's machine show the images):

```json
[
  {
    "AllowedOrigins": [
      "https://wasli-customer-staging.pages.dev",
      "https://wasli-restaurant-staging.pages.dev",
      "http://localhost:8080"
    ],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

## 4. Create the key

1. On **R2 Object Storage** choose **Manage API tokens**, then **Create API token**.
2. Permission **Object Read & Write**, applied to **this bucket only**.
3. Copy the **Access Key ID** and the **Secret Access Key** now: the secret is shown once.
4. Copy the **Account ID** from the R2 overview page.

## 5. Set the variables

Local development (`.env`, never committed) and the Render service of that environment need:

| Variable | Value |
| --- | --- |
| `MEDIA_STORAGE` | `r2` |
| `R2_ACCOUNT_ID` | the Account ID |
| `R2_ACCESS_KEY_ID` | the Access Key ID |
| `R2_SECRET_ACCESS_KEY` | the Secret Access Key (a secret) |
| `R2_BUCKET_NAME` | the bucket name |
| `R2_PUBLIC_BASE_URL` | the public address from step 2, with `https` and no path |

A missing variable stops the service at start-up with a message that names it. On Render a service that is not `local`
and still has `MEDIA_STORAGE=filesystem` shows the warning `core.W001`, because the disk is erased at every deploy.

## 6. Check it

```bash
python manage.py check_media --fetch
```

The command writes a small file, prints its public URL, downloads it from that URL and deletes it. If it reports that the
file cannot be read, the public access of step 2 or the variables are wrong. Then upload a logo in the Django admin on
the restaurant page and open the restaurant in the API: `logo_url` must be an `https` address on the public host.

## Notes

- A new upload never replaces a file (a name that exists gets a random suffix), so a stored file never changes and is cached
  for a year.
- Small images matter on the free plans: WebP or JPEG, about 1,600 px wide and 300 KB at most.
- Tests never reach a bucket: the test settings keep images in memory whatever the environment says.
