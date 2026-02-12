"""FastAPI application factory with lifespan management."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import AppConfig, load_config
from .db import init_db
from .services.mcp_manager import McpManager

logger = logging.getLogger(__name__)

MAX_REQUEST_BODY_BYTES = 15 * 1024 * 1024  # 15 MB


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config: AppConfig = app.state.config
    db_path = config.app.data_dir / "chat.db"
    app.state.db = init_db(db_path)

    mcp_manager = None
    if config.mcp_servers:
        mcp_manager = McpManager(config.mcp_servers)
        try:
            await mcp_manager.startup()
            tools = mcp_manager.get_all_tools()
            logger.info(f"MCP: {len(tools)} tools available from {len(config.mcp_servers)} server(s)")
        except Exception as e:
            logger.warning(f"MCP startup error: {e}")
    app.state.mcp_manager = mcp_manager

    yield

    if app.state.db:
        app.state.db.close()
    if app.state.mcp_manager:
        await app.state.mcp_manager.shutdown()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests with Content-Length exceeding the limit."""

    def __init__(self, app: FastAPI, max_body_size: int = MAX_REQUEST_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_body_size:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP rate limiter: max requests per window with LRU eviction."""

    MAX_TRACKED_IPS = 10000

    def __init__(self, app: FastAPI, max_requests: int = 60, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: OrderedDict[str, list[float]] = OrderedDict()

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Evict oldest IPs if over capacity
        while len(self._hits) > self.MAX_TRACKED_IPS:
            self._hits.popitem(last=False)

        if client_ip not in self._hits:
            self._hits[client_ip] = []

        hits = self._hits[client_ip]
        hits[:] = [t for t in hits if now - t < self.window]
        self._hits.move_to_end(client_ip)

        if not hits:
            del self._hits[client_ip]
            self._hits[client_ip] = []
            hits = self._hits[client_ip]

        if len(hits) >= self.max_requests:
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})
        hits.append(now)
        return await call_next(request)


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Auth via bearer token header or HttpOnly session cookie."""

    def __init__(self, app: FastAPI, token_hash: str) -> None:
        super().__init__(app)
        self.token_hash = token_hash

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        # Check Authorization header
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:]
            provided_hash = hashlib.sha256(provided.encode()).hexdigest()
            if hmac.compare_digest(provided_hash, self.token_hash):
                return await call_next(request)

        # Check HttpOnly session cookie
        cookie_token = request.cookies.get("parlor_session", "")
        if cookie_token:
            cookie_hash = hashlib.sha256(cookie_token.encode()).hexdigest()
            if hmac.compare_digest(cookie_hash, self.token_hash):
                return await call_next(request)

        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = load_config()

    app = FastAPI(
        title="Parlor",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = config

    origin = f"http://{config.app.host}:{config.app.port}"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin, "http://127.0.0.1:" + str(config.app.port), "http://localhost:" + str(config.app.port)],
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=True,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)

    auth_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(auth_token.encode()).hexdigest()
    app.add_middleware(BearerTokenMiddleware, token_hash=token_hash)
    app.state.auth_token = auth_token

    from .routers import chat, config_api, conversations

    app.include_router(conversations.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(config_api.router, prefix="/api")

    static_dir = Path(__file__).parent / "static"

    @app.get("/")
    async def index():
        """Serve index.html and set auth token via HttpOnly cookie."""
        from fastapi.responses import HTMLResponse

        html_path = static_dir / "index.html"
        html = html_path.read_text()
        response = HTMLResponse(html)
        response.set_cookie(
            key="parlor_session",
            value=auth_token,
            httponly=True,
            samesite="strict",
            path="/api/",
        )
        return response

    app.mount("/", StaticFiles(directory=str(static_dir)), name="static")

    return app
