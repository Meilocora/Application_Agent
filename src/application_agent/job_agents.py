"""Agent definitions."""

from agents import Agent

from application_agent.config import FAST_MODEL
from application_agent.tools import search_arbeitsagentur

job_scout = Agent(
    name="Job Scout",
    model=FAST_MODEL,
    tools=[search_arbeitsagentur],
    instructions=(
        "You are an experienced recruiter searching jobs for a candidate.\n"
        "1. Search with several different short keywords (German AND English), since job boards "
        "only match literal terms. Think of synonyms and related job titles.\n"
        "2. Pick the 3 best matching postings from all results and explain in one sentence each "
        "why they fit. Mention each posting's id in square brackets."
    ),
)
