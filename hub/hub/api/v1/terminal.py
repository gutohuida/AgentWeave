"""The operator's shells in a conversation's side panel (`a-terminal-in-the-side-panel`, TSP-2).

    GET    /terminal/shells?conversation_id=C   the new-shell menu: installed shells, last pick,
                                                why the terminal or the worktree is unavailable
    GET    /conversations/{C}/terminals         the conversation's shells
    POST   /conversations/{C}/terminals         {shell, location, page?, cols?, rows?} -> 201
    DELETE /conversations/{C}/terminals/{T}     end it and everything it started
    POST   /conversations/{C}/terminals/{T}/restart
    WS     /conversations/{C}/terminals/{T}/attach   live input, output and resize
    WS     /terminal/page?page=<id>             held by a page for as long as it is loaded

Every route here is refused (403) in Docker mode, from anywhere but loopback, and -- for whatever
starts, drives or ends a shell -- from any page but the app's own (`terminal.access`); the menu
route alone answers instead with `unavailable` set, so the tab can say why. HTTP routes are signed
in by `get_project`. A browser cannot give a WebSocket a header, so the two sockets take the
operator's `Authorization` header or a project ticket from `GET /events/ticket` as `?token=`; a raw
key in the query string is refused, as the event stream refuses it, since URLs reach logs.

WebSocket messages, both directions JSON text:
    client -> {"type": "input", "data": str} | {"type": "resize", "cols": int, "rows": int}
    server -> {"type": "output", "data": str}   (first, everything kept so far, then as produced)
              {"type": "exit", "code": int|null} (the shell ended by itself; it stays listed)
              {"type": "closed"}                 (closed or restarted; the socket then closes)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from ...auth import _operator_from_credential, _verify_ticket, get_project
from ...db.engine import async_session_factory, get_session
from ...db.models import Project
from ...schemas.common import RequestModel
from ...terminal import LIMIT, access, registry
from ...terminal import shells as shell_detection
from ...terminal.sessions import LimitReachedError, Shell
from .workspace import _checkout_for

logger = logging.getLogger(__name__)

router = APIRouter(tags=["terminal"])

Location = Literal["worktree", "root"]


class OpenShell(RequestModel):
    shell: str = Field(..., max_length=200)
    location: Location = "root"
    #: The page load opening it: the shell ends when that page goes away (a reload ends it).
    page: Optional[str] = Field(None, max_length=100)
    cols: Optional[int] = Field(None, ge=10, le=1000)
    rows: Optional[int] = Field(None, ge=2, le=500)


def _refuse(request: Request, *, changes_something: bool) -> None:
    refusal = access.refusal(request, changes_something=changes_something)
    if refusal is not None:
        logger.warning(
            "Refused a shell request (%s) from %s: %s %s",
            refusal.reason,
            request.client.host if request.client else None,
            request.method,
            request.url.path,
        )
        raise HTTPException(status_code=refusal.status, detail=refusal.detail)


async def _places(session: AsyncSession, project_id: str, conversation_id: str):
    """(root, worktree or None, why there is no worktree): the Files tab's own rule."""
    repo_root, checkout, _branch, message = await _checkout_for(
        session, project_id, conversation_id
    )
    why = None
    if checkout is None:
        why = message or "This conversation's agent has no worktree."
    return repo_root, checkout, why


def _shell_of(project_id: str, conversation_id: str, terminal_id: str) -> Shell:
    shell = registry.get(terminal_id)
    if shell is None or shell.project_id != project_id or shell.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="No such shell in this conversation")
    return shell


