import difflib
import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

try:
    from groq import Groq
except Exception:
    Groq = None


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GEMINI_PRIMARY = "gemini-3.8-flash"
GEMINI_FALLBACK = "gemini-3.7-flash"
GEMINI_SECONDARY_FALLBACK = "gemini-3.6-flash"

GROQ_MODEL = "qwen/qwen3.8-27b"

MAX_TARGET_FILES = 4
MAX_FILE_CONTEXT_CHARS = 18000
MAX_TOTAL_CONTEXT_CHARS = 42000
MAX_OUTPUT_TOKENS = 1400
MAX_EDITS_PER_FILE = 8


gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if genai is not None and GEMINI_API_KEY
    else None
)

groq_client = (
    Groq(api_key=GROQ_API_KEY)
    if Groq is not None and GROQ_API_KEY
    else None
)


SYSTEM_PROMPT = """
You are DevPilot, an AI software patch generation agent.

Your job is to convert a validated implementation plan into small,
deterministic source-code edits.

CRITICAL SAFETY RULES:

1. Use ONLY the supplied issue, analysis, plan and source code.
2. Never invent source code.
3. Never generate a whole rewritten file unless absolutely necessary.
4. Prefer exact SEARCH/REPLACE edits.
5. Every "find" string MUST be copied exactly from the supplied source.
6. Every "find" string should uniquely identify the intended code location.
7. Keep each change as small as possible.
8. Do not modify unrelated code.
9. Do not modify secrets, .env files, credentials, tokens or private keys.
10. Do not change GitHub permissions, repository settings or destructive infrastructure.
11. Do not generate shell commands as replacements.
12. Do not create fake fixes when the analysis says no defect is confirmed.
13. If no justified code change exists, return an empty edits array.
14. Preserve existing coding style.
15. Return ONLY valid JSON.
16. Do not use markdown fences.

Required JSON:

{
  "status": "ready|no_changes_required|blocked",
  "summary": "string",
  "edits": [
    {
      "path": "string",
      "find": "exact source text",
      "replace": "replacement source text",
      "reason": "string"
    }
  ],
  "tests": ["string"],
  "risk": "low|medium|high",
  "notes": ["string"]
}

Rules for edits:

- "find" must match the supplied source exactly.
- Do not use placeholders such as "...".
- Do not omit characters.
- Do not use regular expressions.
- Do not use line-number prefixes inside find/replace unless they actually exist
  in the source code.
- Keep edits atomic.
"""


BLOCKED_PATH_PARTS = {
    ".env",
    ".git/",
    ".github/dependabot.yml",
    "credentials",
    "secrets",
    "private_key",
    "id_rsa",
}


def clean_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "")

    if limit is not None:
        return text[:limit]

    return text


