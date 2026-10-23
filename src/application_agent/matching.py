"""Assess shortlisted postings against the candidate - one matcher run per posting, in parallel."""

import asyncio

from agents import Runner

from application_agent.arbeitsagentur import fetch_details
from application_agent.config import MAX_PARALLEL_MATCHES
from application_agent.geo import distance_km
from application_agent.job_agents import job_matcher
from application_agent.models import CandidateProfile, JobMatch, JobPosting, ScoredJob, SearchPreferences

MAX_DESCRIPTION_CHARS = 8000  # long ads are cut off to limit token costs


def _distance(preferences: SearchPreferences, job: JobPosting) -> float | None:
    if None in (preferences.home_latitude, preferences.home_longitude, job.latitude, job.longitude):
        return None
    return distance_km(preferences.home_latitude, preferences.home_longitude, job.latitude, job.longitude)


def _build_input(
    profile: CandidateProfile, preferences: SearchPreferences, job: JobPosting, distance: float | None
) -> str:
    # The address and coordinates are excluded on purpose: the matcher only needs the distance.
    wishes = preferences.model_dump_json(indent=1, exclude={"address", "home_latitude", "home_longitude"})
    distance_text = f"{distance:.0f} km (straight line)" if distance is not None else "unknown"
    return (
        f"<candidate_profile>\n{profile.model_dump_json(indent=1)}\n</candidate_profile>\n\n"
        f"<candidate_wishes>\n{wishes}\n</candidate_wishes>\n\n"
        f"Distance from the candidate's home to the job: {distance_text}\n\n"
        f"<job_posting>\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n\n"
        f"{job.description[:MAX_DESCRIPTION_CHARS]}\n</job_posting>"
    )


async def match_job(profile: CandidateProfile, preferences: SearchPreferences, job: JobPosting) -> ScoredJob:
    detailed_job = await fetch_details(job)
    distance = _distance(preferences, detailed_job)
    result = await Runner.run(job_matcher, _build_input(profile, preferences, detailed_job, distance))
    match: JobMatch = result.final_output
    return ScoredJob(job=detailed_job, match=match, distance_km=distance)


async def match_jobs(
    profile: CandidateProfile, preferences: SearchPreferences, jobs: list[JobPosting]
) -> list[ScoredJob]:
    """Assess all jobs concurrently and return them sorted by score, best first."""
    # Limits how many matcher runs talk to the APIs at the same time (rate limits, costs).
    semaphore = asyncio.Semaphore(MAX_PARALLEL_MATCHES)

    async def guarded(job: JobPosting) -> ScoredJob | None:
        async with semaphore:
            try:
                return await match_job(profile, preferences, job)
            except Exception as exc:  # one failing posting must not kill the whole run
                print(f"Could not assess {job.title!r}: {exc}")
                return None

    results = await asyncio.gather(*(guarded(job) for job in jobs))
    scored = [result for result in results if result is not None]
    return sorted(scored, key=lambda s: s.match.score, reverse=True)
