from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.testing.patch_apply import apply_patch
from app.testing.workspace import (
    cleanup_workspace,
    clone_repository,
)


router = APIRouter(
    tags=["patches"]
)


class PatchEdit(BaseModel):
    find: str
    replace: str


class PatchFile(BaseModel):
    path: str
    edits: list[PatchEdit] = Field(
        default_factory=list
    )


class ApplyPatchRequest(BaseModel):
    files: list[PatchFile] = Field(
        default_factory=list
    )

    branch: str | None = None

    keep_workspace: bool = False


@router.post(
    "/repositories/{owner}/{repo}/apply-patch"
)
def apply_repository_patch(
    owner: str,
    repo: str,
    payload: ApplyPatchRequest,
) -> dict[str, Any]:

    if not payload.files:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one patch file is required."
            ),
        )

    workspace_info = None

    try:
        workspace_info = clone_repository(
            owner=owner,
            repo=repo,
            branch=payload.branch,
        )

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

        result = apply_patch(
            workspace=workspace_info["workspace"],
            patch=patch_payload,
        )

        return {
            "ok": True,
            "repository": workspace_info[
                "repository"
            ],
            "branch": workspace_info[
                "branch"
            ],
            "stage": "apply-patch",
            "workspace": (
                workspace_info["workspace"]
                if payload.keep_workspace
                else None
            ),
            "patch": result,
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
                f"Patch application failed: {exc}"
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