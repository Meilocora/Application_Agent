"""Assess shortlisted postings against the candidate - one matcher run per posting, in parallel."""

import asyncio

from agents import Runner

from application_agent.arbeitsagentur import fetch_details
from application_agent.commute import compute_commutes
from application_agent.config import MAX_PARALLEL_MATCHES
from application_agent.job_agents import job_matcher
from application_agent.models import (
    CandidateProfile,
    JobMatch,
    JobPosting,
    ScoredJob,
    SearchPreferences,
    TravelMode,
)

MAX_DESCRIPTION_CHARS = 8000  # long ads are cut off to limit token costs
# Never sent to the matcher: it only needs the resulting commute times (privacy).
PRIVATE_FIELDS = {"address", "home_latitude", "home_longitude"}


def _commute_text(commute: dict[TravelMode, int]) -> str:
    if not commute:
        return "unknown"
    return ", ".join(f"{mode}: {minutes} min" for mode, minutes in commute.items())


def _build_input(
    profile: CandidateProfile,
    preferences: SearchPreferences,
    job: JobPosting,
    commute: dict[TravelMode, int],
) -> str:
    wishes = preferences.model_dump_json(indent=1, exclude=PRIVATE_FIELDS)
    return (
        f"<candidate_profile>\n{profile.model_dump_json(indent=1)}\n</candidate_profile>\n\n"
        f"<candidate_wishes>\n{wishes}\n</candidate_wishes>\n\n"
        f"Commute from the candidate's home (weekday 7:00): {_commute_text(commute)}\n\n"
        f"<job_posting>\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n\n"
        f"{job.description[:MAX_DESCRIPTION_CHARS]}\n</job_posting>"
    )


async def match_job(
    profile: CandidateProfile,
    preferences: SearchPreferences,
    job: JobPosting,
    commute: dict[TravelMode, int],
) -> ScoredJob:
    detailed_job = await fetch_details(job)
    result = await Runner.run(job_matcher, _build_input(profile, preferences, detailed_job, commute))
    match: JobMatch = result.final_output
    return ScoredJob(job=detailed_job, match=match, commute_minutes=commute)


async def match_jobs(
    profile: CandidateProfile, preferences: SearchPreferences, jobs: list[JobPosting]
) -> list[ScoredJob]:
    """Assess all jobs concurrently and return them sorted by score, best first."""
    # One batch request per travel mode for all jobs, before the individual assessments.
    commutes = await compute_commutes(preferences, jobs)

    # Limits how many matcher runs talk to the APIs at the same time (rate limits, costs).
    semaphore = asyncio.Semaphore(MAX_PARALLEL_MATCHES)

    async def guarded(job: JobPosting) -> ScoredJob | None:
        async with semaphore:
            try:
                return await match_job(profile, preferences, job, commutes.get(job.id, {}))
            except Exception as exc:  # one failing posting must not kill the whole run
                print(f"Could not assess {job.title!r}: {exc}")
                return None

    results = await asyncio.gather(*(guarded(job) for job in jobs))
    scored = [result for result in results if result is not None]
    return sorted(scored, key=lambda s: s.match.score, reverse=True)
