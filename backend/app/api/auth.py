from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import os
import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.auth.store import (
    access_token_for,
    create_session,
    delete_session,
    get_session,
)
from app.core.config import settings


router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

SESSION_COOKIE = "devpilot_session"
OAUTH_STATE_COOKIE = "devpilot_oauth_state"
PKCE_COOKIE = "devpilot_pkce_verifier"


def _get_callback_url(request: Request | None = None) -> str:
    custom = (
        os.getenv("GITHUB_CALLBACK_URL")
        or os.getenv("CALLBACK_URL")
        or getattr(settings, "callback_url", "")
    ).strip()
    if custom:
        return custom
    if request:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.url.netloc
        if host:
            return f"{proto}://{host}/api/auth/github/callback"
    return "http://127.0.0.1:8000/api/auth/github/callback"


def _get_frontend_url(request: Request | None = None) -> str:
    custom = (
        os.getenv("FRONTEND_URL")
        or getattr(settings, "frontend_url", "")
    ).strip()
    if custom:
        return custom.rstrip("/")
    if request:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.url.netloc
        if host:
            return f"{proto}://{host}".rstrip("/")
    return "http://127.0.0.1:5173"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _base64url(secrets.token_bytes(32))

    challenge = _base64url(
        hashlib.sha256(
            verifier.encode("ascii")
        ).digest()
    )

    return verifier, challenge


def _secure_cookie() -> bool:
    return settings.app_env.lower() == "production" or bool(os.getenv("VERCEL"))


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": _secure_cookie(),
        "samesite": "lax",
        "path": "/",
    }


@router.get("/github/login")
async def github_login(request: Request):
    if not settings.github_client_id:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_CLIENT_ID is not configured",
        )

    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()
    callback_url = _get_callback_url(request)

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": callback_url,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": "repo read:user user:email",
    }

    response = RedirectResponse(
        f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}",
        status_code=302,
    )

    cookie_kwargs = _cookie_kwargs()

    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        **cookie_kwargs,
    )

    response.set_cookie(
        PKCE_COOKIE,
        verifier,
        max_age=600,
        **cookie_kwargs,
    )

    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    devpilot_oauth_state: str | None = Cookie(default=None),
    devpilot_pkce_verifier: str | None = Cookie(default=None),
):
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"GitHub authorization failed: {error}",
        )

    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing GitHub authorization code or state",
        )

    if not devpilot_oauth_state or not secrets.compare_digest(
        state,
        devpilot_oauth_state,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth state",
        )

    if not devpilot_pkce_verifier:
        raise HTTPException(
            status_code=400,
            detail="Missing PKCE verifier",
        )

    callback_url = _get_callback_url(request)
    token_payload = {
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "code": code,
        "redirect_uri": callback_url,
        "code_verifier": devpilot_pkce_verifier,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data=token_payload,
            headers={
                "Accept": "application/json",
            },
        )

        token_response.raise_for_status()
        token_data = token_response.json()

        if "error" in token_data:
            raise HTTPException(
                status_code=400,
                detail=token_data.get(
                    "error_description",
                    token_data["error"],
                ),
            )

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")

        if not access_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub did not return an access token",
            )

        user_response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        user_response.raise_for_status()
        github_user = user_response.json()

    now = datetime.now(timezone.utc)

    access_token_expires_at = None
    refresh_token_expires_at = None

    if token_data.get("expires_in"):
        access_token_expires_at = now + timedelta(
            seconds=int(token_data["expires_in"])
        )

    if token_data.get("refresh_token_expires_in"):
        refresh_token_expires_at = now + timedelta(
            seconds=int(token_data["refresh_token_expires_in"])
        )

    session_id = create_session(
        github_user_id=str(github_user["id"]),
        github_login=github_user["login"],
        github_name=github_user.get("name"),
        github_avatar_url=github_user.get("avatar_url"),
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_at=access_token_expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
    )

    frontend_url = _get_frontend_url(request)
    response = RedirectResponse(
        f"{frontend_url}/?auth=success",
        status_code=302,
    )

    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=60 * 60 * 24 * 30,
        **_cookie_kwargs(),
    )

    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(PKCE_COOKIE, path="/")

    return response


@router.get("/me")
async def auth_me(
    request: Request,
    response: Response,
    devpilot_session: str | None = Cookie(default=None),
):
    session_id = devpilot_session
    if not isinstance(session_id, str) or not session_id.strip():
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            session_id = auth_header[7:].strip()
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = request.query_params.get("session_id")

    if not isinstance(session_id, str) or not session_id.strip():
        return {
            "authenticated": False,
            "user": None,
        }

    session = get_session(session_id)

    if not session:
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {
            "authenticated": False,
            "user": None,
        }

    try:
        token = access_token_for(session)
    except HTTPException as e:
        if e.status_code == 401:
            delete_session(session_id)
            response.delete_cookie(SESSION_COOKIE, path="/")
        return {
            "authenticated": False,
            "user": None,
        }
    except Exception:
        return {
            "authenticated": False,
            "user": None,
        }

    if not token:
        return {
            "authenticated": False,
            "user": None,
        }

    return {
        "authenticated": True,
        "user": {
            "id": session.github_user_id,
            "login": session.github_login,
            "name": session.github_name,
            "avatar_url": session.github_avatar_url,
        },
    }


@router.post("/logout")
async def logout(
    response: Response,
    devpilot_session: str | None = Cookie(default=None),
):
    if devpilot_session:
        delete_session(devpilot_session)

    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
    )

    return {
        "authenticated": False,
    }



