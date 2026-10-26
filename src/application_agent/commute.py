"""Commute times from the user's home to job locations via the Google Routes API.

One request per travel mode: origin = home, destinations = all jobs (a "route matrix").
Docs: https://developers.google.com/maps/documentation/routes/compute_route_matrix
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from application_agent.config import GOOGLE_MAPS_API_KEY
from application_agent.models import JobPosting, SearchPreferences, TravelMode

ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
# The field mask tells Google which response fields to return (required by the API).
FIELD_MASK = "originIndex,destinationIndex,duration,condition"
GOOGLE_TRAVEL_MODES = {
    TravelMode.CAR: "DRIVE",
    TravelMode.BICYCLE: "BICYCLE",
    TravelMode.TRANSIT: "TRANSIT",
}
# Google's terms require showing this for bicycle routes (beta).
BICYCLE_WARNING = "Bicycle routes are in beta and might sometimes lack clear bicycling paths."


def _next_workday_7am() -> datetime:
    """Typical commute departure: next Monday-Friday at 07:00 German time."""
    berlin = ZoneInfo("Europe/Berlin")
    day = datetime.now(berlin).date() + timedelta(days=1)
    while day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        day += timedelta(days=1)
    return datetime.combine(day, time(7, 0), tzinfo=berlin)


def _waypoint(latitude: float, longitude: float) -> dict:
    return {"waypoint": {"location": {"latLng": {"latitude": latitude, "longitude": longitude}}}}


async def _route_matrix(
    client: httpx.AsyncClient, home: dict, jobs: list[JobPosting], mode: TravelMode
) -> dict[str, int]:
    """Return {job id: minutes} for one travel mode."""
    body = {
        "origins": [home],
        "destinations": [_waypoint(job.latitude, job.longitude) for job in jobs if job.latitude is not None and job.longitude is not None],
        "travelMode": GOOGLE_TRAVEL_MODES[mode],
    }
    if mode == TravelMode.TRANSIT:
        # Without a departure time Google uses "now" - at night there would hardly be any trains.
        body["departureTime"] = _next_workday_7am().isoformat()

    response = await client.post(ROUTE_MATRIX_URL, json=body)
    response.raise_for_status()

    minutes = {}
    # Elements come back in arbitrary order - destinationIndex maps them to our jobs.
    for element in response.json():
        if element.get("condition") == "ROUTE_EXISTS" and "duration" in element:
            seconds = int(element["duration"].rstrip("s"))  # e.g. "2016s"
            minutes[jobs[element["destinationIndex"]].id] = round(seconds / 60)
    return minutes


async def compute_commutes(
    preferences: SearchPreferences, jobs: list[JobPosting]
) -> dict[str, dict[TravelMode, int]]:
    """Return {job id: {travel mode: minutes}} for all jobs with known coordinates."""
    if not GOOGLE_MAPS_API_KEY or preferences.home_latitude is None or preferences.home_longitude is None:
        print("No Google Maps API key or home coordinates - commute times are not available.")
        return {}

    jobs_with_location = [job for job in jobs if job.latitude is not None and job.longitude is not None]
    if not jobs_with_location:
        return {}

    home = _waypoint(preferences.home_latitude, preferences.home_longitude)
    headers = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY, "X-Goog-FieldMask": FIELD_MASK}
    commutes: dict[str, dict[TravelMode, int]] = {job.id: {} for job in jobs_with_location}

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        for mode in preferences.travel_modes:
            try:
                minutes_by_job = await _route_matrix(client, home, jobs_with_location, mode)
            except httpx.HTTPError as exc:
                print(f"Commute calculation for {mode} failed: {exc}")
                continue
            for job_id, minutes in minutes_by_job.items():
                commutes[job_id][mode] = minutes
    return commutes
