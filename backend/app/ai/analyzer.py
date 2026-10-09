import json
import os
import re
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


from app.core.config import settings

GEMINI_API_KEY = (settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")).strip()
GROQ_API_KEY = (settings.groq_api_key or os.getenv("GROQ_API_KEY", "")).strip()

GEMINI_PRIMARY = settings.gemini_model or "gemini-flash-latest"
GEMINI_FALLBACK = settings.gemini_fallback_model or "gemini-flash-lite-latest"
GEMINI_SECONDARY_FALLBACK = settings.gemini_secondary_fallback_model or "gemini-3.8-flash"
GROQ_MODEL = settings.groq_model or "qwen/qwen3.8-27b"

MAX_FILES = 3
MAX_FILE_CHARS = 4200
MAX_TOTAL_CONTEXT_CHARS = 12000
MAX_OUTPUT_TOKENS = 1000


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
You are DevPilot, an AI software-engineering analysis agent.

Your job is to analyze a GitHub issue using ONLY the supplied issue and repository
source evidence.

STRICT RULES:

1. Do not invent source code.
2. Do not assume that code is missing just because there is a line-number gap
   between two CODE WINDOW sections.
3. Read the ENTIRE supplied FILE block before reaching a conclusion.
4. Treat line-number prefixes such as "663:" as source line numbers.
5. If a function declaration is followed by its implementation in the supplied
   evidence, analyze the implementation.
6. Clearly separate observed facts from inference.
7. If the source does not prove a bug, say "Insufficient evidence" or
   "No confirmed defect in supplied source".
8. Do not call a suspicious-looking omission a root cause unless the supplied
   source actually proves it.
9. Recommend the smallest justified fix.
10. Give exact file names and exact line numbers for evidence.
11. Keep the JSON compact.
12. Return ONLY valid JSON.

Required JSON shape:

{
  "summary": "string",
  "root_cause": "string",
  "confidence": "high|medium|low",
  "evidence": [
    {
      "file": "string",
      "line": 123,
      "observation": "string"
    }
  ],
  "affected_files": ["string"],
  "recommended_fix": "string",
  "tests_to_run": ["string"],
  "uncertainty": ["string"]
}

Do not include markdown fences.
"""


def clean_text(value: Any, limit: int | None = None) -> str:
    text = str(value or "").strip()

    if limit is not None:
        return text[:limit]

    return text


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        raise ValueError("AI returned invalid JSON.")

    parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("AI returned JSON but not an object.")

    return parsed


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    evidence = []

    for item in data.get("evidence", []) or []:
        if not isinstance(item, dict):
            continue

        try:
            line = int(item.get("line") or 0)
        except (TypeError, ValueError):
            line = 0

        evidence.append(
            {
                "file": clean_text(item.get("file")),
                "line": line,
                "observation": clean_text(item.get("observation")),
            }
        )

    confidence = clean_text(data.get("confidence"), 20).lower()

    if confidence not in {"high", "medium", "low"}:
        confidence = "low"

    affected_files = []
    for value in data.get("affected_files", []) or []:
        value = clean_text(value)
        if value:
            affected_files.append(value)

    tests_to_run = []
    for value in data.get("tests_to_run", []) or []:
        value = clean_text(value)
        if value:
            tests_to_run.append(value)

    uncertainty = []
    for value in data.get("uncertainty", []) or []:
        value = clean_text(value)
        if value:
            uncertainty.append(value)

    return {
        "summary": clean_text(data.get("summary")),
        "root_cause": clean_text(data.get("root_cause")),
        "confidence": confidence,
        "evidence": evidence[:8],
        "affected_files": affected_files[:10],
        "recommended_fix": clean_text(data.get("recommended_fix")),
        "tests_to_run": tests_to_run[:8],
        "uncertainty": uncertainty[:8],
    }


def build_small_context(
    issue: dict[str, Any],
    files: list[dict[str, Any]],
) -> str:
    """
    The repository retrieval layer has ALREADY selected targeted code windows.

    Important:
    Do not run another semantic/excerpting pass here.

    The old analyzer was compressing already-targeted source again, which caused
    relevant implementation lines to disappear before the model saw them.
    """

    parts = [
        "ISSUE TITLE:",
        clean_text(issue.get("title")),
        "",
        "ISSUE BODY:",
        clean_text(issue.get("body"), 5000),
        "",
        "REPOSITORY SOURCE EVIDENCE:",
    ]

    total_chars = sum(len(part) for part in parts)

    usable_files = []

    for file in files:
        if not isinstance(file, dict):
            continue

        path = clean_text(
            file.get("path") or file.get("name")
        )

        content = clean_text(file.get("content"))

        if not path or not content:
            continue

        usable_files.append(
            {
                "path": path,
                "content": content,
                "score": float(file.get("score") or 0),
            }
        )

    usable_files.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    for file in usable_files[:MAX_FILES]:
        content = file["content"]

        if len(content) > MAX_FILE_CHARS:
            # Preserve the beginning and end of the targeted excerpt.
            # This avoids losing implementation code that may sit near the end.
            head_size = MAX_FILE_CHARS // 2
            tail_size = MAX_FILE_CHARS - head_size

            content = (
                content[:head_size]
                + "\n\n--- SOURCE MIDDLE OMITTED ---\n\n"
                + content[-tail_size:]
            )

        block = (
            f"\nFILE: {file['path']}\n"
            f"{content}\n"
        )

        if total_chars + len(block) > MAX_TOTAL_CONTEXT_CHARS:
            remaining = MAX_TOTAL_CONTEXT_CHARS - total_chars

            if remaining <= 0:
                break

            # Add only complete lines rather than cutting arbitrary JSON/source
            # halfway through.
            lines = block.splitlines()
            kept = []
            current = 0

            for line in lines:
                extra = len(line) + 1

                if current + extra > remaining:
                    break

                kept.append(line)
                current += extra

            block = "\n".join(kept) + "\n"

        if not block.strip():
            continue

        parts.append(block)
        total_chars += len(block)

        if total_chars >= MAX_TOTAL_CONTEXT_CHARS:
            break

    return "\n".join(parts)


def build_prompt(
    issue: dict[str, Any],
    files: list[dict[str, Any]],
) -> str:
    context = build_small_context(issue, files)

    return f"""
{SYSTEM_PROMPT}

IMPORTANT:

The repository retrieval system already selected relevant code windows.
Those windows may contain multiple separated sections from the same file.

A line-number gap DOES NOT mean that the omitted lines are the root cause.

For example, if the evidence contains:

661: ...
663: async function quickComplete(id) {{
664: ...
665: await api(`/api/tasks/${{id}}`, ...);
666: }}

you MUST recognize that quickComplete has a visible implementation.

Analyze the actual supplied evidence below.

{context}
"""


def call_gemini(
    model: str,
    prompt: str,
) -> dict[str, Any]:
    if gemini_client is None or genai_types is None:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    # Deliberately use JSON MIME output without response_schema here.
    # This avoids SDK/schema incompatibility while our application still
    # validates and normalizes the returned JSON.
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )

    text = getattr(response, "text", None)

    if not text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return normalize_analysis(
        extract_json(text)
    )


def call_groq(
    prompt: str,
) -> dict[str, Any]:
    if groq_client is None:
        raise RuntimeError(
            "GROQ_API_KEY is not configured."
        )

    response = groq_client.chat.completions.create(
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

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError(
            "Groq returned an empty response."
        )

    return normalize_analysis(
        extract_json(content)
    )


def analyze_issue(
    issue: dict[str, Any],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = build_prompt(
        issue=issue,
        files=files,
    )

    fallback = {
        "used": False,
        "gemini_primary_error": None,
        "gemini_fallback_error": None,
        "gemini_secondary_fallback_error": None,
    }

    # ------------------------------------------------------------
    # GEMINI PRIMARY
    # ------------------------------------------------------------

    if gemini_client is not None:
        try:
            analysis = call_gemini(
                model=GEMINI_PRIMARY,
                prompt=prompt,
            )

            return {
                "ok": True,
                "provider": "gemini",
                "model": GEMINI_PRIMARY,
                "analysis": analysis,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            fallback["used"] = True
            fallback["gemini_primary_error"] = (
                f"{GEMINI_PRIMARY} failed: {exc}"
            )

        # --------------------------------------------------------
        # GEMINI FALLBACK
        # --------------------------------------------------------

        try:
            analysis = call_gemini(
                model=GEMINI_FALLBACK,
                prompt=prompt,
            )

            return {
                "ok": True,
                "provider": "gemini",
                "model": GEMINI_FALLBACK,
                "analysis": analysis,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            fallback["gemini_fallback_error"] = (
                f"{GEMINI_FALLBACK} failed: {exc}"
            )

        # --------------------------------------------------------
        # GEMINI SECONDARY FALLBACK
        # --------------------------------------------------------

        try:
            analysis = call_gemini(
                model=GEMINI_SECONDARY_FALLBACK,
                prompt=prompt,
            )

            return {
                "ok": True,
                "provider": "gemini",
                "model": GEMINI_SECONDARY_FALLBACK,
                "analysis": analysis,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            fallback["gemini_secondary_fallback_error"] = (
                f"{GEMINI_SECONDARY_FALLBACK} failed: {exc}"
            )

    else:
        fallback["used"] = True
        fallback["gemini_primary_error"] = (
            "Gemini client unavailable or GEMINI_API_KEY is not configured."
        )

    # ------------------------------------------------------------
    # GROQ FALLBACK
    # ------------------------------------------------------------

    if groq_client is not None:
        try:
            analysis = call_groq(prompt)

            return {
                "ok": True,
                "provider": "groq",
                "model": GROQ_MODEL,
                "analysis": analysis,
                "fallback": fallback,
                "errors": None,
            }

        except Exception as exc:
            return {
                "ok": False,
                "provider": "groq",
                "model": GROQ_MODEL,
                "analysis": None,
                "fallback": fallback,
                "errors": [
                    f"Groq failed: {exc}"
                ],
            }

    return {
        "ok": False,
        "provider": None,
        "model": None,
        "analysis": None,
        "fallback": fallback,
        "errors": [
            "No AI provider is configured."
        ],
    }