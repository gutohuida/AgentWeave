"""FastAPI application factory + lifespan."""

import functools
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, bound_address, instance_identity
from .api.v1 import v1_router
from .api.v1.agent_trigger import terminate_all_active_runs
from .config import settings
from .db.engine import init_db
from .run_reconciliation import reconcile_interrupted_runs
from .scheduler import init_scheduler, shutdown_scheduler

logger = logging.getLogger(__name__)

UI_DIST = Path(__file__).parent / "static" / "ui"
UI_SRC = Path(__file__).parent.parent / "ui" / "src"


def _git_last_commit_iso(path: Path) -> Optional[str]:
    """Return the ISO-8601 commit date of the most recent commit touching `path`."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", "."],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _compute_ui_staleness_warning(ui_dist: Path, ui_src: Path) -> Optional[str]:
    """Compare git history of the built UI against its source to catch a stale bundle.

    `hub/hub/static/ui` is a committed build artefact — nothing rebuilds it
    automatically in a source checkout, so it silently drifts behind `hub/ui/src`
    if a contributor edits the UI without rebuilding and recopying. `ui_src` only
    exists in a source checkout (not in an installed package), so this is a no-op
    for end users.
    """
    if not ui_src.exists() or not ui_dist.exists():
        return None
    src_date = _git_last_commit_iso(ui_src)
    dist_date = _git_last_commit_iso(ui_dist)
    if not src_date or not dist_date:
        return None
    if datetime.fromisoformat(src_date) <= datetime.fromisoformat(dist_date):
        return None
    return (
        f"hub/hub/static/ui was last rebuilt {dist_date}, but hub/ui/src has commits "
        f"as recent as {src_date}. Run `cd hub/ui && npm run build` and copy dist/ "
        f"into hub/hub/static/ui to refresh it."
    )


@functools.lru_cache(maxsize=1)
def _ui_staleness_warning() -> Optional[str]:
    return _compute_ui_staleness_warning(UI_DIST, UI_SRC)


class ContentSizeLimitMiddleware:
    """ASGI middleware that rejects request bodies larger than a configured limit.

    Defaults to 1 MB. Enforcing the cap at the middleware layer prevents giant
    payloads from reaching FastAPI validation or route handlers.
    """

    def __init__(self, app, max_size: int = 1_048_576):
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope: Dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method in ("GET", "HEAD", "OPTIONS", "TRACE"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                length = int(content_length.decode())
            except (ValueError, UnicodeDecodeError):
                length = 0
            if length > self.max_size:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [[b"content-type", b"application/json"]],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"Request body too large"}',
                    }
                )
                return

        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    instance_identity.load_or_create()
    await reconcile_interrupted_runs()
    await init_scheduler()
    warning = _ui_staleness_warning()
    if warning:
        logger.warning(warning)
    yield
    await terminate_all_active_runs()
    await shutdown_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentWeave Hub",
        description=(
            "Self-hosted collaboration server for AgentWeave agents. "
            "Provides REST + SSE + MCP interfaces for messages, tasks, and human interaction."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    # CORS — origins configurable via AW_CORS_ORIGINS env var (comma-separated).
    # Default: same-origin only (empty list = browser blocks cross-origin).
    _cors_origins_raw = os.environ.get("AW_CORS_ORIGINS", "")
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        ContentSizeLimitMiddleware,
        max_size=settings.aw_max_body_size,
    )

    @app.middleware("http")
    async def _observe_bound_address(request: Request, call_next):
        server = request.scope.get("server")
        if server:
            bound_address.observe(server[0], server[1])
        return await call_next(request)

    @app.get("/health", include_in_schema=False)
    async def health():
        payload: Dict[str, Any] = {"status": "ok"}
        warning = _ui_staleness_warning()
        if warning:
            payload["ui_stale"] = True
            payload["ui_stale_detail"] = warning
        return JSONResponse(payload)

    app.include_router(v1_router)

    # Serve built React UI if dist/ exists (production Docker image)
    if UI_DIST.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(UI_DIST / "assets")),
            name="assets",
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path == "health":
                raise HTTPException(404)
            if not (UI_DIST / "index.html").exists():
                raise HTTPException(404, "UI not built")
            return HTMLResponse((UI_DIST / "index.html").read_text())

    return app


app = create_app()


def run() -> None:
    """Entry point for `agentweave-hub` CLI command."""
    import uvicorn

    uvicorn.run("hub.main:app", host=settings.aw_host, port=settings.aw_port, reload=False)


if __name__ == "__main__":
    run()
