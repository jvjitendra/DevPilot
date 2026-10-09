import base64
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv
from app.auth.store import access_token_for, get_session
from fastapi import APIRouter, Cookie, HTTPException, Request

load_dotenv()

router = APIRouter()

def _resolve_token_and_source(devpilot_session: Any = None) -> tuple[str, str]:
    raw_session = devpilot_session
    if hasattr(devpilot_session, "default"):
        raw_session = None

    if isinstance(raw_session, str) and raw_session.strip():
        session = get_session(raw_session)
        if session:
            try:
                token = access_token_for(session)
                if token:
                    return token, "session"
            except HTTPException:
                raise
            except Exception:
                pass

    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token, "server_env"

    raise HTTPException(
        status_code=401,
        detail="GitHub session is not authenticated and GITHUB_TOKEN is not configured. Please sign in with GitHub.",
    )


def _session_or_env_token(devpilot_session: Any = None) -> str:
    token, _ = _resolve_token_and_source(devpilot_session)
    return token


def _auth_error_detail(status_code: int, source: str = "server_env", raw_message: str | None = None) -> str:
    if status_code == 401:
        if source == "session":
            return "Your GitHub OAuth session has expired or was revoked. Please sign in again with GitHub."
        return "Server fallback GitHub token is invalid or expired (Bad credentials). Please sign in with your GitHub account."
    if status_code == 403:
        if raw_message and "rate limit" in raw_message.lower():
            return "GitHub API rate limit exceeded. Please sign in with GitHub or retry later."
        return "Access to this GitHub repository is forbidden. Verify permissions or repository visibility."
    return raw_message or "GitHub API request failed."



TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".json",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".xml",
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".toml",
    ".ini",
    ".cfg",
}

SKIP_PATH_PARTS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "coverage",
}

DOC_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
}

STYLE_EXTENSIONS = {
    ".css",
    ".scss",
    ".sass",
    ".less",
}

IMPLEMENTATION_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".sql",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "by",
    "correctly",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "is",
    "it",
    "its",
    "not",
    "of",
    "on",
    "or",
    "should",
    "state",
    "that",
    "the",
    "their",
    "this",
    "to",
    "update",
    "updating",
    "user",
    "when",
    "after",
    "before",
    "page",
    "refreshing",
    "refresh",
    "expected",
    "show",
    "immediately",
    "marks",
}

GENERIC_TERMS = {
    "fix",
    "task",
    "tasks",
    "ui",
    "show",
    "user",
    "state",
}

COMMON_LOGIC_TERMS = {
    "complete",
    "completed",
    "completion",
    "status",
    "persist",
    "persisted",
    "refresh",
    "update",
    "updated",
    "api",
    "put",
    "post",
    "patch",
    "delete",
}

IMPORTANT_FILE_NAMES = {
    "app.py",
    "main.py",
    "server.py",
    "app.js",
    "main.js",
    "index.js",
    "index.ts",
    "index.jsx",
    "index.tsx",
}


# Higher number = stronger evidence that the line
# contains the actual implementation related to
# the reported issue.
CODE_ANCHOR_WEIGHTS = [
    (r"\bquickComplete\s*\(", 120),
    (r"\bquickcomplete\b", 115),
    (r"data-complete", 110),
    (r"/api/tasks/", 105),
    (r"@app\.put\s*\(", 105),
    (r"\bmethod\s*:\s*[\"']PUT[\"']", 100),
    (r"\bdb\.session\.commit\s*\(", 100),
    (r"\bdb\.session\.add\s*\(", 90),
    (r"\bstatus\s*===\s*[\"']done[\"']", 95),
    (r"\bstatus\s*==\s*[\"']done[\"']", 95),
    (r"\bstatus\s*=\s*[\"']done[\"']", 90),
    (r"\bTask\.query\b", 85),
    (r"\bloadTasks\s*\(", 75),
    (r"\brenderTasks\s*\(", 65),
    (r"\bto_dict\s*\(", 60),
    (r"\bupdated_at\b", 55),
]


