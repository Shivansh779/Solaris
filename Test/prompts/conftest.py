"""Shared fixtures for the prompt-builder test suite.

Modules under test call `system_log`, which appends to System_Logs.txt in the
repo root. Patch it to a no-op so tests never pollute the repo.
"""

import pytest

import _log
import helper_ai
import study_ai
import specialist_ai


@pytest.fixture(autouse=True)
def _noop_system_log(monkeypatch):
    def noop(*args, **kwargs):
        pass

    monkeypatch.setattr(_log, "system_log", noop)
    monkeypatch.setattr(helper_ai, "system_log", noop)
    monkeypatch.setattr(study_ai, "system_log", noop)
    monkeypatch.setattr(specialist_ai, "system_log", noop)