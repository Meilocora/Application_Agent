"""Domain models shared across the application."""

from pydantic import BaseModel


class JobPosting(BaseModel):
    """A job ad in our own format, independent of the job board it came from."""

    id: str
    title: str
    company: str
    location: str = ""
    url: str = ""
    description: str = ""
    remote: bool | None = None
    published: str | None = None