def github_headers(devpilot_session: str | None = None):
    token = _session_or_env_token(devpilot_session)
    if not token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN is not configured"
        )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def should_search_file(path: str) -> bool:
    lower_path = path.lower()

    for part in SKIP_PATH_PARTS:
        if (
            f"/{part}/" in f"/{lower_path}/"
            or lower_path.startswith(f"{part}/")
        ):
            return False

    filename = lower_path.rsplit("/", 1)[-1]

    if "." in filename:
        extension = "." + filename.rsplit(".", 1)[-1]

        if extension in TEXT_EXTENSIONS:
            return True

    return filename in {
        "dockerfile",
        "makefile",
        "procfile",
    }


def fetch_github_file(
    owner: str,
    repo: str,
    path: str,
    headers: dict,
):
    response = httpx.get(
        f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
        headers=headers,
        timeout=15,
    )

    if response.status_code != 200:
        return None

    file_data = response.json()

    if file_data.get("type") != "file":
        return None

    content = file_data.get("content")

    if not content:
        return None

    try:
        decoded = base64.b64decode(
            content
        ).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None

    return {
        "path": file_data.get("path"),
        "size": file_data.get("size"),
        "sha": file_data.get("sha"),
        "content": decoded,
    }


def extract_issue_keywords(
    title: str,
    body: str,
):
    text = f"{title} {body}".lower()

    words = re.findall(
        r"[a-zA-Z_][a-zA-Z0-9_]{2,}",
        text
    )

    keywords = []

    for word in words:
        if word in STOPWORDS:
            continue

        if word not in keywords:
            keywords.append(word)

    for term in COMMON_LOGIC_TERMS:
        if term in text and term not in keywords:
            keywords.append(term)

    return keywords[:20]


def file_extension(path: str) -> str:
    lower_path = path.lower()

    if "." not in lower_path:
        return ""

    return "." + lower_path.rsplit(".", 1)[-1]


def implementation_bonus(path: str) -> int:
    lower_path = path.lower()
    extension = file_extension(path)
    filename = lower_path.rsplit("/", 1)[-1]

    bonus = 0

    if extension in IMPLEMENTATION_EXTENSIONS:
        bonus += 10

    if filename in IMPORTANT_FILE_NAMES:
        bonus += 12

    if "/backend/" in f"/{lower_path}/":
        bonus += 8

    if "/frontend/" in f"/{lower_path}/":
        bonus += 6

    if filename in {
        "readme.md",
        "readme.txt",
        "readme.rst",
    }:
        bonus -= 25

    if extension in DOC_EXTENSIONS:
        bonus -= 18

    if extension in STYLE_EXTENSIONS:
        bonus -= 10

    if lower_path.endswith(".svg"):
        bonus -= 20

    if "render.yaml" in lower_path:
        bonus -= 15

    if "deploy" in filename:
        bonus -= 10

    return bonus


def find_code_anchors(
    content: str,
):
    lines = content.splitlines()
    anchors = []

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        best_weight = 0
        matched_pattern = None

        for pattern, weight in CODE_ANCHOR_WEIGHTS:
            if re.search(
                pattern,
                line,
                flags=re.IGNORECASE,
            ):
                if weight > best_weight:
                    best_weight = weight
                    matched_pattern = pattern

        if best_weight > 0:
            anchors.append({
                "line": line_number,
                "weight": best_weight,
                "pattern": matched_pattern,
                "text": line.strip()[:300],
            })

    anchors.sort(
        key=lambda item: (
            item["weight"],
            item["line"],
        ),
        reverse=True,
    )

    return anchors


def score_file(
    path: str,
    content: str,
    keywords: list[str],
):
    path_lower = path.lower()
    content_lower = content.lower()

    score = implementation_bonus(path)

    matched_keywords = []
    matches = []

    for keyword in keywords:
        occurrences = content_lower.count(
            keyword
        )

        if occurrences <= 0:
            continue

        matched_keywords.append(keyword)

        if keyword in GENERIC_TERMS:
            score += min(
                occurrences,
                2,
            )
        else:
            score += min(
                occurrences * 4,
                24,
            )

        keyword_line_count = 0

        for line_number, line in enumerate(
            content.splitlines(),
            start=1,
        ):
            if keyword in line.lower():
                matches.append({
                    "keyword": keyword,
                    "line": line_number,
                    "text": line.strip()[:300],
                })

                keyword_line_count += 1

                if keyword_line_count >= 5:
                    break

    anchors = find_code_anchors(
        content
    )

    # Stronger implementation evidence contributes
    # substantially more than generic keyword hits.
    anchor_score = sum(
        min(anchor["weight"], 120)
        for anchor in anchors[:8]
    )

    score += anchor_score

    filename = path_lower.rsplit(
        "/",
        1,
    )[-1]

    for keyword in keywords:
        if keyword in filename:
            score += 8

        if keyword in path_lower:
            score += 3

    return {
        "score": score,
        "matched_keywords": matched_keywords,
        "matches": matches,
        "anchor_hits": len(anchors),
        "anchors": anchors[:20],
    }


