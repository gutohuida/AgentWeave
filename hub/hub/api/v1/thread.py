"""The project's thread: one level of its history at a time, paged by time in both directions."""

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ... import chapters, manager, project_thread, vault
from ...auth import get_project
from ...db.engine import get_session
from .vault import project_root, roots

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/thread", tags=["thread"])


async def vault_additions(session: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """The sources in the project's vault, with when they were added. A vault that cannot be read
    leaves its entries off the thread rather than failing the page."""
    try:
        root, private = await roots(session, project_id)
        records = await asyncio.to_thread(vault._records, root, private)
    except Exception:  # noqa: BLE001 -- the thread outlives an unreadable vault
        logger.warning("the thread could not read the vault", exc_info=True)
        return []
    return [
        {
            "id": record.meta["id"],
            "name": record.meta.get("name"),
            "created_at": record.meta.get("created_at"),
            "added_by": record.meta.get("added_by"),
        }
        for record in records.values()
    ]


async def built(session: AsyncSession, project_id: str) -> project_thread.Thread:
    thread = await project_thread.build(
        session, project_id, await vault_additions(session, project_id)
    )
    repo: Optional[Path] = None
    # No workspace: chapters still show; commits they cite cannot be opened.
    with contextlib.suppress(HTTPException):
        repo = await project_root(session, project_id)
    return await chapters.overlay(session, project_id, thread, repo)


@router.get("")
async def get_thread(
    under: Optional[str] = Query(None, description="A knot's address; omit for the surface"),
    limit: int = Query(40, ge=1, le=200),
    before: Optional[str] = Query(None, description="Page ending just before this cursor"),
    after: Optional[str] = Query(None, description="Page starting just after this cursor"),
    first: bool = Query(False, description="The oldest page instead of the newest"),
    around: Optional[str] = Query(None, description="The page with this knot (by address) in it"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """One level of the thread, oldest first. With no cursor it is the newest page, so the present
    is in view; `first` is the beginning; `before`/`after` walk from a page's cursors."""
    thread = await built(session, project[0])
    level = thread.level(under)
    if level is None:
        raise HTTPException(status_code=404, detail="There is no such knot")
    result = project_thread.page(
        level, limit=limit, before=before, after=after, first=first, around=around
    )
    if result is None:
        raise HTTPException(status_code=422, detail="That is not a cursor this thread gave out")
    result["knots"] = [project_thread.face(k, thread) for k in result["knots"]]
    result["under"] = under or project_thread.SURFACE
    # 'Weave the thread' is offered only while the chapters job is on.
    row = await manager.get_job_row(session, project[0], manager.CHAPTERS)
    result["can_weave"] = bool(row is not None and row.enabled)
    return result


@router.get("/knot")
async def get_knot(
    key: str = Query(..., description="A knot's address"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """One knot and the knots to open, outermost first, to reach it."""
    thread = await built(session, project[0])
    knot = thread.find(key)
    chain = thread.ancestors(key) if knot is not None else None
    if knot is None or chain is None:
        raise HTTPException(status_code=404, detail="There is no such knot")
    return {"knot": project_thread.face(knot, thread), "ancestors": chain}
