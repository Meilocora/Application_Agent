"""Domain models shared across the application."""

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class EmploymentType(StrEnum):
    FULL_TIME = "full-time"
    PART_TIME = "part-time"
    WORKING_STUDENT = "working student"
    INTERNSHIP = "internship"


class TravelMode(StrEnum):
    CAR = "car"
    BICYCLE = "bicycle"
    TRANSIT = "public transport"


class JobStatus(StrEnum):
    """Where the user stands with a posting - set by the user, never by an LLM."""

    NEW = "new"
    APPLIED = "applied"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    DISMISSED = "dismissed"  # not interested


class SearchPreferences(BaseModel):
    """What the user is looking for - entered by the user in the setup, never by an LLM."""

    employment_type: EmploymentType
    target_roles: list[str]
    # Full address, kept local for commute calculation. Never sent to the LLM.
    address: str
    radius_km: int = 30  # coarse pre-filter for the job board, which only knows km
    travel_modes: list[TravelMode] = Field(default_factory=lambda: [TravelMode.TRANSIT]) # default_factory needed because of mutable default value
    max_commute_minutes: int = 45
    wishes: str = ""
    # Coordinates of the address, geocoded once and cached here. None = not geocoded yet.
    home_latitude: float | None = None
    home_longitude: float | None = None

    @property # Returns the postal code extracted from the full address for privacy.
    def search_location(self) -> str:
        """Only the postal code of the address is used for searching (privacy)."""
        match = re.search(r"\b\d{5}\b", self.address)  # Only the postal code is extracted for privacy.
        return match.group() if match else ""


class JobPosting(BaseModel):
    """A job ad in our own format, independent of the job board it came from."""

    id: str
    title: str
    company: str
    location: str = ""
    url: str = ""  # the ad on the job board
    # Where to apply (employer's career page or application form). Empty if the job board doesn't know.
    application_url: str = ""
    description: str = ""
    remote: bool | None = None
    published: str | None = None
    latitude: float | None = None
    longitude: float | None = None


# ---------------------------------------------------------------------------
# Structured agent outputs. Class docstrings and Field descriptions are sent to
# the model as part of the JSON schema - they are prompt text.
# ---------------------------------------------------------------------------


class JobPick(BaseModel):
    """One posting the scout recommends."""

    job_id: str = Field(description="Id of the posting exactly as returned by a search tool.")
    reason: str = Field(description="One sentence on why this posting fits the candidate.")


class SearchResult(BaseModel):
    """Outcome of a job search run."""

    picks: list[JobPick] = Field(description="Best matching postings, best first.")
    strategy: str = Field(description="Short summary of which searches were run and why.")


class Experience(BaseModel):
    role: str
    organisation: str
    period: str
    highlights: list[str] = Field(description="Concrete achievements and responsibilities.")


class Project(BaseModel):
    name: str
    description: str
    technologies: list[str]


class CandidateProfile(BaseModel):
    """Structured view of the candidate, extracted from CV, certificates and project notes."""

    name: str
    headline: str = Field(description="One-sentence professional summary.")
    location: str
    skills: list[str]
    languages: list[str] = Field(description="Spoken languages incl. level, e.g. 'English (C1)'.")
    experience: list[Experience]
    education: list[str]
    projects: list[Project]
    target_roles: list[str] = Field(
        description="5-8 roles the candidate is a plausible fit for, in German job board wording, "
        "e.g. 'Python Entwickler'. Cover different directions the candidate could take."
    )


class JobMatch(BaseModel):
    """Assessment of how well one posting fits the candidate."""

    score: int = Field(ge=0, le=100, description="Overall fit from 0 to 100.")
    verdict: Literal["very good", "good", "medium", "weak"]
    fits_employment_type: bool = Field(
        description="Whether the posting is the employment type the candidate is looking for."
    )
    summary: str = Field(description="2-3 sentences on why this job fits or not.")
    matching_skills: list[str]
    missing_skills: list[str]
    selling_points: list[str] = Field(
        description="Concrete facts from the profile that should be highlighted in a cover letter."
    )
    red_flags: list[str] = Field(description="E.g. seniority mismatch, language, unwanted tasks.")


class ScoredJob(BaseModel):
    job: JobPosting
    match: JobMatch
    # Commute time in minutes per travel mode; modes without a route are missing.
    commute_minutes: dict[TravelMode, int] = Field(default_factory=dict)

    @property
    def fastest_commute(self) -> tuple[TravelMode, int] | None:
        if not self.commute_minutes:
            return None
        return min(self.commute_minutes.items(), key=lambda item: item[1])


class CoverLetter(BaseModel):
    """A cover letter draft. The sender's address block is added by code, not by the model."""

    subject: str = Field(description="Subject line, e.g. 'Bewerbung als Werkstudent Softwareentwicklung'.")
    salutation: str = Field(description="Use the contact person's name if the posting names one.")
    paragraphs: list[str] = Field(description="3-5 paragraphs of body text.")
    closing: str = Field(description="Only the closing formula, e.g. 'Mit freundlichen Grüßen' - no name.")

    def as_text(self) -> str:
        return "\n\n".join([self.subject, self.salutation, *self.paragraphs, self.closing])


class LetterReview(BaseModel):
    """The reviewer's verdict on a cover letter draft."""

    approved: bool = Field(description="True only if there are no unsupported claims and it is ready to send.")
    unsupported_claims: list[str] = Field(
        description="Factual statements about the candidate that are NOT backed by the profile."
    )
    feedback: list[str] = Field(description="Concrete, actionable improvement suggestions.")
