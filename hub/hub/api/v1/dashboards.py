"""A project's dashboards: query, save, list, read, run and delete (`ask-any-agent-for-a-
dashboard-and-get-one-that-stays`, FR-1, FR-7, FR-9 to FR-13).

Two routers over one store. `router` is the operator's, under `/projects/{project_id}/dashboards`
on the project credential; `agent_router` is the agents', under `/agent-actions/dashboards` on a
run credential, whose project and author come from the run, never from the body. Agents cannot
delete a dashboard: only the operator can, from the Dashboards screen.

Saving checks each panel's chart kind (`invalid_chart_kind`) and that its query names nothing
never queryable (`not_queryable`), but does not run the queries: a panel whose query fails is saved
and shows its error when the dashboard is run. Running answers every panel on its own, so one
failing panel never fails the rest. The fixed paths (`query-reference`, `query`) are declared
before `/{dashboard_id}` so neither is read as an id.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ... import dashboard_query
from ...agent_auth import AgentActor, get_agent_actor
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Dashboard
from ...schemas.common import RequestModel
from ...sse import sse_manager
from ...utils import short_id

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
agent_router = APIRouter(prefix="/agent-actions/dashboards", tags=["agent-actions"])

#: The chart kinds the app draws (FR-10), in the order the screen offers them.
CHART_KINDS: Tuple[str, ...] = ("number", "table", "bar", "stacked_bar", "line")

#: Who a dashboard the operator saved is recorded as.
OPERATOR_AUTHOR = "operator"

_PANEL_ID_RE = re.compile(r"^pnl-[0-9a-f]{12}$")


class PanelIn(RequestModel):
    id: Optional[str] = Field(default=None, max_length=64)
    title: str = Field(max_length=200)
    query: str = Field(max_length=100_000)
    # A plain string, checked by `_panels`, so another kind answers `invalid_chart_kind` rather
    # than pydantic's generic validation error.
    kind: str = Field(max_length=64)


class DashboardIn(RequestModel):
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=10_000)
    panels: List[PanelIn] = Field(max_length=50)


class AgentDashboardIn(DashboardIn):
    #: Replace this dashboard whole rather than save a new one.
    dashboard_id: str = Field(default="", max_length=64)


class QueryIn(RequestModel):
    sql: str = Field(max_length=100_000)


def _refuse(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message, **extra}
    )


def _panels(panels: Sequence[PanelIn], kept: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """The panels as stored, or a 422 naming the first that cannot be saved.

    A panel keeps an id it carries that is well formed, unique in the dashboard and, on a replace,
    one of the dashboard's own (`kept`); otherwise the Hub assigns one."""
    known = {p.get("id") for p in kept}
    out: List[Dict[str, Any]] = []
    used: set = set()
    for index, panel in enumerate(panels):
        title = panel.title.strip()
        if not title:
            raise _refuse(422, "invalid_panel", f"Panel {index + 1} has no title.", panel=index)
        if not panel.query.strip():
            raise _refuse(422, "invalid_panel", f"Panel {index + 1} has no query.", panel=index)
        if panel.kind not in CHART_KINDS:
            raise _refuse(
                422,
                "invalid_chart_kind",
                f"Panel {index + 1} ({title}) names chart kind {panel.kind!r}; a chart kind is one "
                f"of {', '.join(CHART_KINDS)}.",
                panel=index,
            )
        try:
            dashboard_query.check_queryable(panel.query)
        except dashboard_query.QueryRefused as exc:
            raise _refuse(
                422, exc.code, f"Panel {index + 1} ({title}): {exc.message}", panel=index
            ) from exc
        pid = panel.id
        fresh = not pid or not _PANEL_ID_RE.match(pid) or pid in used
        if not fresh and kept and pid not in known:
            fresh = True
        if fresh:
            pid = f"pnl-{short_id()}"
        used.add(pid)
        out.append({"id": pid, "title": title, "query": panel.query, "kind": panel.kind})
    return out


def _name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise _refuse(422, "invalid_dashboard", "A dashboard needs a name.")
    return name


def _view(dashboard: Dashboard) -> Dict[str, Any]:
    return {
        "id": dashboard.id,
        "name": dashboard.name,
        "description": dashboard.description,
        "panels": list(dashboard.panels or []),
        "author": dashboard.author,
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "updated_at": dashboard.updated_at.isoformat() if dashboard.updated_at else None,
    }


