# ADR 0015: A restaurant's service distance replaces the parking lot

- Status: accepted
- Date: 2026-11-20
- Changes: the "Range" rule of [ADR 0008](0008-public-visibility-and-flags.md) and the parking-lot part of the first data model.

## Context

The first design put restaurants in a `ParkingLot` (a centre and a radius) and listed a restaurant when the customer was
within the lot's radius. A restaurant had to belong to a lot, even when its customers park in the street, and a lot was a
record to enter before the restaurant.

The owner decided that customers may park anywhere. A restaurant has its own location and, if it wants, a distance it
serves. The customer says where the car is, the app sends the phone's position, and the restaurant sees both on a map and
accepts or rejects the order, with a reason such as "too far".

## Decision

- `ParkingLot` and `Restaurant.parking_lot` are removed. `Restaurant.service_radius_m` is added: optional, a positive number
  of metres, empty meaning no limit of its own. The migration copies each existing lot's radius to its restaurants first.
- **Nearby.** A restaurant is listed when the customer is within the platform search distance of it
  (`NEARBY_SEARCH_RADIUS_M`, default 3,000 m) and, when it has a `service_radius_m`, within that too. The smaller of the two
  applies, so a restaurant with no service distance is listed everywhere inside the search distance. `distance_m` is the
  distance to the restaurant. `nearest` is unchanged: the closest visible restaurant when none serves the point.
- **The order's distance label.** The only stored distance is `distance_m`, from the customer to the restaurant (the
  separate `lot_distance_m` is removed). `distance_band` keeps its four values: `in_lot` now means within the restaurant's
  service distance, `near` up to three times it, `far` beyond, `unknown` without a position. A restaurant with no service
  distance is measured against a reference of 300 m (`DEFAULT_BAND_RADIUS_M`) for the label only. The name `in_lot` is kept
  because the apps already use it.
- **Nothing refuses an order for its distance.** The restaurant sees the distance, the label and a map and decides. When
  `LOCATION_CHECK=enforce` is built (the product, later), an order outside the service distance is refused with
  `outside_service_distance` (it was named `outside_parking_lot`); a restaurant with no service distance has nothing to
  enforce.
- **Where the customer is parked** comes from two things: the free answer to the chat's car question (`parking_note`) and the
  position the app sends. The staff order shows both.
- **Reject reasons.** The list is unchanged, and the note stays optional except for `other`. The code `item_unavailable` is
  worded "Part of the order is finished or unavailable", so it covers an item that has run out.
- **Contract.** `parking_lot` is removed from the restaurant detail and from `nearest` (and is not part of the future staff
  `me`); `service_radius_m` is an optional integer, absent when the restaurant sets none. This is a breaking change,
  labelled as such; nothing is released and both apps pin by commit, so they adapt in their next pin.

## Consequences

- No parking lot has to be entered before a restaurant. Restaurants that stand near each other no longer share a record:
  each is listed by its own distance, which gives the same result for a customer in the middle.
- The customer app's "Simulate: I'm at the restaurant" button uses the restaurant's own position from `nearest`, and the
  restaurant app can draw the service distance as a circle around the restaurant.
- A new setting, `NEARBY_SEARCH_RADIUS_M`, goes in `.env.example` and `docker-compose.yml`.
- The migration is not reversible, because the lots are deleted.
