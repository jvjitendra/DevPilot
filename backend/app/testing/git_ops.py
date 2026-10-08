from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


MAX_BRANCH_LENGTH = 80
MAX_COMMIT_MESSAGE_LENGTH = 160


def _run_git(
    workspace: str | Path,
    args: list[str],
) -> dict[str, Any]:

    root = Path(workspace).resolve()

    if not root.exists() or not root.is_dir():
        raise ValueError(
            f"Git workspace does not exist: {root}"
        )

    command = ["git", *args]

    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        shell=False,
    )

    return {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "ok": result.returncode == 0,
    }


def _safe_branch_name(
    branch_name: str,
) -> str:

    value = str(branch_name or "").strip()

    if not value:
        raise ValueError(
            "Branch name is required."
        )

    if len(value) > MAX_BRANCH_LENGTH:
        raise ValueError(
            f"Branch name cannot exceed {MAX_BRANCH_LENGTH} characters."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._/-]*",
        value,
    ):
        raise ValueError(
            (
                "Branch name contains unsupported characters. "
                "Use letters, numbers, '.', '_' '/' or '-'."
            )
        )

    if value.startswith("/") or value.endswith("/"):
        raise ValueError(
            "Branch name cannot start or end with '/'."
        )

    if ".." in value:
        raise ValueError(
            "Branch name cannot contain '..'."
        )

    if "@{" in value:
        raise ValueError(
            "Branch name cannot contain '@{'."
        )

    return value


def _safe_commit_message(
    message: str,
) -> str:

    value = str(message or "").strip()

    if not value:
        raise ValueError(
            "Commit message is required."
        )

    if len(value) > MAX_COMMIT_MESSAGE_LENGTH:
        raise ValueError(
            (
                "Commit message cannot exceed "
                f"{MAX_COMMIT_MESSAGE_LENGTH} characters."
            )
        )

    if "\x00" in value:
        raise ValueError(
            "Commit message contains invalid characters."
        )

    return value


def create_branch(
    workspace: str | Path,
    branch_name: str,
) -> dict[str, Any]:

    branch = _safe_branch_name(
        branch_name
    )

    check = _run_git(
        workspace,
        [
            "rev-parse",
            "--verify",
            f"refs/heads/{branch}",
        ],
    )

    if check["ok"]:
        raise ValueError(
            f"Branch already exists: {branch}"
        )

    result = _run_git(
        workspace,
        [
            "switch",
            "-c",
            branch,
        ],
    )

    if not result["ok"]:
        raise RuntimeError(
            result["stderr"]
            or result["stdout"]
            or "Failed to create branch."
        )

    return {
        "ok": True,
        "branch": branch,
        "action": "branch_created",
    }


def stage_files(
    workspace: str | Path,
    file_paths: list[str],
) -> dict[str, Any]:

    if not file_paths:
        raise ValueError(
            "At least one file is required for staging."
        )

    root = Path(workspace).resolve()

    normalized: list[str] = []

    for raw in file_paths:
        path = str(raw or "").replace(
            "\\",
            "/",
        ).strip("/")

        if not path:
            raise ValueError(
                "Invalid empty file path."
            )

        candidate = (
            root / path
        ).resolve()

        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"File path escapes workspace: {path}"
            ) from exc

        if not candidate.is_file():
            raise ValueError(
                f"Changed file does not exist: {path}"
            )

        normalized.append(path)

    result = _run_git(
        workspace,
        [
            "add",
            "--",
            *normalized,
        ],
    )

    if not result["ok"]:
        raise RuntimeError(
            result["stderr"]
            or result["stdout"]
            or "Failed to stage changed files."
        )

    staged = _run_git(
        workspace,
        [
            "diff",
            "--cached",
            "--name-only",
        ],
    )

    if not staged["ok"]:
        raise RuntimeError(
            staged["stderr"]
            or staged["stdout"]
            or "Unable to inspect staged files."
        )

    staged_files = [
        line.strip()
        for line in staged["stdout"].splitlines()
        if line.strip()
    ]

    expected = sorted(
        set(normalized)
    )

    actual = sorted(
        set(staged_files)
    )

    if expected != actual:
        raise RuntimeError(
            (
                "Staged file scope does not match "
                "the approved patch. "
                f"Expected={expected}, Actual={actual}"
            )
        )

    return {
        "ok": True,
        "action": "files_staged",
        "files": actual,
    }


def commit_changes(
    workspace: str | Path,
    message: str,
) -> dict[str, Any]:

    commit_message = _safe_commit_message(
        message
    )

    status = _run_git(
        workspace,
        [
            "status",
            "--porcelain",
        ],
    )

    if not status["ok"]:
        raise RuntimeError(
            status["stderr"]
            or status["stdout"]
            or "Unable to inspect git status."
        )

    if not status["stdout"]:
        raise ValueError(
            "There are no changes available to commit."
        )

    config_name = _run_git(
        workspace,
        [
            "config",
            "user.name",
            "DevPilot",
        ],
    )

    if not config_name["ok"]:
        raise RuntimeError(
            config_name["stderr"]
            or "Unable to configure git user.name."
        )

    config_email = _run_git(
        workspace,
        [
            "config",
            "user.email",
            "devpilot@localhost",
        ],
    )

    if not config_email["ok"]:
        raise RuntimeError(
            config_email["stderr"]
            or "Unable to configure git user.email."
        )

    commit = _run_git(
        workspace,
        [
            "commit",
            "-m",
            commit_message,
        ],
    )

    if not commit["ok"]:
        raise RuntimeError(
            commit["stderr"]
            or commit["stdout"]
            or "Git commit failed."
        )

    head = _run_git(
        workspace,
        [
            "rev-parse",
            "HEAD",
        ],
    )

    if not head["ok"]:
        raise RuntimeError(
            head["stderr"]
            or "Unable to resolve commit SHA."
        )

    return {
        "ok": True,
        "action": "commit_created",
        "commit_sha": head["stdout"],
        "message": commit_message,
    }


def get_worktree_status(
    workspace: str | Path,
) -> dict[str, Any]:

    branch = _run_git(
        workspace,
        [
            "branch",
            "--show-current",
        ],
    )

    status = _run_git(
        workspace,
        [
            "status",
            "--porcelain",
        ],
    )

    return {
        "branch": branch["stdout"]
        if branch["ok"]
        else None,
        "clean": (
            status["ok"]
            and not status["stdout"]
        ),
        "status_output": status["stdout"],
    }