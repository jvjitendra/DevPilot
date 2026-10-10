from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.github.client import (
    GitHubWriteError,
    create_pull_request,
    push_branch,
)

from app.testing.git_ops import (
    commit_changes,
    create_branch,
    stage_files,
)

from app.testing.patch_apply import apply_patch

from app.testing.review_store import (
    create_review,
    delete_review,
    get_review,
)

from app.testing.retry_engine import run_bounded_retry

from app.testing.workspace import (
    cleanup_workspace,
    clone_repository,
)


router = APIRouter(
    tags=["workflow"]
)


class WorkflowPatchEdit(BaseModel):
    find: str
    replace: str


class WorkflowPatchFile(BaseModel):
    path: str
    edits: list[WorkflowPatchEdit] = Field(
        default_factory=list
    )


class ApplyAndTestRequest(BaseModel):
    files: list[WorkflowPatchFile] = Field(
        default_factory=list
    )

    commands: list[str] = Field(
        default_factory=list
    )

    branch: str | None = None

    timeout_seconds: int = Field(
        default=120,
        ge=1,
        le=300,
    )

    auto_retry: bool = True

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=3,
    )

    issue: dict[str, Any] | None = None

    plan: dict[str, Any] | None = None


class ApproveReviewRequest(BaseModel):
    approval_reason: str

    new_branch: str = "devpilot/approved-change"

    commit_message: str = (
        "devpilot: apply approved change"
    )

    pr_title: str | None = None

    pr_body: str | None = None

    draft_pr: bool = False

    create_pr: bool = True


@router.post(
    "/repositories/{owner}/{repo}/apply-and-test"
)
def apply_patch_and_test(
    owner: str,
    repo: str,
    payload: ApplyAndTestRequest,
) -> dict[str, Any]:

    if not payload.files:
        raise HTTPException(
            status_code=400,
            detail="At least one patch file is required.",
        )

    if not payload.commands:
        raise HTTPException(
            status_code=400,
            detail="At least one test command is required.",
        )

    workspace_info = None
    handed_to_review = False

    try:
        # ------------------------------------------------
        # 1. CREATE ISOLATED WORKSPACE
        # ------------------------------------------------

        workspace_info = clone_repository(
            owner=owner,
            repo=repo,
            branch=payload.branch,
        )

        workspace = workspace_info["workspace"]
        repository = workspace_info["repository"]
        source_branch = workspace_info["branch"]

        # ------------------------------------------------
        # 2. BUILD STRUCTURED PATCH
        # ------------------------------------------------

        patch_payload = {
            "files": [
                {
                    "path": item.path,
                    "edits": [
                        {
                            "find": edit.find,
                            "replace": edit.replace,
                        }
                        for edit in item.edits
                    ],
                }
                for item in payload.files
            ]
        }

        # ------------------------------------------------
        # 3. APPLY PATCH
        # ------------------------------------------------

        patch_result = apply_patch(
            workspace=workspace,
            patch=patch_payload,
        )

        if patch_result.get("status") == (
            "no_changes_required"
        ):
            return {
                "ok": True,
                "repository": repository,
                "source_branch": source_branch,
                "stage": "apply-and-test",
                "status": "no_changes_required",
                "patch": patch_result,
                "execution": None,
                "review": None,
            }

        # ------------------------------------------------
        # 4. RUN TESTS IN SAME WORKSPACE
        # ------------------------------------------------

        if payload.auto_retry:
            execution = run_bounded_retry(
                commands=payload.commands,
                workspace=workspace,
                timeout_seconds=payload.timeout_seconds,
                repository=repository,
                branch=source_branch,
                issue=payload.issue,
                plan=payload.plan,
                max_attempts=payload.max_attempts,
            )

        else:
            from app.testing.executor import (
                execute_commands,
            )

            execution = execute_commands(
                commands=payload.commands,
                workspace=workspace,
                timeout_seconds=payload.timeout_seconds,
            )

        # ------------------------------------------------
        # 5. TEST FAILURE -> STOP
        # ------------------------------------------------

        if execution.get("status") != "passed":
            return {
                "ok": True,
                "repository": repository,
                "source_branch": source_branch,
                "stage": "apply-and-test",
                "status": "tests_failed",
                "patch": patch_result,
                "execution": execution,
                "review": None,
            }

        # ------------------------------------------------
        # 6. TESTS PASS -> CREATE REVIEW SESSION
        # ------------------------------------------------

        review = create_review(
            owner=owner,
            repo=repo,
            repository=repository,
            source_branch=source_branch,
            workspace_info=workspace_info,
            patch_result=patch_result,
            execution=execution,
        )

        handed_to_review = True

        return {
            "ok": True,
            "repository": repository,
            "source_branch": source_branch,
            "stage": "human-review",
            "status": "ready_for_review",
            "approval_required": True,
            "review": review,
            "patch": patch_result,
            "execution": execution,
            "next_action": (
                "Review the diff and approve the review session."
            ),
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Apply-and-test workflow failed: {exc}"
            ),
        )

    finally:
        # Once ownership transfers to review_store,
        # the review session owns the workspace lifecycle.
        if (
            workspace_info
            and not handed_to_review
        ):
            cleanup_workspace(
                workspace_info
            )


