"""Client for the public job board API of the Bundesagentur fuer Arbeit.

Docs (community-maintained): https://github.com/bundesAPI/jobsuche-api
"""

import base64
import re

import httpx

from application_agent.models import EmploymentType, JobPosting

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
# Public key, identical for everyone and documented in the link above - not a secret.
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}
PUBLIC_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"
# Many ads link their application form in the text, e.g. "[Zum Bewerbungsformular](https://...)".
_APPLY_LINK = re.compile(r"\[[^\]]*(?:bewerb|apply|application)[^\]]*\]\((https?://[^)\s]+)\)", re.IGNORECASE)

# How our employment types map to the API's filters.
# angebotsart: 1 = regular employment, 34 = internship/trainee - the API files almost all
# working student jobs under 34, not 1 (tested 2026-10-23: 24 of 25 results).
# arbeitszeit: tz = part-time.
_EMPLOYMENT_FILTERS: dict[EmploymentType, dict] = {
    EmploymentType.FULL_TIME: {"angebotsart": 1, "arbeitszeit": "vz"},
    EmploymentType.PART_TIME: {"angebotsart": 1, "arbeitszeit": "tz"},
    EmploymentType.WORKING_STUDENT: {"angebotsart": 34},
    EmploymentType.INTERNSHIP: {"angebotsart": 34},
}


def _location(item: dict) -> str:
    """Build 'City, Region' from the first location of an ad (ads can list several)."""
    locations = item.get("stellenlokationen") or []
    if not locations:
        return ""
    address = locations[0].get("adresse", {})
    return ", ".join(part for part in (address.get("ort"), address.get("region")) if part)


def _to_posting(item: dict) -> JobPosting:
    """Translate one result of the API into our own JobPosting format."""
    refnr = item["referenznummer"]
    first_location = (item.get("stellenlokationen") or [{}])[0]
    return JobPosting(
        id=refnr,
        title=item.get("stellenangebotsTitel", ""),
        company=item.get("firma", "unbekannt"),
        location=_location(item),
        url=PUBLIC_DETAIL_URL.format(refnr=refnr),
        remote=item.get("homeofficemoeglich"),
        published=item.get("datumErsteVeroeffentlichung"),
        latitude=first_location.get("breite"),
        longitude=first_location.get("laenge"),
    )


async def search_jobs(
    what: str,
    where: str | None = None,
    radius_km: int = 30,
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
    size: int = 10,
) -> list[JobPosting]:
    """Search job ads on the job board of the Bundesagentur fuer Arbeit."""
    params = {"was": what, "size": size, **_EMPLOYMENT_FILTERS[employment_type]}
    if where:
        params["wo"] = where
        params["umkreis"] = radius_km

    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=20) as client:
        response = await client.get("/pc/v6/jobs", params=params)
    response.raise_for_status()
    return [_to_posting(item) for item in response.json().get("ergebnisliste", [])]


async def fetch_details(job: JobPosting) -> JobPosting:
    """Return a copy of ``job`` with the full ad text (search results don't contain it)."""
    # The API expects the reference number base64-encoded in the URL.
    encoded = base64.b64encode(job.id.encode()).decode()
    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=20) as client:
        response = await client.get(f"/pc/v4/jobdetails/{encoded}")
    response.raise_for_status()
    details = response.json()
    description = details.get("stellenangebotsBeschreibung", "")
    return job.model_copy(
        update={"description": description, "application_url": _application_url(details, description)}
    )


def _application_url(details: dict, description: str) -> str:
    """Link to apply, if the ad has one. Only the details endpoint knows it, not the search."""
    # Set for ads that are hosted elsewhere (about 1 in 6, tested 2026-10-23). Note the
    # spelling "URL". "allianzpartnerUrl" is no alternative: it is just the partner's homepage.
    if details.get("externeURL"):
        return details["externeURL"]
    match = _APPLY_LINK.search(description)
    return match.group(1) if match else ""
