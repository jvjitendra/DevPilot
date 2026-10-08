from __future__ import annotations

import secrets
import time
from typing import Any


REVIEW_TTL_SECONDS = 30 * 60
MAX_REVIEW_SESSIONS = 20


_reviews: dict[str, dict[str, Any]] = {}


def _cleanup_expired() -> None:
    now = time.time()

    expired = [
        review_id
        for review_id, session in _reviews.items()
        if now - session["created_at"] > REVIEW_TTL_SECONDS
    ]

    for review_id in expired:
        _reviews.pop(review_id, None)


def create_review(
    *,
    owner: str,
    repo: str,
    repository: str,
    source_branch: str,
    workspace_info: dict[str, Any],
    patch_result: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:

    _cleanup_expired()

    while len(_reviews) >= MAX_REVIEW_SESSIONS:
        oldest_id = min(
            _reviews,
            key=lambda key: _reviews[key]["created_at"],
        )
        _reviews.pop(oldest_id, None)

    review_id = secrets.token_urlsafe(24)

    _reviews[review_id] = {
        "review_id": review_id,
        "owner": owner,
        "repo": repo,
        "repository": repository,
        "source_branch": source_branch,
        "workspace_info": workspace_info,
        "patch_result": patch_result,
        "execution": execution,
        "created_at": time.time(),
    }

    return {
        "review_id": review_id,
        "repository": repository,
        "source_branch": source_branch,
        "status": "ready_for_review",
        "expires_in_seconds": REVIEW_TTL_SECONDS,
    }


def get_review(
    review_id: str,
) -> dict[str, Any] | None:

    _cleanup_expired()

    return _reviews.get(
        str(review_id or "").strip()
    )


def delete_review(
    review_id: str,
) -> None:

    _reviews.pop(
        str(review_id or "").strip(),
        None,
    )