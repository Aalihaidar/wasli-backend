# ADR 0021: A voice clip is read in memory and never stored

- Status: accepted
- Date: 2026-11-23

## Context

A customer can speak an order instead of typing it. The clip is personal data (a voice, and often a place and a car), and the
product's rule is that it is understood and dropped: only what was said stays, as text. The hosting makes this easy to get
wrong: Django writes an upload above 2.5 MB to a temporary file by default, and a handler that only keeps files in memory
silently drops anything above that size.

## Decision

- **`POST /api/v1/conversations/{id}/voice`** takes a multipart request with a `client_message_id` and one `audio` file and
  answers like a message (`201`, the customer's message and the bot's replies, a replay returns the first result). The clip is
  understood like a typed message in the `ordering` step; in any other state it is `409 invalid_action_for_state`.
- **Only WAV for now** (the clip the customer app records), at most 30 seconds and 5 MB, checked on the file itself and not only
  on its declared type (`chat/audio.py`). The refusals are `400` with `unsupported_audio_format`, `audio_too_long` and
  `audio_too_large`; a whole request above 6 MB is refused on `Content-Length` before any view (`audio_too_large`). Other types
  are added once they have been tried with real clips.
- **Never stored.** The clip is read into memory (`chat/uploads.py`, an upload handler used by this endpoint only, which keeps the
  file in memory whatever its size; the request is capped at 6 MB first, so the memory is bounded), passed to the assistant and
  dropped. Nothing of it is kept: not in the message, the payload, the call log or a temporary file. The customer's message is
  stored with `used_voice: true`, an empty `text` and the `transcript`. The Django admin keeps Django's default handlers for its
  images.
- **Understanding failures are not HTTP errors.** A clip with no words (an empty transcript), or one the provider cannot read
  (`http_400`, `413`, `415`, `422`), is stored with an empty transcript and the bot asks again ("I could not hear that"); the
  assistant stays on, because the clip was the problem. An outage, a timeout or a used-up budget is answered in the chat
  ("I cannot understand voice messages right now") and, for an outage, turns `ai_available` off for five minutes like a typed
  message does. A badly formed answer is "not understood".
- **One assistant call per clip.** The provider that takes the clip returns the transcript with the understanding (Gemini in one
  request; Groq in two, Whisper then the text model, logged as one call). The transcript on the message is what the provider
  heard.

## Consequences

- Whisper invents a word for silence or noise: for two seconds of silence it answered "you", with a `no_speech_prob` of 0.70. The Groq adapter asks for the segments and drops those above 0.6, so a clip with no speech is an empty transcript and the bot asks again. The threshold is a starting value for the benchmark on real clips to tune.
- A conversation past `ordering` takes no voice until the car and note steps exist; those steps add their own voice paths.
- If the text model fails after Whisper has heard the clip, the transcript is not kept (the call fails as a whole). Splitting the
  two steps would keep it, at the cost of a second logged call per clip; not needed for now.
- The same endpoint serves every provider, so comparing Groq and Gemini on the same clip is `assistant_spike --audio`.
