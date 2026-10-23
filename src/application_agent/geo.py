"""Geocoding of the user's address - plain code, no LLM involved."""

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent.
HEADERS = {"User-Agent": "application-agent/0.1 (portfolio project)"}


def geocode(address: str) -> tuple[float, float] | None:
    """Return (latitude, longitude) of an address via OpenStreetMap, or None if not found."""
    response = httpx.get(
        NOMINATIM_URL,
        params={"q": address, "format": "json", "limit": 1, "countrycodes": "de"},
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])