def get_repository_tree_data(
    owner: str,
    repo: str,
    headers: dict,
):
    repo_response = httpx.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers=headers,
        timeout=15,
    )

    if repo_response.status_code != 200:
        raise HTTPException(
            status_code=repo_response.status_code,
            detail="GitHub repository request failed"
        )

    repository = repo_response.json()
    default_branch = repository["default_branch"]

    tree_response = httpx.get(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}",
        headers=headers,
        params={
            "recursive": "1"
        },
        timeout=20,
    )

    if tree_response.status_code != 200:
        raise HTTPException(
            status_code=tree_response.status_code,
            detail="GitHub repository tree request failed"
        )

    return {
        "repository": repository,
        "default_branch": default_branch,
        "tree": tree_response.json(),
    }


def rank_repository_files(
    owner: str,
    repo: str,
    issue: dict,
    candidate_files: list[dict],
    headers: dict,
):
    title = issue.get("title", "")
    body = issue.get("body") or ""

    keywords = extract_issue_keywords(
        title,
        body,
    )

    ranked = []

    for item in candidate_files:
        path = item.get("path", "")

        try:
            file_data = fetch_github_file(
                owner,
                repo,
                path,
                headers,
            )

            if not file_data:
                continue

            analysis = score_file(
                path,
                file_data["content"],
                keywords,
            )

            if analysis["score"] <= 0:
                continue

            ranked.append({
                "name": path.rsplit(
                    "/",
                    1,
                )[-1],
                "path": path,
                "sha": file_data["sha"],
                "size": file_data["size"],
                "score": analysis["score"],
                "matched_keywords": analysis[
                    "matched_keywords"
                ],
                "matches": analysis["matches"],
                "anchor_hits": analysis[
                    "anchor_hits"
                ],
                "anchors": analysis[
                    "anchors"
                ],
                "content": file_data["content"],
            })

        except Exception:
            continue

    ranked.sort(
        key=lambda item: (
            item["score"],
            item["anchor_hits"],
        ),
        reverse=True,
    )

    return ranked, keywords


def is_frontend_file(path: str) -> bool:
    lower_path = path.lower()

    return (
        lower_path.startswith("frontend/")
        or "/frontend/" in f"/{lower_path}/"
    )


def is_backend_file(path: str) -> bool:
    lower_path = path.lower()

    return (
        lower_path.startswith("backend/")
        or "/backend/" in f"/{lower_path}/"
    )


def select_context_files(
    ranked_files: list[dict],
    max_files: int = 5,
):
    selected = []

    # Always try to include the strongest frontend
    # implementation file.
    for file in ranked_files:
        if is_frontend_file(file["path"]):
            selected.append(file)
            break

    # Always try to include the strongest backend
    # implementation file.
    for file in ranked_files:
        if is_backend_file(file["path"]):
            selected.append(file)
            break

    # Fill remaining slots using relevance.
    for file in ranked_files:
        if len(selected) >= max_files:
            break

        if any(
            existing["path"] == file["path"]
            for existing in selected
        ):
            continue

        selected.append(file)

    return selected


