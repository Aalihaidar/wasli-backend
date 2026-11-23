# ADR 0020: Groq is the main assistant provider, Gemini the second

- Status: accepted
- Date: 2026-11-23

## Context

The assistant layer ([ADR 0010](0010-the-assistant-layer.md)) was built with Gemini first because it takes a voice clip
directly. The Gemini free tier turned out to be too small for the first end-to-end test: the model chosen for it allows
20 requests a day and 5 a minute, and AI Studio may refuse the free tier for a project altogether. Groq's free tier serves
an open text model and Whisper with much larger request limits, so the everyday path moves there and Gemini is kept to
compare answers.

## Decision

- **`AI_PROVIDER=groq` is the main provider.** `assistant/adapters/groq.py` implements the same four calls as the other
  adapters. A voice note is two requests: Whisper writes the words (the audio is sent and dropped, never stored), then the
  text model understands the text. What was heard is Whisper's text, kept as the message's transcript. A clip with no words
  understands nothing without a second request. The chat answer is requested in JSON mode with the JSON shape in the prompt
  and then validated with the same pydantic models as every provider; anything that does not fit is `invalid_output`. The
  model codes are settings, never written in the code. No automatic retry of a failed call.
- **Gemini stays configured** (`AI_PROVIDER=gemini`, or `--provider gemini` in `assistant_spike` for one run) so the same
  input can be sent to both and compared when an answer looks wrong. The prompts and the JSON shapes
  (`assistant/adapters/schemas.py`) are shared.
- **Numbered keys, used in order** (`GROQ_API_KEY_1` to `GROQ_API_KEY_10`, `assistant/keys.py`). The first key is used until
  it cannot take another call, then the second, and so on, and back to the first: the scan always starts at key 1. A key
  cannot take a call when its count for the minute or the day (per key and per model, from the limits in the settings) is
  full, when Groq answered `429` (it then rests for the time Groq names) or `401` / `403` (it rests for an hour). Within one
  request the next key is tried at once. With no key left the call is `rate_limited` (`all_keys_busy`) and the conversation
  turns the assistant off for five minutes and offers the item picker.
- **Counting.** Groq keys count requests in the cache (a fixed minute and day, per key and per model), an estimate that is
  per worker and empty after a restart; Groq's own `429` is the safety net. Gemini counts the day's rows of the call log
  since midnight Pacific against `GEMINI_DAILY_REQUEST_LIMIT` (default 18, under Google's 20), which is exact across workers.
  A call refused by the backend is logged as `budget_exceeded` and never sent.
- **Nothing sensitive is kept.** A key is never written to a log, the call log or an error (the HTTP library's exceptions are
  re-raised without their cause), and which key answered is not recorded.

## Consequences

- The free text model limit is in tokens as well as requests (8,000 a minute and 200,000 a day per key when this was
  written), and a call carries the whole menu, so a large menu uses the tokens fast and one request over the per-minute
  limit cannot be served by any key. The real restaurant's prompt size has to be measured before the pilot; shortening the
  ids in the prompt is the first remedy if it is too large. The backend counts requests only.
- Groq applies its limits per account, so several keys of one account share a limit; keys from separate accounts do not, and
  whether that use is allowed is for the owner to confirm in Groq's terms. Rotation also keeps the service running when one
  key is revoked.
- Arabic quality of Whisper and of an open text model on mixed Arabic and English input, and on noisy car audio, is not known
  until it is measured with real clips; the spec's benchmark of 30 to 50 clips decides between the providers.
- The call log has no field for the key, so a rotation problem is read from the `all_keys_busy` and `http_*` codes.
