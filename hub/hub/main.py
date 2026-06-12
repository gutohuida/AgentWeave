"""FastAPI application factory + lifespan."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.v1 import v1_router
from .config import settings
from .db.engine import init_db
from .scheduler import init_scheduler, shutdown_scheduler

UI_DIST = Path(__file__).parent / "static" / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_scheduler()
    yield
    await shutdown_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgentWeave Hub",
        description=(
            "Self-hosted collaboration server for AgentWeave agents. "
            "Provides REST + SSE + MCP interfaces for messages, tasks, and human interaction."
        ),
        version="0.1.0",
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

    @app.get("/health", include_in_schema=False)
    async def health():
        return JSONResponse({"status": "ok"})

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

    uvicorn.run("hub.main:app", host="0.0.0.0", port=settings.aw_port, reload=False)


if __name__ == "__main__":
    run()
