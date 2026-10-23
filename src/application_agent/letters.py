"""Write cover letters with a writer/reviewer loop and save them to disk."""

import re
from datetime import date
from pathlib import Path

from agents import Runner, trace

from application_agent.config import DATA_DIR, MAX_REVISIONS
from application_agent.job_agents import letter_reviewer, letter_writer
from application_agent.matching import MAX_DESCRIPTION_CHARS, PRIVATE_FIELDS
from application_agent.models import CandidateProfile, CoverLetter, LetterReview, ScoredJob, SearchPreferences

OUTPUT_DIR = DATA_DIR / "output"


def _profile_block(profile: CandidateProfile) -> str:
    return f"<candidate_profile>\n{profile.model_dump_json(indent=1)}\n</candidate_profile>"


def _posting_block(scored: ScoredJob) -> str:
    job = scored.job
    return (
        f"<job_posting>\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n\n"
        f"{job.description[:MAX_DESCRIPTION_CHARS]}\n</job_posting>"
    )


async def write_cover_letter(
    profile: CandidateProfile, preferences: SearchPreferences, scored: ScoredJob, notes: str = ""
) -> tuple[CoverLetter, list[LetterReview]]:
    """Draft a letter, then review and revise it until approved or MAX_REVISIONS is reached."""
    wishes = preferences.model_dump_json(indent=1, exclude=PRIVATE_FIELDS)
    writer_input = (
        f"{_profile_block(profile)}\n\n"
        f"<candidate_wishes>\n{wishes}\n</candidate_wishes>\n\n"
        f"{_posting_block(scored)}\n\n"
        # The matcher's analysis tells the writer which strengths to emphasise.
        f"<match_analysis>\n{scored.match.model_dump_json(indent=1)}\n</match_analysis>\n\n"
        f"Additional notes from the candidate: {notes or '(none)'}"
    )

    reviews: list[LetterReview] = []
    with trace("Cover letter"):
        print("Writing first draft ...")
        letter: CoverLetter = (await Runner.run(letter_writer, writer_input)).final_output

        # Every version - including the last revision - is reviewed, so we always know
        # whether the letter that is returned was approved.
        for round_number in range(1, MAX_REVISIONS + 2):
            review_input = (
                f"{_profile_block(profile)}\n\n{_posting_block(scored)}\n\n"
                f"<cover_letter>\n{letter.as_text()}\n</cover_letter>"
            )
            review: LetterReview = (await Runner.run(letter_reviewer, review_input)).final_output
            reviews.append(review)
            print(f"Review {round_number}: {'approved' if review.approved else 'changes requested'}")
            if review.approved or round_number > MAX_REVISIONS:
                break

            revision_input = (
                f"{writer_input}\n\n<previous_draft>\n{letter.as_text()}\n</previous_draft>\n\n"
                f"<review>\n{review.model_dump_json(indent=1)}\n</review>\n\n"
                "Revise the draft and apply the feedback. Remove all unsupported claims."
            )
            letter = (await Runner.run(letter_writer, revision_input)).final_output

    return letter, reviews


def save_cover_letter(
    letter: CoverLetter, profile: CandidateProfile, preferences: SearchPreferences, scored: ScoredJob
) -> Path:
    """Save the letter as text. The sender block is built here, so the address never reaches the LLM."""
    header = "\n".join(
        [
            profile.name,
            preferences.address,
            "",
            scored.job.company,
            scored.job.location,
            "",
            f"{date.today():%d.%m.%Y}",
        ]
    )
    content = f"{header}\n\n{letter.as_text()}\n{profile.name}\n"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Keep only letters, digits, - and _ so the file name is valid on every OS.
    safe_name = re.sub(r"[^\w-]+", "_", f"{scored.job.company}_{scored.job.title}")[:80]
    path = OUTPUT_DIR / f"{safe_name}.txt"
    path.write_text(content, encoding="utf-8")
    return path
