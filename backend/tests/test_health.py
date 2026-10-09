from fastapi.testclient import TestClient
from main import app


def test_health():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rollback_rejects_unmerged_pull_request(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "number": 3,
                "state": "closed",
                "merged": False,
                "merge_commit_sha": None,
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def get(self, url):
            return FakeResponse()

        def post(self, url, json=None):
            raise AssertionError(
                "GitHub revert API must not be called for an unmerged PR."
            )

    monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
    monkeypatch.setattr(
        "app.api.rollback.httpx.Client",
        FakeClient,
    )

    client = TestClient(app)

    response = client.post(
        "/api/repositories/jvjitendra/task-manager/pulls/3/rollback",
        json={
            "reason": "Automated safety test",
        },
    )

    assert response.status_code == 409

    body = response.json()

    assert body["detail"]["message"] == (
        "Rollback is allowed only for a merged Pull Request."
    )

    assert body["detail"]["pull_request"] == 3
    assert body["detail"]["state"] == "closed"
    assert body["detail"]["merged"] is False