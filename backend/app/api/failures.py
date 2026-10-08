from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.failure_analyzer import analyze_failure


router = APIRouter(
    tags=["failure-analysis"],
)


class FailureAnalysisRequest(BaseModel):
    execution: dict[str, Any] = Field(default_factory=dict)

    issue: dict[str, Any] | None = None

    plan: dict[str, Any] | None = None


def _extract_execution_result(
    execution: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract the most useful execution result for the failure analyzer.

    Expected shape:

    {
        "status": "...",
        "commands": [...],
        "results": [
            {
                "status": "...",
                "command": "...",
                ...
            }
        ]
    }

    The analyzer itself works on one concrete result dict.
    """

    results = execution.get("results")

    if isinstance(results, list) and results:
        first_result = results[0]

        if isinstance(first_result, dict):
            return dict(first_result)

    # Graceful fallback if the caller sends a single result-like object.
    return dict(execution)


def _build_context(
    issue: dict[str, Any] | None,
    plan: dict[str, Any] | None,
) -> str:
    context_parts: list[str] = []

    if isinstance(issue, dict) and issue:
        context_parts.append(
            "ISSUE CONTEXT:\n"
            + _format_context_dict(issue)
        )

    if isinstance(plan, dict) and plan:
        context_parts.append(
            "IMPLEMENTATION PLAN CONTEXT:\n"
            + _format_context_dict(plan)
        )

    return "\n\n".join(context_parts)


def _format_context_dict(data: dict[str, Any]) -> str:
    lines: list[str] = []

    for key, value in data.items():
        lines.append(
            f"{key}: {value}"
        )

    return "\n".join(lines)


@router.post("/failure-analysis")
def failure_analysis(
    payload: FailureAnalysisRequest,
) -> dict[str, Any]:
    execution = payload.execution

    if not isinstance(execution, dict):
        raise HTTPException(
            status_code=400,
            detail="execution must be a JSON object.",
        )

    result = _extract_execution_result(
        execution
    )

    if not result:
        raise HTTPException(
            status_code=400,
            detail="execution result is empty.",
        )

    context = _build_context(
        issue=payload.issue,
        plan=payload.plan,
    )

    return analyze_failure(
        result=result,
        context=context,
    )