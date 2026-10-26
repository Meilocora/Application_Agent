"""The address from the setup must never reach an LLM.

Every prompt that is built from the preferences is checked for the street, the full address and
the home coordinates. The README promises this - these tests keep the promise.

Note: the CV itself goes to the Profile Extractor as a whole, so whatever address is written in
the CV is sent there. That is outside of what the code can protect.
"""

from types import SimpleNamespace

import pytest
from agents import RunContextWrapper

from application_agent import letters
from application_agent.context import JobSearchContext
from application_agent.job_agents import letter_writer, scout_instructions
from application_agent.matching import _build_input
from application_agent.models import (
    CandidateProfile,
    CoverLetter,
    EmploymentType,
    JobMatch,
    JobPosting,
    LetterReview,
    ScoredJob,
    SearchPreferences,
    TravelMode,
)

ADDRESS = "Geheimweg 7, 80331 München"
LATITUDE, LONGITUDE = 48.137154, 11.576124
# Each of these must not appear in any prompt. Coordinates with many decimals, so a match
# can't happen by chance.
SECRETS = ["Geheimweg", ADDRESS, str(LATITUDE), str(LONGITUDE)]


def assert_no_secrets(prompt: str) -> None:
    for secret in SECRETS:
        assert secret not in prompt, f"{secret!r} was sent to the LLM"


@pytest.fixture
def preferences() -> SearchPreferences:
    return SearchPreferences(
        employment_type=EmploymentType.WORKING_STUDENT,
        target_roles=["Python Entwickler"],
        address=ADDRESS,
        home_latitude=LATITUDE,
        home_longitude=LONGITUDE,
        wishes="remote preferred",
    )


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        name="Alex Example",
        headline="Python developer",
        location="München",
        skills=["Python"],
        languages=["German (native)"],
        experience=[],
        education=[],
        projects=[],
        target_roles=["Python Entwickler"],
    )


@pytest.fixture
def scored() -> ScoredJob:
    job = JobPosting(id="job-1", title="Werkstudent Python", company="Example GmbH", description="Ad text")
    match = JobMatch(
        score=80,
        verdict="good",
        fits_employment_type=True,
        summary="Fits.",
        matching_skills=["Python"],
        missing_skills=[],
        selling_points=[],
        red_flags=[],
    )
    return ScoredJob(job=job, match=match, commute_minutes={TravelMode.TRANSIT: 25})


# ---------------------------------------------------------------------------
# Postal code extraction - the only part of the address the job search gets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("Geheimweg 7, 80331 München", "80331"),
        ("80331 München", "80331"),
        ("Postfach 1234567, 80331 München", "80331"),  # 7 digits are no postal code
        ("Geheimweg 7, München", ""),  # no postal code: nothing, NOT the whole address
    ],
)
def test_search_location_is_only_the_postal_code(address, expected):
    preferences = SearchPreferences(employment_type=EmploymentType.FULL_TIME, target_roles=[], address=address)
    assert preferences.search_location == expected


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_scout_gets_postal_code_but_not_address(preferences, profile):
    wrapper = RunContextWrapper(context=JobSearchContext(profile=profile, preferences=preferences))

    prompt = scout_instructions(wrapper, agent=None)  # type: ignore[arg-type] - agent is unused

    assert_no_secrets(prompt)
    assert "80331" in prompt  # proves the check above looked at a real prompt


def test_matcher_gets_commute_time_but_not_address(preferences, profile, scored):
    prompt = _build_input(profile, preferences, scored.job, scored.commute_minutes)

    assert_no_secrets(prompt)
    assert "public transport: 25 min" in prompt
    assert "remote preferred" in prompt  # the other wishes are still there


class FakeRunner:
    """Stands in for agents.Runner: records every prompt instead of calling the LLM."""

    def __init__(self, approve: bool):
        self.approve = approve
        self.calls: list[tuple[str, str]] = []  # (agent name, prompt)

    async def run(self, agent, prompt):
        self.calls.append((agent.name, prompt))
        if agent is letter_writer:
            output = CoverLetter(subject="Bewerbung", salutation="Hallo,", paragraphs=["Text."], closing="Gruß")
        else:
            output = LetterReview(approved=self.approve, unsupported_claims=[], feedback=[])
        # Runner.run returns a result object - only final_output is used.
        return SimpleNamespace(final_output=output)


async def test_letter_agents_never_get_the_address(monkeypatch, preferences, profile, scored):
    # approve=False: runs every revision round, so every prompt variant is checked.
    runner = FakeRunner(approve=False)
    monkeypatch.setattr(letters, "Runner", runner)

    await letters.write_cover_letter(profile, preferences, scored, notes="available from 01.12.")

    assert runner.calls  # the fake was really used
    for _, prompt in runner.calls:
        assert_no_secrets(prompt)
        assert "Werkstudent Python" in prompt


# ---------------------------------------------------------------------------
# Writer/reviewer loop - while the fake runner is here anyway
# ---------------------------------------------------------------------------


async def test_approved_first_draft_is_not_revised(monkeypatch, preferences, profile, scored):
    runner = FakeRunner(approve=True)
    monkeypatch.setattr(letters, "Runner", runner)

    _, reviews = await letters.write_cover_letter(profile, preferences, scored)

    assert [name for name, _ in runner.calls] == ["Cover Letter Writer", "Cover Letter Reviewer"]
    assert len(reviews) == 1


async def test_unapproved_letter_stops_after_max_revisions(monkeypatch, preferences, profile, scored):
    runner = FakeRunner(approve=False)
    monkeypatch.setattr(letters, "Runner", runner)

    _, reviews = await letters.write_cover_letter(profile, preferences, scored)

    writer_calls = [name for name, _ in runner.calls if name == "Cover Letter Writer"]
    assert len(writer_calls) == 1 + letters.MAX_REVISIONS  # first draft + revisions
    # Every version is reviewed - also the last one, so we know whether it was approved.
    assert len(reviews) == 1 + letters.MAX_REVISIONS
    assert not reviews[-1].approved
