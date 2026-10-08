from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubWriteError(RuntimeError):
    """Raised when a GitHub write operation fails."""


def github_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not token:
        raise GitHubWriteError(
            "GITHUB_TOKEN is not configured."
        )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not token:
        raise GitHubWriteError(
            "GITHUB_TOKEN is not configured."
        )

    return token


def validate_devpilot_branch(branch_name: str) -> str:
    branch = str(branch_name or "").strip()

    if not branch:
        raise GitHubWriteError(
            "Branch name is required."
        )

    if not branch.startswith("devpilot/"):
        raise GitHubWriteError(
            "DevPilot can only publish branches beginning with "
            "'devpilot/'."
        )

    if branch in {"main", "master"}:
        raise GitHubWriteError(
            "DevPilot cannot publish directly to main/master."
        )

    if re.search(r"[\s~^:?*\[\]\\]", branch):
        raise GitHubWriteError(
            f"Invalid Git branch name: {branch}"
        )

    if branch.endswith(".") or branch.endswith("/"):
        raise GitHubWriteError(
            f"Invalid Git branch name: {branch}"
        )

    return branch


def _create_askpass_script(folder: Path) -> Path:
    script_path = folder / ".devpilot-askpass.cmd"

    script_path.write_text(
        """@echo off
set "prompt=%~1"

echo %prompt% | findstr /i "username" >nul
if not errorlevel 1 (
    echo x-access-token
    exit /b 0
)

echo %GITHUB_TOKEN%
""",
        encoding="utf-8",
    )

    return script_path


def push_branch(
    workspace: str,
    branch_name: str,
) -> dict[str, Any]:
    """
    Push the approved DevPilot branch to GitHub.

    Authentication follows the same pattern used by repository
    cloning: the GitHub username is embedded in the HTTPS remote
    URL and the token is supplied through GIT_ASKPASS.
    """

    branch = validate_devpilot_branch(
        branch_name
    )

    token = _token()

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="devpilot_git_push_"
        )
    )

    askpass_script = _create_askpass_script(
        temp_dir
    )

    env = os.environ.copy()

    env["GITHUB_TOKEN"] = token
    env["GIT_ASKPASS"] = str(
        askpass_script
    )
    env["GIT_TERMINAL_PROMPT"] = "0"

    # Disable Windows/Git credential helpers so the
    # GitHub credentials supplied by DevPilot are used.
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "credential.helper"
    env["GIT_CONFIG_VALUE_0"] = ""

    try:
        remote_process = subprocess.run(
            [
                "git",
                "-C",
                workspace,
                "remote",
                "get-url",
                "origin",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )

        if remote_process.returncode != 0:
            error = (
                remote_process.stderr.strip()
                or remote_process.stdout.strip()
                or "Unable to read origin remote URL."
            )

            raise GitHubWriteError(
                f"Git remote lookup failed: {error}"
            )

        remote_url = remote_process.stdout.strip()

        if not remote_url:
            raise GitHubWriteError(
                "Git origin remote URL is empty."
            )

        if "github.com/" not in remote_url:
            raise GitHubWriteError(
                "GitHub push requires a GitHub HTTPS origin remote."
            )

        authenticated_url = remote_url

        process = subprocess.run(
            [
                "git",
                "-C",
                workspace,
                "push",
                authenticated_url,
                branch,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )

        if process.returncode != 0:
            stderr = (
                process.stderr.strip()
                or process.stdout.strip()
                or "Unknown git push error."
            )

            raise GitHubWriteError(
                f"Git push failed: {stderr}"
            )

        return {
            "ok": True,
            "action": "branch-pushed",
            "remote": "origin",
            "branch": branch,
            "stdout": process.stdout.strip(),
        }

    except subprocess.TimeoutExpired as exc:
        raise GitHubWriteError(
            "Git push timed out."
        ) from exc

    finally:
        try:
            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )
        except Exception:
            pass


def _github_request(
    method: str,
    url: str,
    **kwargs: Any,
) -> dict[str, Any] | list[Any]:
    try:
        response = httpx.request(
            method=method,
            url=url,
            headers=github_headers(),
            timeout=20,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise GitHubWriteError(
            f"GitHub API request failed: {exc}"
        ) from exc

    if response.status_code >= 400:
        try:
            payload = response.json()
        except Exception:
            payload = {}

        message = (
            payload.get("message")
            if isinstance(payload, dict)
            else None
        )

        if not message:
            message = response.text.strip()

        raise GitHubWriteError(
            f"GitHub API returned "
            f"{response.status_code}: {message}"
        )

    try:
        return response.json()
    except Exception as exc:
        raise GitHubWriteError(
            "GitHub returned a non-JSON response."
        ) from exc


def list_open_pull_requests(
    owner: str,
    repo: str,
    branch_name: str,
) -> list[dict[str, Any]]:
    branch = validate_devpilot_branch(
        branch_name
    )

    data = _github_request(
        "GET",
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        params={
            "state": "open",
            "head": f"{owner}:{branch}",
            "per_page": 100,
        },
    )

    if not isinstance(data, list):
        return []

    return [
        item
        for item in data
        if isinstance(item, dict)
    ]


def create_pull_request(
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    draft: bool = False,
) -> dict[str, Any]:
    head_branch = validate_devpilot_branch(
        head
    )

    base_branch = str(base or "").strip()

    if not base_branch:
        raise GitHubWriteError(
            "Base branch is required."
        )

    if head_branch == base_branch:
        raise GitHubWriteError(
            "PR head and base branches cannot be the same."
        )

    title = str(title or "").strip()

    if not title:
        raise GitHubWriteError(
            "Pull request title is required."
        )

    existing = list_open_pull_requests(
        owner=owner,
        repo=repo,
        branch_name=head_branch,
    )

    for pull_request in existing:
        if (
            pull_request.get("base", {}).get("ref")
            == base_branch
        ):
            return {
                "ok": True,
                "action": "existing-pr",
                "pull_request": pull_request,
            }

    payload = {
        "title": title,
        "head": head_branch,
        "base": base_branch,
        "body": body or "",
        "draft": bool(draft),
        "maintainer_can_modify": False,
    }

    data = _github_request(
        "POST",
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        json=payload,
    )

    if not isinstance(data, dict):
        raise GitHubWriteError(
            "GitHub PR creation returned an unexpected response."
        )

    return {
        "ok": True,
        "action": "created-pr",
        "pull_request": data,
    }


def get_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
) -> dict[str, Any]:
    data = _github_request(
        "GET",
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}",
    )

    if not isinstance(data, dict):
        raise GitHubWriteError(
            "GitHub PR response was not an object."
        )

    return data


