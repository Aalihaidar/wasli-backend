# ADR 0014: Arabic names are optional, with an English fallback

- Status: accepted
- Date: 2026-11-20

## Context

Text shown to customers comes as a pair (`name_en`, `name_ar`). Many restaurants in the UAE have an English name and an
English-only menu, and the first real restaurant is one of them. The Arabic name was required on the restaurant, the
category, the item, the option group and the option, so such a restaurant could not be entered without inventing Arabic
text. Typing the English text into the Arabic field would work but loses the difference between a real translation and a
copy, and the copy goes stale when the English text is renamed.

The assistant that understands the customer's order also receives both names, and an Arabic-speaking customer may order from
an English-only menu.

## Decision

- The Arabic **names** of the restaurant, category, item, option group and option are optional (`blank=True`). An empty
  value stays empty in the database. The Arabic descriptions and captions were already optional.
- **The fallback is applied when the text is read**, in one helper (`core.locales.arabic_or_english`, exposed as
  `name_ar_display` on those models and as `description_ar_display` and `caption_ar_display`). The public API returns the
  English text in an empty Arabic field, so `name_ar` stays a required, non-empty string: the contract keeps its shape and
  the apps change nothing. The schema only gains descriptions of those fields.
- Anything that copies a name later uses the display value, not the raw field: the order service (D2) when it snapshots an
  order line, and the conversation engine for the welcome text (the English welcome stands in for a missing Arabic one).
- **The assistant** does not see a made-up or duplicated Arabic name: an entry with no Arabic name has no `name_ar` key in the
  prompt. The parse rules tell it to match by meaning in either language against the English name, the Arabic name and the
  item's aliases, so Arabic speech, Arabic spellings and transliterations of English names resolve to the right entry.
  Aliases are how the platform team adds the Arabic and transliterated names of an English-only menu
  ([`docs/data-entry.md`](../data-entry.md)).

## Consequences

- An Arabic-language customer sees English names for an English-only restaurant, while the bot's own messages stay in
  Arabic. Adding Arabic names later needs no migration and no change in the apps.
- The migration is schema-neutral (only the `blank` flag and help texts change), so deploying it touches no data.
- The matching rule is a prompt change that cannot be proved with the fake adapter. It is checked with the real provider
  by the assistant spike on the real restaurant's menu (`assistant_spike order --restaurant <slug>`), before the engine
  relies on it.
- A new bilingual field must follow the same rule: optional Arabic side, English fallback when read.
