import asyncio
import sys

from agents import Runner, trace

from application_agent.commute import BICYCLE_WARNING
from application_agent.context import JobSearchContext
from application_agent.job_agents import job_scout
from application_agent.letters import save_cover_letter, write_cover_letter
from application_agent.matching import match_jobs
from application_agent.models import CandidateProfile, ScoredJob, SearchPreferences, SearchResult, TravelMode
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

    for number, scored in enumerate(scored_jobs, start=1):
        job, match = scored.job, scored.match
        type_warning = "" if match.fits_employment_type else "  [wrong employment type]"
        fastest = scored.fastest_commute
        commute = f"{fastest[1]} min" if fastest else "? min"
        too_far = fastest is not None and fastest[1] > preferences.max_commute_minutes
        print(f"{number:>2}) {match.score:>3} | {commute:>7} | {job.title} | {job.company}{type_warning}")
        details = ", ".join(f"{mode}: {minutes} min" for mode, minutes in scored.commute_minutes.items())
        print(f"      Commute: {details or 'unknown'}{'  [over your limit]' if too_far else ''}")
        print(f"      {match.summary}")
        if match.red_flags:
            print(f"      Red flags: {'; '.join(match.red_flags)}")
        print(f"      {job.url}\n")

    if TravelMode.BICYCLE in preferences.travel_modes:
        print(f"Note: {BICYCLE_WARNING}")

    await offer_cover_letter(profile, preferences, scored_jobs)


async def offer_cover_letter(
    profile: CandidateProfile, preferences: SearchPreferences, scored_jobs: list[ScoredJob]
) -> None:
    print("\nWrite a cover letter for which job? (number, Enter to skip)")
    answer = input("> ").strip()
    if not (answer.isdigit() and 1 <= int(answer) <= len(scored_jobs)):
        return
    scored = scored_jobs[int(answer) - 1]

    print("Anything the letter should mention? (e.g. 'available from 01.12.', Enter for none)")
    notes = input("> ").strip()

    letter, reviews = await write_cover_letter(profile, preferences, scored, notes)
    path = save_cover_letter(letter, profile, preferences, scored)

    print(f"\n{letter.as_text()}\n")
    last_review = reviews[-1]
    if not last_review.approved:
        print("The reviewer did not approve the final version. Please check:")
        for item in last_review.unsupported_claims + last_review.feedback:
            print(f"  - {item}")
    print(f"\nSaved to {path}")


def main() -> None:
    # `uv run application-agent setup` re-runs the setup questions.
    force_setup = len(sys.argv) > 1 and sys.argv[1] == "setup"
    asyncio.run(run(force_setup))
