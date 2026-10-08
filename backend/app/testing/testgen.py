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

MAX_CONTEXT_CHARS = 30000
MAX_OUTPUT_TOKENS = 1200


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
You are DevPilot, an AI software testing engineer.

Your job is to convert a GitHub issue, its software-engineering analysis,
implementation plan and relevant source code into a concrete validation plan.

Rules:

1. Use only supplied evidence.
2. Never invent functions, endpoints, files or behavior.
3. Prefer tests that reproduce the reported issue.
4. Prefer existing project test conventions when visible.
5. Separate automated tests from manual tests.
6. Give an exact test target when it can be determined.
7. Include expected result.
8. Include a test command only when it is justified by visible project structure.
9. Do not claim that a test was executed.
10. This stage generates tests/specifications only. It does not execute code.
11. Return ONLY valid JSON.
12. Do not use markdown fences.

Required JSON:

{
  "status": "ready|insufficient_evidence",
  "summary": "string",
  "automated_tests": [
    {
      "name": "string",
      "target": "string",
      "type": "unit|integration|regression",
      "purpose": "string",
      "expected": "string"
    }
  ],
  "manual_tests": [
    {
      "name": "string",
      "steps": ["string"],
      "expected": "string"
    }
  ],
  "commands": ["string"],
  "coverage_targets": ["string"],
  "notes": ["string"]
}
"""


def clean_text(
    value: Any,
    limit: int | None = None,
) -> str:
    text = str(value or "").strip()

    if limit is not None:
        return text[:limit]

    return text


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
        value = json.loads(text)

        if isinstance(value, dict):
            return value

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        raise ValueError(
            "Test generator returned invalid JSON."
        )

    value = json.loads(
        text[start:end + 1]
    )

    if not isinstance(value, dict):
        raise ValueError(
            "Test generator returned a non-object JSON value."
        )

    return value


def normalize_test_plan(
    data: dict[str, Any],
) -> dict[str, Any]:

    status = clean_text(
        data.get("status")
    ).lower()

    if status not in {
        "ready",
        "insufficient_evidence",
    }:
        status = "insufficient_evidence"

    automated_tests = []

    for item in (
        data.get("automated_tests", [])
        or []
    ):
        if not isinstance(item, dict):
            continue

        test_type = clean_text(
            item.get("type")
        ).lower()

        if test_type not in {
            "unit",
            "integration",
            "regression",
        }:
            test_type = "integration"

        automated_tests.append(
            {
                "name": clean_text(
                    item.get("name")
                ),
                "target": clean_text(
                    item.get("target")
                ),
                "type": test_type,
                "purpose": clean_text(
                    item.get("purpose")
                ),
                "expected": clean_text(
                    item.get("expected")
                ),
            }
        )

    manual_tests = []

    for item in (
        data.get("manual_tests", [])
        or []
    ):
        if not isinstance(item, dict):
            continue

        steps = [
            clean_text(step)
            for step in (
                item.get("steps", [])
                or []
            )
            if clean_text(step)
        ]

        manual_tests.append(
            {
                "name": clean_text(
                    item.get("name")
                ),
                "steps": steps[:12],
                "expected": clean_text(
                    item.get("expected")
                ),
            }
        )

    commands = [
        clean_text(command)
        for command in (
            data.get("commands", [])
            or []
        )
        if clean_text(command)
    ]

    coverage_targets = [
        clean_text(target)
        for target in (
            data.get("coverage_targets", [])
            or []
        )
        if clean_text(target)
    ]

    notes = [
        clean_text(note)
        for note in (
            data.get("notes", [])
            or []
        )
        if clean_text(note)
    ]

    return {
        "status": status,
        "summary": clean_text(
            data.get("summary")
        ),
        "automated_tests": automated_tests[:12],
        "manual_tests": manual_tests[:8],
        "commands": commands[:8],
        "coverage_targets": coverage_targets[:12],
        "notes": notes[:10],
    }


def build_prompt(
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
        "SOURCE:",
    ]

    total = sum(
        len(section)
        for section in sections
    )

    for file in files[:6]:

        if not isinstance(file, dict):
            continue

        path = clean_text(
            file.get("path")
            or file.get("name")
        )

        content = clean_text(
            file.get("content")
        )

        if not path or not content:
            continue

        if len(content) > 5000:
            content = content[:5000]

        block = (
            f"\nFILE: {path}\n"
            f"{content}\n"
        )

        if total + len(block) > MAX_CONTEXT_CHARS:
            remaining = (
                MAX_CONTEXT_CHARS - total
            )

            if remaining <= 0:
                break

            block = block[:remaining]

        sections.append(block)
        total += len(block)

    return f"""
{SYSTEM_PROMPT}

