from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 300
MAX_PYTHON_SETUP_SECONDS = 300


ALLOWED_COMMAND_PATTERNS = [
    r"^pytest(?:\.exe)?(?:\s|$)",
    r"^python(?:\.exe)?\s+-m\s+pytest(?:\s|$)",
    r"^python(?:\.exe)?\s+-m\s+unittest(?:\s|$)",
    r"^npm\s+(?:test|ci|install)(?:\s|$)",
    r"^npm\s+run\s+(?:test|lint|build)(?:\s|$)",
    r"^node\s+--test(?:\s|$)",
    r"^go\s+test(?:\s|$)",
    r"^cargo\s+test(?:\s|$)",
]


BLOCKED_COMMAND_PATTERNS = [
    r"(?i)\brm\s+-rf\b",
    r"(?i)\brm\s+-r\b",
    r"(?i)\bremove-item\b",
    r"(?i)\bdel(?:\.exe)?\b",
    r"(?i)\bformat(?:\.exe)?\b",
    r"(?i)\bdrop\s+database\b",
    r"(?i)\bgit\s+push\s+--force\b",
    r"(?i)\bgit\s+push\s+-f\b",
    r"(?i)\bgit\s+reset\s+--hard\b",
    r"(?i)\bshutdown\b",
    r"(?i)\brestart-computer\b",
    r"(?i)\bpowershell(?:\.exe)?\s+-c\b",
    r"(?i)\bcmd(?:\.exe)?\s+/c\b",
    r"(?i)\bbash(?:\.exe)?\s+-c\b",
    r"(?i)\bsh(?:\.exe)?\s+-c\b",
]


BLOCKED_SHELL_TOKENS = [
    "&&",
    "||",
    ";",
    ">",
    "<",
    "|",
]


REQUIREMENTS_CANDIDATES = [
    Path("requirements.txt"),
    Path("backend") / "requirements.txt",
]


def _truncate_output(value: str) -> str:
    text = value or ""

    if len(text) <= MAX_OUTPUT_CHARS:
        return text

    half = MAX_OUTPUT_CHARS // 2

    return (
        text[:half]
        + "\n\n[OUTPUT TRUNCATED BY DEVPILOT]\n\n"
        + text[-half:]
    )


def _mask_secrets(value: str) -> str:
    text = value or ""

    patterns = [
        (
            r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,]+)",
            r"\1[REDACTED]",
        ),
        (
            r"(?i)(access[_-]?token\s*[=:]\s*)([^\s,]+)",
            r"\1[REDACTED]",
        ),
        (
            r"(?i)(secret\s*[=:]\s*)([^\s,]+)",
            r"\1[REDACTED]",
        ),
        (
            r"(?i)(password\s*[=:]\s*)([^\s,]+)",
            r"\1[REDACTED]",
        ),
        (
            r"(?i)(authorization\s*[=:]\s*)([^\s,]+)",
            r"\1[REDACTED]",
        ),
        (
            r"(?i)(bearer\s+)([A-Za-z0-9._\-+/=]+)",
            r"\1[REDACTED]",
        ),
    ]

    for pattern, replacement in patterns:
        text = re.sub(
            pattern,
            replacement,
            text,
        )

    return text


def _safe_environment(
    base_env: dict[str, str] | None = None,
    venv_path: Path | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)

    secret_names = {
        "GITHUB_TOKEN",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DATABASE_URL",
        "SECRET_KEY",
        "NVIDIA_API_KEY",
    }

    for name in secret_names:
        env.pop(name, None)

    env["PYTHONNOUSERSITE"] = "1"

    if venv_path is not None:
        scripts_dir = (
            venv_path / "Scripts"
            if os.name == "nt"
            else venv_path / "bin"
        )

        env["PATH"] = (
            str(scripts_dir)
            + os.pathsep
            + env.get("PATH", "")
        )

        env["VIRTUAL_ENV"] = str(venv_path)

    return env


