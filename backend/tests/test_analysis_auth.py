from app.api import analysis as analysis_api


def test_patch_generation_forwards_resolved_session(monkeypatch):
    context = {
        "ok": True,
        "keywords": [],
        "selected_file_count": 1,
        "total_context_chars": 12,
    }
    issue = {"number": 7}
    files = [{"path": "src/app.py", "content": "pass"}]
    analysis = {"summary": "A test issue"}
    analysis_result = {"provider": "test", "model": "test"}
    plan = {"files_to_modify": [{"path": "src/app.py"}]}

    monkeypatch.setattr(
        analysis_api,
        "build_issue_pipeline",
        lambda *args: (context, issue, files, analysis_result, analysis),
    )
    monkeypatch.setattr(
        analysis_api,
        "build_plan",
        lambda **kwargs: ({"provider": "test", "model": "test"}, plan),
    )

    file_request = {}

    def get_repository_file(**kwargs):
        file_request.update(kwargs)
        return {"ok": True, "path": "src/app.py", "content": "pass"}

    monkeypatch.setattr(analysis_api, "get_repository_file", get_repository_file)
    monkeypatch.setattr(
        analysis_api,
        "generate_patch",
        lambda **kwargs: {
            "ok": True,
            "patch": {"files": []},
            "diff": {"files_changed": 0, "patches": []},
        },
    )

    analysis_api.patch_repository_issue(
        "owner",
        "repo",
        7,
        devpilot_session="resolved-session-id",
    )

    assert file_request["devpilot_session"] == "resolved-session-id"


def test_expired_session_raises_401(monkeypatch):
    from datetime import datetime, timedelta, timezone
    import pytest
    from fastapi import HTTPException
    from app.auth.store import AuthSession, access_token_for, encrypt

    past = datetime.now(timezone.utc) - timedelta(days=2)
    session = AuthSession(
        id=999,
        session_hash="fake-hash",
        github_user_id="123",
        github_login="tester",
        access_token=encrypt("expired-token"),
        refresh_token=None,
        access_token_expires_at=past,
    )
    with pytest.raises(HTTPException) as exc_info:
        access_token_for(session)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_session_or_env_token_handles_fastapi_cookie_object(monkeypatch):
    from fastapi import Cookie
    from app.api.repositories import _session_or_env_token

    monkeypatch.setenv("GITHUB_TOKEN", "test-env-token")
    cookie_param = Cookie(default=None)
    token = _session_or_env_token(cookie_param)
    assert token == "test-env-token"