Generate a test strategy for the supplied issue.

Important:

- Do not report tests as executed.
- Do not invent test files that are not supported by the source.
- If the issue is not reproducible from supplied evidence, generate validation
  tests for the suspected behavior rather than inventing a root cause.
- Include regression coverage for the expected behavior.

{chr(10).join(sections)}
"""


def call_gemini(
    model: str,
    prompt: str,
) -> dict[str, Any]:

    if (
        gemini_client is None
        or genai_types is None
    ):
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    response = (
        gemini_client.models.generate_content(
            model=model,
            contents=prompt,
            config=(
                genai_types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type=(
                        "application/json"
                    ),
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
            ),
        )
    )

    content = getattr(
        response,
        "text",
        None,
    )

    if not content:
        raise RuntimeError(
            "Gemini returned an empty test plan."
        )

    return normalize_test_plan(
        extract_json(content)
    )


def call_groq(
    prompt: str,
) -> dict[str, Any]:

    if groq_client is None:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    response = (
        groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=0.1,
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
    )

    content = (
        response.choices[0]
        .message
        .content
    )

    if not content:
        raise RuntimeError(
            "Groq returned an empty test plan."
        )

    return normalize_test_plan(
        extract_json(content)
    )


def generate_test_plan(
    issue: dict[str, Any],
    analysis: dict[str, Any],
    plan: dict[str, Any],
    files: list[dict[str, Any]],
) -> dict[str, Any]:

    prompt = build_prompt(
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

    if gemini_client is not None:

        try:
            result = call_gemini(
                model=GEMINI_PRIMARY,
                prompt=prompt,
            )

            return {
                "ok": True,
                "provider": "gemini",
                "model": GEMINI_PRIMARY,
                "tests": result,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            fallback["used"] = True
            fallback["gemini_primary_error"] = (
                f"{GEMINI_PRIMARY} failed: {exc}"
            )

        try:
            result = call_gemini(
                model=GEMINI_FALLBACK,
                prompt=prompt,
            )

            return {
                "ok": True,
                "provider": "gemini",
                "model": GEMINI_FALLBACK,
                "tests": result,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            fallback["gemini_fallback_error"] = (
                f"{GEMINI_FALLBACK} failed: {exc}"
            )

        try:
            result = call_gemini(
                model=GEMINI_SECONDARY_FALLBACK,
                prompt=prompt,
            )

            return {
                "ok": True,
                "provider": "gemini",
                "model": GEMINI_SECONDARY_FALLBACK,
                "tests": result,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            fallback[
                "gemini_secondary_fallback_error"
            ] = (
                f"{GEMINI_SECONDARY_FALLBACK} failed: {exc}"
            )

    else:
        fallback["used"] = True
        fallback["gemini_primary_error"] = (
            "Gemini is unavailable or "
            "GEMINI_API_KEY is not configured."
        )

    if groq_client is not None:

        try:
            result = call_groq(
                prompt=prompt
            )

            return {
                "ok": True,
                "provider": "groq",
                "model": GROQ_MODEL,
                "tests": result,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            return {
                "ok": False,
                "provider": "groq",
                "model": GROQ_MODEL,
                "tests": None,
                "fallback": fallback,
                "errors": [
                    f"Groq test generation failed: {exc}"
                ],
            }

    return {
        "ok": False,
        "provider": None,
        "model": None,
        "tests": None,
        "fallback": fallback,
        "errors": [
            "No AI provider is configured."
        ],
    }