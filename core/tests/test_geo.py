import math

import pytest

from core.geo import (
    DEFAULT_BAND_RADIUS_M,
    DistanceBand,
    distance_band,
    haversine_m,
    is_valid_location,
)


def test_the_distance_between_the_same_point_is_zero() -> None:
    assert haversine_m(25.2048, 55.2708, 25.2048, 55.2708) == 0


def test_one_degree_of_latitude_is_about_111_kilometres() -> None:
    assert haversine_m(0, 0, 1, 0) == pytest.approx(111_195, abs=5)


def test_one_degree_of_longitude_shrinks_towards_the_poles() -> None:
    at_equator = haversine_m(0, 0, 0, 1)
    at_sixty_degrees = haversine_m(60, 0, 60, 1)

    assert at_sixty_degrees == pytest.approx(at_equator / 2, rel=0.01)


def test_the_distance_is_the_same_in_both_directions() -> None:
    forward = haversine_m(25.2048, 55.2708, 25.2100, 55.2800)
    backward = haversine_m(25.2100, 55.2800, 25.2048, 55.2708)

    assert forward == pytest.approx(backward)


@pytest.mark.parametrize(
    ("lat", "lng", "accuracy", "expected"),
    [
        (25.2, 55.3, None, True),
        (25.2, 55.3, 0, True),
        (25.2, 55.3, 12.5, True),
        (90, 180, None, True),
        (-90, -180, None, True),
        (90.1, 0, None, False),
        (-90.1, 0, None, False),
        (0, 180.1, None, False),
        (0, -180.1, None, False),
        (25.2, 55.3, -1, False),
        (math.nan, 55.3, None, False),
        (25.2, math.inf, None, False),
        (25.2, 55.3, math.nan, False),
    ],
)
def test_is_valid_location(
    lat: float, lng: float, accuracy: float | None, expected: bool
) -> None:
    assert is_valid_location(lat, lng, accuracy) is expected


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (None, DistanceBand.UNKNOWN),
        (0, DistanceBand.IN_LOT),
        (300, DistanceBand.IN_LOT),
        (300.1, DistanceBand.NEAR),
        (900, DistanceBand.NEAR),
        (900.1, DistanceBand.FAR),
        (50_000, DistanceBand.FAR),
    ],
)
def test_distance_band_with_a_300_metre_service_distance(
    distance: float | None, expected: DistanceBand
) -> None:
    assert distance_band(distance, 300) == expected


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (None, DistanceBand.UNKNOWN),
        (100, DistanceBand.IN_LOT),
        (101, DistanceBand.NEAR),
        (300, DistanceBand.NEAR),
        (301, DistanceBand.FAR),
    ],
)
def test_distance_band_follows_the_restaurants_own_service_distance(
    distance: float | None, expected: DistanceBand
) -> None:
    assert distance_band(distance, 100) == expected


def test_a_restaurant_with_no_service_distance_is_measured_against_the_default() -> (
    None
):
    assert DEFAULT_BAND_RADIUS_M == 300
    assert distance_band(300, None) == DistanceBand.IN_LOT
    assert distance_band(900, None) == DistanceBand.NEAR
    assert distance_band(901, None) == DistanceBand.FAR
    assert distance_band(None, None) == DistanceBand.UNKNOWN


def test_distance_band_values_are_the_contract_strings() -> None:
    assert [band.value for band in DistanceBand] == ["in_lot", "near", "far", "unknown"]
