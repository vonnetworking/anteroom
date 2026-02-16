from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..services.tool_approval import resolve_approval

router = APIRouter()


class ApprovalResponse(BaseModel):
    approval_id: str
    approved: bool


@router.post("/approvals/respond")
async def respond_approval(payload: ApprovalResponse, request: Request) -> dict[str, Any]:
    ok = resolve_approval(payload.approval_id, payload.approved)
    return {"ok": ok}
