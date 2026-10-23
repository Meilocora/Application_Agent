"""Function tools the agents can call.

The docstring and type hints of each tool are sent to the model: they ARE the tool's
documentation, from which the model decides when and how to call it.
"""

import httpx
from agents import function_tool

from application_agent.arbeitsagentur import search_jobs


@function_tool
async def search_arbeitsagentur(what: str, where: str | None = None, radius_km: int = 30) -> str:
    """Search the job board of the German Bundesagentur fuer Arbeit (largest job board in Germany).

    Args:
        what: Job title or keyword in German or English, e.g. "Python Entwickler". Keep it short (1-3 words).
        where: City or postal code. Use null for a nationwide search.
        radius_km: Search radius around `where` in km.
    """
    try:
        jobs = await search_jobs(what, where, radius_km)
    except httpx.HTTPError as exc:
        # Returned to the model as text, so it can react (e.g. retry with other keywords).
        return f"Error calling the Arbeitsagentur API: {exc}"

    if not jobs:
        return "No results."
    return "\n".join(f"[{job.id}] {job.title} | {job.company} | {job.location}" for job in jobs)
