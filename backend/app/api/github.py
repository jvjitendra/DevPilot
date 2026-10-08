from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.github.client import (
    GitHubWriteError,
    create_pull_request,
    get_pull_request,
    get_pull_request_ci,
)


router = APIRouter(
    tags=["github"]
)


class CreatePullRequestRequest(BaseModel):
    head: str
    base: str
    title: str
    body: str = ""
    draft: bool = False


@router.post(
    "/repositories/{owner}/{repo}/pulls"
)
def create_repository_pull_request(
    owner: str,
    repo: str,
    payload: CreatePullRequestRequest,
) -> dict[str, Any]:

    try:
        result = create_pull_request(
            owner=owner,
            repo=repo,
            head=payload.head,
            base=payload.base,
            title=payload.title,
            body=payload.body,
            draft=payload.draft,
        )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            **result,
        }

    except GitHubWriteError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get(
    "/repositories/{owner}/{repo}/pulls/{pull_number}"
)
def read_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
) -> dict[str, Any]:

    try:
        pull_request = get_pull_request(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
        )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "pull_request": pull_request,
        }

    except GitHubWriteError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get(
    "/repositories/{owner}/{repo}/pulls/{pull_number}/ci"
)
def read_pull_request_ci(
    owner: str,
    repo: str,
    pull_number: int,
) -> dict[str, Any]:

    try:
        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            **get_pull_request_ci(
                owner=owner,
                repo=repo,
                pull_number=pull_number,
            ),
        }

    except GitHubWriteError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )