"""Function tools the agents can call.

The docstring and type hints of each tool are sent to the model: they ARE the tool's
documentation, from which the model decides when and how to call it.
"""

import httpx
from agents import RunContextWrapper, function_tool

from application_agent.arbeitsagentur import search_jobs
from application_agent.context import JobSearchContext


@function_tool
async def search_arbeitsagentur(
    wrapper: RunContextWrapper[JobSearchContext],
    what: str,
    where: str | None = None,
) -> str:
    """Search the job board of the German Bundesagentur fuer Arbeit (largest job board in Germany).

    Employment type and search radius are applied automatically from the user's preferences.

    Args:
        what: Job title or keyword in German or English, e.g. "Python Entwickler". Keep it short (1-3 words).
        where: German city name (e.g. "München", not "Munich") or postal code. Use null for a nationwide search.
    """
    # Hard constraints come from the user's preferences, not from the model.
    preferences = wrapper.context.preferences
    try:
        jobs = await search_jobs(what, where, preferences.radius_km, preferences.employment_type)
    except httpx.HTTPError as exc:
        # Returned to the model as text, so it can react (e.g. retry with other keywords).
        return f"Error calling the Arbeitsagentur API: {exc}"

    new_jobs = wrapper.context.add_postings(jobs)
    if not new_jobs:
        return "No new results."
    # "id=..." instead of "[...]": with brackets the model sometimes returned them as part of the id.
    return "\n".join(f"id={job.id} | {job.title} | {job.company} | {job.location}" for job in new_jobs)
