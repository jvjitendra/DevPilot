from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any


MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_EDITS_PER_FILE = 8
MAX_TOTAL_FILES = 12
MAX_TOTAL_CHANGED_LINES = 1200


BLOCKED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}


BLOCKED_EXTENSIONS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
}


BLOCKED_PATH_PARTS = {
    ".git",
    ".github/workflows",
}


ALLOWED_TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".json",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".xml",
    ".sql",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".php",
    ".sh",
    ".bat",
    ".ps1",
}


def _resolve_root(workspace: str | Path) -> Path:
    root = Path(workspace).resolve()

    if not root.exists():
        raise ValueError(f"Workspace does not exist: {root}")

    if not root.is_dir():
        raise ValueError(f"Workspace is not a directory: {root}")

    return root


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    raw = str(relative_path or "").strip()

    if not raw:
        raise ValueError("Patch file path cannot be empty.")

    normalized = raw.replace("\\", "/").strip("/")
    candidate = (root / normalized).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Patch path escapes workspace: {raw}"
        ) from exc

    parts = [part.lower() for part in Path(normalized).parts]

    if ".git" in parts:
        raise ValueError("Patching .git content is not allowed.")

    lowered = normalized.lower()

    if any(
        lowered == part or lowered.startswith(part + "/")
        for part in BLOCKED_PATH_PARTS
    ):
        raise ValueError(
            f"Protected path cannot be patched: {raw}"
        )

    filename = candidate.name.lower()

    if filename in BLOCKED_FILENAMES:
        raise ValueError(
            f"Protected file cannot be patched: {raw}"
        )

    if candidate.suffix.lower() in BLOCKED_EXTENSIONS:
        raise ValueError(
            f"Sensitive file type cannot be patched: {raw}"
        )

    if (
        candidate.suffix
        and candidate.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS
    ):
        raise ValueError(
            f"File type is not allowlisted for patching: {raw}"
        )

    return candidate


def _read_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(
            f"Patch target does not exist: {path}"
        )

    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(
            f"Patch target is too large: {path.name}"
        )

    return path.read_bytes()


def _decode_text(raw: bytes, path: Path) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Patch target is not a UTF-8 text file: {path.name}"
        ) from exc


def _normalize_edit(edit: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(edit, dict):
        raise ValueError(
            "Each patch edit must be a JSON object."
        )

    find = edit.get("find")
    replace = edit.get("replace")

    if find is None:
        raise ValueError(
            "Patch edit is missing 'find'."
        )

    if replace is None:
        raise ValueError(
            "Patch edit is missing 'replace'."
        )

    find_text = str(find)
    replace_text = str(replace)

    if not find_text:
        raise ValueError(
            "Patch 'find' cannot be empty."
        )

    return find_text, replace_text


def _apply_edits_to_text(
    original: str,
    edits: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:

    if not isinstance(edits, list):
        raise ValueError(
            "'edits' must be a list."
        )

    if not edits:
        raise ValueError(
            "At least one edit is required."
        )

    if len(edits) > MAX_EDITS_PER_FILE:
        raise ValueError(
            (
                f"Too many edits for one file. "
                f"Maximum is {MAX_EDITS_PER_FILE}."
            )
        )

    updated = original
    applied: list[dict[str, Any]] = []

    for index, edit in enumerate(edits, start=1):
        find_text, replace_text = _normalize_edit(edit)

        occurrences = updated.count(find_text)

        if occurrences == 0:
            candidate_crlf = find_text.replace("\r\n", "\n").replace("\n", "\r\n")
            candidate_lf = find_text.replace("\r\n", "\n")
            if updated.count(candidate_crlf) == 1:
                find_text = candidate_crlf
                replace_text = replace_text.replace("\r\n", "\n").replace("\n", "\r\n")
                occurrences = 1
            elif updated.count(candidate_lf) == 1:
                find_text = candidate_lf
                replace_text = replace_text.replace("\r\n", "\n")
                occurrences = 1

        if occurrences != 1:
            raise ValueError(
                (
                    f"Edit {index}: expected exact source "
                    f"text to occur once, found {occurrences}."
                )
            )

        updated = updated.replace(
            find_text,
            replace_text,
            1,
        )

        applied.append(
            {
                "edit": index,
                "matched_once": True,
                "find_chars": len(find_text),
                "replace_chars": len(replace_text),
            }
        )

    return updated, applied


def _build_unified_diff(
    path_display: str,
    original: str,
    updated: str,
) -> str:

    original_lines = original.splitlines(
        keepends=True
    )

    updated_lines = updated.splitlines(
        keepends=True
    )

    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"a/{path_display}",
        tofile=f"b/{path_display}",
        lineterm="",
    )

    return "\n".join(diff)


def _diff_stats(
    original: str,
    updated: str,
) -> dict[str, int]:

    original_lines = original.splitlines()
    updated_lines = updated.splitlines()

    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            updated_lines,
            lineterm="",
        )
    )

    added = 0
    removed = 0

    for line in diff_lines:
        if line.startswith("+++"):
            continue

        if line.startswith("---"):
            continue

        if line.startswith("+"):
            added += 1

        elif line.startswith("-"):
            removed += 1

    return {
        "added": added,
        "removed": removed,
        "changed": added + removed,
    }


