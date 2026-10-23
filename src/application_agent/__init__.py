import asyncio
import sys

from agents import Runner

from application_agent.context import JobSearchContext
from application_agent.job_agents import job_scout
from application_agent.models import SearchResult
from application_agent.preferences import load_preferences, run_setup
from application_agent.profile import get_profile


async def run(force_setup: bool) -> None:
    profile = await get_profile()
    print(f"Profile: {profile.name} - {profile.headline}")

    preferences = None if force_setup else load_preferences()
    if preferences is None:  # first start, or `application-agent setup`
        preferences = run_setup(profile)
    print(f"Looking for: {preferences.employment_type} | {', '.join(preferences.target_roles)}\n")

    context = JobSearchContext(profile=profile, preferences=preferences)
    result = await Runner.run(job_scout, "Find matching jobs for me.", context=context)
    search: SearchResult = result.final_output

    print(f"Strategy: {search.strategy}")
    print(f"{len(context.postings)} postings found in total.\n")

    for pick in search.picks:
        job = context.postings.get(pick.job_id)
        if job is None:  # the model invented an id - never trust LLM output blindly
            print(f"Unknown id {pick.job_id!r}, skipped.")
            continue
        print(f"{job.title} | {job.company} | {job.location}")
        print(f"   Why: {pick.reason}")
        print(f"   {job.url}\n")


def main() -> None:
    # `uv run application-agent setup` re-runs the setup questions.
    force_setup = len(sys.argv) > 1 and sys.argv[1] == "setup"
    asyncio.run(run(force_setup))
