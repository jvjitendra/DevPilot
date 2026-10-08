from fastapi import APIRouter, HTTPException

from app.ai.analyzer import analyze_issue
from app.agents.patcher import generate_patch
from app.agents.planner import create_implementation_plan
from app.api.repositories import (
    get_issue_context_code,
    get_repository_file,
)
from app.testing.testgen import generate_test_plan


router = APIRouter()


def build_issue_pipeline(
    owner: str,
    repo: str,
    issue_number: int,
):
    context = get_issue_context_code(
        owner,
        repo,
        issue_number,
    )

    if not context.get("ok"):
        raise HTTPException(
            status_code=502,
            detail="Failed to build issue source context.",
        )

    issue = context["issue"]
    files = context["files"]

    if not files:
        raise HTTPException(
            status_code=422,
            detail="No relevant source files were found for this issue.",
        )

    analysis_result = analyze_issue(
        issue=issue,
        files=files,
    )

    if not analysis_result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Issue analysis failed.",
                "errors": analysis_result.get("errors"),
            },
        )

    analysis = analysis_result.get("analysis")

    if not isinstance(analysis, dict):
        raise HTTPException(
            status_code=502,
            detail="AI analysis returned no usable result.",
        )

    return (
        context,
        issue,
        files,
        analysis_result,
        analysis,
    )


def build_plan(
    issue: dict,
    analysis: dict,
    files: list[dict],
):
    planner_result = (
        create_implementation_plan(
            issue=issue,
            analysis=analysis,
            files=files,
        )
    )

    if not planner_result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Implementation planning failed.",
                "errors": planner_result.get("errors"),
            },
        )

    plan = planner_result.get("plan")

    if not isinstance(plan, dict):
        raise HTTPException(
            status_code=502,
            detail="Planner returned no usable implementation plan.",
        )

    return planner_result, plan


@router.get(
    "/repositories/{owner}/{repo}/issues/{issue_number}/analyze"
)
def analyze_repository_issue(
    owner: str,
    repo: str,
    issue_number: int,
):
    try:
        (
            context,
            issue,
            _files,
            analysis_result,
            analysis,
        ) = build_issue_pipeline(
            owner,
            repo,
            issue_number,
        )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "issue": issue,
            "context": {
                "keywords": context.get(
                    "keywords",
                    [],
                ),
                "selected_file_count": context.get(
                    "selected_file_count",
                    0,
                ),
                "total_context_chars": context.get(
                    "total_context_chars",
                    0,
                ),
            },
            "provider": analysis_result.get(
                "provider"
            ),
            "model": analysis_result.get(
                "model"
            ),
            "analysis": analysis,
            "fallback": analysis_result.get(
                "fallback"
            ),
            "errors": analysis_result.get(
                "errors"
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Issue AI analysis failed: {exc}",
        )


@router.get(
    "/repositories/{owner}/{repo}/issues/{issue_number}/plan"
)
def plan_repository_issue(
    owner: str,
    repo: str,
    issue_number: int,
):
    try:
        (
            context,
            issue,
            files,
            analysis_result,
            analysis,
        ) = build_issue_pipeline(
            owner,
            repo,
            issue_number,
        )

        planner_result, plan = build_plan(
            issue=issue,
            analysis=analysis,
            files=files,
        )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "issue": issue,
            "context": {
                "keywords": context.get(
                    "keywords",
                    [],
                ),
                "selected_file_count": context.get(
                    "selected_file_count",
                    0,
                ),
                "total_context_chars": context.get(
                    "total_context_chars",
                    0,
                ),
            },
            "analysis": {
                "provider": analysis_result.get(
                    "provider"
                ),
                "model": analysis_result.get(
                    "model"
                ),
                "result": analysis,
            },
            "plan_provider": planner_result.get(
                "provider"
            ),
            "plan_model": planner_result.get(
                "model"
            ),
            "plan": plan,
            "fallback": planner_result.get(
                "fallback"
            ),
            "errors": planner_result.get(
                "errors"
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Implementation planning failed: {exc}",
        )


