"""FastAPI application factory + lifespan."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.v1 import v1_router
from .db.engine import init_db

UI_DIST = Path(__file__).parent / "static" / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
            # Let API and health routes pass through (handled above)
            if full_path.startswith("api/") or full_path == "health":
                raise HTTPException(404)
            index = UI_DIST / "index.html"
            return FileResponse(str(index))

    return app


app = create_app()


def run() -> None:
    """Entry point for `agentweave-hub` CLI command."""
    import uvicorn
    from .config import settings

    uvicorn.run("hub.main:app", host="0.0.0.0", port=settings.aw_port, reload=False)


if __name__ == "__main__":
    run()
