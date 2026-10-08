import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()


GITHUB_API = "https://api.github.com"


def _github_headers() -> dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_repository_metadata(owner: str, repo: str) -> dict:
    response = httpx.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=_github_headers(),
        timeout=20,
    )

    response.raise_for_status()

    return response.json()


def _create_askpass_script(folder: Path) -> Path:
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured")

    script = folder / ".devpilot-askpass.cmd"

    script.write_text(
        """@echo off
set "prompt=%~1"
echo %prompt% | findstr /i "username" >nul
if not errorlevel 1 (
    echo x-access-token
) else (
    echo %GITHUB_TOKEN%
)
""",
        encoding="utf-8",
    )

    return script


def clone_repository(
    owner: str,
    repo: str,
    branch: str | None = None,
) -> dict:
    metadata = get_repository_metadata(owner, repo)

    selected_branch = branch or metadata.get("default_branch") or "main"

    root = Path(
        tempfile.mkdtemp(
            prefix=f"devpilot_{owner}_{repo}_"
        )
    ).resolve()

    destination = root / repo
    askpass = _create_askpass_script(root)

    env = dict(os.environ)
    env["GITHUB_TOKEN"] = os.getenv("GITHUB_TOKEN", "").strip()
    env["GIT_ASKPASS"] = str(askpass)
    env["GIT_TERMINAL_PROMPT"] = "0"

    clone_url = (
        f"https://x-access-token@github.com/"
        f"{owner}/{repo}.git"
    )

    try:
        completed = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                selected_branch,
                clone_url,
                str(destination),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            env=env,
        )

        if completed.returncode != 0:
            shutil.rmtree(root, ignore_errors=True)

            raise RuntimeError(
                "Git clone failed: "
                + (completed.stderr or completed.stdout).strip()
            )

        return {
            "workspace": str(destination),
            "root": str(root),
            "branch": selected_branch,
            "repository": f"{owner}/{repo}",
            "default_branch": metadata.get("default_branch"),
        }

    finally:
        try:
            askpass.unlink(missing_ok=True)
        except Exception:
            pass


def cleanup_workspace(workspace_info: dict) -> None:
    root = workspace_info.get("root")

    if root:
        shutil.rmtree(root, ignore_errors=True)