def _fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _scope_guard(
    changed_files: list[dict[str, Any]],
) -> dict[str, Any]:

    total_added = sum(
        int(item["stats"]["added"])
        for item in changed_files
    )

    total_removed = sum(
        int(item["stats"]["removed"])
        for item in changed_files
    )

    total_changed = total_added + total_removed

    return {
        "files_changed": len(changed_files),
        "lines_added": total_added,
        "lines_removed": total_removed,
        "lines_changed": total_changed,
        "within_limits": (
            len(changed_files) <= MAX_TOTAL_FILES
            and total_changed <= MAX_TOTAL_CHANGED_LINES
        ),
        "max_files": MAX_TOTAL_FILES,
        "max_changed_lines": MAX_TOTAL_CHANGED_LINES,
    }


def apply_patch(
    workspace: str | Path,
    patch: dict[str, Any],
) -> dict[str, Any]:

    root = _resolve_root(workspace)

    if not isinstance(patch, dict):
        raise ValueError(
            "Patch must be a JSON object."
        )

    files = patch.get("files")

    if not isinstance(files, list):
        raise ValueError(
            "Patch must contain a 'files' list."
        )

    if not files:
        return {
            "status": "no_changes_required",
            "summary": (
                "The patch contains no file changes."
            ),
            "files_changed": 0,
            "files": [],
            "scope": {
                "files_changed": 0,
                "lines_added": 0,
                "lines_removed": 0,
                "lines_changed": 0,
                "within_limits": True,
                "max_files": MAX_TOTAL_FILES,
                "max_changed_lines": MAX_TOTAL_CHANGED_LINES,
            },
            "diff": "",
        }

    if len(files) > MAX_TOTAL_FILES:
        raise ValueError(
            (
                f"Patch contains {len(files)} files. "
                f"Maximum is {MAX_TOTAL_FILES}."
            )
        )

    originals: dict[Path, bytes] = {}
    original_texts: dict[Path, str] = {}
    updated_texts: dict[Path, str] = {}
    updated_bytes: dict[Path, bytes] = {}
    metadata: list[dict[str, Any]] = []

    try:
        # -------------------------------------------------
        # 1. VALIDATE EVERYTHING BEFORE WRITING ANYTHING
        # -------------------------------------------------

        for file_spec in files:
            if not isinstance(file_spec, dict):
                raise ValueError(
                    "Each patch file must be a JSON object."
                )

            path_raw = file_spec.get("path")

            if not path_raw:
                raise ValueError(
                    "Patch file is missing 'path'."
                )

            path = _safe_relative_path(
                root,
                str(path_raw),
            )

            if path in originals:
                raise ValueError(
                    f"Duplicate patch target: {path_raw}"
                )

            raw_original = _read_bytes(path)
            original = _decode_text(
                raw_original,
                path,
            )

            edits = file_spec.get("edits")

            updated, applied = _apply_edits_to_text(
                original,
                edits,
            )

            if updated == original:
                raise ValueError(
                    (
                        f"Patch for '{path_raw}' "
                        "does not change the file."
                    )
                )

            raw_updated = updated.encode(
                "utf-8"
            )

            stats = _diff_stats(
                original,
                updated,
            )

            originals[path] = raw_original
            original_texts[path] = original
            updated_texts[path] = updated
            updated_bytes[path] = raw_updated

            relative_display = str(
                path.relative_to(root)
            ).replace("\\", "/")

            metadata.append(
                {
                    "path": relative_display,
                    "before_sha": _fingerprint(
                        raw_original
                    ),
                    "after_sha": _fingerprint(
                        raw_updated
                    ),
                    "stats": stats,
                    "edits": applied,
                }
            )

        scope = _scope_guard(
            metadata
        )

        if not scope["within_limits"]:
            raise ValueError(
                (
                    "Patch exceeds the safe change-scope "
                    "limits."
                )
            )

        # -------------------------------------------------
        # 2. WRITE EXACT BYTES
        # -------------------------------------------------

        for path, raw_updated in updated_bytes.items():
            path.write_bytes(
                raw_updated
            )

        # -------------------------------------------------
        # 3. VERIFY EXACT BYTES
        # -------------------------------------------------

        verification: list[dict[str, Any]] = []

        for path, expected_bytes in updated_bytes.items():
            actual_bytes = _read_bytes(path)

            verified = (
                actual_bytes == expected_bytes
            )

            verification.append(
                {
                    "path": str(
                        path.relative_to(root)
                    ).replace("\\", "/"),
                    "verified": verified,
                    "expected_sha": _fingerprint(
                        expected_bytes
                    ),
                    "actual_sha": _fingerprint(
                        actual_bytes
                    ),
                }
            )

            if not verified:
                raise RuntimeError(
                    (
                        "Post-write verification failed "
                        f"for {path.name}."
                    )
                )

        # -------------------------------------------------
        # 4. BUILD DIFF
        # -------------------------------------------------

        diffs: list[str] = []

        for item in metadata:
            path_display = item["path"]
            path = root / Path(path_display)

            diff = _build_unified_diff(
                path_display,
                original_texts[path],
                updated_texts[path],
            )

            if diff:
                diffs.append(diff)

        combined_diff = "\n".join(
            diffs
        )

        return {
            "status": "applied",
            "summary": (
                f"Patch applied safely to "
                f"{scope['files_changed']} file(s)."
            ),
            "files_changed": scope[
                "files_changed"
            ],
            "files": metadata,
            "verification": verification,
            "scope": scope,
            "diff": combined_diff,
        }

    except Exception:
        # -------------------------------------------------
        # 5. ROLLBACK TO ORIGINAL BYTES
        # -------------------------------------------------

        for path, raw_original in originals.items():
            try:
                path.write_bytes(
                    raw_original
                )
            except Exception:
                pass

        raise