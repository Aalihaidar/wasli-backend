# Setting up the Gemini key (the second provider)

Groq is the main provider ([`docs/groq-setup.md`](groq-setup.md), [ADR 0020](adr/0020-groq-is-the-main-assistant-provider.md)).
Gemini stays configured so the same input can be sent to both and the answers compared:
`python manage.py assistant_spike ... --provider gemini`. It can also be the main provider (`AI_PROVIDER=gemini`), and it takes a voice clip
directly, in one request. It only **understands** what a customer typed or said; it never writes a reply, never sees a price
and never creates an order ([ADR 0010](adr/0010-the-assistant-layer.md)). The code reads the variables below; nothing here is
ever committed.

| Variable | Value | Where it lives |
| --- | --- | --- |
| `AI_PROVIDER` | `groq` for the main provider; `gemini` only to make Gemini the main one (`fake` needs no key and is what the tests and a fresh local setup use) | `.env` and the Render service |
| `GEMINI_API_KEY` | the key from Google AI Studio (a secret) | `.env` and the Render service, nowhere else |
| `GEMINI_MODEL` | the model code chosen in step 3 (never hard-coded in the repository) | `.env` and the Render service |
| `GEMINI_DAILY_REQUEST_LIMIT` | requests per day before the backend stops calling Gemini (default 18) | optional |

Staging and production each get their own Render values. Local development uses the staging values, like the database
and the media bucket.

## 1. Create the key in Google AI Studio

1. Open [Google AI Studio](https://aistudio.google.com) and sign in with the Google account that will own the key.
2. Choose **Get API key**, then **Create API key**.
3. When it asks for a project, choose **Create API key in new project** (or create a project named for Wasli first), so
   the key and its quota belong to a project made for Wasli and not to another app.
4. Copy the key. Keep it only in `.env` and in the Render variables (steps 4 and 5). Do not paste it into a chat, a
   ticket, a commit or a document.

Billing stays off while the free tier is enough. AI Studio may instead say that the free tier is not available for the
project (it depends on the account's country and on how the project was made): the **Learn more** link in that message names the
reason, and a project created from AI Studio's own "Create API key in new project" on a personal account is the first thing to
try. Setting up billing is the owner's decision.

## 2. Know what the free tier means

- **Limits.** The free tier has a daily and a per-minute request limit per project, and the numbers change and differ
  per model. Read them in AI Studio (**Dashboard**, **Usage**, the **Rate limit** tab) for the model you chose.
  `GEMINI_DAILY_REQUEST_LIMIT` is the number of requests the backend allows itself per day (default 18): keep it a little
  under the daily limit shown there, so the backend stops before Google does. The day is counted from the call log since
  midnight Pacific, like Google's, and the developer spike counts too. A call the backend refuses itself is logged as
  `budget_exceeded`.
- **Privacy.** Google's terms for the free tier may allow it to use what is sent to improve its products, and say that
  the paid tier does not. Read the current terms before real customers use the chat. Until then, test only with
  invented orders and your own voice, never with a customer's name, number or position. The position is never sent to
  the assistant in any case. Whether the pilot moves to the paid tier is a decision for the owner, and the privacy
  policy has to say that typed and spoken orders are processed by Google.

## 3. Choose the model

1. In AI Studio, open the model list and pick the current **Flash** model that takes **audio input** and **structured
   (JSON) output**. A stable model is better than a preview, because a preview can be changed or retired.
2. Copy its **model code** exactly as Google writes it (the text used in the API, not the display name).
3. Check that model's free-tier limits (step 2) and note the daily number.

If a model is retired later, change `GEMINI_MODEL` in the two places; no code changes.

## 4. Put the values in the local `.env`

Add these lines to `.env` (it is git-ignored, and it is yours: nobody else reads or edits it):

```text
GEMINI_API_KEY=<the key from step 1>
GEMINI_MODEL=<the model code from step 3>
GEMINI_DAILY_REQUEST_LIMIT=<a little under the model's daily limit>
```

## 5. Put the same values on the staging Render service

1. Open the `wasli-staging` service, then **Environment**.
2. Add `GEMINI_API_KEY`, `GEMINI_MODEL` and `GEMINI_DAILY_REQUEST_LIMIT` with the same values.
3. Deploy by hand (Auto-Deploy is off) after the pull request that needs them is merged. Saving a variable may start a
   deploy by itself on Render; that is fine.

`GET /api/v1/config` answers `"ai_enabled": true` when the chosen provider has what it needs (with `AI_PROVIDER=gemini`,
the key and the model). It answers `false` when something is missing, and the app then offers the item picker.

## 6. Check that it works

With the three values in `.env`, the developer spike sends one invented sentence to the real provider and prints what
came back, how long it took and how many tokens it used. It never prints the key.

```bash
python manage.py assistant_spike order --provider gemini --locale en --text "two karak tea and one cheese sandwich"
python manage.py assistant_spike order --provider gemini --restaurant <slug> --locale ar --text "<an Arabic sentence about that menu>"
```

A good run prints a JSON result with the items it matched and a latency of a few seconds at most. Every call is also
written to the assistant call log in the admin (provider, model, purpose, latency, outcome, and never the content).

## If something goes wrong

| What you see | Likely cause | What to do |
| --- | --- | --- |
| `ai_enabled` is `false` on staging | the key or the model is missing on the Render service | add it and deploy |
| the log shows `http_400` | the model code is wrong or the model was retired | copy the model code again (step 3) |
| the log shows `http_401` or `http_403` | the key is wrong, deleted or restricted | create a new key (step 1) and update both places |
| the log shows `rate_limited` | Google's limit of the minute or the day was reached | wait, or lower `GEMINI_DAILY_REQUEST_LIMIT` |
| the log shows `budget_exceeded` | the backend's own daily limit for Gemini was reached; nothing was sent | wait for midnight Pacific, or raise the limit |
| the log shows `http_504` | Google's gateway timed out (a slow model or a project problem) | try again; if it repeats, check the project in AI Studio |
| the log shows `timeout` | the provider was slow (the backend waits `AI_TIMEOUT_SECONDS`, 15 by default) | try again; the chat says so and offers the picker for five minutes |
| the log shows `invalid_output` | the provider answered something that does not fit the expected shape | tell the developer, with the time of the call |

If the key is ever pasted anywhere it should not be (a commit, a screenshot, a message), delete it in AI Studio at once,
create a new one and update `.env` and Render.