def _is_blocked_command(
    command: str,
) -> tuple[bool, str]:
    normalized = (command or "").strip()

    for pattern in BLOCKED_COMMAND_PATTERNS:
        if re.search(pattern, normalized):
            return (
                True,
                f"Command matched blocked safety pattern: {pattern}",
            )

    for token in BLOCKED_SHELL_TOKENS:
        if token in normalized:
            return (
                True,
                (
                    f"Shell chaining/redirection token '{token}' "
                    "is not allowed."
                ),
            )

    return False, ""


def _is_allowed_command(
    command: str,
) -> bool:
    normalized = (command or "").strip()

    return any(
        re.match(pattern, normalized)
        for pattern in ALLOWED_COMMAND_PATTERNS
    )


def _validate_timeout(
    timeout_seconds: int,
) -> int:
    try:
        value = int(timeout_seconds)
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT_SECONDS

    return max(
        1,
        min(
            value,
            MAX_TIMEOUT_SECONDS,
        ),
    )


def _resolve_workspace_path(
    workspace: str | Path,
) -> Path:
    path = Path(workspace).resolve()

    if not path.exists():
        raise ValueError(
            f"Workspace does not exist: {path}"
        )

    if not path.is_dir():
        raise ValueError(
            f"Workspace is not a directory: {path}"
        )

    return path


def _find_python_manifest(
    workspace: Path,
) -> Path | None:
    for relative_path in REQUIREMENTS_CANDIDATES:
        candidate = workspace / relative_path

        if candidate.is_file():
            return candidate

    return None


def _requirements_fingerprint(
    requirements_path: Path,
) -> str:
    data = requirements_path.read_bytes()

    return hashlib.sha256(data).hexdigest()


def _venv_python(
    venv_path: Path,
) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"

    return venv_path / "bin" / "python"


def _venv_pip(
    venv_path: Path,
) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "pip.exe"

    return venv_path / "bin" / "pip"