def is_blocked_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").lower()

    if normalized in {".env", ".env.local", ".env.production"}:
        return True

    for blocked in BLOCKED_PATH_PARTS:
        if blocked in normalized:
            return True

    return False


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()

    if text.startswith("```"):
        if text.lower().startswith("```json"):
            text = text[7:]
        else:
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        raise ValueError("Patch AI returned invalid JSON.")

    parsed = json.loads(text[start:end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Patch AI returned a non-object JSON value.")

    return parsed


def normalize_patch_result(data: dict[str, Any]) -> dict[str, Any]:
    status = clean_text(data.get("status")).lower()

    if status not in {
        "ready",
        "no_changes_required",
        "blocked",
    }:
        status = "blocked"

    edits = []

    for item in data.get("edits", []) or []:
        if not isinstance(item, dict):
            continue

        edits.append(
            {
                "path": clean_text(item.get("path")),
                "find": clean_text(item.get("find")),
                "replace": clean_text(item.get("replace")),
                "reason": clean_text(item.get("reason")),
            }
        )

    tests = [
        clean_text(x)
        for x in (data.get("tests", []) or [])
        if clean_text(x)
    ]

    notes = [
        clean_text(x)
        for x in (data.get("notes", []) or [])
        if clean_text(x)
    ]

    risk = clean_text(data.get("risk")).lower()

    if risk not in {"low", "medium", "high"}:
        risk = "medium"

    return {
        "status": status,
        "summary": clean_text(data.get("summary")),
        "edits": edits[:30],
        "tests": tests[:10],
        "risk": risk,
        "notes": notes[:10],
    }


def build_patch_prompt(
    issue: dict[str, Any],
    analysis: dict[str, Any],
    plan: dict[str, Any],
    files: list[dict[str, Any]],
) -> str:
    sections = [
        "ISSUE:",
        json.dumps(
            {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "body": issue.get("body"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "ANALYSIS:",
        json.dumps(
            analysis,
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "IMPLEMENTATION PLAN:",
        json.dumps(
            plan,
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "SOURCE FILES:",
    ]

    total = sum(len(x) for x in sections)

    target_paths = {
        clean_text(item.get("path"))
        for item in (plan.get("files_to_modify", []) or [])
        if isinstance(item, dict) and clean_text(item.get("path"))
    }

    selected_files = []

    for file in files:
        if not isinstance(file, dict):
            continue

        path = clean_text(
            file.get("path") or file.get("name")
        )

        content = clean_text(file.get("content"))

        if not path or not content:
            continue

        if target_paths and path not in target_paths:
            continue

        selected_files.append(
            {
                "path": path,
                "content": content,
            }
        )

    if not selected_files:
        selected_files = [
            {
                "path": clean_text(
                    file.get("path") or file.get("name")
                ),
                "content": clean_text(
                    file.get("content")
                ),
            }
            for file in files
            if isinstance(file, dict)
        ]

    for file in selected_files[:MAX_TARGET_FILES]:

        content = file["content"]

        if len(content) > MAX_FILE_CONTEXT_CHARS:
            content = (
                content[:MAX_FILE_CONTEXT_CHARS]
                + "\n\n--- FILE CONTENT TRUNCATED ---\n"
            )

        block = (
            f"\nFILE: {file['path']}\n"
            f"{content}\n"
        )

        if total + len(block) > MAX_TOTAL_CONTEXT_CHARS:
            remaining = MAX_TOTAL_CONTEXT_CHARS - total

            if remaining <= 0:
                break

            lines = block.splitlines()

            kept = []
            size = 0

            for line in lines:
                extra = len(line) + 1

                if size + extra > remaining:
                    break

                kept.append(line)
                size += extra

            block = "\n".join(kept) + "\n"

        sections.append(block)
        total += len(block)

    return f"""
{SYSTEM_PROMPT}

Before creating an edit, verify:

- the target file is explicitly justified by the implementation plan;
- the exact search text exists in the supplied source;
- the search text identifies one specific location;
- the replacement is minimal;
- the edit does not alter unrelated behavior.

If the implementation plan says no code modification is justified,
return:

{{
  "status": "no_changes_required",
  "summary": "No justified code change is supported by current evidence.",
  "edits": [],
  "tests": [],
  "risk": "low",
  "notes": []
}}

SOURCE AND TASK CONTEXT:

{chr(10).join(sections)}
"""


def call_gemini(
    model: str,
    prompt: str,
) -> dict[str, Any]:
    if gemini_client is None or genai_types is None:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.05,
            response_mime_type="application/json",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )

    content = getattr(response, "text", None)

    if not content:
        raise RuntimeError(
            "Gemini returned an empty patch response."
        )

    return normalize_patch_result(
        extract_json(content)
    )


def call_groq(prompt: str) -> dict[str, Any]:
    if groq_client is None:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.05,
        max_completion_tokens=MAX_OUTPUT_TOKENS,
        reasoning_effort="none",
        response_format={
            "type": "json_object"
        },
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "Groq returned an empty patch response."
        )

    return normalize_patch_result(
        extract_json(content)
    )


def apply_edits_and_build_diff(
    files: list[dict[str, Any]],
    patch_result: dict[str, Any],
) -> dict[str, Any]:
    file_map = {}

    for file in files:
        if not isinstance(file, dict):
            continue

        path = clean_text(
            file.get("path") or file.get("name")
        )

        content = clean_text(
            file.get("content")
        )

        if path and content:
            file_map[path] = content

    edits_by_file: dict[str, list[dict[str, str]]] = {}

    for edit in patch_result.get("edits", []):
        path = clean_text(edit.get("path"))

        if not path:
            raise ValueError(
                "Patch edit is missing a file path."
            )

        if is_blocked_path(path):
            raise ValueError(
                f"Patch attempted to modify a blocked path: {path}"
            )

        if path not in file_map:
            raise ValueError(
                f"Patch references a file that was not supplied: {path}"
            )

        edits_by_file.setdefault(path, []).append(edit)

    file_results = []

    for path, edits in edits_by_file.items():

        if len(edits) > MAX_EDITS_PER_FILE:
            raise ValueError(
                f"Too many edits requested for {path}."
            )

        original = file_map[path]
        updated = original
        applied = []

        for edit in edits:

            find_text = edit.get("find", "")
            replace_text = edit.get("replace", "")

            if not find_text:
                raise ValueError(
                    f"Empty search text in patch for {path}."
                )

            if find_text == replace_text:
                raise ValueError(
                    f"Patch edit for {path} makes no change."
                )

            occurrences = updated.count(find_text)

            if occurrences != 1:
                raise ValueError(
                    f"Patch search text for {path} matched "
                    f"{occurrences} times; expected exactly 1."
                )

            updated = updated.replace(
                find_text,
                replace_text,
                1,
            )

            applied.append(
                {
                    "reason": clean_text(
                        edit.get("reason")
                    ),
                }
            )

        if updated == original:
            raise ValueError(
                f"No effective change produced for {path}."
            )

        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=4,
            )
        )

        unified_diff = "".join(diff_lines)

        if not unified_diff.strip():
            raise ValueError(
                f"Unable to generate diff for {path}."
            )

        file_results.append(
            {
                "path": path,
                "original_sha": clean_text(
                    next(
                        (
                            file.get("sha")
                            for file in files
                            if clean_text(
                                file.get("path") or file.get("name")
                            ) == path
                        ),
                        "",
                    )
                ),
                "original_size": len(original),
                "updated_size": len(updated),
                "changed_chars": abs(
                    len(updated) - len(original)
                ),
                "edits_applied": applied,
                "unified_diff": unified_diff,
            }
        )

    return {
        "files_changed": len(file_results),
        "patches": file_results,
    }


def generate_patch(
    issue: dict[str, Any],
    analysis: dict[str, Any],
    plan: dict[str, Any],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    target_files = plan.get("files_to_modify", []) or []

    if not target_files:
        return {
            "ok": True,
            "provider": None,
            "model": None,
            "patch": {
                "status": "no_changes_required",
                "summary": (
                    "The implementation plan does not identify a justified "
                    "source-file modification."
                ),
                "edits": [],
                "tests": plan.get("implementation_steps", [])[:5],
                "risk": plan.get("risk", "low"),
                "notes": [
                    "No patch was generated because the planner "
                    "identified no confirmed code change."
                ],
            },
            "diff": {
                "files_changed": 0,
                "patches": [],
            },
            "fallback": {
                "used": False,
                "gemini_primary_error": None,
                "gemini_fallback_error": None,
                "gemini_secondary_fallback_error": None,
            },
            "errors": None,
        }

    prompt = build_patch_prompt(
        issue=issue,
        analysis=analysis,
        plan=plan,
        files=files,
    )

    fallback = {
        "used": False,
        "gemini_primary_error": None,
        "gemini_fallback_error": None,
        "gemini_secondary_fallback_error": None,
    }

    providers = []

    if gemini_client is not None:
        providers = [
            ("gemini", GEMINI_PRIMARY),
            ("gemini", GEMINI_FALLBACK),
            ("gemini", GEMINI_SECONDARY_FALLBACK),
        ]

    for provider, model in providers:

        try:
            raw = call_gemini(
                model=model,
                prompt=prompt,
            )

            normalized = raw

            if normalized["status"] == "no_changes_required":
                return {
                    "ok": True,
                    "provider": provider,
                    "model": model,
                    "patch": normalized,
                    "diff": {
                        "files_changed": 0,
                        "patches": [],
                    },
                    "fallback": fallback,
                    "errors": None,
                }

            diff = apply_edits_and_build_diff(
                files=files,
                patch_result=normalized,
            )

            return {
                "ok": True,
                "provider": provider,
                "model": model,
                "patch": normalized,
                "diff": diff,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:

            fallback["used"] = True

            if model == GEMINI_PRIMARY:
                fallback["gemini_primary_error"] = (
                    f"{model} failed: {exc}"
                )

            elif model == GEMINI_FALLBACK:
                fallback["gemini_fallback_error"] = (
                    f"{model} failed: {exc}"
                )

            else:
                fallback["gemini_secondary_fallback_error"] = (
                    f"{model} failed: {exc}"
                )

    if groq_client is not None:

        try:
            normalized = call_groq(prompt)

            if normalized["status"] == "no_changes_required":
                return {
                    "ok": True,
                    "provider": "groq",
                    "model": GROQ_MODEL,
                    "patch": normalized,
                    "diff": {
                        "files_changed": 0,
                        "patches": [],
                    },
                    "fallback": fallback,
                    "errors": None,
                }

            diff = apply_edits_and_build_diff(
                files=files,
                patch_result=normalized,
            )

            return {
                "ok": True,
                "provider": "groq",
                "model": GROQ_MODEL,
                "patch": normalized,
                "diff": diff,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            return {
                "ok": False,
                "provider": "groq",
                "model": GROQ_MODEL,
                "patch": None,
                "diff": None,
                "fallback": fallback,
                "errors": [
                    f"Groq patch generation failed: {exc}"
                ],
            }

    return {
        "ok": False,
        "provider": None,
        "model": None,
        "patch": None,
        "diff": None,
        "fallback": fallback,
        "errors": [
            "No AI provider is configured."
        ],
    }