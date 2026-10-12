from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
import httpx
from fastapi import HTTPException
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings


from pathlib import Path

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _database_url() -> str:
    env_url = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRES_URL_NON_POOLING") or getattr(settings, "database_url", "")).strip()
    is_placeholder = any(
        token in env_url.lower()
        for token in ["@host:", "@host/", "user:password@host", "user:pass@host"]
    )
    if env_url and not is_placeholder:
        if env_url.startswith("postgres://"):
            env_url = env_url.replace("postgres://", "postgresql://", 1)
        return env_url

    if os.getenv("VERCEL"):
        tmp_db = Path("/tmp") / "devpilot_auth.db"
        return f"sqlite:///{tmp_db.as_posix()}"

    backend_dir = Path(__file__).resolve().parent.parent.parent
    db_file = backend_dir / "devpilot_auth.db"
    return f"sqlite:///{db_file.as_posix()}"

DATABASE_URL = _database_url()

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    github_user_id: Mapped[str] = mapped_column(String(64), index=True)
    github_login: Mapped[str] = mapped_column(String(255))
    github_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


def _fernet() -> Fernet:
    secret = (
        settings.session_secret_key
        or os.getenv("SESSION_SECRET_KEY")
        or os.getenv("SESSION_SECRET")
        or getattr(settings, "github_client_secret", "")
        or os.getenv("GITHUB_CLIENT_SECRET", "")
    ).strip()

    if not secret:
        secret = "devpilot-default-session-encryption-key-32b"

    key = hashlib.sha256(secret.encode("utf-8")).digest()
    import base64

    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str | None) -> str | None:
    if value is None:
        return None

    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str | None) -> str | None:
    if value is None:
        return None

    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def init_auth_store() -> None:
    Base.metadata.create_all(bind=engine)


def create_session(
    *,
    github_user_id: str,
    github_login: str,
    github_name: str | None,
    github_avatar_url: str | None,
    access_token: str,
    refresh_token: str | None,
    access_token_expires_at: datetime | None,
    refresh_token_expires_at: datetime | None,
) -> str:
    session_data = {
        "v": 1,
        "nonce": secrets.token_urlsafe(16),
        "user_id": github_user_id,
        "login": github_login,
        "name": github_name,
        "avatar_url": github_avatar_url,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_token_expires_at": access_token_expires_at.isoformat() if access_token_expires_at else None,
        "refresh_token_expires_at": refresh_token_expires_at.isoformat() if refresh_token_expires_at else None,
    }
    raw_session_id = _fernet().encrypt(json.dumps(session_data).encode("utf-8")).decode("utf-8")

    record = AuthSession(
        session_hash=hashlib.sha256(
            raw_session_id.encode("utf-8")
        ).hexdigest(),
        github_user_id=github_user_id,
        github_login=github_login,
        github_name=github_name,
        github_avatar_url=github_avatar_url,
        access_token=encrypt(access_token),
        refresh_token=encrypt(refresh_token),
        access_token_expires_at=access_token_expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
    )

    try:
        with SessionLocal() as db:
            db.add(record)
            db.commit()
    except Exception:
        pass

    return raw_session_id


def get_session(raw_session_id: str | None) -> AuthSession | None:
    if not isinstance(raw_session_id, str) or not raw_session_id.strip():
        return None

    session_hash = hashlib.sha256(
        raw_session_id.encode("utf-8")
    ).hexdigest()

    # 1. Try reading from database
    try:
        with SessionLocal() as db:
            record = db.scalar(
                select(AuthSession).where(
                    AuthSession.session_hash == session_hash
                )
            )
            if record:
                return record
    except Exception:
        pass

    # 2. Stateless fallback: decrypt signed Fernet token directly
    try:
        decrypted_bytes = _fernet().decrypt(raw_session_id.encode("utf-8"))
        data = json.loads(decrypted_bytes.decode("utf-8"))
        if isinstance(data, dict) and data.get("login") and data.get("access_token"):
            access_exp = datetime.fromisoformat(data["access_token_expires_at"]) if data.get("access_token_expires_at") else None
            refresh_exp = datetime.fromisoformat(data["refresh_token_expires_at"]) if data.get("refresh_token_expires_at") else None
            return AuthSession(
                id=0,
                session_hash=session_hash,
                github_user_id=str(data.get("user_id", "")),
                github_login=data["login"],
                github_name=data.get("name"),
                github_avatar_url=data.get("avatar_url"),
                access_token=encrypt(data["access_token"]),
                refresh_token=encrypt(data.get("refresh_token")),
                access_token_expires_at=access_exp,
                refresh_token_expires_at=refresh_exp,
            )
    except Exception:
        pass

    return None


def delete_session(raw_session_id: str | None) -> None:
    if not isinstance(raw_session_id, str) or not raw_session_id.strip():
        return

    session_hash = hashlib.sha256(
        raw_session_id.encode("utf-8")
    ).hexdigest()

    with SessionLocal() as db:
        record = db.scalar(
            select(AuthSession).where(
                AuthSession.session_hash == session_hash
            )
        )

        if record:
            db.delete(record)
            db.commit()


def refresh_session_token(session: AuthSession) -> str | None:
    if not session.refresh_token:
        return None

    if session.refresh_token_expires_at is not None:
        ref_exp = _as_utc(session.refresh_token_expires_at)
        if ref_exp and ref_exp <= utcnow():
            return None

    decrypted_refresh = decrypt(session.refresh_token)
    if not decrypted_refresh:
        return None

    if not settings.github_client_id or not settings.github_client_secret:
        return None

    try:
        response = httpx.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": decrypted_refresh,
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data and not data.get("error"):
                new_access = data["access_token"]
                new_refresh = data.get("refresh_token")
                now = utcnow()
                exp_in = data.get("expires_in")
                ref_exp_in = data.get("refresh_token_expires_in")

                new_access_exp = now + timedelta(seconds=int(exp_in)) if exp_in else None
                new_ref_exp = now + timedelta(seconds=int(ref_exp_in)) if ref_exp_in else None

                with SessionLocal() as db:
                    db_sess = db.get(AuthSession, session.id)
                    if db_sess:
                        db_sess.access_token = encrypt(new_access)
                        if new_refresh:
                            db_sess.refresh_token = encrypt(new_refresh)
                        db_sess.access_token_expires_at = new_access_exp
                        if new_ref_exp:
                            db_sess.refresh_token_expires_at = new_ref_exp
                        db.commit()

                session.access_token = encrypt(new_access)
                if new_refresh:
                    session.refresh_token = encrypt(new_refresh)
                session.access_token_expires_at = new_access_exp
                if new_ref_exp:
                    session.refresh_token_expires_at = new_ref_exp

                return new_access
    except Exception:
        pass

    return None


def access_token_for(session: AuthSession) -> str:
    now = utcnow()
    exp = _as_utc(session.access_token_expires_at)
    if exp is not None and exp <= now:
        refreshed = refresh_session_token(session)
        if refreshed:
            return refreshed
        raise HTTPException(
            status_code=401,
            detail="GitHub session expired. Please sign in again.",
        )

    value = decrypt(session.access_token)
    if not value:
        raise HTTPException(
            status_code=401,
            detail="Authenticated session has no access token. Please sign in again.",
        )

    return value
