"""Tests for the Arbeitsagentur API client.

Three kinds of tests, from fast and isolated to slow and real:
1. Pure functions (_location, _to_posting, _application_url): dict in, value out.
2. HTTP functions (search_jobs, fetch_details) against a fake server (respx).
3. One live test against the real API, skipped by default (`uv run pytest -m live`).
"""

import httpx
import pytest

from application_agent.arbeitsagentur import (
    BASE_URL,
    _application_url,
    _location,
    _to_posting,
    fetch_details,
    search_jobs,
)
from application_agent.models import EmploymentType, JobPosting

REFNR = "10001-1003859205-S"
# base64 of REFNR, written out instead of computed - so the test notices if the encoding changes.
REFNR_BASE64 = "MTAwMDEtMTAwMzg1OTIwNS1T"


def api_item(**overrides) -> dict:
    """One search result as the real API returns it (shortened). Override fields per test."""
    item = {
        "referenznummer": REFNR,
        "stellenangebotsTitel": "Werkstudent Softwareentwicklung (m/w/d)",
        "firma": "BMW AG",
        "homeofficemoeglich": True,
        "datumErsteVeroeffentlichung": "2026-10-01",
        "stellenlokationen": [
            {"adresse": {"ort": "München", "region": "Bayern"}, "breite": 48.17, "laenge": 11.56}
        ],
    }
    return item | overrides


# ---------------------------------------------------------------------------
# 1. Pure functions
# ---------------------------------------------------------------------------


def test_location_joins_city_and_region():
    assert _location(api_item()) == "München, Bayern"


def test_location_uses_only_the_first_of_several_locations():
    item = api_item(stellenlokationen=[{"adresse": {"ort": "Berlin"}}, {"adresse": {"ort": "Hamburg"}}])
    assert _location(item) == "Berlin"


# One test function, run once per value - each run shows up separately in the results.
@pytest.mark.parametrize("locations", [None, [], [{}]], ids=["null", "empty list", "no address"])
def test_location_is_empty_without_address(locations):
    assert _location(api_item(stellenlokationen=locations)) == ""


def test_to_posting_maps_all_fields():
    posting = _to_posting(api_item())

    assert posting == JobPosting(
        id=REFNR,
        title="Werkstudent Softwareentwicklung (m/w/d)",
        company="BMW AG",
        location="München, Bayern",
        url=f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{REFNR}",
        remote=True,
        published="2026-10-01",
        latitude=48.17,
        longitude=11.56,
    )


def test_to_posting_survives_missing_optional_fields():
    # Only the reference number is guaranteed - everything else can be missing in real data.
    posting = _to_posting({"referenznummer": REFNR})

    assert posting.company == "unbekannt"
    assert posting.title == ""
    assert posting.location == ""
    assert posting.latitude is None
    # The search never knows the application link - only fetch_details fills it in.
    assert posting.application_url == ""


def test_application_url_prefers_externe_url():
    details = {"externeURL": "https://jobs.example.com/123"}
    description = "[Zum Bewerbungsformular](https://other.example.com)"
    assert _application_url(details, description) == "https://jobs.example.com/123"


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Hier: [Zum Bewerbungsformular](https://a.example.com/form)", "https://a.example.com/form"),
        ("[Jetzt BEWERBEN](https://b.example.com)", "https://b.example.com"),  # case-insensitive
        ("[Apply now](https://c.example.com)", "https://c.example.com"),
        ("[Unsere Website](https://www.example.com)", ""),  # a link, but not for applying
        ("Bewerbung bitte an jobs@example.com", ""),  # no link at all
        ("", ""),
    ],
)
def test_application_url_from_description(description, expected):
    assert _application_url({}, description) == expected


def test_application_url_ignores_partner_homepage():
    # allianzpartnerUrl is only the partner's homepage, e.g. "www.bosch.de" - no application page.
    assert _application_url({"allianzpartnerUrl": "www.bosch.de"}, "") == ""


# ---------------------------------------------------------------------------
# 2. HTTP functions against a fake server
#
# `respx_mock` is a pytest fixture from respx: while the test runs, it intercepts every
# request httpx makes. Mocked routes answer with what we define; any other request
# fails the test - so these tests can never reach the real API by accident.
# ---------------------------------------------------------------------------

SEARCH_URL = f"{BASE_URL}/pc/v6/jobs"