def _run_setup_process(
    args: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> tuple[
    int | None,
    str,
    str,
    int,
    bool,
]:
    start = time.perf_counter()

    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            env=_safe_environment(),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        duration_ms = int(
            (time.perf_counter() - start) * 1000
        )

        return (
            completed.returncode,
            _mask_secrets(
                _truncate_output(
                    completed.stdout or ""
                )
            ),
            _mask_secrets(
                _truncate_output(
                    completed.stderr or ""
                )
            ),
            duration_ms,
            False,
        )

    except subprocess.TimeoutExpired as exc:
        duration_ms = int(
            (time.perf_counter() - start) * 1000
        )

        stdout = (
            exc.stdout.decode(
                errors="replace"
            )
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )

        stderr = (
            exc.stderr.decode(
                errors="replace"
            )
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )

        return (
            None,
            _mask_secrets(
                _truncate_output(stdout)
            ),
            _mask_secrets(
                _truncate_output(stderr)
            ),
            duration_ms,
            True,
        )

    except Exception as exc:
        duration_ms = int(
            (time.perf_counter() - start) * 1000
        )

        return (
            None,
            "",
            _mask_secrets(str(exc)),
            duration_ms,
            False,
        )


def prepare_python_environment(
    workspace: str | Path,
) -> dict[str, Any]:
    root = _resolve_workspace_path(workspace)

    requirements_path = _find_python_manifest(
        root
    )

    if requirements_path is None:
        return {
            "status": "not_required",
            "language": "python",
            "requirements_file": None,
            "venv_path": None,
            "python": None,
            "pip": None,
            "message": (
                "No Python requirements manifest was found."
            ),
        }

    venv_path = root / ".devpilot_venv"

    marker_path = (
        venv_path
        / ".devpilot_requirements.sha256"
    )

    fingerprint = _requirements_fingerprint(
        requirements_path
    )

    python_executable = _venv_python(
        venv_path
    )

    if (
        python_executable.exists()
        and marker_path.is_file()
        and marker_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()
        == fingerprint
    ):
        return {
            "status": "ready",
            "language": "python",
            "requirements_file": str(
                requirements_path.relative_to(root)
            ),
            "venv_path": str(venv_path),
            "python": str(python_executable),
            "pip": str(
                _venv_pip(venv_path)
            ),
            "reused": True,
        }

    try:
        if venv_path.exists():
            shutil.rmtree(
                venv_path,
                ignore_errors=True,
            )

        (
            venv_exit_code,
            venv_stdout,
            venv_stderr,
            venv_duration_ms,
            venv_timed_out,
        ) = _run_setup_process(
            [
                sys.executable,
                "-m",
                "venv",
                str(venv_path),
            ],
            root,
            MAX_PYTHON_SETUP_SECONDS,
        )

        if venv_timed_out:
            return {
                "status": "setup_failed",
                "language": "python",
                "requirements_file": str(
                    requirements_path.relative_to(root)
                ),
                "venv_path": str(venv_path),
                "error": (
                    "Virtual environment creation timed out."
                ),
                "stdout": venv_stdout,
                "stderr": venv_stderr,
                "duration_ms": venv_duration_ms,
            }

        if (
            venv_exit_code != 0
            or not python_executable.exists()
        ):
            return {
                "status": "setup_failed",
                "language": "python",
                "requirements_file": str(
                    requirements_path.relative_to(root)
                ),
                "venv_path": str(venv_path),
                "error": (
                    "Failed to create isolated "
                    "Python environment."
                ),
                "exit_code": venv_exit_code,
                "stdout": venv_stdout,
                "stderr": venv_stderr,
                "duration_ms": venv_duration_ms,
            }

        pip_executable = _venv_pip(
            venv_path
        )

        (
            install_exit_code,
            install_stdout,
            install_stderr,
            install_duration_ms,
            install_timed_out,
        ) = _run_setup_process(
            [
                str(python_executable),
                "-m",
                "pip",
                "install",
                "-r",
                str(requirements_path),
            ],
            root,
            MAX_PYTHON_SETUP_SECONDS,
        )

        if install_timed_out:
            return {
                "status": "setup_failed",
                "language": "python",
                "requirements_file": str(
                    requirements_path.relative_to(root)
                ),
                "venv_path": str(venv_path),
                "python": str(python_executable),
                "pip": str(pip_executable),
                "error": (
                    "Dependency installation timed out."
                ),
                "exit_code": None,
                "stdout": install_stdout,
                "stderr": install_stderr,
                "duration_ms": install_duration_ms,
            }

        if install_exit_code != 0:
            return {
                "status": "setup_failed",
                "language": "python",
                "requirements_file": str(
                    requirements_path.relative_to(root)
                ),
                "venv_path": str(venv_path),
                "python": str(python_executable),
                "pip": str(pip_executable),
                "error": (
                    "Repository dependency installation failed."
                ),
                "exit_code": install_exit_code,
                "stdout": install_stdout,
                "stderr": install_stderr,
                "duration_ms": install_duration_ms,
            }

        marker_path.write_text(
            fingerprint,
            encoding="utf-8",
        )

        return {
            "status": "ready",
            "language": "python",
            "requirements_file": str(
                requirements_path.relative_to(root)
            ),
            "venv_path": str(venv_path),
            "python": str(python_executable),
            "pip": str(pip_executable),
            "reused": False,
            "install_duration_ms": install_duration_ms,
        }

    except Exception as exc:
        return {
            "status": "setup_failed",
            "language": "python",
            "requirements_file": str(
                requirements_path.relative_to(root)
            ),
            "venv_path": str(venv_path),
            "error": _mask_secrets(
                str(exc)
            ),
        }


def _extract_pytest_target(
    command: str,
) -> tuple[str | None, str | None]:
    normalized = (command or "").strip()

    match = re.match(
        r"^(?:python(?:\.exe)?\s+-m\s+pytest|pytest(?:\.exe)?)\s+(.+)$",
        normalized,
    )

    if not match:
        return None, None

    remainder = match.group(1).strip()

    try:
        tokens = shlex.split(
            remainder,
            posix=False,
        )
    except ValueError:
        tokens = remainder.split()

    target_token = None

    for token in tokens:
        cleaned = token.strip('"')

        if cleaned.startswith("-"):
            continue

        target_token = cleaned
        break

    if not target_token:
        return None, None

    if "::" not in target_token:
        return target_token, None

    test_file, test_name = target_token.split(
        "::",
        1,
    )

    return (
        test_file,
        test_name,
    )


def _collect_pytest_targets(
    test_file: Path,
    cwd: Path,
    env: dict[str, str],
) -> tuple[
    bool,
    list[str],
    str,
    str,
]:
    start = time.perf_counter()

    python_cmd = "python"

    try:
        completed = subprocess.run(
            [
                python_cmd,
                "-m",
                "pytest",
                str(test_file),
                "--collect-only",
                "-q",
            ],
            cwd=str(cwd),
            env=env,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

        duration_ms = int(
            (time.perf_counter() - start) * 1000
        )

        stdout_raw = completed.stdout or ""
        stderr_raw = completed.stderr or ""

        stdout = _mask_secrets(
            _truncate_output(
                stdout_raw
            )
        )

        stderr = _mask_secrets(
            _truncate_output(
                stderr_raw
            )
        )

        combined = (
            stdout_raw
            + "\n"
            + stderr_raw
        )

        candidates: list[str] = []

        for line in combined.splitlines():
            line = line.strip()

            if not line:
                continue

            if "::" not in line:
                continue

            if line.startswith("="):
                continue

            if line.startswith("<"):
                continue

            candidate = line.split(
                " ",
                1,
            )[0].strip()

            candidate = candidate.rstrip()

            if (
                "::" in candidate
                and candidate not in candidates
            ):
                candidates.append(candidate)

        return (
            completed.returncode == 0,
            candidates,
            stdout,
            stderr,
        )

    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(
                errors="replace"
            )
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )

        stderr = (
            exc.stderr.decode(
                errors="replace"
            )
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )

        return (
            False,
            [],
            _mask_secrets(
                _truncate_output(stdout)
            ),
            _mask_secrets(
                _truncate_output(stderr)
            ),
        )

    except Exception as exc:
        return (
            False,
            [],
            "",
            _mask_secrets(
                str(exc)
            ),
        )


def validate_pytest_target(
    command: str,
    cwd: str | Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = _resolve_workspace_path(
        cwd
    )

    test_file_raw, requested_target = (
        _extract_pytest_target(
            command
        )
    )

    if (
        not test_file_raw
        or not requested_target
    ):
        return {
            "valid": True,
            "status": "not_applicable",
            "reason": (
                "Command does not contain an "
                "explicit pytest test node target."
            ),
        }

    test_file = (
        root / test_file_raw
    ).resolve()

    try:
        test_file.relative_to(root)
    except ValueError:
        return {
            "valid": False,
            "status": "invalid_target",
            "reason": (
                "Pytest test file escapes the "
                "isolated workspace."
            ),
            "test_file": test_file_raw,
            "requested_target": requested_target,
            "candidates": [],
        }

    if not test_file.is_file():
        return {
            "valid": False,
            "status": "invalid_target",
            "reason": (
                f"Pytest test file "
                f"'{test_file_raw}' does not exist "
                "in the workspace."
            ),
            "test_file": test_file_raw,
            "requested_target": requested_target,
            "candidates": [],
        }

    safe_env = env or _safe_environment()

    (
        collected_ok,
        candidates,
        stdout,
        stderr,
    ) = _collect_pytest_targets(
        test_file=test_file,
        cwd=root,
        env=safe_env,
    )

    requested_full = (
        f"{test_file_raw}::{requested_target}"
    )

    candidate_targets = [
        item
        for item in candidates
        if item.startswith(
            f"{test_file_raw}::"
        )
    ]

    if requested_full in candidate_targets:
        return {
            "valid": True,
            "status": "valid",
            "reason": (
                "Requested pytest target exists "
                "in the collected tests."
            ),
            "test_file": test_file_raw,
            "requested_target": requested_target,
            "candidates": candidate_targets,
            "collect_stdout": stdout,
            "collect_stderr": stderr,
        }

    normalized_requested = (
        requested_full.replace(
            "\\",
            "/",
        )
    )

    normalized_candidates = [
        item.replace(
            "\\",
            "/",
        )
        for item in candidate_targets
    ]

    if (
        normalized_requested
        in normalized_candidates
    ):
        return {
            "valid": True,
            "status": "valid",
            "reason": (
                "Requested pytest target exists "
                "in the collected tests."
            ),
            "test_file": test_file_raw,
            "requested_target": requested_target,
            "candidates": candidate_targets,
            "collect_stdout": stdout,
            "collect_stderr": stderr,
        }

    return {
        "valid": False,
        "status": "invalid_target",
        "reason": (
            f"Pytest target '{requested_target}' "
            f"was not found in {test_file_raw}"
        ),
        "test_file": test_file_raw,
        "requested_target": requested_target,
        "candidates": candidate_targets,
        "collect_stdout": stdout,
        "collect_stderr": stderr,
        "collection_ok": collected_ok,
    }


def execute_command(
    command: str,
    cwd: str | Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
    workspace_setup: dict[str, Any] | None = None,
) -> dict[str, Any]:

    root = _resolve_workspace_path(
        cwd
    )

    command = str(
        command or ""
    ).strip()

    if not command:
        return {
            "status": "error",
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": (
                "Command cannot be empty."
            ),
            "duration_ms": 0,
            "timed_out": False,
        }

    blocked, blocked_reason = (
        _is_blocked_command(
            command
        )
    )

    if blocked:
        return {
            "status": "blocked",
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": blocked_reason,
            "duration_ms": 0,
            "timed_out": False,
        }

    if not _is_allowed_command(
        command
    ):
        return {
            "status": "blocked",
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": (
                "Command is not on the "
                "DevPilot execution allowlist."
            ),
            "duration_ms": 0,
            "timed_out": False,
        }

    timeout_seconds = _validate_timeout(
        timeout_seconds
    )

    setup_venv = None

    if (
        workspace_setup
        and workspace_setup.get("status")
        == "ready"
        and workspace_setup.get("venv_path")
    ):
        setup_venv = Path(
            workspace_setup["venv_path"]
        )

    safe_env = (
        env
        if env is not None
        else _safe_environment(
            venv_path=setup_venv
        )
    )

    validation = validate_pytest_target(
        command=command,
        cwd=root,
        env=safe_env,
    )

    if validation.get("status") == "invalid_target":
        return {
            "status": "invalid_target",
            "command": command,
            "exit_code": None,
            "stdout": validation.get(
                "collect_stdout",
                "",
            ),
            "stderr": validation.get(
                "collect_stderr",
                "",
            ),
            "duration_ms": 0,
            "timed_out": False,
            "validation": validation,
        }

    start = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=safe_env,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        duration_ms = int(
            (time.perf_counter() - start)
            * 1000
        )

        stdout = _mask_secrets(
            _truncate_output(
                completed.stdout or ""
            )
        )

        stderr = _mask_secrets(
            _truncate_output(
                completed.stderr or ""
            )
        )

        status = (
            "passed"
            if completed.returncode == 0
            else "failed"
        )

        return {
            "status": status,
            "command": command,
            "exit_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": duration_ms,
            "timed_out": False,
            "validation": validation,
        }

    except subprocess.TimeoutExpired as exc:
        duration_ms = int(
            (time.perf_counter() - start)
            * 1000
        )

        stdout = (
            exc.stdout.decode(
                errors="replace"
            )
            if isinstance(
                exc.stdout,
                bytes,
            )
            else (
                exc.stdout or ""
            )
        )

        stderr = (
            exc.stderr.decode(
                errors="replace"
            )
            if isinstance(
                exc.stderr,
                bytes,
            )
            else (
                exc.stderr or ""
            )
        )

        return {
            "status": "timeout",
            "command": command,
            "exit_code": None,
            "stdout": _mask_secrets(
                _truncate_output(
                    stdout
                )
            ),
            "stderr": _mask_secrets(
                _truncate_output(
                    stderr
                )
            ),
            "duration_ms": duration_ms,
            "timed_out": True,
            "validation": validation,
        }

    except Exception as exc:
        duration_ms = int(
            (time.perf_counter() - start)
            * 1000
        )

        return {
            "status": "error",
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr": _mask_secrets(
                str(exc)
            ),
            "duration_ms": duration_ms,
            "timed_out": False,
            "validation": validation,
        }