def _summary(dashboard: Dashboard) -> Dict[str, Any]:
    view = _view(dashboard)
    view["panel_count"] = len(view.pop("panels"))
    return view


async def _get(session: AsyncSession, project_id: str, dashboard_id: str) -> Dashboard:
    dashboard = await session.get(Dashboard, dashboard_id)
    # Another project's id is the same 404 as a missing one: its existence is not this project's.
    if dashboard is None or dashboard.project_id != project_id:
        raise _refuse(404, "dashboard_not_found", f"No dashboard {dashboard_id} in this project.")
    return dashboard


async def _name_taken(
    session: AsyncSession, project_id: str, name: str, other_than: Optional[str]
) -> None:
    query = select(Dashboard.id).where(Dashboard.project_id == project_id, Dashboard.name == name)
    if other_than:
        query = query.where(Dashboard.id != other_than)
    if (await session.execute(query)).first() is not None:
        raise _refuse(
            409, "dashboard_name_taken", f"This project already has a dashboard named {name!r}."
        )


async def _commit(session: AsyncSession, name: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _refuse(
            409, "dashboard_name_taken", f"This project already has a dashboard named {name!r}."
        ) from exc


async def list_dashboards(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    rows = (
        (
            await session.execute(
                select(Dashboard)
                .where(Dashboard.project_id == project_id)
                .order_by(Dashboard.updated_at.desc(), Dashboard.name)
            )
        )
        .scalars()
        .all()
    )
    return {"dashboards": [_summary(d) for d in rows]}


async def create_dashboard(
    session: AsyncSession, project_id: str, body: DashboardIn, author: str
) -> Dict[str, Any]:
    name = _name(body.name)
    panels = _panels(body.panels)
    await _name_taken(session, project_id, name, None)
    now = datetime.now(timezone.utc)
    dashboard = Dashboard(
        id=f"dash-{short_id()}",
        project_id=project_id,
        name=name,
        description=body.description,
        panels=panels,
        author=author[:32],
        created_at=now,
        updated_at=now,
    )
    session.add(dashboard)
    await _commit(session, name)
    await sse_manager.broadcast(
        project_id, "dashboard_saved", {"id": dashboard.id, "name": dashboard.name}
    )
    return _view(dashboard)


async def replace_dashboard(
    session: AsyncSession, project_id: str, dashboard_id: str, body: DashboardIn, author: str
) -> Dict[str, Any]:
    dashboard = await _get(session, project_id, dashboard_id)
    name = _name(body.name)
    panels = _panels(body.panels, kept=list(dashboard.panels or []))
    await _name_taken(session, project_id, name, dashboard.id)
    dashboard.name = name
    dashboard.description = body.description
    dashboard.panels = panels
    dashboard.author = author[:32]
    dashboard.updated_at = datetime.now(timezone.utc)
    await _commit(session, name)
    await sse_manager.broadcast(
        project_id, "dashboard_saved", {"id": dashboard.id, "name": dashboard.name}
    )
    return _view(dashboard)


def _numeric(rows: Sequence[Sequence[Any]], index: int) -> bool:
    values = [row[index] for row in rows if row[index] is not None]
    return bool(values) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in values
    )


def drawing_warning(
    kind: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]
) -> Optional[str]:
    """Why a result cannot be drawn as `kind`, or None when it can (FR-12). A table draws anything."""
    if kind == "table":
        return None
    if not rows:
        return "The query returned no rows, so there is nothing to draw."
    numeric = [i for i in range(len(columns)) if _numeric(rows, i)]
    if kind == "number":
        if not numeric:
            return "A single number needs a numeric column; this result has none."
        return None
    # Bar, stacked bar and line: the first column labels the points, the others are drawn.
    if len(columns) < 2:
        return (
            f"A {kind.replace('_', ' ')} chart needs a label column and at least one numeric "
            "column; this result has one column."
        )
    if not [i for i in numeric if i > 0]:
        return (
            f"A {kind.replace('_', ' ')} chart needs a numeric column after the first (label) "
            f"column; none of {', '.join(columns[1:])} is numeric."
        )
    return None


