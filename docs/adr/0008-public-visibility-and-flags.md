# ADR 0008: What a customer can see, and what the flags mean

- Status: accepted
- Date: 2026-11-10

## Context

The contract lists `is_open` on a nearby restaurant and `ai_enabled` in the configuration, but the data model has no
opening hours, and the assistant layer does not exist yet. The apps need a meaning they can rely on now.

## Decision

- **`is_open`** is true while the restaurant's site polled in the last 60 seconds (`screen_last_seen_at`), because that
  is when the restaurant can receive an order. There is no opening-hours model in the first version.
- **`REQUIRE_SCREEN_ONLINE`** decides whether a restaurant that is not open is hidden from the list (true) or listed with
  `is_open: false` (false). A hidden restaurant is not the `nearest` either.
- **Visibility.** The public endpoints start from the restaurants that are active and whose subscription is not
  suspended (`restaurants.services.public_restaurants`). Any other restaurant is not listed and its page is a `404`.
  Reactivating it makes it visible again.
- **Range.** A restaurant is listed when the customer is within the radius of its parking lot's centre; `distance_m` is the
  distance to the restaurant itself.
- **`ai_enabled`** is true for the fake provider, and for the Gemini provider when its key and model are set. The daily
  request budget and the five minutes after a provider failure are added with the assistant layer.
- `nearby` is a reserved slug, so no restaurant can take the name of a route.

## Consequences

- Real opening hours can be added later without changing the shape: `is_open` would combine them with the screen state.
- Suspending a subscription takes effect on the public endpoints immediately.
