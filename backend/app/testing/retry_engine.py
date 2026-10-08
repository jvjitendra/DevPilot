from __future__ import annotations

from typing import Any

from app.agents.failure_analyzer import analyze_failure
from app.testing.executor import execute_commands


MAX_RETRY_ATTEMPTS = 3


def _build_context(
    repository: str,
    branch: str,
    issue: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> str:
    parts = [
        f"Repository: {repository}",
        f"Branch: {branch}",
    ]

    if isinstance(issue, dict) and issue:
        parts.append(
            "Issue context:\n"
            + "\n".join(
                f"{key}: {value}"
                for key, value in issue.items()
            )
        )

    if isinstance(plan, dict) and plan:
        parts.append(
            "Plan context:\n"
            + "\n".join(
                f"{key}: {value}"
                for key, value in plan.items()
            )
        )

    return "\n\n".join(parts)


def _first_result(
    execution: dict[str, Any],
) -> dict[str, Any]:
    results = execution.get("results")

    if isinstance(results, list) and results:
        result = results[-1]

        if isinstance(result, dict):
            return result

    return {}


def _normalize_attempt(
    attempt_number: int,
    command: str,
    execution: dict[str, Any],
    failure_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _first_result(execution)

    return {
        "attempt": attempt_number,
        "command": command,
        "status": execution.get("status"),
        "summary": execution.get("summary"),
        "result": result,
        "failure_analysis": failure_analysis,
    }


def _can_retry_analysis(
    analysis: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    if not isinstance(analysis, dict):
        return False, None

    if analysis.get("ok") is not True:
        return False, None

    details = analysis.get("analysis")

    if not isinstance(details, dict):
        return False, None

    if details.get("retry_safe") is not True:
        return False, None

    retry_command = details.get("retry_command")

    if not retry_command:
        return False, None

    retry_command = str(
        retry_command
    ).strip()

    if not retry_command:
        return False, None

    return True, retry_command


def run_bounded_retry(
    commands: list[str],
    workspace: str,
    timeout_seconds: int,
    repository: str,
    branch: str,
    issue: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    max_attempts: int = MAX_RETRY_ATTEMPTS,
) -> dict[str, Any]:
    """
    Execute commands with a bounded failure-analysis retry loop.

    Safety properties:
    - Maximum 3 attempts.
    - Only one command is auto-retried.
    - Retry must be explicitly marked retry_safe by Failure Analyzer.
    - Retry command must exist in the analyzer response.
    - Previously attempted commands are never repeated.
    - Every attempt runs through the existing executor safety gates.
    - No production/main mutation is performed here.
    """

    try:
        requested_attempts = int(
            max_attempts
        )
    except (TypeError, ValueError):
        requested_attempts = MAX_RETRY_ATTEMPTS

    max_attempts = max(
        1,
        min(
            requested_attempts,
            MAX_RETRY_ATTEMPTS,
        ),
    )

    if not isinstance(commands, list):
        return {
            "status": "error",
            "summary": "commands must be a list.",
            "attempts": [],
            "attempt_count": 0,
            "max_attempts": max_attempts,
            "retry_used": False,
        }

    if not commands:
        return {
            "status": "error",
            "summary": "No commands were supplied.",
            "attempts": [],
            "attempt_count": 0,
            "max_attempts": max_attempts,
            "retry_used": False,
        }

    # Automatic retry is intentionally limited to one command.
    # Multi-command workflows need dependency-aware orchestration
    # rather than blindly replacing one command.
    if len(commands) != 1:
        execution = execute_commands(
            commands=commands,
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )

        return {
            "status": execution.get("status"),
            "summary": execution.get("summary"),
            "attempts": [
                _normalize_attempt(
                    attempt_number=1,
                    command=" && ".join(
                        str(x)
                        for x in commands
                    ),
                    execution=execution,
                )
            ],
            "attempt_count": 1,
            "max_attempts": max_attempts,
            "retry_used": False,
            "retry_blocked_reason": (
                "Automatic retry is limited to "
                "single-command executions."
            ),
            "final_execution": execution,
        }

    current_command = str(
        commands[0]
    ).strip()

    attempted_commands: set[str] = set()

    attempts: list[dict[str, Any]] = []

    current_execution: dict[str, Any] = {}

    retry_used = False

    for attempt_number in range(
        1,
        max_attempts + 1,
    ):
        attempted_commands.add(
            current_command
        )

        current_execution = execute_commands(
            commands=[current_command],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
        )

        status = str(
            current_execution.get(
                "status"
            )
            or "error"
        )

        if status == "passed":
            attempts.append(
                _normalize_attempt(
                    attempt_number=attempt_number,
                    command=current_command,
                    execution=current_execution,
                )
            )

            return {
                "status": "passed",
                "summary": (
                    "Execution passed "
                    f"after {attempt_number} "
                    "attempt(s)."
                ),
                "attempts": attempts,
                "attempt_count": attempt_number,
                "max_attempts": max_attempts,
                "retry_used": retry_used,
                "final_execution": current_execution,
            }

        result = _first_result(
            current_execution
        )

        failure_analysis = analyze_failure(
            result=result,
            context=_build_context(
                repository=repository,
                branch=branch,
                issue=issue,
                plan=plan,
            ),
        )

        attempts.append(
            _normalize_attempt(
                attempt_number=attempt_number,
                command=current_command,
                execution=current_execution,
                failure_analysis=failure_analysis,
            )
        )

        retry_allowed, retry_command = (
            _can_retry_analysis(
                failure_analysis
            )
        )

        if not retry_allowed:
            return {
                "status": status,
                "summary": (
                    "Execution stopped because "
                    "the failure was not marked "
                    "safe for automatic retry."
                ),
                "attempts": attempts,
                "attempt_count": attempt_number,
                "max_attempts": max_attempts,
                "retry_used": retry_used,
                "final_execution": current_execution,
                "stopped_reason": (
                    "retry_not_safe"
                ),
            }

        if attempt_number >= max_attempts:
            return {
                "status": status,
                "summary": (
                    "Execution stopped after "
                    f"the maximum of {max_attempts} "
                    "attempts."
                ),
                "attempts": attempts,
                "attempt_count": attempt_number,
                "max_attempts": max_attempts,
                "retry_used": retry_used,
                "final_execution": current_execution,
                "stopped_reason": (
                    "max_attempts_reached"
                ),
            }

        retry_command = str(
            retry_command
        ).strip()

        if retry_command in attempted_commands:
            return {
                "status": status,
                "summary": (
                    "Execution stopped because "
                    "the proposed retry command "
                    "was already attempted."
                ),
                "attempts": attempts,
                "attempt_count": attempt_number,
                "max_attempts": max_attempts,
                "retry_used": retry_used,
                "final_execution": current_execution,
                "stopped_reason": (
                    "duplicate_retry_command"
                ),
            }

        # The retry command must be passed through the same executor.
        # The executor itself enforces the command allowlist,
        # blocked patterns, pytest target validation and timeouts.
        current_command = retry_command
        retry_used = True

    return {
        "status": current_execution.get(
            "status",
            "error",
        ),
        "summary": (
            "Execution loop stopped safely."
        ),
        "attempts": attempts,
        "attempt_count": len(attempts),
        "max_attempts": max_attempts,
        "retry_used": retry_used,
        "final_execution": current_execution,
        "stopped_reason": "loop_exit",
    }