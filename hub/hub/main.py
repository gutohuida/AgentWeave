"""FastAPI application factory + lifespan."""

import hashlib
import json
import logging
import os
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, bound_address, instance_identity
from .api.v1 import v1_router
from .api.v1.agent_trigger import terminate_all_active_runs
from .config import settings
from .db.engine import init_db
from .run_reconciliation import reconcile_interrupted_runs, reconcile_stale_job_runs
from .run_task_binding import TaskBindingError
from .scheduler import init_scheduler, shutdown_scheduler
from .subprocess_windows import no_console_kwargs
from .task_transition_service import TransitionRefusedError

logger = logging.getLogger(__name__)

UI_DIST = Path(__file__).parent / "static" / "ui"
UI_SRC = Path(__file__).parent.parent / "ui" / "src"

#: Written by `scripts/refresh_ui_bundle.py`, recording the source state the bundle was built from.
#: Not dot-prefixed, so a `cp -r dist static/ui` cannot silently miss it.
UI_BUILD_STAMP = UI_DIST / "ui-build-stamp.json"

#: How long a staleness answer is reused. Two git calls and a small file read is not worth caching
#: for the life of a process — and caching it for the life of a process is why, before this, a real
#: rebuild needed a Hub restart before the warning would clear.
UI_STALENESS_TTL_SECONDS = 30.0


class UTF8JSONResponse(JSONResponse):
    """Starlette's default `JSONResponse` sends `Content-Type: application/json` with no
    `charset` parameter. JSON is UTF-8 by definition (RFC 8259) so the body itself is
    correct either way — but a client that does not itself default to UTF-8 for an
    unlabelled `application/json` response can decode it wrong. Reproduced live: Windows
    PowerShell 5.1's `Invoke-WebRequest`/`Invoke-RestMethod` is exactly such a client — a
    stored runner name containing an em dash (`Codex CLI — GPT-5.4-Mini`, correct UTF-8
    on the wire and in the database, confirmed by inspecting raw bytes at every layer)
    rendered as `Codex CLI â€” GPT-5.4-Mini` through it, and correctly through curl / a
    browser / PowerShell 7+. See openspec/changes/2026-08-06-agent-messaging-delivery
    design.md, Decision 5 — this replaces that decision's original "double-encoding
    somewhere in the write path" hypothesis, which raw-byte inspection at the DB, the
    HTTP wire, and construction time all ruled out.
    """

    media_type = "application/json; charset=utf-8"


