# ADR 0010: The assistant layer

- Status: accepted
- Date: 2026-11-10

## Context

Customers write or speak their order in Arabic, English or a mix, and the car answer arrives as one free sentence. A
language model understands that far better than rules do. But the model must never write what the customer reads, never
see or invent a price, and never create an order. The first version also runs on a provider's free tier, where content may
be used by the provider, so no real customer data may reach it, and every call counts against a small daily quota.

## Decision

- **One interface.** `AssistantAdapter` (`assistant/adapters/base.py`) has four functions: `parse_order`, `classify_reply`,
  `extract_car_details` and `transcribe`. `AI_PROVIDER` chooses `fake` or `gemini`; the Gemini model is the setting
  `GEMINI_MODEL`, never written in code, because models are renamed and retired. Another provider is another adapter.
- **The assistant only understands.** It returns structured data: order changes, an intent, car fields or a transcript. The
  server validates every id against this restaurant's menu, prices the order and writes every reply.
- **Input.** `parse_order` receives only this restaurant's menu (ids, names in both languages, aliases, options and their
  availability) and the current lines. The menu carries no price. Nothing else about the customer is sent: no phone number,
  no name, no position.
- **Output is validated twice.** The provider is asked for JSON in its schema mode (hand-written schemas, because that
  mode takes a small subset), then every answer is validated against pydantic models (`assistant/types.py`). Anything that
  does not fit (an unknown intent, a quantity above 20, an `add` without an item, a `confirm` with actions) is an
  `invalid_output` failure, never data.
- **Prompt injection.** Every prompt states that the customer's words are data and never instructions. A typed message is
  placed inside a `<customer_message>` block and a closing tag typed by the customer is removed, so it cannot end the
  block; audio is attached as audio.
- **Caps before any call.** Text up to 500 characters; audio up to 5 MB, 60 seconds (30 at first) and a type the provider accepts. An
  input over a cap is refused before it is sent.
- **One log row per call, never content.** `assistant.services.Assistant` writes an `AICallLog` row with the provider, the
  model, the purpose, the input kind, the latency, the tokens and the outcome. A failure keeps a short code
  (`timeout`, `rate_limited`, `invalid_output`, `http_503`); the provider's message, which could echo what was sent, is
  dropped, and so is the text of an unexpected exception.
- **No retry inside a customer's request.** A call that fails raises an `AssistantError` and the conversation uses its
  no-assistant path (the item picker, one car question at a time). The timeout is `AI_TIMEOUT_SECONDS`.
- **Tests never reach a provider.** The fake adapter replays recorded outputs (the spec's English and Arabic car answers, a
  confirm, an edit, a transcript), a test scripts anything else, and a test can make a call fail. The test settings use it
  whatever `AI_PROVIDER` says.
- **A developer spike.** `python manage.py assistant_spike` sends one invented text or one test clip to the configured
  provider and reports the answer, the latency, the tokens and the accepted audio types. It never runs in production.

## Consequences

- The conversation engine (D2) calls `Assistant`, and the daily budget guard and the five minutes after a failure (D3)
  extend `assistant.availability.ai_enabled` and the conversation's `ai_available`; neither changes this interface.
- Gemini's schema mode may reject a schema that the tests accept. The spike with a real key shows it; the adapter and its
  schemas are then adjusted.
- Every call, the spike included, is counted by the budget guard because it is logged.
- Staging uses invented customer data only while the provider's free tier may use content.
