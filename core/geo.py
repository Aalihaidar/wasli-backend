"""Distance and location helpers. Plain haversine, no PostGIS."""

import math
from enum import StrEnum

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius


# The reference distance for the label when a restaurant sets no service distance. It only
# shapes the label shown to staff: nothing is ever refused because of it.
DEFAULT_BAND_RADIUS_M = 300


class DistanceBand(StrEnum):
    """How far a customer is from the restaurant, against the restaurant's service distance,
    for the restaurant's screen. ``in_lot`` is the contract's name for "within the service
    distance": the apps already use it, and renaming it would break them for no gain."""

    IN_LOT = "in_lot"
    NEAR = "near"
    FAR = "far"
    UNKNOWN = "unknown"


# The bands as choices, for the API schema (a list that can grow: ``DistanceBandEnum``).
DISTANCE_BAND_CHOICES = [(band.value, band.value) for band in DistanceBand]


class LocationSource(StrEnum):
    """Where a customer's position came from: the phone's GPS, a position the app made up
    for testing on staging, or none because the customer did not share it."""

    GPS = "gps"
    SIMULATED = "simulated"
    NONE = "none"


LOCATION_SOURCE_CHOICES = [
    (LocationSource.GPS.value, "GPS"),
    (LocationSource.SIMULATED.value, "Simulated"),
    (LocationSource.NONE.value, "Not shared"),
]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two points given in degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def is_valid_location(lat: float, lng: float, accuracy_m: float | None = None) -> bool:
    """Latitude within [-90, 90], longitude within [-180, 180], accuracy zero or more."""
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return False
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return False
    return accuracy_m is None or (math.isfinite(accuracy_m) and accuracy_m >= 0)


def distance_band(
    distance_m: float | None, service_radius_m: int | None = None
) -> DistanceBand:
    """Band of a distance to the restaurant: within its service distance (``in_lot``), up to
    three times it (``near``) or farther (``far``); ``unknown`` without a position.

    A restaurant with no service distance is measured against ``DEFAULT_BAND_RADIUS_M``, so
    the label still tells the staff something. The distance in metres is always shown too.
    """
    if distance_m is None:
        return DistanceBand.UNKNOWN
    radius = DEFAULT_BAND_RADIUS_M if service_radius_m is None else service_radius_m
    if distance_m <= radius:
        return DistanceBand.IN_LOT
    if distance_m <= 3 * radius:
        return DistanceBand.NEAR
    return DistanceBand.FAR
