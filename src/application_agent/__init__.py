import asyncio
import sys

from agents import Runner, trace

from application_agent.commute import BICYCLE_WARNING
from application_agent.context import JobSearchContext
from application_agent.documents import save_cover_letter, save_search_report
from application_agent.export import export_excel
from application_agent.job_agents import job_scout
from application_agent.letters import write_cover_letter
from application_agent.matching import match_jobs
from application_agent.models import JobStatus, SearchResult, TravelMode
from application_agent.preferences import ensure_home_coordinates, load_preferences, run_setup
from application_agent.profile import get_profile
from application_agent.storage import load_jobs, save_jobs, set_status

# TODO: Tests
# TODO: KPIs for evaluating workflows
# TODO: Evals, Costs, Latency
# TODO: Monitoring

# TODO: Connect more APIs

# TODO: Gradio UI with password security or comparable
# TODO: Guardrails

# TODO: Search for usefull infos about the company (e.g. impact for a future career, chances for writing a masters thesis)

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
        # Postings assessed in an earlier run are taken from the database instead of paying
        # for a new assessment. Their status (e.g. "applied") is kept.
        known = {stored.scored.job.id: stored.scored for stored in load_jobs([job.id for job in shortlist])}
        to_assess = [job for job in shortlist if job.id not in known]
        print(
            f"{len(context.postings)} postings found, {len(shortlist)} shortlisted "
            f"({len(known)} already assessed earlier). Assessing ...\n"
        )

        new_jobs = await match_jobs(profile, preferences, to_assess)

    save_jobs(new_jobs)
    scored_jobs = sorted([*new_jobs, *known.values()], key=lambda s: s.match.score, reverse=True)

    for number, scored in enumerate(scored_jobs, start=1):
        job, match = scored.job, scored.match
        type_warning = "" if match.fits_employment_type else "  [wrong employment type]"
        fastest = scored.fastest_commute
        commute = f"{fastest[1]} min" if fastest else "? min"
        too_far = fastest is not None and fastest[1] > preferences.max_commute_minutes
        print(f"{number:>2}) {match.score:>3} | {commute:>7} | {job.title} | {job.company}{type_warning}")
        print(f"      ID: {job.id}")
        details = ", ".join(f"{mode}: {minutes} min" for mode, minutes in scored.commute_minutes.items())
        print(f"      Commute: {details or 'unknown'}{'  [over your limit]' if too_far else ''}")
        print(f"      {match.summary}")
        if match.red_flags:
            print(f"      Red flags: {'; '.join(match.red_flags)}")
        print(f"      Apply:  {job.application_url or '(see job ad)'}")
        print(f"      Job ad: {job.url}\n")

    if TravelMode.BICYCLE in preferences.travel_modes:
        print(f"Note: {BICYCLE_WARNING}")

    if scored_jobs:
        new_ids = {scored.job.id for scored in new_jobs}
        print(f"Report of this search: {save_search_report(scored_jobs, new_ids, search.strategy, preferences)}")
    _update_excel()
    print("Write a cover letter with: uv run cover-letter <ID>")
    print("Change the status with:    uv run job-status <ID> applied")


def _update_excel() -> None:
    excel_path = export_excel()
    if excel_path:
        print(f"All postings so far: {excel_path}")
    else:
        print("Could not update the Excel file - close it in Excel and run again.")


async def run_cover_letter(job_id: str) -> None:
    """Separate workflow: write a letter for a posting found in an earlier search run."""
    stored = load_jobs([job_id])
    if not stored:
        sys.exit(f"No posting with ID {job_id!r} in the database. Copy the ID from the Excel file.")
    preferences = load_preferences()
    if preferences is None:  # the sender address comes from the setup
        sys.exit("No preferences yet - run `uv run application-agent setup` first.")
    profile = await get_profile()
    scored = stored[0].scored
    print(f"Cover letter for: {scored.job.title} | {scored.job.company}\n")

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
    print(f"Apply here: {scored.job.application_url or scored.job.url}")


def main() -> None:
    # `uv run application-agent setup` re-runs the setup questions.
    force_setup = len(sys.argv) > 1 and sys.argv[1] == "setup"
    asyncio.run(run(force_setup))


def _argument(index: int, prompt: str) -> str:
    """Command line argument at ``index``, or ask for it if it is missing."""
    value = sys.argv[index] if len(sys.argv) > index else input(prompt)
    # Copied cells sometimes bring spaces or quotes along.
    return value.strip().strip("'\"")


def cover_letter_main() -> None:
    # `uv run cover-letter <ID>`, or without an ID to be asked for it.
    job_id = _argument(1, "Job ID (from the Excel file): ")
    asyncio.run(run_cover_letter(job_id))


def job_status_main() -> None:
    # `uv run job-status <ID> <status>`, missing arguments are asked for.
    statuses = ", ".join(JobStatus)
    job_id = _argument(1, "Job ID (from the Excel file): ")
    value = _argument(2, f"New status ({statuses}): ").lower()
    if value not in JobStatus:
        sys.exit(f"Unknown status {value!r}. Choose one of: {statuses}")
    if not set_status(job_id, JobStatus(value)):
        sys.exit(f"No posting with ID {job_id!r} in the database. Copy the ID from the Excel file.")
    print(f"{job_id} is now '{value}'.")
    _update_excel()
