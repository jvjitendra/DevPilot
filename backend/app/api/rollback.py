from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

load_dotenv()

router = APIRouter(
    tags=["rollback"]
)

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class RollbackRequest(BaseModel):
    reason: str


def _github_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not token:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_TOKEN is not configured.",
        )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


@router.post(
    "/repositories/{owner}/{repo}/pulls/{pull_number}/rollback"
)
def rollback_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    payload: RollbackRequest,
) -> dict[str, Any]:
    reason = payload.reason.strip()

    if not reason:
        raise HTTPException(
            status_code=400,
            detail="reason is required.",
        )

    headers = _github_headers()

    pr_url = (
        f"{GITHUB_API}/repos/"
        f"{owner}/{repo}/pulls/{pull_number}"
    )

    try:
        with httpx.Client(
            timeout=30.0,
            headers=headers,
        ) as client:

            # -------------------------------------------------
            # 1. Get Pull Request
            # -------------------------------------------------
            pr_response = client.get(pr_url)

            if pr_response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail="Pull Request not found.",
                )

            if pr_response.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": (
                            "GitHub Pull Request lookup failed."
                        ),
                        "status_code": (
                            pr_response.status_code
                        ),
                    },
                )

            pr = pr_response.json()

            # -------------------------------------------------
            # 2. Rollback only merged PRs
            # -------------------------------------------------
            if not pr.get("merged"):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": (
                            "Rollback is allowed only for "
                            "a merged Pull Request."
                        ),
                        "pull_request": pull_number,
                        "state": pr.get("state"),
                        "merged": False,
                    },
                )

            # -------------------------------------------------
            # 3. Ask GitHub to create the revert PR
            # -------------------------------------------------
            revert_url = (
                f"{GITHUB_API}/repos/"
                f"{owner}/{repo}/pulls/"
                f"{pull_number}/revert"
            )

            revert_response = client.post(
                revert_url,
                json={},
            )

            if revert_response.status_code >= 400:
                try:
                    github_error = revert_response.json()
                except Exception:
                    github_error = (
                        revert_response.text.strip()
                    )

                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": (
                            "GitHub rollback failed."
                        ),
                        "status_code": (
                            revert_response.status_code
                        ),
                        "github": github_error,
                    },
                )

            reverted_pr = revert_response.json()

            # -------------------------------------------------
            # 4. Return rollback result
            # -------------------------------------------------
            return {
                "ok": True,
                "stage": "rollback",
                "status": "revert-pr-created",
                "repository": f"{owner}/{repo}",
                "original_pull_request": pull_number,
                "original_merge_commit": (
                    pr.get("merge_commit_sha")
                ),
                "reason": reason,
                "rollback_pull_request": {
                    "number": reverted_pr.get("number"),
                    "url": reverted_pr.get("html_url"),
                    "state": reverted_pr.get("state"),
                    "title": reverted_pr.get("title"),
                },
            }

    except HTTPException:
        raise

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub rollback connection failed: {exc}",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Rollback failed: {exc}",
        ) from exc