def execute_commands(
    commands: list[str],
    cwd: str | Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """
    Execute one or more allowlisted commands in an isolated workspace.

    `workspace` is retained as a compatibility alias for callers that
    use the existing API layer.

    Example:
        execute_commands(
            commands=[...],
            workspace=temp_workspace,
        )

    or:

        execute_commands(
            commands=[...],
            cwd=temp_workspace,
        )
    """

    selected_workspace = (
        workspace
        if workspace is not None
        else cwd
    )

    if selected_workspace is None:
        return {
            "status": "error",
            "summary": (
                "No execution workspace was supplied."
            ),
            "commands": commands
            if isinstance(commands, list)
            else [],
            "results": [],
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "invalid_targets": 0,
        }

    root = _resolve_workspace_path(
        selected_workspace
    )

    if not isinstance(
        commands,
        list,
    ):
        return {
            "status": "error",
            "summary": (
                "commands must be a list."
            ),
            "commands": [],
            "results": [],
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "invalid_targets": 0,
        }

    if not commands:
        return {
            "status": "error",
            "summary": (
                "No commands were supplied."
            ),
            "commands": [],
            "results": [],
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "invalid_targets": 0,
        }

    timeout_seconds = _validate_timeout(
        timeout_seconds
    )

    workspace_setup = (
        prepare_python_environment(
            root
        )
    )

    if (
        workspace_setup.get("status")
        == "setup_failed"
    ):
        return {
            "status": "setup_failed",
            "summary": (
                "Repository dependency environment "
                "could not be prepared. "
                "Test execution was stopped."
            ),
            "commands": commands,
            "results": [],
            "passed": 0,
            "failed": 0,
            "blocked": 0,
            "invalid_targets": 0,
            "workspace_setup": workspace_setup,
        }

    setup_venv = None

    if (
        workspace_setup.get("status")
        == "ready"
        and workspace_setup.get("venv_path")
    ):
        setup_venv = Path(
            workspace_setup["venv_path"]
        )

    execution_env = _safe_environment(
        venv_path=setup_venv
    )

    results: list[dict[str, Any]] = []

    passed = 0
    failed = 0
    blocked = 0
    invalid_targets = 0

    for command in commands:
        result = execute_command(
            command=command,
            cwd=root,
            timeout_seconds=timeout_seconds,
            env=execution_env,
            workspace_setup=workspace_setup,
        )

        results.append(result)

        status = result.get(
            "status"
        )

        if status == "passed":
            passed += 1

        elif status == "blocked":
            blocked += 1
            break

        elif status == "invalid_target":
            invalid_targets += 1
            break

        elif status in {
            "failed",
            "timeout",
            "error",
        }:
            failed += 1
            break

    if blocked > 0:
        overall_status = "blocked"

    elif invalid_targets > 0:
        overall_status = "invalid_target"

    elif failed > 0:
        overall_status = "failed"

    elif passed == len(commands):
        overall_status = "passed"

    else:
        overall_status = "error"

    summary = (
        f"{passed} passed, "
        f"{failed} failed, "
        f"{blocked} blocked, "
        f"{invalid_targets} invalid target(s) "
        f"out of {len(results)} executed "
        f"command(s)."
    )

    return {
        "status": overall_status,
        "summary": summary,
        "commands": commands,
        "results": results,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "invalid_targets": invalid_targets,
        "workspace_setup": workspace_setup,
    }