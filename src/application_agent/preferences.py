"""Interactive setup that asks the user what they are looking for, and its storage."""

import httpx

from application_agent.config import DATA_DIR
from application_agent.geo import geocode
from application_agent.models import CandidateProfile, EmploymentType, SearchPreferences

PREFERENCES_FILE = DATA_DIR / "preferences.json"


def load_preferences() -> SearchPreferences | None:
    if not PREFERENCES_FILE.exists():
        return None
    return SearchPreferences.model_validate_json(PREFERENCES_FILE.read_text(encoding="utf-8"))


def save_preferences(preferences: SearchPreferences) -> None:
    PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCES_FILE.write_text(preferences.model_dump_json(indent=2), encoding="utf-8")


def ensure_home_coordinates(preferences: SearchPreferences) -> SearchPreferences:
    """Geocode the address once and store the coordinates, so it never has to be sent again."""
    if preferences.home_latitude is not None or not preferences.address:
        return preferences
    try:
        coordinates = geocode(preferences.address)
    except httpx.HTTPError as exc:
        print(f"Geocoding failed ({exc}) - distances are not available this time.")
        return preferences
    if coordinates is None:
        print("Address not found - distances are not available. Check it with `application-agent setup`.")
        return preferences

    latitude, longitude = coordinates
    updated = preferences.model_copy(update={"home_latitude": latitude, "home_longitude": longitude})
    save_preferences(updated)
    return updated


def _ask_choice(question: str, options: list[str]) -> int:
    print(question)
    for number, option in enumerate(options, start=1):
        print(f"  {number}) {option}")
    while True:
        answer = input("> ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return int(answer) - 1
        print(f"Please enter a number between 1 and {len(options)}.")


def _ask_roles(suggestions: list[str]) -> list[str]:
    print("\nBased on your profile, these roles were suggested:")
    for number, role in enumerate(suggestions, start=1):
        print(f"  {number}) {role}")
    print("Pick numbers and/or type your own roles, comma-separated (e.g. '2, Python Entwickler'):")
    while True:
        roles = []
        for part in input("> ").split(","):
            part = part.strip()
            if part.isdigit() and 1 <= int(part) <= len(suggestions):
                roles.append(suggestions[int(part) - 1])
            elif part:
                roles.append(part)
        if roles:
            return list(dict.fromkeys(roles))  # removes duplicates, keeps the order
        print("Please choose at least one role.")


def run_setup(profile: CandidateProfile) -> SearchPreferences:
    """Ask the user for their search preferences in the terminal and save them."""
    print("\n=== Setup ===\n")
    types = list(EmploymentType)
    employment_type = types[_ask_choice("What kind of position are you looking for?", types)]

    target_roles = _ask_roles(profile.target_roles)

    print("\nYour address incl. postal code (stays on your machine, used for search and distance):")
    address = input("> ").strip()

    print("\nSearch radius in km [30]:")
    radius = input("> ").strip()

    print("\nAnything else? (e.g. 'remote preferred', 'no ITIL / service management') [none]:")
    wishes = input("> ").strip()

    preferences = SearchPreferences(
        employment_type=employment_type,
        target_roles=target_roles,
        address=address,
        radius_km=int(radius) if radius.isdigit() else 30,
        wishes=wishes,
    )
    save_preferences(preferences)
    print(f"\nSaved to {PREFERENCES_FILE}\n")
    return preferences