def build_targeted_excerpt(
    content: str,
    issue: dict,
    max_chars: int = 7000,
):
    lines = content.splitlines()

    if not lines:
        return ""

    anchors = find_code_anchors(
        content
    )

    # If there are implementation anchors,
    # prioritize those over generic keyword matches.
    if anchors:
        top_anchors = anchors[:12]

        windows = []

        for anchor in top_anchors:
            line_number = anchor["line"]

            start = max(
                1,
                line_number - 7,
            )

            end = min(
                len(lines),
                line_number + 10,
            )

            windows.append({
                "start": start,
                "end": end,
                "weight": anchor["weight"],
                "line": line_number,
            })

        # Merge windows only when they overlap.
        windows.sort(
            key=lambda item: item["line"]
        )

        merged = []

        for window in windows:
            if not merged:
                merged.append(window.copy())
                continue

            previous = merged[-1]

            if window["start"] <= (
                previous["end"] + 2
            ):
                previous["end"] = max(
                    previous["end"],
                    window["end"],
                )
                previous["weight"] = max(
                    previous["weight"],
                    window["weight"],
                )
            else:
                merged.append(
                    window.copy()
                )

        # Most important windows first.
        merged.sort(
            key=lambda item: (
                item["weight"],
                item["line"],
            ),
            reverse=True,
        )

        output_parts = []
        total_chars = 0

        for window in merged:
            block = "\n".join(
                f"{number}: {lines[number - 1]}"
                for number in range(
                    window["start"],
                    window["end"] + 1,
                )
            )

            if total_chars + len(block) > max_chars:
                remaining = (
                    max_chars
                    - total_chars
                )

                if remaining <= 0:
                    break

                block = block[:remaining]

            output_parts.append(block)
            total_chars += len(block)

            if total_chars >= max_chars:
                break

        if output_parts:
            return (
                "\n\n--- CODE WINDOW ---\n\n"
                .join(output_parts)
            )

    # Fallback only when no strong code anchors exist.
    return content[:max_chars]


@router.get("/repositories")
def get_repositories(devpilot_session: str | None = Cookie(default=None)):
    token, source = _resolve_token_and_source(devpilot_session)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = httpx.get(
            "https://api.github.com/user/repos",
            headers=headers,
            params={
                "per_page": 100,
                "sort": "updated",
            },
            timeout=15,
        )

        if response.status_code != 200:
            raw_msg = None
            try:
                raw_msg = response.json().get("message")
            except Exception:
                pass
            raise HTTPException(
                status_code=response.status_code,
                detail=_auth_error_detail(response.status_code, source, raw_msg)
            )

        repositories = response.json()

        return {
            "ok": True,
            "count": len(repositories),
            "repositories": [
                {
                    "id": repo["id"],
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "default_branch": repo[
                        "default_branch"
                    ],
                    "language": repo["language"],
                    "html_url": repo["html_url"],
                }
                for repo in repositories
            ],
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub connection failed: {exc}"
        )


@router.get(
    "/repositories/{owner}/{repo}/tree"
)
def get_repository_tree(
    owner: str,
    repo: str,
    devpilot_session: str | None = Cookie(default=None),
):
    headers = github_headers(devpilot_session)

    try:
        tree_data = get_repository_tree_data(
            owner,
            repo,
            headers,
        )

        files = [
            {
                "path": item["path"],
                "type": item["type"],
                "size": item.get("size"),
            }
            for item in tree_data["tree"].get(
                "tree",
                [],
            )
        ]

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "default_branch": tree_data[
                "default_branch"
            ],
            "truncated": tree_data["tree"].get(
                "truncated",
                False,
            ),
            "count": len(files),
            "files": files,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "GitHub repository tree "
                f"connection failed: {exc}"
            )
        )


@router.get(
    "/repositories/{owner}/{repo}/issues"
)
def get_repository_issues(
    owner: str,
    repo: str,
    devpilot_session: str | None = Cookie(default=None),
):
    token, source = _resolve_token_and_source(devpilot_session)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            headers=headers,
            params={
                "state": "open",
                "per_page": 100,
            },
            timeout=15,
        )

        if response.status_code != 200:
            raw_msg = None
            try:
                raw_msg = response.json().get("message")
            except Exception:
                pass
            raise HTTPException(
                status_code=response.status_code,
                detail=_auth_error_detail(response.status_code, source, raw_msg)
            )

        issues = response.json()

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "count": len(issues),
            "issues": [
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue["body"],
                    "state": issue["state"],
                    "html_url": issue["html_url"],
                    "user": issue["user"]["login"],
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                }
                for issue in issues
                if "pull_request" not in issue
            ],
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "GitHub issues connection "
                f"failed: {exc}"
            )
        )


