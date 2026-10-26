"""Tests for the commute time calculation (Google Routes API, mocked with respx).

A bug here doesn't crash anything - it shows plausible but wrong minutes, e.g. the commute of
job A next to job B. That is why the mapping of answers to jobs gets the most tests.
"""

import json

import httpx
import pytest

from application_agent import commute
from application_agent.commute import ROUTE_MATRIX_URL, _next_workday_7am, compute_commutes
from application_agent.models import EmploymentType, JobPosting, SearchPreferences, TravelMode


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch):
    """A fixed key instead of the real one from .env - the tests must not depend on it."""
    monkeypatch.setattr(commute, "GOOGLE_MAPS_API_KEY", "test-key")


def job(job_id: str, latitude: float | None = 48.1, longitude: float | None = 11.5) -> JobPosting:
    return JobPosting(id=job_id, title="Job", company="Firma", latitude=latitude, longitude=longitude)


def preferences(*modes: TravelMode, home: tuple[float, float] | None = (48.0, 11.0)) -> SearchPreferences:
    return SearchPreferences(
        employment_type=EmploymentType.FULL_TIME,
        target_roles=[],
        address="irrelevant",
        travel_modes=list(modes) or [TravelMode.TRANSIT],
        home_latitude=home[0] if home else None,
        home_longitude=home[1] if home else None,
    )


def route(index: int, seconds: int, condition: str = "ROUTE_EXISTS") -> dict:
    """One element of a route matrix answer, as Google sends it."""
    return {"originIndex": 0, "destinationIndex": index, "duration": f"{seconds}s", "condition": condition}


def answer_per_mode(answers: dict[str, list[dict] | int]):
    """respx side effect: answer depending on the travel mode in the request body.

    A list is returned as JSON, an int as an HTTP error status.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        result = answers[json.loads(request.content)["travelMode"]]
        if isinstance(result, int):
            return httpx.Response(result)
        return httpx.Response(200, json=result)

    return handler


# ---------------------------------------------------------------------------
# Mapping Google's answer to our jobs
# ---------------------------------------------------------------------------


async def test_minutes_are_mapped_by_destination_index(respx_mock):
    # Google answers in arbitrary order - here job b (index 1) comes first.
    respx_mock.post(ROUTE_MATRIX_URL).respond(json=[route(1, 600), route(0, 2016)])

    result = await compute_commutes(preferences(), [job("a"), job("b")])

    assert result == {
        "a": {TravelMode.TRANSIT: 34},  # 2016 s = 33.6 min, rounded
        "b": {TravelMode.TRANSIT: 10},
    }


async def test_job_without_coordinates_does_not_shift_the_mapping(respx_mock):
    # x has no coordinates and is not sent - so index 1 in the answer must be b, not x.
    route_mock = respx_mock.post(ROUTE_MATRIX_URL).respond(json=[route(0, 300), route(1, 900)])

    result = await compute_commutes(preferences(), [job("a"), job("x", None, None), job("b")])

    assert result == {"a": {TravelMode.TRANSIT: 5}, "b": {TravelMode.TRANSIT: 15}}
    assert len(json.loads(route_mock.calls.last.request.content)["destinations"]) == 2


async def test_jobs_without_route_get_no_minutes(respx_mock):
    no_duration = {"originIndex": 0, "destinationIndex": 1, "condition": "ROUTE_EXISTS"}
    respx_mock.post(ROUTE_MATRIX_URL).respond(json=[route(0, 600, condition="ROUTE_NOT_FOUND"), no_duration])

    result = await compute_commutes(preferences(), [job("a"), job("b")])

    assert result == {"a": {}, "b": {}}


async def test_several_travel_modes(respx_mock):
    respx_mock.post(ROUTE_MATRIX_URL).mock(
        side_effect=answer_per_mode({"DRIVE": [route(0, 900)], "TRANSIT": [route(0, 1800)]})
    )

    result = await compute_commutes(preferences(TravelMode.CAR, TravelMode.TRANSIT), [job("a")])

    assert result == {"a": {TravelMode.CAR: 15, TravelMode.TRANSIT: 30}}


async def test_one_failing_travel_mode_does_not_stop_the_others(respx_mock):
    respx_mock.post(ROUTE_MATRIX_URL).mock(side_effect=answer_per_mode({"DRIVE": 500, "TRANSIT": [route(0, 1800)]}))

    result = await compute_commutes(preferences(TravelMode.CAR, TravelMode.TRANSIT), [job("a")])

    assert result == {"a": {TravelMode.TRANSIT: 30}}


# ---------------------------------------------------------------------------
# What we send
# ---------------------------------------------------------------------------


async def test_request_contains_key_field_mask_and_mode(respx_mock):
    route_mock = respx_mock.post(ROUTE_MATRIX_URL).respond(json=[])

    await compute_commutes(preferences(TravelMode.BICYCLE), [job("a")])

    request = route_mock.calls.last.request
    assert request.headers["X-Goog-Api-Key"] == "test-key"
    assert request.headers["X-Goog-FieldMask"]  # required by Google, request fails without
    assert json.loads(request.content)["travelMode"] == "BICYCLE"


@pytest.mark.parametrize(("mode", "has_departure_time"), [(TravelMode.TRANSIT, True), (TravelMode.CAR, False)])
async def test_only_transit_gets_a_departure_time(respx_mock, mode, has_departure_time):
    # Without it Google would use "now" - at night there are hardly any trains.
    route_mock = respx_mock.post(ROUTE_MATRIX_URL).respond(json=[])

    await compute_commutes(preferences(mode), [job("a")])

    assert ("departureTime" in json.loads(route_mock.calls.last.request.content)) is has_departure_time


# ---------------------------------------------------------------------------
# When nothing is calculated
#
# respx_mock without any route: if the code sent a request anyway, the test would fail.
# ---------------------------------------------------------------------------


async def test_without_api_key_nothing_is_requested(respx_mock, monkeypatch):
    monkeypatch.setattr(commute, "GOOGLE_MAPS_API_KEY", "")

    assert await compute_commutes(preferences(), [job("a")]) == {}


async def test_without_home_coordinates_nothing_is_requested(respx_mock):
    assert await compute_commutes(preferences(home=None), [job("a")]) == {}


async def test_without_job_coordinates_nothing_is_requested(respx_mock):
    assert await compute_commutes(preferences(), [job("a", None, None)]) == {}


# ---------------------------------------------------------------------------
# Departure time for public transport
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now_utc", "expected"),
    [
        ("2026-10-19T08:00:00+00:00", "2026-10-20T07:00:00+02:00"),  # Monday -> Tuesday
        ("2026-10-22T08:00:00+00:00", "2026-10-23T07:00:00+02:00"),  # Thursday -> Friday
        ("2026-10-23T08:00:00+00:00", "2026-10-26T07:00:00+01:00"),  # Friday -> Monday
        ("2026-10-24T08:00:00+00:00", "2026-10-26T07:00:00+01:00"),  # Saturday -> Monday
        ("2026-10-25T08:00:00+00:00", "2026-10-26T07:00:00+01:00"),  # Sunday -> Monday
        # 23:30 UTC on Friday is already Saturday in Berlin - the German date counts.
        ("2026-10-23T23:30:00+00:00", "2026-10-26T07:00:00+01:00"),
    ],
)
def test_next_workday_7am(freeze_time, now_utc, expected):
    # +02:00 vs. +01:00: summer time ends on 2026-10-25, the offset has to follow.
    freeze_time(commute, now_utc)

    assert _next_workday_7am().isoformat() == expected
