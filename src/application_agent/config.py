"""Central configuration, read from environment variables (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Runs once, on the first import of this module - before any other module reads a setting.
load_dotenv(override=True)

# src/application_agent/config.py -> three levels up is the project root.
ROOT_DIR = Path(__file__).resolve().parents[2]

FAST_MODEL = os.getenv("APP_FAST_MODEL", "gpt-5.4-mini")

# How many postings the scout shortlists, and how many of them are assessed at the same time.
MAX_SHORTLIST = int(os.getenv("APP_MAX_SHORTLIST", "8"))
MAX_PARALLEL_MATCHES = int(os.getenv("APP_MAX_PARALLEL_MATCHES", "4"))

DATA_DIR = Path(os.getenv("APP_DATA_DIR", ROOT_DIR / "data"))
# Your CV, certificates, project descriptions (PDF, Markdown or text).
PROFILE_DIR = Path(os.getenv("APP_PROFILE_DIR", DATA_DIR / "profile"))
