import os

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException

load_dotenv()

router = APIRouter()


@router.get("/repositories/{owner}/{repo}/issues")
def get_issues(owner: str, repo: str):
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN is not configured"
        )

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
                "per_page": 50,
            },
            timeout=15,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="GitHub Issues API request failed"
            )

        issues = response.json()

        return {
            "ok": True,
            "count": len(issues),
            "issues": [
                {
                    "id": issue["id"],
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "body": issue["body"],
                    "html_url": issue["html_url"],
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
            detail=f"GitHub Issues connection failed: {exc}"
        )


@router.get("/repositories/{owner}/{repo}/issues/{issue_number}")
def get_issue(owner: str, repo: str, issue_number: int):
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        raise HTTPException(
            status_code=503,
            detail="GITHUB_TOKEN is not configured"
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}",
            headers=headers,
            timeout=15,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="GitHub Issue request failed"
            )

        issue = response.json()

        return {
            "ok": True,
            "issue": {
                "id": issue["id"],
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "body": issue["body"],
                "html_url": issue["html_url"],
                "user": issue["user"]["login"],
                "created_at": issue["created_at"],
                "updated_at": issue["updated_at"],
            },
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub Issue connection failed: {exc}"
        )