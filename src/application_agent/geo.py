"""Geocoding of the user's address and distance calculation - plain code, no LLM involved."""

import math

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent.
HEADERS = {"User-Agent": "application-agent/0.1 (portfolio project)"}
EARTH_RADIUS_KM = 6371.0


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


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance between two coordinates (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
