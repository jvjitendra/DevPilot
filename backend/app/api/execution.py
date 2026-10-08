from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.testing.executor import execute_commands
from app.testing.retry_engine import run_bounded_retry
from app.testing.workspace import (
    cleanup_workspace,
    clone_repository,
)


router = APIRouter()


class ExecuteTestsRequest(BaseModel):
    commands: list[str] = Field(
        default_factory=list
    )

    timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=300,
    )

    keep_workspace: bool = False

    branch: str | None = None

    auto_retry: bool = True

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=3,
    )

    issue: dict[str, Any] | None = None

    plan: dict[str, Any] | None = None


@router.post(
    "/repositories/{owner}/{repo}/execute-tests"
)
def execute_repository_tests(
    owner: str,
    repo: str,
    payload: ExecuteTestsRequest,
) -> dict[str, Any]:
    if not payload.commands:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one test command is required"
            ),
        )

    workspace_info = None

    try:
        workspace_info = clone_repository(
            owner=owner,
            repo=repo,
            branch=payload.branch,
        )

        if payload.auto_retry:
            execution = run_bounded_retry(
                commands=payload.commands,
                workspace=workspace_info["workspace"],
                timeout_seconds=payload.timeout_seconds,
                repository=workspace_info["repository"],
                branch=workspace_info["branch"],
                issue=payload.issue,
                plan=payload.plan,
                max_attempts=payload.max_attempts,
            )
        else:
            execution = execute_commands(
                commands=payload.commands,
                workspace=workspace_info["workspace"],
                timeout_seconds=payload.timeout_seconds,
            )

        return {
            "ok": True,
            "repository": (
                workspace_info["repository"]
            ),
            "branch": (
                workspace_info["branch"]
            ),
            "stage": "execute-tests",
            "auto_retry": payload.auto_retry,
            "max_attempts": payload.max_attempts,
            "workspace": (
                workspace_info["workspace"]
                if payload.keep_workspace
                else None
            ),
            "execution": execution,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Test execution failed: {exc}"
            ),
        )

    finally:
        if (
            workspace_info
            and not payload.keep_workspace
        ):
            cleanup_workspace(
                workspace_info
            )