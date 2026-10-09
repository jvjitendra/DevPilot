from __future__ import annotations

import os
import pytest
from app.core.config import settings


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    """Ensure all test suites have safe, hermetic environment defaults."""
    test_session_secret = "devpilot-test-session-secret-key-32-chars-long"
    test_github_token = "ghp_test_github_token_for_unit_tests"

    monkeypatch.setenv("SESSION_SECRET_KEY", test_session_secret)
    monkeypatch.setenv("GITHUB_TOKEN", test_github_token)

    if not settings.session_secret_key:
        monkeypatch.setattr(settings, "session_secret_key", test_session_secret)