def _git_last_commit_iso(path: Path, *, exclude: Sequence[str] = ()) -> Optional[str]:
    """Return the ISO-8601 commit date of the most recent commit touching `path`.

    `exclude` takes git pathspecs to leave out, for source that cannot change the built output.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", ".", *(f":(exclude){p}" for p in exclude)],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def ui_source_fingerprint(
    ui_src: Path, *, exclude: Sequence[str] = ("__tests__",)
) -> Optional[str]:
    """A stable hash of the interface source as it actually reads on disk right now.

    Enumerated via `git ls-files` — one subprocess, and it honours .gitignore without
    reimplementing it — but hashed from each file's *working-tree bytes*, not the index's blob id.
    That makes the fingerprint depend only on file content, never on whether that content has been
    staged or committed, which is the property the previous approach lacked: it hashed `git
    ls-files -s`'s blob ids and folded in `git status --porcelain`'s dirty diff as a separate
    component, so a stamp recorded against a dirty tree (`scripts/refresh_ui_bundle.py` always
    runs before `git add`/`git commit` — `CLAUDE.md`'s documented build-then-commit order) could
    never match again once that same content was committed and porcelain went quiet. Confirmed
    live: commit `8898155` rebuilt and committed byte-identical output to a fresh rebuild, and only
    the stamp moved (`ab7e5fe`) — see `known_debts.ui-stale-false-positive`. An edit nobody has
    committed still moves this fingerprint, same as before: the bytes on disk changed.
    """
    pathspec = [".", *(f":(exclude){p}" for p in exclude)]
    try:
        listing = subprocess.run(
            ["git", "ls-files", "--", *pathspec],
            cwd=ui_src,
            capture_output=True,
            text=True,
            timeout=5,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if listing.returncode != 0 or not listing.stdout.strip():
        return None

    digest = hashlib.sha256()
    for rel_path in sorted(listing.stdout.splitlines()):
        digest.update(rel_path.encode("utf-8"))
        try:
            digest.update((ui_src / rel_path).read_bytes())
        except OSError:
            # Listed by git but unreadable right now (mid-rename, deleted since the listing) --
            # fold in a marker rather than letting the health check crash over it.
            digest.update(b"<unreadable>")
    return digest.hexdigest()


def read_ui_build_stamp(ui_dist: Path) -> Optional[dict]:
    """The recorded assertion that this bundle was built from a particular source state."""
    stamp = ui_dist / UI_BUILD_STAMP.name
    try:
        return json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _compute_ui_staleness_warning(ui_dist: Path, ui_src: Path) -> Optional[str]:
    """Whether the built UI can still be believed to match its source.

    `hub/hub/static/ui` is a committed build artefact — nothing rebuilds it automatically in a
    source checkout, so it silently drifts behind `hub/ui/src` if a contributor edits the UI
    without rebuilding and recopying. `ui_src` only exists in a source checkout (not in an
    installed package), so this is a no-op for end users.

    This used to be answered by comparing commit dates, which cannot be cleared by doing what it
    asks. A change that leaves the built output byte-identical — types, comments, anything erased
    before the bundle is produced — gives a rebuild nothing to commit, so the artefact's commit
    date never moves and the warning stands forever. A warning that survives its own remedy
    teaches the operator to ignore the one signal that catches a genuinely stale bundle.

    So the bundle carries an *assertion* instead: the source state it was built from. Comparing
    that against the source as it stands answers "was this built from what is here now?", which is
    the question. It is a promise rather than a proof — only rebuilding proves it — but a dated,
    committed, attributable promise is a reviewable diff rather than an invisible omission.

    Where no stamp has been recorded this falls back to the old comparison exactly, so an
    installation carrying no assertion is not thereby declared current.
    """
    if not ui_src.exists() or not ui_dist.exists():
        return None

    stamp = read_ui_build_stamp(ui_dist)
    if stamp and stamp.get("src_fingerprint"):
        current = ui_source_fingerprint(ui_src)
        if current is None:
            return None
        if current == stamp["src_fingerprint"]:
            return None
        detail = (
            f"hub/hub/static/ui asserts it was built from hub/ui/src as of "
            f"{stamp.get('built_at', 'an earlier state')}, but the source has changed since."
        )
        if _has_uncommitted_ui_source(ui_src):
            detail += " hub/ui/src has uncommitted changes."
        # The script first, `make ui` second: `make` is absent from both shells on some supported
        # installations, and an instruction naming a command the operator does not have is one
        # they learn to ignore — including on the occasions it is right. The first command in a
        # sentence is the one that gets pasted.
        return detail + (
            " Run `python scripts/refresh_ui_bundle.py` (or `make ui`) to rebuild and re-record it."
        )

    # Tests are not bundled, so a commit touching only them cannot make the artefact stale.
    src_date = _git_last_commit_iso(ui_src, exclude=("__tests__",))
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


def _has_uncommitted_ui_source(ui_src: Path) -> bool:
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", ".", ":(exclude)__tests__"],
            cwd=ui_src,
            capture_output=True,
            text=True,
            timeout=5,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return dirty.returncode == 0 and bool(dirty.stdout.strip())


#: `(expires_at, warning)`. A TTL rather than `lru_cache(maxsize=1)`, so a rebuild clears the
#: warning within half a minute instead of requiring a Hub restart.
_ui_staleness_cache: "tuple[float, Optional[str]] | None" = None


def _runtime_kind() -> str:
    """Whether this process is running in a container or directly on the host (F34).

    Reported on `/health` because **this process is the only thing that knows**. The CLI used to
    infer it — `native` if it found a PID file it had written, `docker` otherwise — which made the
    absence of its own bookkeeping proof of a container. Measured 2026-08-25: a Hub started by hand
    with `uvicorn` was reported `running (docker)`.

    `/.dockerenv` is the conventional marker and is present in Docker's own images; `AW_RUNTIME`
    overrides it for anything that containerises differently, so a deployment this check does not
    recognise can state the answer rather than be guessed about.
    """
    declared = os.environ.get("AW_RUNTIME", "").strip()
    if declared:
        return declared
    return "docker" if Path("/.dockerenv").exists() else "native"


def _ui_staleness_warning() -> Optional[str]:
    global _ui_staleness_cache
    now = time.monotonic()
    if _ui_staleness_cache is not None and _ui_staleness_cache[0] > now:
        return _ui_staleness_cache[1]
    warning = _compute_ui_staleness_warning(UI_DIST, UI_SRC)
    _ui_staleness_cache = (now + UI_STALENESS_TTL_SECONDS, warning)
    return warning


def _reset_ui_staleness_cache() -> None:
    """Forget the cached answer. A test seam, and the only way to clear it deliberately."""
    global _ui_staleness_cache
    _ui_staleness_cache = None


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
    await reconcile_stale_job_runs()
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
        default_response_class=UTF8JSONResponse,
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

    # One handler rather than a try/except at each of the four call sites — the two task routes
    # times create-and-update. `detail` is written for a reader who has to correct themselves, and
    # the MCP adapter surfaces it verbatim, so this shape is an agent's only feedback on a refusal.
    @app.exception_handler(TransitionRefusedError)
    async def _transition_refused(request: Request, exc: TransitionRefusedError):
        # A gate refusal carries structure as well as a sentence: a surface has to be able to render
        # each blocked requirement and what would satisfy it without parsing prose. The `message`
        # inside it is the same text every other refusal sends, so a caller reading only that keeps
        # working.
        refusal = getattr(exc, "refusal", None)
        return UTF8JSONResponse(
            status_code=exc.http_status,
            content={"detail": refusal.to_dict() if refusal is not None else exc.detail},
        )

    @app.exception_handler(TaskBindingError)
    async def _task_binding_refused(request: Request, exc: TaskBindingError):
        # One handler rather than a raise at each site, for the same reason the transition one is:
        # the refusal reaches HTTP and MCP identically, and a route that forgot to translate it
        # would turn a nameable problem into a 500.
        return UTF8JSONResponse(
            status_code=exc.http_status,
            content={"detail": exc.detail},
        )

    @app.get("/health", include_in_schema=False)
    async def health():
        payload: Dict[str, Any] = {"status": "ok", "runtime": _runtime_kind()}
        warning = _ui_staleness_warning()
        if warning:
            payload["ui_stale"] = True
            payload["ui_stale_detail"] = warning
        return UTF8JSONResponse(payload)

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
