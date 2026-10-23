"""Central configuration, read from environment variables (.env)."""

import os

from dotenv import load_dotenv

# Runs once, on the first import of this module - before any other module reads a setting.
load_dotenv(override=True)

FAST_MODEL = os.getenv("APP_FAST_MODEL", "gpt-5.4-mini")