@router.get("/terminal/shells")
async def get_shell_options(
    request: Request,
    conversation_id: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The new-shell menu: what is installed (last pick first, marked), and what is unavailable."""
    project_id, _ = project
    where = access.where_refusal(request)
    foreign = access.origin_refusal(request, required=False)
    if where is not None or foreign is not None:
        refusal = where or foreign
        assert refusal is not None
        return {
            "shells": [],
            "last_pick": None,
            "unavailable": refusal.reason,
            "unavailable_reason": refusal.detail,
            "worktree_unavailable": None,
            "limit": LIMIT,
        }
    options = await asyncio.to_thread(shell_detection.detect)
    pick = registry.last_pick
    rows = [dict(o.to_dict(), last_used=bool(pick and pick["option_id"] == o.id)) for o in options]
    rows.sort(key=lambda row: not row["last_used"])
    worktree_why: Optional[str] = "Choose a conversation to open a shell in its agent's worktree."
    root = worktree = None
    if conversation_id:
        repo_root, checkout, worktree_why = await _places(session, project_id, conversation_id)
        root, worktree = str(repo_root), (str(checkout) if checkout else None)
    return {
        "shells": rows,
        "last_pick": pick if pick and any(o.id == pick["option_id"] for o in options) else None,
        "unavailable": None,
        "unavailable_reason": None,
        "worktree_unavailable": worktree_why,
        "root_directory": root,
        "worktree_directory": worktree,
        "limit": LIMIT,
    }


@router.get("/conversations/{conversation_id}/terminals")
async def list_terminals(
    request: Request,
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
):
    _refuse(request, changes_something=False)
    project_id, _ = project
    shells = registry.for_conversation(project_id, conversation_id)
    return {"shells": [s.to_dict() for s in shells], "limit": LIMIT}


@router.post("/conversations/{conversation_id}/terminals", status_code=201)
async def open_terminal(
    request: Request,
    conversation_id: str,
    body: OpenShell,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    _refuse(request, changes_something=True)
    project_id, _ = project
    option = await asyncio.to_thread(shell_detection.find, body.shell)
    if option is None:
        raise HTTPException(status_code=422, detail=f"No shell '{body.shell}' is installed here")
    repo_root, checkout, why = await _places(session, project_id, conversation_id)
    if body.location == "worktree" and checkout is None:
        raise HTTPException(status_code=409, detail=why)
    path = checkout if body.location == "worktree" else repo_root
    # The session is not needed past here, and a shell can take a second to start.
    await session.close()
    size = (body.rows, body.cols) if body.rows and body.cols else None
    try:
        shell = await registry.open(
            project_id=project_id,
            conversation_id=conversation_id,
            option=option,
            location=body.location,
            path=path,
            page=body.page,
            size=size,
        )
    except LimitReachedError as exc:
        return JSONResponse(status_code=409, content={"detail": str(exc), "limit": LIMIT})
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"{option.label} could not be started: {exc}"
        ) from exc
    return shell.to_dict()


@router.delete("/conversations/{conversation_id}/terminals/{terminal_id}")
async def close_terminal(
    request: Request,
    conversation_id: str,
    terminal_id: str,
    project: Tuple[str, str] = Depends(get_project),
):
    _refuse(request, changes_something=True)
    project_id, _ = project
    shell = _shell_of(project_id, conversation_id, terminal_id)
    await registry.close(shell)
    return {"id": shell.id, "closed": True, "exit_code": shell.exit_code}


@router.post("/conversations/{conversation_id}/terminals/{terminal_id}/restart")
async def restart_terminal(
    request: Request,
    conversation_id: str,
    terminal_id: str,
    project: Tuple[str, str] = Depends(get_project),
):
    _refuse(request, changes_something=True)
    project_id, _ = project
    shell = _shell_of(project_id, conversation_id, terminal_id)
    try:
        fresh = await registry.restart(shell)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"{shell.label} could not be started again: {exc}"
        ) from exc
    return dict(fresh.to_dict(), replaces=shell.id)


# --------------------------------------------------------------------------- WebSockets


async def _websocket_refusal(websocket: WebSocket, project_id: str) -> Optional[str]:
    """Why *websocket* may not reach this project's shells, or None. Checks what the HTTP routes
    check: where it came from, which page asked, and the operator's sign-in."""
    refusal = access.refusal(websocket, changes_something=True)
    if refusal is not None:
        return refusal.detail
    header = websocket.headers.get("authorization") or ""
    token = websocket.query_params.get("token") or ""
    async with async_session_factory() as session:
        if header.lower().startswith("bearer "):
            try:
                await _operator_from_credential(header[7:].strip(), session)
            except HTTPException as exc:
                return str(exc.detail)
        elif token:
            if _verify_ticket(token) != project_id:
                return "Invalid or expired ticket for this project's shells"
        else:
            return "Sign in to open a shell"
        if await session.get(Project, project_id) is None:
            return "Project not found"
    return None


async def _refuse_websocket(websocket: WebSocket, reason: str) -> None:
    logger.warning(
        "Refused a shell connection from %s (%s): %s",
        websocket.client.host if websocket.client else None,
        websocket.headers.get("origin"),
        reason,
    )
    # Closing before accepting answers the handshake 403: the socket never opens.
    await websocket.close(code=1008, reason=reason[:120])


@router.websocket("/conversations/{conversation_id}/terminals/{terminal_id}/attach")
async def attach_terminal(
    websocket: WebSocket, project_id: str, conversation_id: str, terminal_id: str
):
    reason = await _websocket_refusal(websocket, project_id)
    shell = registry.get(terminal_id)
    if reason is None and (
        shell is None or shell.project_id != project_id or shell.conversation_id != conversation_id
    ):
        reason = "No such shell in this conversation"
    if reason is not None or shell is None:
        await _refuse_websocket(websocket, reason or "No such shell")
        return
    await websocket.accept()
    queue = shell.subscribe()
    try:
        await websocket.send_text(json.dumps({"type": "output", "data": shell.buffer.text()}))
        if not shell.running and not shell.closed:
            await websocket.send_text(json.dumps({"type": "exit", "code": shell.exit_code}))
        sender = asyncio.create_task(_forward(websocket, queue))
        try:
            while True:
                message = await websocket.receive_text()
                _apply(shell, message)
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
    finally:
        shell.unsubscribe(queue)


async def _forward(websocket: WebSocket, queue: asyncio.Queue) -> None:
    try:
        while True:
            frame = await queue.get()
            if frame is None:
                await websocket.close(code=1000)
                return
            await websocket.send_text(frame)
    except Exception:  # noqa: BLE001 - the socket went away; the receive loop sees it
        return


def _apply(shell: Shell, message: str) -> None:
    try:
        payload = json.loads(message)
    except ValueError:
        return
    if not isinstance(payload, dict):
        return
    if payload.get("type") == "input" and isinstance(payload.get("data"), str):
        shell.write(payload["data"])
    elif payload.get("type") == "resize":
        try:
            shell.resize(int(payload.get("rows")), int(payload.get("cols")))
        except (TypeError, ValueError):
            return


@router.websocket("/terminal/page")
async def page_presence(websocket: WebSocket, project_id: str):
    """Held open by a page for as long as it is loaded; its shells end when it goes away."""
    page = websocket.query_params.get("page") or ""
    reason = await _websocket_refusal(websocket, project_id)
    if reason is None and not (0 < len(page) <= 100):
        reason = "A page id is required"
    if reason is not None:
        await _refuse_websocket(websocket, reason)
        return
    await websocket.accept()
    registry.page_arrived(page)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        registry.page_left(page)