@router.get(
    "/repositories/{owner}/{repo}/search"
)
def search_repository_code(
    owner: str,
    repo: str,
    q: str,
    devpilot_session: str | None = Cookie(default=None),
):
    headers = github_headers(devpilot_session)

    query = q.strip()

    if not query:
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty"
        )

    try:
        tree_data = get_repository_tree_data(
            owner,
            repo,
            headers,
        )

        candidate_files = [
            item
            for item in tree_data["tree"].get(
                "tree",
                [],
            )
            if item.get("type") == "blob"
            and should_search_file(
                item.get("path", "")
            )
        ]

        query_lower = query.lower()
        results = []

        for item in candidate_files:
            path = item["path"]

            try:
                file_data = fetch_github_file(
                    owner,
                    repo,
                    path,
                    headers,
                )

                if not file_data:
                    continue

                content = file_data["content"]

                if query_lower not in content.lower():
                    continue

                matches = []

                for line_number, line in enumerate(
                    content.splitlines(),
                    start=1,
                ):
                    if query_lower in line.lower():
                        matches.append({
                            "line": line_number,
                            "text": line.strip()[:300],
                        })

                        if len(matches) >= 10:
                            break

                results.append({
                    "name": path.rsplit(
                        "/",
                        1,
                    )[-1],
                    "path": path,
                    "sha": file_data["sha"],
                    "size": file_data["size"],
                    "matches": matches,
                    "priority": implementation_bonus(
                        path
                    ),
                })

            except Exception:
                continue

        results.sort(
            key=lambda item: item["priority"],
            reverse=True,
        )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "query": query,
            "count": len(results),
            "results": results[:50],
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Repository code search "
                f"failed: {exc}"
            )
        )


@router.get(
    "/repositories/{owner}/{repo}/issues/{issue_number}/context"
)
def get_issue_context(
    owner: str,
    repo: str,
    issue_number: int,
    devpilot_session: str | None = Cookie(default=None),
):
    headers = github_headers(devpilot_session)

    try:
        issue_response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}",
            headers=headers,
            timeout=15,
        )

        if issue_response.status_code != 200:
            raise HTTPException(
                status_code=issue_response.status_code,
                detail="GitHub issue request failed"
            )

        issue = issue_response.json()

        if "pull_request" in issue:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Requested item is a pull request, "
                    "not an issue"
                )
            )

        tree_data = get_repository_tree_data(
            owner,
            repo,
            headers,
        )

        candidate_files = [
            item
            for item in tree_data["tree"].get(
                "tree",
                [],
            )
            if item.get("type") == "blob"
            and should_search_file(
                item.get("path", "")
            )
        ]

        ranked_files, keywords = rank_repository_files(
            owner=owner,
            repo=repo,
            issue=issue,
            candidate_files=candidate_files,
            headers=headers,
        )

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "issue": {
                "number": issue["number"],
                "title": issue.get(
                    "title",
                    "",
                ),
                "body": issue.get(
                    "body"
                ) or "",
                "state": issue["state"],
                "html_url": issue["html_url"],
            },
            "keywords": keywords,
            "candidate_file_count": len(
                candidate_files
            ),
            "relevant_file_count": len(
                ranked_files
            ),
            "relevant_files": [
                {
                    "name": file["name"],
                    "path": file["path"],
                    "sha": file["sha"],
                    "size": file["size"],
                    "score": file["score"],
                    "anchor_hits": file[
                        "anchor_hits"
                    ],
                    "matched_keywords": file[
                        "matched_keywords"
                    ],
                    "matches": file[
                        "matches"
                    ][:20],
                    "anchors": file[
                        "anchors"
                    ][:12],
                }
                for file in ranked_files[:20]
            ],
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Issue context analysis "
                f"failed: {exc}"
            )
        )


