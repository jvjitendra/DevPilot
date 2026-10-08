from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _database_url() -> str:
    return "sqlite:///./devpilot_auth.db"

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
    secret = settings.session_secret_key.strip()

    if not secret:
        raise RuntimeError("SESSION_SECRET_KEY is not configured")

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
    raw_session_id = secrets.token_urlsafe(48)

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

    with SessionLocal() as db:
        db.add(record)
        db.commit()

    return raw_session_id


def get_session(raw_session_id: str) -> AuthSession | None:
    session_hash = hashlib.sha256(
        raw_session_id.encode("utf-8")
    ).hexdigest()

    with SessionLocal() as db:
        return db.scalar(
            select(AuthSession).where(
                AuthSession.session_hash == session_hash
            )
        )


def delete_session(raw_session_id: str) -> None:
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


def access_token_for(session: AuthSession) -> str:
    value = decrypt(session.access_token)

    if not value:
        raise RuntimeError("Authenticated session has no access token")

    return value