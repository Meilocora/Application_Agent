"""Shared fixtures. pytest loads this file automatically - its fixtures are available in every
test file without an import."""

from datetime import datetime
from types import ModuleType

import pytest
from agents import set_tracing_disabled


@pytest.fixture(autouse=True, scope="session")
def no_tracing():
    """config.py loads .env, so the real OpenAI key is active during tests. Without this, the
    Agents SDK would upload a trace of every test run to the OpenAI dashboard."""
    set_tracing_disabled(True)


@pytest.fixture
def freeze_time(monkeypatch):
    """Returns a function that makes ``datetime.now()`` inside one module return a fixed time.

    Usage in a test:  freeze_time(storage, "2026-10-01T08:00:00")
    Patch the module that *uses* datetime - see the note on DB_PATH in test_storage.py.
    """

    def freeze(module: ModuleType, iso: str) -> None:
        frozen = datetime.fromisoformat(iso)

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                # now(tz) converts to that time zone, like the real datetime.now(tz) does.
                return frozen.astimezone(tz) if tz else frozen

        monkeypatch.setattr(module, "datetime", FrozenDatetime)

    return freeze
