"""Distance and location helpers. Plain haversine, no PostGIS."""

import math
from enum import StrEnum

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius


class DistanceBand(StrEnum):
    """How far a customer is from a restaurant's parking lot, for the restaurant's screen."""

    IN_LOT = "in_lot"
    NEAR = "near"
    FAR = "far"
    UNKNOWN = "unknown"


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


def distance_band(lot_distance_m: float | None, radius_m: int) -> DistanceBand:
    """Band of a distance to the parking lot centre: within the radius, up to 3x, or farther."""
    if lot_distance_m is None:
        return DistanceBand.UNKNOWN
    if lot_distance_m <= radius_m:
        return DistanceBand.IN_LOT
    if lot_distance_m <= 3 * radius_m:
        return DistanceBand.NEAR
    return DistanceBand.FAR