@router.get(
    "/repositories/{owner}/{repo}/issues/{issue_number}/context-code"
)
def get_issue_context_code(
    owner: str,
    repo: str,
    issue_number: int,
    devpilot_session: str | None = Cookie(default=None),
):
    headers = github_headers(devpilot_session)

    try:
        issue_response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}",
            headers=headers,
            timeout=15,
        )

        if issue_response.status_code != 200:
            raise HTTPException(
                status_code=issue_response.status_code,
                detail="GitHub issue request failed"
            )

        issue = issue_response.json()

        if "pull_request" in issue:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Requested item is a pull request, "
                    "not an issue"
                )
            )

        tree_data = get_repository_tree_data(
            owner,
            repo,
            headers,
        )

        candidate_files = [
            item
            for item in tree_data["tree"].get(
                "tree",
                [],
            )
            if item.get("type") == "blob"
            and should_search_file(
                item.get("path", "")
            )
        ]

        ranked_files, keywords = rank_repository_files(
            owner=owner,
            repo=repo,
            issue=issue,
            candidate_files=candidate_files,
            headers=headers,
        )

        selected_files = select_context_files(
            ranked_files,
            max_files=5,
        )

        MAX_TOTAL_CONTEXT_CHARS = 13000

        files = []
        total_context_chars = 0

        for item in selected_files:
            remaining = (
                MAX_TOTAL_CONTEXT_CHARS
                - total_context_chars
            )

            if remaining <= 0:
                break

            excerpt_limit = min(
                7000,
                remaining,
            )

            excerpt = build_targeted_excerpt(
                content=item["content"],
                issue=issue,
                max_chars=excerpt_limit,
            )

            if not excerpt:
                continue

            files.append({
                "name": item["name"],
                "path": item["path"],
                "sha": item["sha"],
                "size": item["size"],
                "score": item["score"],
                "anchor_hits": item[
                    "anchor_hits"
                ],
                "anchors": item[
                    "anchors"
                ][:12],
                "matched_keywords": item[
                    "matched_keywords"
                ],
                "matches": item[
                    "matches"
                ][:20],
                "content": excerpt,
                "truncated": (
                    len(excerpt)
                    < len(item["content"])
                ),
            })

            total_context_chars += len(
                excerpt
            )

            if total_context_chars >= (
                MAX_TOTAL_CONTEXT_CHARS
            ):
                break

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "default_branch": (
                tree_data["default_branch"]
            ),
            "issue": {
                "number": issue["number"],
                "title": issue.get(
                    "title",
                    "",
                ),
                "body": issue.get(
                    "body"
                ) or "",
                "state": issue["state"],
                "html_url": issue["html_url"],
            },
            "keywords": keywords,
            "candidate_file_count": len(
                candidate_files
            ),
            "ranked_file_count": len(
                ranked_files
            ),
            "selected_file_count": len(
                files
            ),
            "total_context_chars": (
                total_context_chars
            ),
            "files": files,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Issue source context "
                f"failed: {exc}"
            )
        )


@router.get(
    "/repositories/{owner}/{repo}/file"
)
def get_repository_file(
    owner: str,
    repo: str,
    path: str,
    devpilot_session: str | None = Cookie(default=None),
):
    headers = github_headers(devpilot_session)

    try:
        file_data = fetch_github_file(
            owner,
            repo,
            path,
            headers,
        )

        if not file_data:
            raise HTTPException(
                status_code=404,
                detail="GitHub file not found"
            )

        return {
            "ok": True,
            "path": file_data["path"],
            "size": file_data["size"],
            "sha": file_data["sha"],
            "content": file_data["content"],
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "GitHub file connection "
                f"failed: {exc}"
            )
        )
