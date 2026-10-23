import asyncio
import sys

from agents import Runner, trace

from application_agent.context import JobSearchContext
from application_agent.job_agents import job_scout
from application_agent.matching import match_jobs
from application_agent.models import SearchResult
from application_agent.preferences import ensure_home_coordinates, load_preferences, run_setup
from application_agent.profile import get_profile


async def run(force_setup: bool) -> None:
    profile = await get_profile()
    print(f"Profile: {profile.name} - {profile.headline}")

    preferences = None if force_setup else load_preferences()
    if preferences is None:  # first start, or `application-agent setup`
        preferences = run_setup(profile)
    preferences = ensure_home_coordinates(preferences)
    print(f"Looking for: {preferences.employment_type} | {', '.join(preferences.target_roles)}\n")

    # One trace for the whole workflow instead of one per agent run.
    with trace("Job search"):
        context = JobSearchContext(profile=profile, preferences=preferences)
        result = await Runner.run(job_scout, "Find matching jobs for me.", context=context)
        search: SearchResult = result.final_output
        print(f"Strategy: {search.strategy}")

        # Drop ids the model may have invented - never trust LLM output blindly.
        shortlist = [context.postings[pick.job_id] for pick in search.picks if pick.job_id in context.postings]
        print(f"{len(context.postings)} postings found, {len(shortlist)} shortlisted. Assessing ...\n")

        scored_jobs = await match_jobs(profile, preferences, shortlist)

    for scored in scored_jobs:
        job, match = scored.job, scored.match
        type_warning = "" if match.fits_employment_type else "  [wrong employment type]"
        distance = f"{scored.distance_km:.0f} km" if scored.distance_km is not None else "? km"
        print(f"{match.score:>3} | {distance:>6} | {job.title} | {job.company}{type_warning}")
        print(f"      {match.summary}")
        if match.red_flags:
            print(f"      Red flags: {'; '.join(match.red_flags)}")
        print(f"      {job.url}\n")


def main() -> None:
    # `uv run application-agent setup` re-runs the setup questions.
    force_setup = len(sys.argv) > 1 and sys.argv[1] == "setup"
    asyncio.run(run(force_setup))