@router.get(
    "/repositories/{owner}/{repo}/issues/{issue_number}/patch"
)
def patch_repository_issue(
    owner: str,
    repo: str,
    issue_number: int,
):
    try:
        (
            context,
            issue,
            retrieved_files,
            analysis_result,
            analysis,
        ) = build_issue_pipeline(
            owner,
            repo,
            issue_number,
        )

        planner_result, plan = build_plan(
            issue=issue,
            analysis=analysis,
            files=retrieved_files,
        )

        full_files = []

        planned_files = (
            plan.get(
                "files_to_modify",
                [],
            )
            or []
        )

        for item in planned_files:

            if not isinstance(item, dict):
                continue

            path = str(
                item.get("path")
                or ""
            ).strip()

            if not path:
                continue

            file_data = get_repository_file(
                owner=owner,
                repo=repo,
                path=path,
            )

            if file_data.get("ok"):
                full_files.append(
                    file_data
                )

        if not planned_files:

            return {
                "ok": True,
                "repository": f"{owner}/{repo}",
                "issue": issue,
                "stage": "patch",
                "context": {
                    "keywords": context.get(
                        "keywords",
                        [],
                    ),
                    "selected_file_count": context.get(
                        "selected_file_count",
                        0,
                    ),
                    "total_context_chars": context.get(
                        "total_context_chars",
                        0,
                    ),
                },
                "analysis": {
                    "provider": analysis_result.get(
                        "provider"
                    ),
                    "model": analysis_result.get(
                        "model"
                    ),
                    "result": analysis,
                },
                "plan": plan,
                "plan_provider": planner_result.get(
                    "provider"
                ),
                "plan_model": planner_result.get(
                    "model"
                ),
                "patch_provider": None,
                "patch_model": None,
                "patch": {
                    "status": "no_changes_required",
                    "summary": (
                        "The current evidence and implementation plan "
                        "do not justify a source-code modification."
                    ),
                    "edits": [],
                    "tests": [],
                    "risk": plan.get(
                        "risk",
                        "low",
                    ),
                    "notes": [
                        "No code patch generated."
                    ],
                },
                "diff": {
                    "files_changed": 0,
                    "patches": [],
                },
                "fallback": planner_result.get(
                    "fallback"
                ),
                "errors": None,
            }

        if not full_files:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Planned files could not be retrieved "
                    "from GitHub."
                ),
            )

        patch_result = generate_patch(
            issue=issue,
            analysis=analysis,
            plan=plan,
            files=full_files,
        )

        return {
            "ok": patch_result.get(
                "ok",
                False,
            ),
            "repository": f"{owner}/{repo}",
            "issue": issue,
            "stage": "patch",
            "context": {
                "keywords": context.get(
                    "keywords",
                    [],
                ),
                "selected_file_count": context.get(
                    "selected_file_count",
                    0,
                ),
                "total_context_chars": context.get(
                    "total_context_chars",
                    0,
                ),
            },
            "analysis": {
                "provider": analysis_result.get(
                    "provider"
                ),
                "model": analysis_result.get(
                    "model"
                ),
                "result": analysis,
            },
            "plan": plan,
            "plan_provider": planner_result.get(
                "provider"
            ),
            "plan_model": planner_result.get(
                "model"
            ),
            "patch_provider": patch_result.get(
                "provider"
            ),
            "patch_model": patch_result.get(
                "model"
            ),
            "patch": patch_result.get(
                "patch"
            ),
            "diff": patch_result.get(
                "diff"
            ),
            "fallback": patch_result.get(
                "fallback"
            ),
            "errors": patch_result.get(
                "errors"
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Patch generation failed: {exc}",
        )


@router.get(
    "/repositories/{owner}/{repo}/issues/{issue_number}/tests"
)
def generate_repository_issue_tests(
    owner: str,
    repo: str,
    issue_number: int,
):
    try:
        # ========================================================
        # 1. ISSUE + SOURCE + ANALYSIS
        # ========================================================

        (
            context,
            issue,
            files,
            analysis_result,
            analysis,
        ) = build_issue_pipeline(
            owner,
            repo,
            issue_number,
        )

        # ========================================================
        # 2. IMPLEMENTATION PLAN
        # ========================================================

        planner_result, plan = build_plan(
            issue=issue,
            analysis=analysis,
            files=files,
        )

        # ========================================================
        # 3. TEST GENERATION
        # ========================================================

        test_result = generate_test_plan(
            issue=issue,
            analysis=analysis,
            plan=plan,
            files=files,
        )

        if not test_result.get("ok"):
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Test generation failed.",
                    "errors": test_result.get(
                        "errors"
                    ),
                },
            )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "issue": issue,
            "stage": "tests",
            "context": {
                "keywords": context.get(
                    "keywords",
                    [],
                ),
                "selected_file_count": context.get(
                    "selected_file_count",
                    0,
                ),
                "total_context_chars": context.get(
                    "total_context_chars",
                    0,
                ),
            },
            "analysis": {
                "provider": analysis_result.get(
                    "provider"
                ),
                "model": analysis_result.get(
                    "model"
                ),
                "result": analysis,
            },
            "plan": plan,
            "plan_provider": planner_result.get(
                "provider"
            ),
            "plan_model": planner_result.get(
                "model"
            ),
            "test_provider": test_result.get(
                "provider"
            ),
            "test_model": test_result.get(
                "model"
            ),
            "tests": test_result.get(
                "tests"
            ),
            "fallback": test_result.get(
                "fallback"
            ),
            "errors": test_result.get(
                "errors"
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Test generation failed: {exc}",
        )