@router.post(
    "/repositories/{owner}/{repo}/reviews/{review_id}/approve"
)
def approve_review(
    owner: str,
    repo: str,
    review_id: str,
    payload: ApproveReviewRequest,
) -> dict[str, Any]:

    session = get_review(
        review_id
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail=(
                "Review session not found or expired."
            ),
        )

    if (
        session["owner"].lower()
        != owner.lower()
        or session["repo"].lower()
        != repo.lower()
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Review session does not belong "
                "to this repository."
            ),
        )

    approval_reason = str(
        payload.approval_reason or ""
    ).strip()

    if not approval_reason:
        raise HTTPException(
            status_code=400,
            detail="approval_reason is required.",
        )

    workspace_info = session[
        "workspace_info"
    ]

    workspace = workspace_info[
        "workspace"
    ]

    branch_result = None
    stage_result = None
    commit_result = None
    push_result = None
    pull_request_result = None

    try:
        # ------------------------------------------------
        # 1. SAFETY CHECK
        # REVIEW MUST HAVE PASSED TESTS
        # ------------------------------------------------

        execution = session[
            "execution"
        ]

        if execution.get("status") != "passed":
            raise HTTPException(
                status_code=409,
                detail=(
                    "This review cannot be approved because "
                    "the stored test execution did not pass."
                ),
            )

        # ------------------------------------------------
        # 2. CREATE BRANCH ONLY AFTER HUMAN APPROVAL
        # ------------------------------------------------

        branch_result = create_branch(
            workspace=workspace,
            branch_name=payload.new_branch,
        )

        # ------------------------------------------------
        # 3. STAGE ONLY REVIEWED PATCH FILES
        # ------------------------------------------------

        patch_result = session[
            "patch_result"
        ]

        changed_files = [
            item["path"]
            for item in (
                patch_result.get("files")
                or []
            )
        ]

        if not changed_files:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The approved patch contains no "
                    "reviewed files to stage."
                ),
            )

        stage_result = stage_files(
            workspace=workspace,
            file_paths=changed_files,
        )

        # ------------------------------------------------
        # 4. COMMIT
        # ------------------------------------------------

        commit_result = commit_changes(
            workspace=workspace,
            message=payload.commit_message,
        )

        commit_sha = (
            commit_result.get("commit_sha")
            if isinstance(commit_result, dict)
            else None
        )

        # ------------------------------------------------
        # 5. PUSH APPROVED BRANCH TO GITHUB
        # ------------------------------------------------

        try:
            push_result = push_branch(
                workspace=workspace,
                branch_name=payload.new_branch,
            )

        except GitHubWriteError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": (
                        "Local commit was created, but "
                        "the approved branch could not be "
                        "pushed to GitHub."
                    ),
                    "repository": session["repository"],
                    "source_branch": session["source_branch"],
                    "new_branch": payload.new_branch,
                    "commit_sha": commit_sha,
                    "git": {
                        "branch": branch_result,
                        "staging": stage_result,
                        "commit": commit_result,
                    },
                    "github": {
                        "push": {
                            "ok": False,
                            "error": str(exc),
                        },
                        "pull_request": None,
                    },
                },
            )

        # ------------------------------------------------
        # 6. CREATE PULL REQUEST (IF REQUESTED)
        # ------------------------------------------------

        if payload.create_pr:
            pr_title = (
                str(payload.pr_title or "").strip()
                or payload.commit_message
            )

            pr_body = (
                str(payload.pr_body or "").strip()
                or (
                    f"Approved change from DevPilot review "
                    f"`{review_id}`.\n\n"
                    f"Approval reason:\n"
                    f"{approval_reason}\n\n"
                    f"Commit:\n"
                    f"`{commit_sha or 'unknown'}`"
                )
            )

            try:
                pull_request_result = create_pull_request(
                    owner=owner,
                    repo=repo,
                    head=payload.new_branch,
                    base=session["source_branch"],
                    title=pr_title,
                    body=pr_body,
                    draft=payload.draft_pr,
                )

            except GitHubWriteError as exc:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": (
                            "The approved branch was pushed to "
                            "GitHub, but Pull Request creation failed."
                        ),
                        "repository": session["repository"],
                        "source_branch": session["source_branch"],
                        "new_branch": payload.new_branch,
                        "commit_sha": commit_sha,
                        "git": {
                            "branch": branch_result,
                            "staging": stage_result,
                            "commit": commit_result,
                        },
                        "github": {
                            "push": push_result,
                            "pull_request": {
                                "ok": False,
                                "error": str(exc),
                            },
                        },
                    },
                )

        # ------------------------------------------------
        # 7. COMPLETE
        # ------------------------------------------------

        return {
            "ok": True,
            "repository": session[
                "repository"
            ],
            "source_branch": session[
                "source_branch"
            ],
            "stage": "github-published",
            "status": (
                "pr-created"
                if payload.create_pr
                else "branch-pushed"
            ),
            "review_id": review_id,
            "approval": {
                "approved": True,
                "reason": approval_reason,
            },
            "patch": patch_result,
            "execution": execution,
            "git": {
                "branch": branch_result,
                "staging": stage_result,
                "commit": commit_result,
            },
            "github": {
                "push": push_result,
                "pull_request": pull_request_result,
            },
        }

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Review approval failed: {exc}"
            ),
        )

    finally:
        # Always clean the isolated workspace after
        # approval succeeds OR approval fails.
        cleanup_workspace(
            workspace_info
        )

        delete_review(
            review_id
        )


@router.post(
    "/repositories/{owner}/{repo}/reviews/{review_id}/discard"
)
def discard_review(
    owner: str,
    repo: str,
    review_id: str,
) -> dict[str, Any]:

    session = get_review(
        review_id
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Review session not found or expired.",
        )

    if (
        session["owner"].lower()
        != owner.lower()
        or session["repo"].lower()
        != repo.lower()
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "Review session does not belong "
                "to this repository."
            ),
        )

    workspace_info = session[
        "workspace_info"
    ]

    cleanup_workspace(
        workspace_info
    )

    delete_review(
        review_id
    )

    return {
        "ok": True,
        "repository": session["repository"],
        "review_id": review_id,
        "stage": "human-review",
        "status": "discarded",
    }