def list_workflow_runs(
    owner: str,
    repo: str,
    branch: str | None = None,
    head_sha: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "per_page": 100,
    }

    if branch:
        params["branch"] = branch

    if head_sha:
        params["head_sha"] = head_sha

    data = _github_request(
        "GET",
        f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs",
        params=params,
    )

    if not isinstance(data, dict):
        return []

    runs = data.get(
        "workflow_runs",
        [],
    )

    if not isinstance(runs, list):
        return []

    return [
        item
        for item in runs
        if isinstance(item, dict)
    ]


def summarize_ci_runs(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not runs:
        return {
            "status": "not_started",
            "total_runs": 0,
            "runs": [],
        }

    normalized_runs = []

    for run in runs:
        normalized_runs.append(
            {
                "id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "branch": run.get("head_branch"),
                "head_sha": run.get("head_sha"),
                "html_url": run.get("html_url"),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
            }
        )

    active = [
        run
        for run in normalized_runs
        if run.get("status") != "completed"
    ]

    if active:
        overall_status = "pending"
    else:
        failures = [
            run
            for run in normalized_runs
            if run.get("conclusion")
            not in {
                "success",
                "skipped",
                "neutral",
            }
        ]

        if failures:
            overall_status = "failure"
        else:
            overall_status = "success"

    return {
        "status": overall_status,
        "total_runs": len(normalized_runs),
        "runs": normalized_runs,
    }


def get_pull_request_ci(
    owner: str,
    repo: str,
    pull_number: int,
) -> dict[str, Any]:
    pull_request = get_pull_request(
        owner=owner,
        repo=repo,
        pull_number=pull_number,
    )

    head = pull_request.get(
        "head",
        {},
    )

    branch = head.get("ref")
    head_sha = head.get("sha")

    runs = list_workflow_runs(
        owner=owner,
        repo=repo,
        branch=branch,
        head_sha=head_sha,
    )

    return {
        "pull_request": {
            "number": pull_request.get("number"),
            "title": pull_request.get("title"),
            "state": pull_request.get("state"),
            "merged": pull_request.get("merged"),
            "html_url": pull_request.get("html_url"),
            "head": {
                "ref": branch,
                "sha": head_sha,
            },
            "base": {
                "ref": pull_request.get(
                    "base",
                    {},
                ).get("ref"),
            },
        },
        "ci": summarize_ci_runs(
            runs
        ),
    }