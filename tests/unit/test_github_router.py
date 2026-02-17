from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from anteroom.routers.github import router


def _app(enable: bool = True) -> FastAPI:
    app = FastAPI()

    class _App:
        enable_github = enable

    class _Cfg:
        app = _App()

    app.state.config = _Cfg()
    app.include_router(router)
    return app


def test_github_disabled_returns_404(monkeypatch):
    app = _app(enable=False)
    client = TestClient(app)

    r = client.get("/api/github/auth/status")
    assert r.status_code == 404


def test_github_auth_status_origin_check(monkeypatch):
    app = _app(enable=True)
    client = TestClient(app)

    # With Origin but mismatched Host -> 403
    r = client.get(
        "/api/github/auth/status",
        headers={"Origin": "http://evil.test", "Host": "127.0.0.1:8080"},
    )
    assert r.status_code == 403
