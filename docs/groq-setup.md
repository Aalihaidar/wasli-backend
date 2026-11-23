# Setting up Groq (the main assistant provider)

The chat uses Groq to **understand** what a customer typed or said. Whisper turns a voice clip into text (the audio is sent
and dropped, never stored), and a text model reads the text and answers in a fixed JSON shape. It never writes a reply,
never sees a price and never creates an order ([ADR 0010](adr/0010-the-assistant-layer.md),
[ADR 0020](adr/0020-groq-is-the-main-assistant-provider.md)). Gemini stays configured as a second provider to compare
answers ([`docs/gemini-setup.md`](gemini-setup.md)). Nothing here is ever committed.

## The variables

| Variable | Value | Where it lives |
| --- | --- | --- |
| `AI_PROVIDER` | `groq` | `.env` and the Render service |
| `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, ... | one key per variable, up to ten (secrets) | `.env` and the Render service, nowhere else |
| `GROQ_CHAT_MODEL` | the text model code, copied from the Groq console's Models page | `.env` and the Render service |
| `GROQ_STT_MODEL` | the Whisper model code, copied from the same page | `.env` and the Render service |
| `GROQ_CHAT_RPM`, `GROQ_CHAT_RPD` | what one key may do with the text model per minute and per day (default 30 and 1000) | optional |
| `GROQ_STT_RPM`, `GROQ_STT_RPD` | the same for Whisper (default 20 and 2000) | optional |

The model codes are never written in the code: Groq adds and retires models, and a change is one variable in two places.
The text model that was tried is a gpt-oss one and the speech model is a Whisper one; the accurate multilingual Whisper
model is the better first choice, and the faster, cheaper "turbo" one is worth trying if it is accurate enough on your own
clips.

## Several keys

Put each key on its own line, numbered from 1:

```text
AI_PROVIDER=groq
GROQ_CHAT_MODEL=<the text model code>
GROQ_STT_MODEL=<the Whisper model code>
# one comment line per key is fine in .env, for example the account it belongs to
GROQ_API_KEY_1=<key 1>
GROQ_API_KEY_2=<key 2>
GROQ_API_KEY_3=<key 3>
```

- The backend uses the **first key until it cannot take another call**, then the second, and so on. After the last key it
  goes back to the first: the scan always starts at key 1, so a key that has room again is used again.
- A key "cannot take another call" when the backend's own count reached the per-minute or per-day limit for that model, or
  when Groq answered `429` (the key then rests for the time Groq names), or `401` / `403` (the key then rests for an hour).
- Voice and text are counted separately, because Groq limits each model on its own.
- A gap is fine (`GROQ_API_KEY_1` and `GROQ_API_KEY_3` only). An empty variable is skipped. At most ten keys are read.
- The count is kept in memory per worker and starts empty after a restart or a deploy, so it is an estimate: Groq's own
  `429` is what really stops a key, and the backend then moves to the next one.
- Which key answered is never written to the call log or any other log, and a key never appears in an error.
- Docker Compose passes the ten names listed in `docker-compose.yml`. After you add keys to `.env`, recreate the
  containers so they see them.

**Check Groq's terms.** Groq applies its limits to the account (organization) that owns the keys. Several keys of one
account share one limit; keys from separate accounts do not. Whether using separate accounts this way is allowed is for you
to confirm in Groq's terms, and a provider may restrict accounts it believes are used to get around its limits.

## What the limits really allow

The limits of the free plan for the text model are in tokens as well as requests (read your own in the Groq console, under
the project's limits). The backend counts requests only; Groq's `429` covers the tokens.

| Limit (one key, text model) | Value seen in the console |
| --- | --- |
| Requests per minute / per day | 30 / 1,000 |
| Tokens per minute / per day | 8,000 / 200,000 |

One order call carries the restaurant's menu, so its size grows with the menu. A call with the five-item sample menu used
about 1,500 tokens in and 200 out, so one key allows about 110 such calls a day and four a minute: the **tokens**, not the
requests, are the limit. A real menu of many items is larger. If one request alone is bigger than the per-minute token
limit, no key can take it, and the call fails. Measure the prompt of the real restaurant's menu before the pilot
(`assistant_spike order --restaurant <slug> ...` prints the tokens in and out).

Whisper is limited in requests and in seconds of audio, which a 30-second clip does not come near.

## Check that it works

With the variables in `.env`, one invented sentence goes to Groq and the answer, the time and the tokens are printed. The
keys are never printed.

```bash
python manage.py assistant_spike order --provider groq --locale en --text "two karak tea and one cheese sandwich"
python manage.py assistant_spike order --provider groq --restaurant <slug> --locale ar --text "<an Arabic sentence about that menu>"
python manage.py assistant_spike car --provider groq --locale ar --text "<an Arabic sentence with a place, a plate, a model and a colour>"
```

To compare with Gemini on the same input, repeat the command with `--provider gemini`.

## If something goes wrong

| What you see | Likely cause | What to do |
| --- | --- | --- |
| `AI_PROVIDER=groq needs ...` at start | a key or a model code is missing | add it, and recreate the containers |
| the log shows `all_keys_busy` | every key is at its limit or resting | wait, add a key, or check the limits |
| the log shows `http_401` or `http_403` | the key is wrong, deleted or restricted | create a new key and update both places |
| the log shows `http_400` | a model code is wrong or retired | copy the model code again from the Models page |
| the log shows `http_413` | the request is larger than the model's token limit | a smaller menu in the prompt, or a model with a higher limit |
| the log shows `invalid_output` | the model answered something that does not fit the shape | tell the developer, with the time of the call |

If a key is ever pasted anywhere it should not be (a commit, a screenshot, a message), delete it in the Groq console at
once, create a new one and update `.env` and Render.
