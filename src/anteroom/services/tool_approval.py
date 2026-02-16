from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    message: str
    created_at: float


# In-memory approval registry.
# This is intentionally process-local; Anteroom's web UI is single-user and typically
# single-process. If you run multiple workers, approval must be routed to the same worker.
_PENDING: dict[str, asyncio.Future[bool]] = {}
_METADATA: dict[str, ApprovalRequest] = {}


def _new_id() -> str:
    return secrets.token_urlsafe(16)


async def confirm_destructive_via_event_bus(
    app: FastAPI,
    message: str,
    timeout_s: float = 300.0,
    db_name: str = "personal",
) -> bool:
    """Request explicit approval for a destructive action via the web UI.

    Publishes an event to the conversation stream; the web UI shows a modal and responds
    through the approve/deny endpoint.

    Fails safe (returns False) if no approval is received.
    """

    approval_id = _new_id()
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[bool] = loop.create_future()

    _PENDING[approval_id] = fut
    _METADATA[approval_id] = ApprovalRequest(approval_id=approval_id, message=message, created_at=time.time())

    event_bus = getattr(app.state, "event_bus", None)
    if event_bus:
        # Broadcast on the existing global channel for the current DB so connected UIs receive it.
        # (The /api/events endpoint currently subscribes to global:{db} and optionally conversation:{id}.)
        await event_bus.publish(
            f"global:{db_name}",
            {
                "type": "destructive_approval_requested",
                "data": {"approval_id": approval_id, "message": message},
            },
        )

    try:
        return bool(await asyncio.wait_for(fut, timeout=timeout_s))
    except (asyncio.TimeoutError, asyncio.CancelledError):
        return False
    finally:
        _PENDING.pop(approval_id, None)
        _METADATA.pop(approval_id, None)


def resolve_approval(approval_id: str, approved: bool) -> bool:
    fut = _PENDING.get(approval_id)
    if not fut or fut.done():
        return False
    fut.set_result(bool(approved))
    return True