def test_auth_me_handles_invalid_or_expired_session():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    response = client.get(
        "/api/auth/me",
        cookies={"devpilot_session": "non-existent-or-expired-session"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert response.json()["user"] is None


def test_access_token_for_handles_sqlite_naive_datetimes():
    from datetime import datetime, timedelta, timezone
    import pytest
    from fastapi import HTTPException
    from app.auth.store import AuthSession, access_token_for, encrypt

    # Test future naive datetime (as read from SQLite without tzinfo)
    future_naive = (datetime.now(timezone.utc) + timedelta(hours=4)).replace(tzinfo=None)
    session_valid = AuthSession(
        id=777,
        session_hash="fake-hash-valid",
        github_user_id="123",
        github_login="tester",
        access_token=encrypt("valid-secret-token"),
        refresh_token=None,
        access_token_expires_at=future_naive,
    )
    token = access_token_for(session_valid)
    assert token == "valid-secret-token"

    # Test past naive datetime (as read from SQLite without tzinfo)
    past_naive = (datetime.now(timezone.utc) - timedelta(hours=4)).replace(tzinfo=None)
    session_expired = AuthSession(
        id=778,
        session_hash="fake-hash-expired",
        github_user_id="123",
        github_login="tester",
        access_token=encrypt("expired-secret-token"),
        refresh_token=None,
        access_token_expires_at=past_naive,
    )
    with pytest.raises(HTTPException) as exc_info:
        access_token_for(session_expired)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_auth_me_succeeds_with_valid_session():
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient
    from main import app
    from app.auth.store import create_session

    future = datetime.now(timezone.utc) + timedelta(hours=4)
    session_id = create_session(
        github_user_id="9999",
        github_login="testuser",
        github_name="Test User",
        github_avatar_url="https://example.com/avatar.png",
        access_token="test-access-token-live",
        refresh_token=None,
        access_token_expires_at=future,
        refresh_token_expires_at=None,
    )

    client = TestClient(app)
    response = client.get(
        "/api/auth/me",
        cookies={"devpilot_session": session_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["user"]["login"] == "testuser"
    assert data["user"]["name"] == "Test User"


def test_token_source_resolution_and_auth_error_distinction(monkeypatch):
    from app.api.repositories import _resolve_token_and_source, _auth_error_detail
    from app.auth.store import create_session, delete_session
    from datetime import datetime, timedelta, timezone

    # 1. Fallback to server GITHUB_TOKEN
    monkeypatch.setenv("GITHUB_TOKEN", "server-pat-1234")
    token, source = _resolve_token_and_source(None)
    assert token == "server-pat-1234"
    assert source == "server_env"
    err_server = _auth_error_detail(401, source, "Bad credentials")
    assert "Server fallback" in err_server
    assert "Bad credentials" in err_server

    # 2. User OAuth session takes precedence
    sess_id = create_session(
        github_user_id="1010",
        github_login="oauth_user",
        github_name="OAuth User",
        github_avatar_url=None,
        access_token="oauth-token-5678",
        refresh_token=None,
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        refresh_token_expires_at=None,
    )
    try:
        tok_session, src_session = _resolve_token_and_source(sess_id)
        assert tok_session == "oauth-token-5678"
        assert src_session == "session"
        err_session = _auth_error_detail(401, src_session)
        assert "Your GitHub OAuth session has expired" in err_session
    finally:
        delete_session(sess_id)


def test_model_configuration_defaults():
    from app.core.config import settings
    assert settings.gemini_model == "gemini-flash-latest"
    assert settings.gemini_fallback_model == "gemini-flash-lite-latest"
    assert settings.groq_model == "qwen/qwen3.8-27b"


def test_database_url_resolution(monkeypatch):
    from app.auth.store import _database_url

    # Real postgresql url
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@ep-cool.neon.tech/neondb")
    assert _database_url() == "postgresql://user:pass@ep-cool.neon.tech/neondb"

    # Placeholder URL should fallback
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:password@host:port/database")
    monkeypatch.delenv("VERCEL", raising=False)
    assert _database_url().startswith("sqlite:///")

    # Vercel fallback without DATABASE_URL
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    assert _database_url() == "sqlite:////tmp/devpilot_auth.db"


def test_oauth_urls_resolution(monkeypatch):
    from app.api.auth import _get_callback_url, _get_frontend_url

    # Defaults
    monkeypatch.delenv("GITHUB_CALLBACK_URL", raising=False)
    monkeypatch.delenv("CALLBACK_URL", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    assert _get_callback_url(None) == "http://127.0.0.1:8000/api/auth/github/callback"
    assert _get_frontend_url(None) == "http://127.0.0.1:5173"

    # Explicit env vars
    monkeypatch.setenv("GITHUB_CALLBACK_URL", "https://devpilot.vercel.app/api/auth/github/callback")
    monkeypatch.setenv("FRONTEND_URL", "https://devpilot.vercel.app")
    assert _get_callback_url(None) == "https://devpilot.vercel.app/api/auth/github/callback"
    assert _get_frontend_url(None) == "https://devpilot.vercel.app"


def test_stateless_session_verification():
    from app.auth.store import create_session, get_session, access_token_for

    # Create session
    raw_token = create_session(
        github_user_id="555",
        github_login="stateless_user",
        github_name="Stateless Test",
        github_avatar_url="https://example.com/avatar.png",
        access_token="gho_stateless_secret_123",
        refresh_token=None,
        access_token_expires_at=None,
        refresh_token_expires_at=None,
    )

    # Verify get_session works
    session = get_session(raw_token)
    assert session is not None
    assert session.github_login == "stateless_user"
    assert access_token_for(session) == "gho_stateless_secret_123"


def test_self_validating_oauth_state():
    import json
    from app.auth.store import encrypt, decrypt

    state_payload = {
        "nonce": "test_nonce_123",
        "verifier": "test_pkce_verifier_abc",
        "ts": 1700000000,
    }
    encrypted_state = encrypt(json.dumps(state_payload))
    assert encrypted_state is not None

    decrypted_state = decrypt(encrypted_state)
    assert decrypted_state is not None
    parsed = json.loads(decrypted_state)
    assert parsed["verifier"] == "test_pkce_verifier_abc"