# ===== DevPilot authenticated GitHub repository layer =====
def _session_github_token(request: Request) -> str:
    from app.auth.store import access_token_for, get_session

    session_id = request.cookies.get("devpilot_session")
    if session_id:
        session = get_session(session_id)
        if session:
            try:
                token = access_token_for(session)
                if token:
                    return token
            except HTTPException:
                raise
            except Exception:
                pass

    env_token = os.getenv("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token

    raise HTTPException(
        status_code=401,
        detail="GitHub session is not authenticated or has expired. Please sign in again.",
    )


def _session_github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@router.get("/repositories/session")
def get_authenticated_repositories(request: Request):
    token = _session_github_token(request)
    headers = _session_github_headers(token)
    repositories: list[dict] = []
    page = 1

    try:
        while True:
            response = httpx.get(
                "https://api.github.com/user/repos",
                headers=headers,
                params={
                    "visibility": "all",
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
                timeout=20,
            )

            if response.status_code != 200:
                if response.status_code == 401:
                    session_id = request.cookies.get("devpilot_session")
                    if session_id:
                        from app.auth.store import delete_session
                        delete_session(session_id)
                    raise HTTPException(
                        status_code=401,
                        detail="GitHub credentials are invalid or expired. Please sign in again.",
                    )
                detail = "GitHub repository request failed."
                try:
                    detail = response.json().get("message") or detail
                except Exception:
                    pass
                raise HTTPException(status_code=response.status_code, detail=detail)

            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break

            repositories.extend(batch)

            if len(batch) < 100:
                break

            page += 1

        return {
            "ok": True,
            "count": len(repositories),
            "repositories": [
                {
                    "id": repo.get("id"),
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "private": repo.get("private"),
                    "default_branch": repo.get("default_branch") or "main",
                    "language": repo.get("language"),
                    "html_url": repo.get("html_url"),
                }
                for repo in repositories
                if repo.get("full_name")
            ],
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub repository connection failed: {exc}",
        )


@router.get("/repositories/{owner}/{repo}/tree-session")
def get_authenticated_tree(
    owner: str,
    repo: str,
    request: Request,
    branch: str | None = None,
):
    token = _session_github_token(request)
    headers = _session_github_headers(token)

    try:
        if not branch:
            meta = httpx.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers,
                timeout=20,
            )
            if meta.status_code != 200:
                raise HTTPException(
                    status_code=meta.status_code,
                    detail="GitHub repository metadata request failed.",
                )
            branch = meta.json().get("default_branch") or "main"

        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}",
            headers=headers,
            params={"recursive": "1"},
            timeout=30,
        )

        if response.status_code != 200:
            if response.status_code == 401:
                session_id = request.cookies.get("devpilot_session")
                if session_id:
                    from app.auth.store import delete_session
                    delete_session(session_id)
                raise HTTPException(
                    status_code=401,
                    detail="GitHub credentials are invalid or expired. Please sign in again.",
                )
            detail = "GitHub repository tree request failed."
            try:
                detail = response.json().get("message") or detail
            except Exception:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)

        payload = response.json()
        tree = payload.get("tree") or []

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "branch": branch,
            "truncated": bool(payload.get("truncated")),
            "tree": [
                {
                    "path": item.get("path"),
                    "type": item.get("type"),
                    "size": item.get("size"),
                    "sha": item.get("sha"),
                }
                for item in tree
                if item.get("path") and item.get("type") in {"blob", "tree"}
            ],
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub tree connection failed: {exc}",
        )


@router.get("/repositories/{owner}/{repo}/file-session")
def get_authenticated_file(
    owner: str,
    repo: str,
    path: str,
    request: Request,
    branch: str | None = None,
):
    token = _session_github_token(request)
    headers = _session_github_headers(token)

    try:
        params = {"ref": branch} if branch else {}

        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
            params=params,
            timeout=25,
        )

        if response.status_code != 200:
            if response.status_code == 401:
                session_id = request.cookies.get("devpilot_session")
                if session_id:
                    from app.auth.store import delete_session
                    delete_session(session_id)
                raise HTTPException(
                    status_code=401,
                    detail="GitHub credentials are invalid or expired. Please sign in again.",
                )
            detail = "GitHub file request failed."
            try:
                detail = response.json().get("message") or detail
            except Exception:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)

        payload = response.json()

        if payload.get("type") != "file":
            raise HTTPException(status_code=400, detail="Selected path is not a file.")

        import base64

        encoded = (payload.get("content") or "").replace("\n", "")
        content = base64.b64decode(encoded).decode("utf-8", errors="replace")

        return {
            "ok": True,
            "repository": f"{owner}/{repo}",
            "path": payload.get("path") or path,
            "size": payload.get("size"),
            "sha": payload.get("sha"),
            "branch": branch,
            "content": content,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub file connection failed: {exc}",
        )