async def test_search_jobs_returns_postings(respx_mock):
    respx_mock.get(SEARCH_URL).respond(json={"ergebnisliste": [api_item(), api_item(referenznummer="2")]})

    jobs = await search_jobs("Python")

    assert [job.id for job in jobs] == [REFNR, "2"]
    assert jobs[0].company == "BMW AG"


async def test_search_jobs_sends_query_and_api_key(respx_mock):
    route = respx_mock.get(SEARCH_URL).respond(json={"ergebnisliste": []})

    await search_jobs("Python Entwickler", size=25)

    request = route.calls.last.request  # the request our code actually sent
    assert request.headers["X-API-Key"] == "jobboerse-jobsuche"
    assert request.url.params["was"] == "Python Entwickler"
    assert request.url.params["size"] == "25"  # URL parameters are always strings


async def test_search_jobs_without_where_is_nationwide(respx_mock):
    route = respx_mock.get(SEARCH_URL).respond(json={"ergebnisliste": []})

    await search_jobs("Python", where=None)

    params = route.calls.last.request.url.params
    assert "wo" not in params
    assert "umkreis" not in params


async def test_search_jobs_with_where_sends_radius(respx_mock):
    route = respx_mock.get(SEARCH_URL).respond(json={"ergebnisliste": []})

    await search_jobs("Python", where="80331", radius_km=15)

    params = route.calls.last.request.url.params
    assert params["wo"] == "80331"
    assert params["umkreis"] == "15"


@pytest.mark.parametrize(
    ("employment_type", "angebotsart", "arbeitszeit"),
    [
        (EmploymentType.FULL_TIME, "1", "vz"),
        (EmploymentType.PART_TIME, "1", "tz"),
        (EmploymentType.WORKING_STUDENT, "34", None),
        (EmploymentType.INTERNSHIP, "34", None),
    ],
)
async def test_search_jobs_employment_filters(respx_mock, employment_type, angebotsart, arbeitszeit):
    route = respx_mock.get(SEARCH_URL).respond(json={"ergebnisliste": []})

    await search_jobs("Python", employment_type=employment_type)

    params = route.calls.last.request.url.params
    assert params["angebotsart"] == angebotsart
    assert params.get("arbeitszeit") == arbeitszeit


async def test_search_jobs_handles_response_without_results(respx_mock):
    # Without hits, the API leaves out "ergebnisliste" entirely instead of sending [].
    respx_mock.get(SEARCH_URL).respond(json={"maxErgebnisse": 0})

    assert await search_jobs("Gibtsnicht") == []


async def test_search_jobs_raises_on_server_error(respx_mock):
    respx_mock.get(SEARCH_URL).respond(status_code=503)

    # The test passes only if exactly this exception is raised inside the block.
    # The tool in tools.py catches it and tells the model - see search_arbeitsagentur.
    with pytest.raises(httpx.HTTPStatusError):
        await search_jobs("Python")


async def test_fetch_details_adds_description_and_application_url(respx_mock):
    route = respx_mock.get(f"{BASE_URL}/pc/v4/jobdetails/{REFNR_BASE64}").respond(
        json={"stellenangebotsBeschreibung": "Full ad text", "externeURL": "https://jobs.example.com/1"}
    )
    job = _to_posting(api_item())

    detailed = await fetch_details(job)

    assert route.called  # proves the reference number was base64-encoded in the URL
    assert detailed.description == "Full ad text"
    assert detailed.application_url == "https://jobs.example.com/1"
    assert detailed.title == job.title  # everything else is kept


async def test_fetch_details_does_not_change_the_original(respx_mock):
    respx_mock.get(f"{BASE_URL}/pc/v4/jobdetails/{REFNR_BASE64}").respond(
        json={"stellenangebotsBeschreibung": "Full ad text"}
    )
    job = _to_posting(api_item())

    await fetch_details(job)

    # fetch_details returns a copy (model_copy) - the posting stored in the context stays as it was.
    assert job.description == ""


# ---------------------------------------------------------------------------
# 3. Live test - checks that the real API still looks the way our code expects.
# The mocks above can't notice when the API changes; this test can.
# ---------------------------------------------------------------------------


@pytest.mark.live
async def test_live_api_still_returns_expected_fields():
    jobs = await search_jobs("Entwickler", size=5)
    assert jobs, "the API returned no results for a very common search"
    assert all(job.id and job.title for job in jobs)

    detailed = await fetch_details(jobs[0])
    assert detailed.description, "the details endpoint returned no ad text"
