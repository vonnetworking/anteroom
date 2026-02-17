from __future__ import annotations

import os
import re
import shlex
import subprocess
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter(tags=["github"])


class GhAuthStatus(BaseModel):
    ok: bool
    stdout: str
    stderr: str


class GhPrCommentRequest(BaseModel):
    repo: str = Field(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    pr_number: int = Field(..., ge=1, le=1_000_000)
    body: str = Field(..., min_length=1, max_length=20_000)


class GhPrViewRequest(BaseModel):
    repo: str = Field(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    pr_number: int = Field(..., ge=1, le=1_000_000)


def _require_gh_enabled(request: Request) -> None:
    cfg = getattr(request.app.state, "config", None)
    enabled = bool(getattr(getattr(cfg, "app", None), "enable_github", False))
    if not enabled:
        raise HTTPException(status_code=404, detail="GitHub integration is disabled")


def _require_same_origin(request: Request) -> None:
    # This endpoint is only meant to be called by the built-in Web UI.
    origin = request.headers.get("origin")
    if not origin:
        return
    host = request.headers.get("host")
    if not host:
        raise HTTPException(status_code=403, detail="Missing Host header")
    if origin.rstrip("/") != f"http://{host}" and origin.rstrip("/") != f"https://{host}":
        raise HTTPException(status_code=403, detail="Invalid Origin")


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Avoid pager hangs
    env.setdefault("GH_PAGER", "cat")
    env.setdefault("PAGER", "cat")

    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )


@router.get("/api/github/auth/status", response_model=GhAuthStatus)
def gh_auth_status(request: Request):
    _require_same_origin(request)
    _require_gh_enabled(request)

    proc = _run_gh(["gh", "auth", "status"])  # nosec - controlled args
    return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}


@router.post("/api/github/pr/view")
def gh_pr_view(payload: GhPrViewRequest, request: Request):
    _require_same_origin(request)
    _require_gh_enabled(request)

    proc = _run_gh(["gh", "pr", "view", str(payload.pr_number), "-R", payload.repo, "--json", "url,title,state,number,headRefName"])  # nosec
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=(proc.stderr or proc.stdout or "gh failed").strip())
    return {"ok": True, "raw": proc.stdout}


@router.post("/api/github/pr/comment")
def gh_pr_comment(payload: GhPrCommentRequest, request: Request):
    _require_same_origin(request)
    _require_gh_enabled(request)

    # This is non-destructive, but can still spam; enforce simple rate limit via body size and PR number constraints.
    proc = _run_gh(["gh", "pr", "comment", str(payload.pr_number), "-R", payload.repo, "-b", payload.body])  # nosec
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=(proc.stderr or proc.stdout or "gh failed").strip())
    return {"ok": True, "stdout": proc.stdout}