async def _run_panel(project_id: str, panel: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": panel.get("id"),
        "title": panel.get("title"),
        "kind": panel.get("kind"),
        "query": panel.get("query"),
        "columns": [],
        "rows": [],
        "row_count": 0,
        "truncated": False,
        "elapsed_ms": None,
        "error": None,
        "warning": None,
    }
    try:
        result = await dashboard_query.run_query(project_id, panel.get("query") or "")
    except dashboard_query.QueryRefused as exc:
        out["error"] = exc.detail
        return out
    except Exception as exc:  # one panel never fails the rest
        out["error"] = {"code": "query_error", "message": str(exc) or type(exc).__name__}
        return out
    out.update(
        columns=result["columns"],
        rows=result["rows"],
        row_count=result["row_count"],
        truncated=result["truncated"],
        elapsed_ms=result["elapsed_ms"],
    )
    out["warning"] = drawing_warning(str(panel.get("kind")), result["columns"], result["rows"])
    return out


async def run_dashboard(
    session: AsyncSession, project_id: str, dashboard_id: str
) -> Dict[str, Any]:
    dashboard = await _get(session, project_id, dashboard_id)
    view = _view(dashboard)
    panels = await asyncio.gather(*(_run_panel(project_id, p) for p in view["panels"]))
    return {
        "id": view["id"],
        "name": view["name"],
        "description": view["description"],
        "author": view["author"],
        "updated_at": view["updated_at"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "panels": list(panels),
    }


async def _query(project_id: str, sql: str) -> Dict[str, Any]:
    try:
        return dict(await dashboard_query.run_query(project_id, sql))
    except dashboard_query.QueryRefused as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


# -------------------------------------------------------------------------------- operator routes


@router.get("/query-reference")
async def operator_query_reference(project: Tuple[str, str] = Depends(get_project)):
    return dashboard_query.query_reference()


@router.post("/query")
async def operator_run_query(body: QueryIn, project: Tuple[str, str] = Depends(get_project)):
    return await _query(project[0], body.sql)


@router.get("")
async def operator_list_dashboards(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    return await list_dashboards(session, project[0])


@router.post("", status_code=status.HTTP_201_CREATED)
async def operator_create_dashboard(
    body: DashboardIn,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    return await create_dashboard(session, project[0], body, OPERATOR_AUTHOR)


@router.put("/{dashboard_id}")
async def operator_replace_dashboard(
    dashboard_id: str,
    body: DashboardIn,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    return await replace_dashboard(session, project[0], dashboard_id, body, OPERATOR_AUTHOR)


@router.get("/{dashboard_id}")
async def operator_read_dashboard(
    dashboard_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    return _view(await _get(session, project[0], dashboard_id))


@router.get("/{dashboard_id}/run")
async def operator_run_dashboard(
    dashboard_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    return await run_dashboard(session, project[0], dashboard_id)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def operator_delete_dashboard(
    dashboard_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    dashboard = await _get(session, project[0], dashboard_id)
    payload = {"id": dashboard.id, "name": dashboard.name}
    await session.delete(dashboard)
    await session.commit()
    await sse_manager.broadcast(project[0], "dashboard_deleted", payload)


# ----------------------------------------------------------------------------------- agent routes


@agent_router.get("/query-reference")
async def agent_query_reference(actor: AgentActor = Depends(get_agent_actor)):
    return dashboard_query.query_reference()


@agent_router.post("/query")
async def agent_run_query(body: QueryIn, actor: AgentActor = Depends(get_agent_actor)):
    return await _query(actor.project_id, body.sql)


@agent_router.get("")
async def agent_list_dashboards(
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await list_dashboards(session, actor.project_id)


@agent_router.post("")
async def agent_save_dashboard(
    body: AgentDashboardIn,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Save a new dashboard, or with `dashboard_id` replace that one whole. The author is the
    run's agent."""
    fields = DashboardIn(name=body.name, description=body.description, panels=body.panels)
    if body.dashboard_id:
        return await replace_dashboard(
            session, actor.project_id, body.dashboard_id, fields, actor.agent
        )
    return await create_dashboard(session, actor.project_id, fields, actor.agent)


@agent_router.get("/{dashboard_id}")
async def agent_read_dashboard(
    dashboard_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return _view(await _get(session, actor.project_id, dashboard_id))
