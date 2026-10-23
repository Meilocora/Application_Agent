"""Run context shared by all tools of one agent run.

The SDK hands this object to every tool via ``RunContextWrapper``, but never sends it to
the model. Tools keep the full postings here and only return short summaries to the model.
"""

from dataclasses import dataclass, field

from application_agent.models import CandidateProfile, JobPosting, SearchPreferences


@dataclass
class JobSearchContext:
    profile: CandidateProfile
    preferences: SearchPreferences
    postings: dict[str, JobPosting] = field(default_factory=dict)

    def add_postings(self, postings: list[JobPosting]) -> list[JobPosting]:
        """Store postings and return only those not seen before in this run."""
        new = [posting for posting in postings if posting.id not in self.postings] # only keep new postings
        for posting in new:
            self.postings[posting.id] = posting
        return new
