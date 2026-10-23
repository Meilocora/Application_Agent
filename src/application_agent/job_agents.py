"""Agent definitions."""

from agents import Agent, RunContextWrapper

from application_agent.config import FAST_MODEL
from application_agent.context import JobSearchContext
from application_agent.models import CandidateProfile, SearchResult
from application_agent.tools import search_arbeitsagentur

profile_extractor = Agent(
    name="Profile Extractor",
    model=FAST_MODEL,
    output_type=CandidateProfile,
    instructions=(
        "You extract a structured candidate profile from a CV, job references and project "
        "descriptions. Only use facts stated in the documents - never invent anything. "
        "Condense job references into concrete strengths (as experience highlights). "
        "Derive target_roles and search_keywords realistically from experience and skills."
    ),
)

def scout_instructions(wrapper: RunContextWrapper[JobSearchContext], agent: Agent) -> str:
    """Build the system prompt for each run from profile and preferences in the context."""
    profile = wrapper.context.profile
    prefs = wrapper.context.preferences
    # Note: the full address is deliberately NOT part of the prompt, only the postal code.
    return f"""You are an experienced recruiter searching jobs for this candidate.

What the candidate is looking for (this decides WHAT to search for):
- Employment type: {prefs.employment_type}
- Target roles: {", ".join(prefs.target_roles)}
- Additional wishes: {prefs.wishes or "(none)"}

Candidate background (use it to judge fit, not to pick search terms):
- {profile.name} - {profile.headline}
- Top skills: {", ".join(profile.skills[:15])}

1. Search for the target roles with several short keywords (German AND English), since job
   boards only match literal terms. Also try synonyms of the target roles.
2. For working student or internship positions, put the type into the keyword, e.g.
   "Werkstudent Python" or "Praktikum Softwareentwicklung".
3. Search at postal code {prefs.search_location or profile.location} unless the wishes say otherwise.
4. Pick the 3 best matching postings from all results. Strictly respect the additional wishes.
Only use ids that a search tool returned to you."""


job_scout = Agent[JobSearchContext](
    name="Job Scout",
    model=FAST_MODEL,
    tools=[search_arbeitsagentur],
    output_type=SearchResult,
    instructions=scout_instructions,
)
