"""A project's dashboards: query, save, list, read, run, edit, undo and delete (`ask-any-agent-
for-a-dashboard-and-get-one-that-stays`, FR-1, FR-7, FR-9 to FR-13; `change-a-dashboard-by-
asking`, FR-1 to FR-9).

Two routers over one store. `router` is the operator's, under `/projects/{project_id}/dashboards`
on the project credential; `agent_router` is the agents', under `/agent-actions/dashboards` on a
run credential, whose project and author come from the run, never from the body. Agents cannot
delete a dashboard: only the operator can, from the Dashboards screen.

Saving checks each panel's chart kind (`invalid_chart_kind`) and that its query names nothing
never queryable (`not_queryable`), but does not run the queries: a panel whose query fails is saved
and shows its error when the dashboard is run. Running answers every panel on its own, so one
failing panel never fails the rest. The fixed paths (`query-reference`, `query`) are declared
before `/{dashboard_id}` so neither is read as an id.

An edit (`PATCH /agent-actions/dashboards/{id}`) names the version it read and a list of
operations, applied whole or not at all and validated like a save. A whole replace of an existing
dashboard is an edit too. Every edit, replace and undo raises the dashboard's `version` by one,
records who made it in `edited_by` / `edited_at` (never from the body), and keeps what it replaced
as the dashboard's one `DashboardVersion`, which undo restores as a new edit. A write naming an
older version than the current one is refused `stale_version` with the current dashboard, never
merged.

Which dashboard an agent writes is held by the Hub, not left to the model (FR-2). An agent's edit,
replace or undo lands only on a dashboard its run's request named: by its `dash-` id, or by its
whole name, case aside -- the request being what was delivered to the run and the answers to the
questions the run asked. Otherwise it is refused `dashboard_not_named`, naming what the request did
name: "the team health dashboard" names neither "Team health North" nor "Team health South". A run
refused so cannot then save a new dashboard in its place, until a question it asks after is
answered. And a run that asked the operator something with no answer (declined, expired or still
open) cannot save, edit or undo a dashboard at all: refused `question_unanswered`; the operator's
answer reaches a later run, which can write.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ... import dashboard_query
from ...agent_auth import AgentActor, get_agent_actor
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    Dashboard,
    DashboardVersion,
    EventLog,
    InboundQueueEntry,
    Question,
)
from ...schemas.common import RequestModel
from ...sse import sse_manager
from ...utils import persist_accepted_event, short_id

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
agent_router = APIRouter(prefix="/agent-actions/dashboards", tags=["agent-actions"])

#: The chart kinds the app draws (FR-10), in the order the screen offers them.
CHART_KINDS: Tuple[str, ...] = ("number", "table", "bar", "stacked_bar", "line")

#: Who a dashboard the operator saved is recorded as.
OPERATOR_AUTHOR = "operator"

#: The most panels a dashboard holds.
MAX_PANELS = 50

_PANEL_ID_RE = re.compile(r"^pnl-[0-9a-f]{12}$")

#: The operations an edit is made of (`change-a-dashboard-by-asking`, FR-4).
OPERATIONS: Tuple[str, ...] = (
    "add_panel",
    "remove_panel",
    "change_panel",
    "move_panel",
    "rename",
    "set_description",
)


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
    panels: List[PanelIn] = Field(max_length=MAX_PANELS)
    #: On a replace, the version it was made against; an older one is refused `stale_version`.
    base_version: Optional[int] = None


class AgentDashboardIn(DashboardIn):
    #: Replace this dashboard whole rather than save a new one.
    dashboard_id: str = Field(default="", max_length=64)


class EditIn(RequestModel):
    #: The `version` the edit was made against, as read.
    base_version: int
    #: Each `{"op": ...}`, checked one by one by `_apply` so a refusal names its index.
    operations: List[Dict[str, Any]] = Field(min_length=1, max_length=100)


class QueryIn(RequestModel):
    sql: str = Field(max_length=100_000)


def _refuse(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message, **extra}
    )


def _panel_refusal(title: str, query: str, kind: str) -> Optional[Tuple[str, str]]:
    """Why a panel cannot be saved, as `(reason, message)` with the message following "Panel n",
    or None when it can. One check for a save and for an edit's operations (FR-8)."""
    if not title:
        return "invalid_panel", "has no title."
    if not query.strip():
        return "invalid_panel", "has no query."
    if kind not in CHART_KINDS:
        return (
            "invalid_chart_kind",
            f"({title}) names chart kind {kind!r}; a chart kind is one of "
            f"{', '.join(CHART_KINDS)}.",
        )
    try:
        dashboard_query.check_queryable(query)
    except dashboard_query.QueryRefused as exc:
        return exc.code, f"({title}): {exc.message}"
    return None


def _panels(panels: Sequence[PanelIn], kept: Sequence[Dict[str, Any]] = ()) -> List[Dict[str, Any]]:
    """The panels as stored, or a 422 naming the first that cannot be saved.

    A panel keeps an id it carries that is well formed, unique in the dashboard and, on a replace,
    one of the dashboard's own (`kept`); otherwise the Hub assigns one."""
    known = {p.get("id") for p in kept}
    out: List[Dict[str, Any]] = []
    used: set = set()
    for index, panel in enumerate(panels):
        title = panel.title.strip()
        refusal = _panel_refusal(title, panel.query, panel.kind)
        if refusal:
            reason, message = refusal
            raise _refuse(422, reason, f"Panel {index + 1} {message}", panel=index)
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


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() if moment else None


def _view(dashboard: Dashboard, can_undo: bool) -> Dict[str, Any]:
    return {
        "id": dashboard.id,
        "name": dashboard.name,
        "description": dashboard.description,
        "panels": list(dashboard.panels or []),
        "author": dashboard.author,
        "created_at": _iso(dashboard.created_at),
        "updated_at": _iso(dashboard.updated_at),
        "version": dashboard.version,
        "edited_by": dashboard.edited_by,
        "edited_at": _iso(dashboard.edited_at),
        "can_undo": can_undo,
    }


async def _kept(session: AsyncSession, dashboard: Dashboard) -> Optional[DashboardVersion]:
    kept = await session.get(DashboardVersion, dashboard.id)
    return kept if kept is not None and kept.project_id == dashboard.project_id else None


async def _read_view(session: AsyncSession, dashboard: Dashboard) -> Dict[str, Any]:
    return _view(dashboard, await _kept(session, dashboard) is not None)


def _summary(dashboard: Dashboard, can_undo: bool) -> Dict[str, Any]:
    view = _view(dashboard, can_undo)
    view["panel_count"] = len(view.pop("panels"))
    return view


async def _get(session: AsyncSession, project_id: str, dashboard_id: str) -> Dashboard:
    dashboard = await session.get(Dashboard, dashboard_id)
    # Another project's id is the same 404 as a missing one: its existence is not this project's.
    if dashboard is None or dashboard.project_id != project_id:
        raise _refuse(404, "dashboard_not_found", f"No dashboard {dashboard_id} in this project.")
    return dashboard


def _taken(name: str) -> HTTPException:
    return _refuse(
        409, "dashboard_name_taken", f"This project already has a dashboard named {name!r}."
    )


async def _name_taken(
    session: AsyncSession, project_id: str, name: str, other_than: Optional[str]
) -> None:
    query = select(Dashboard.id).where(Dashboard.project_id == project_id, Dashboard.name == name)
    if other_than:
        query = query.where(Dashboard.id != other_than)
    if (await session.execute(query)).first() is not None:
        raise _taken(name)


async def _commit(session: AsyncSession, name: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _taken(name) from exc


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
    kept = set(
        (
            await session.execute(
                select(DashboardVersion.dashboard_id).where(
                    DashboardVersion.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    return {"dashboards": [_summary(d, d.id in kept) for d in rows]}


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
        version=1,
    )
    session.add(dashboard)
    await _commit(session, name)
    await sse_manager.broadcast(
        project_id, "dashboard_saved", {"id": dashboard.id, "name": dashboard.name}
    )
    return _view(dashboard, False)


async def _stale(session: AsyncSession, dashboard: Dashboard) -> HTTPException:
    return _refuse(
        409,
        "stale_version",
        f"The dashboard {dashboard.name!r} changed since you read it: it is now version "
        f"{dashboard.version}. Nothing was changed; make your change again against the current "
        "dashboard in `current`.",
        current=await _read_view(session, dashboard),
    )


async def _check_base(
    session: AsyncSession, dashboard: Dashboard, base_version: Optional[int]
) -> None:
    if base_version is not None and base_version != dashboard.version:
        raise await _stale(session, dashboard)


async def _write(
    session: AsyncSession,
    dashboard: Dashboard,
    *,
    name: str,
    description: str,
    panels: List[Dict[str, Any]],
    editor: str,
) -> Dict[str, Any]:
    """Make `dashboard` this content at its next version, keeping what it replaces (FR-6).

    The update is conditional on the version read, so of two writes from the same version only
    the first lands and the second answers `stale_version` (FR-5)."""
    project_id, dashboard_id, base = dashboard.project_id, dashboard.id, dashboard.version
    replaced = {
        "version": base,
        "name": dashboard.name,
        "description": dashboard.description,
        "panels": list(dashboard.panels or []),
        "edited_by": dashboard.edited_by,
        "edited_at": dashboard.edited_at,
    }
    await _name_taken(session, project_id, name, dashboard_id)
    now = datetime.now(timezone.utc)
    try:
        written = await session.execute(
            update(Dashboard)
            .where(Dashboard.id == dashboard_id, Dashboard.version == base)
            .values(
                name=name,
                description=description,
                panels=panels,
                version=base + 1,
                edited_by=editor[:32],
                edited_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if written.rowcount != 1:
            await session.rollback()
            await session.refresh(dashboard)
            raise await _stale(session, dashboard)
        kept = await session.get(DashboardVersion, dashboard_id)
        if kept is None:
            session.add(
                DashboardVersion(dashboard_id=dashboard_id, project_id=project_id, **replaced)
            )
        else:
            kept.project_id = project_id
            for field, value in replaced.items():
                setattr(kept, field, value)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _taken(name) from exc
    await session.refresh(dashboard)
    await sse_manager.broadcast(
        project_id,
        "dashboard_edited",
        {"id": dashboard.id, "name": dashboard.name, "version": dashboard.version},
    )
    return _view(dashboard, True)


async def replace_dashboard(
    session: AsyncSession, project_id: str, dashboard_id: str, body: DashboardIn, editor: str
) -> Dict[str, Any]:
    """Replace a dashboard whole. It is an edit: checked against `base_version` when given, and
    it keeps what it replaced. The author stays who created it; `editor` becomes `edited_by`."""
    dashboard = await _get(session, project_id, dashboard_id)
    await _check_base(session, dashboard, body.base_version)
    name = _name(body.name)
    panels = _panels(body.panels, kept=list(dashboard.panels or []))
    view = await _write(
        session, dashboard, name=name, description=body.description, panels=panels, editor=editor
    )
    await sse_manager.broadcast(
        project_id, "dashboard_saved", {"id": view["id"], "name": view["name"]}
    )
    return view


def _operation_refused(index: int, reason: str, message: str) -> HTTPException:
    return _refuse(
        422,
        "operation_refused",
        f"Operation {index} (counting from 0) was refused, so none was applied: {message}",
        operation_index=index,
        reason=reason,
    )


def _panel_at(panels: List[Dict[str, Any]], op: Dict[str, Any], index: int) -> int:
    panel_id = op.get("panel_id")
    for at, panel in enumerate(panels):
        if panel.get("id") == panel_id:
            return at
    raise _operation_refused(
        index,
        "unknown_panel",
        f"the dashboard has no panel {panel_id!r}; its panels are "
        f"{', '.join(str(p.get('id')) for p in panels) or 'none'}.",
    )


def _position(op: Dict[str, Any], index: int, size: int, required: bool) -> int:
    """Where a panel goes: an index from 0, clamped into the list; the end when null and allowed."""
    raw = op.get("position")
    if raw is None and not required:
        return size
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise _operation_refused(
            index, "invalid_panel", f"position must be a whole number from 0, not {raw!r}."
        )
    return max(0, min(raw, size))


def _text(op: Dict[str, Any], key: str, index: int, limit: int) -> str:
    value = op.get(key)
    if not isinstance(value, str):
        raise _operation_refused(index, "invalid_panel", f"{key} must be text, not {value!r}.")
    if len(value) > limit:
        raise _operation_refused(
            index, "invalid_panel", f"{key} is longer than {limit} characters."
        )
    return value


_PANEL_LIMITS = (("title", 200), ("query", 100_000), ("kind", 64))


def _checked_panel(panel: Dict[str, Any], index: int) -> Dict[str, Any]:
    for key, limit in _PANEL_LIMITS:
        _text(panel, key, index, limit)
    title = panel["title"].strip()
    refusal = _panel_refusal(title, panel["query"], panel["kind"])
    if refusal:
        reason, message = refusal
        raise _operation_refused(index, reason, f"the panel {message}")
    return {**panel, "title": title}


def _apply(
    dashboard: Dashboard, operations: Sequence[Dict[str, Any]]
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """The dashboard's name, description and panels after `operations`, or the refusal of the
    first that cannot apply. Nothing is written here, so a refusal leaves the dashboard as it was
    (FR-4). A panel keeps its id; an added one gets a new id."""
    name, description = dashboard.name, dashboard.description
    panels = [dict(p) for p in dashboard.panels or []]
    for index, op in enumerate(operations):
        kind = op.get("op")
        if kind == "add_panel":
            panel = op.get("panel")
            if not isinstance(panel, dict):
                raise _operation_refused(
                    index, "invalid_panel", "add_panel needs a panel {title, query, kind}."
                )
            if len(panels) >= MAX_PANELS:
                raise _operation_refused(
                    index, "invalid_panel", f"a dashboard holds at most {MAX_PANELS} panels."
                )
            checked = _checked_panel({key: panel.get(key) for key, _ in _PANEL_LIMITS}, index)
            at = _position(op, index, len(panels), required=False)
            panels.insert(at, {"id": f"pnl-{short_id()}", **checked})
        elif kind == "remove_panel":
            panels.pop(_panel_at(panels, op, index))
        elif kind == "change_panel":
            at = _panel_at(panels, op, index)
            changed = {**panels[at]}
            for key, limit in _PANEL_LIMITS:
                if key in op:
                    changed[key] = _text(op, key, index, limit)
            panels[at] = _checked_panel(changed, index)
        elif kind == "move_panel":
            panel = panels.pop(_panel_at(panels, op, index))
            panels.insert(_position(op, index, len(panels), required=True), panel)
        elif kind == "rename":
            name = _text(op, "name", index, 200).strip()
            if not name:
                raise _operation_refused(index, "invalid_dashboard", "a dashboard needs a name.")
        elif kind == "set_description":
            description = _text(op, "description", index, 10_000)
        else:
            raise _operation_refused(
                index,
                "unknown_operation",
                f"{kind!r} is not an operation; one of {', '.join(OPERATIONS)}.",
            )
    return name, description, panels


async def edit_dashboard(
    session: AsyncSession, project_id: str, dashboard_id: str, body: EditIn, editor: str
) -> Dict[str, Any]:
    dashboard = await _get(session, project_id, dashboard_id)
    await _check_base(session, dashboard, body.base_version)
    name, description, panels = _apply(dashboard, body.operations)
    return await _write(
        session, dashboard, name=name, description=description, panels=panels, editor=editor
    )


async def undo_dashboard(
    session: AsyncSession, project_id: str, dashboard_id: str, editor: str
) -> Dict[str, Any]:
    """Restore the kept version as a new edit, keeping what it replaces, so undo undoes itself."""
    dashboard = await _get(session, project_id, dashboard_id)
    kept = await _kept(session, dashboard)
    if kept is None:
        raise _refuse(
            409,
            "nothing_to_undo",
            f"The dashboard {dashboard.name!r} has not been edited, so there is nothing to undo.",
        )
    return await _write(
        session,
        dashboard,
        name=kept.name,
        description=kept.description,
        panels=list(kept.panels or []),
        editor=editor,
    )


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


#: What a run answers of the dashboard beside its panels' results.
_RUN_FIELDS = (
    "id",
    "name",
    "description",
    "author",
    "updated_at",
    "version",
    "edited_by",
    "edited_at",
    "can_undo",
)


async def run_dashboard(
    session: AsyncSession, project_id: str, dashboard_id: str
) -> Dict[str, Any]:
    """Run every panel of a saved dashboard: the operator's screen and an agent read the same
    answer (`change-a-dashboard-by-asking`, FR-7)."""
    dashboard = await _get(session, project_id, dashboard_id)
    view = await _read_view(session, dashboard)
    panels = await asyncio.gather(*(_run_panel(project_id, p) for p in view["panels"]))
    return {
        **{key: view[key] for key in _RUN_FIELDS},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "panels": list(panels),
    }


async def _query(project_id: str, sql: str) -> Dict[str, Any]:
    try:
        return dict(await dashboard_query.run_query(project_id, sql))
    except dashboard_query.QueryRefused as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc


# -------------------------------------------------------------------------------- operator routes


def _named_tables(tables: Optional[str]) -> Optional[List[str]]:
    """`?tables=runs,tasks` as a list; absent, every table."""
    return None if tables is None else tables.split(",")


@router.get("/query-reference")
async def operator_query_reference(
    tables: Optional[str] = None, project: Tuple[str, str] = Depends(get_project)
):
    return dashboard_query.query_reference(_named_tables(tables))


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
    return await _read_view(session, await _get(session, project[0], dashboard_id))


@router.post("/{dashboard_id}/undo")
async def operator_undo_dashboard(
    dashboard_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    return await undo_dashboard(session, project[0], dashboard_id, OPERATOR_AUTHOR)


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
    # Its kept earlier version goes with it (FR-9); the project sweep covers a project's delete.
    kept = await _kept(session, dashboard)
    if kept is not None:
        await session.delete(kept)
    await session.delete(dashboard)
    await session.commit()
    await sse_manager.broadcast(project[0], "dashboard_deleted", payload)


# ----------------------------------------------------------------------------------- agent routes


@agent_router.get("/query-reference")
async def agent_query_reference(
    tables: Optional[str] = None, actor: AgentActor = Depends(get_agent_actor)
):
    return dashboard_query.query_reference(_named_tables(tables))


@agent_router.post("/query")
async def agent_run_query(body: QueryIn, actor: AgentActor = Depends(get_agent_actor)):
    return await _query(actor.project_id, body.sql)


async def _refuse_after_unanswered_question(session: AsyncSession, actor: AgentActor) -> None:
    """Refuse a dashboard write from a run whose own question went without an answer (FR-2)."""
    open_question = await session.scalar(
        select(Question.id)
        .where(
            Question.project_id == actor.project_id,
            Question.created_by_run_id == actor.run_id,
            Question.answered.is_(False),
        )
        .limit(1)
    )
    if open_question is not None:
        raise _refuse(
            409,
            "question_unanswered",
            f"You asked the operator a question ({open_question}) this run and it has no answer "
            "(declined, expired or still open), so no dashboard is saved, edited or undone: "
            "guessing which dashboard was meant edits the wrong one. Nothing was changed. End "
            "your turn saying what you need to know; the operator's answer reaches a later run.",
            question_id=open_question,
        )


_DASHBOARD_ID_RE = re.compile(r"\bdash-[0-9a-f]{12}\b")

#: The event a write to a dashboard the request did not name leaves, so the same run cannot then
#: save a new dashboard in its place.
UNNAMED_EVENT = "dashboard_write_unnamed"


async def _request_of(session: AsyncSession, actor: AgentActor) -> str:
    """What this run was asked: every input delivered to it, and the operator's answers to the
    questions it asked (a blocking answer comes back inside the run, not as a delivery)."""
    delivered = (
        await session.execute(
            select(InboundQueueEntry.content).where(
                InboundQueueEntry.project_id == actor.project_id,
                InboundQueueEntry.delivered_in_run_id == actor.run_id,
            )
        )
    ).scalars()
    answers = (
        await session.execute(
            select(Question.answer, Question.answer_labels).where(
                Question.project_id == actor.project_id,
                Question.created_by_run_id == actor.run_id,
                Question.answered.is_(True),
            )
        )
    ).all()
    parts = list(delivered)
    for answer, labels in answers:
        parts.append(answer or "")
        parts.extend(str(label) for label in labels or [])
    return "\n".join(parts)


def named_dashboards(text: str, dashboards: Sequence[Tuple[str, str]]) -> List[str]:
    """The ids of the `(id, name)` dashboards *text* names: by id, or by the whole name as words,
    case aside. A name met only inside a longer name that is also met ("Weekly" inside "Weekly
    delivery") is not named by it."""
    ids = set(_DASHBOARD_ID_RE.findall(text))
    spans: Dict[str, List[Tuple[int, int]]] = {}
    for dash_id, name in dashboards:
        if not name.strip():
            continue
        pattern = re.compile(r"(?<!\w)" + re.escape(name.strip()) + r"(?!\w)", re.IGNORECASE)
        found = [m.span() for m in pattern.finditer(text)]
        if found:
            spans[dash_id] = found
    every = [(span, dash_id) for dash_id, found in spans.items() for span in found]

    def inside_a_longer(dash_id: str, start: int, end: int) -> bool:
        return any(
            other != dash_id and o_start <= start and end <= o_end and o_end - o_start > end - start
            for (o_start, o_end), other in every
        )

    for dash_id, found in spans.items():
        if any(not inside_a_longer(dash_id, start, end) for start, end in found):
            ids.add(dash_id)
    return [dash_id for dash_id, _ in dashboards if dash_id in ids]


async def _refuse_unless_named(session: AsyncSession, actor: AgentActor, dashboard_id: str) -> None:
    """Refuse a write to a dashboard this run's request did not name (FR-2). A guess between two
    dashboards, or at one the request never mentioned, cannot land however the agent decides."""
    target = await _get(session, actor.project_id, dashboard_id)
    rows = (
        await session.execute(
            select(Dashboard.id, Dashboard.name).where(Dashboard.project_id == actor.project_id)
        )
    ).all()
    names = {row[0]: row[1] for row in rows}
    named = named_dashboards(await _request_of(session, actor), list(names.items()))
    if target.id in named:
        return
    said = (
        "names " + ", ".join(f"{names[n]!r} ({n})" for n in named)
        if named
        else "names no dashboard by its id or its whole name"
    )
    await persist_accepted_event(
        actor.project_id,
        UNNAMED_EVENT,
        {"run_id": actor.run_id, "dashboard_id": target.id, "named": named},
        agent=actor.agent,
    )
    raise _refuse(
        409,
        "dashboard_not_named",
        f"The request this run was given {said}, and not {target.name!r} ({target.id}), so it "
        "is not changed: guessing which dashboard was meant edits the wrong one. Nothing was "
        "changed, and no new dashboard may be saved in its place. Ask the operator which "
        "dashboard they mean -- `ask_user` with the fitting dashboards' exact names as its "
        "options -- or end your turn saying which ones fit.",
        named=named,
    )


async def _refuse_create_after_unnamed(session: AsyncSession, actor: AgentActor) -> None:
    """A run refused a write to a dashboard its request did not name saves no new one instead,
    until a question it asked after is answered (FR-2: "creates nothing")."""
    refused_at = await session.scalar(
        select(EventLog.timestamp)
        .where(
            EventLog.project_id == actor.project_id,
            EventLog.event_type == UNNAMED_EVENT,
            EventLog.agent == actor.agent,
            EventLog.data["run_id"].as_string() == actor.run_id,
        )
        .order_by(EventLog.timestamp.desc())
        .limit(1)
    )
    if refused_at is None:
        return
    answered_since = await session.scalar(
        select(Question.id)
        .where(
            Question.project_id == actor.project_id,
            Question.created_by_run_id == actor.run_id,
            Question.answered.is_(True),
            Question.answered_at >= refused_at,
        )
        .limit(1)
    )
    if answered_since is None:
        raise _refuse(
            409,
            "dashboard_not_named",
            "This run was refused a change to a dashboard its request did not name, so it saves "
            "no new dashboard in its place. Nothing was created. Ask the operator which dashboard "
            "they mean, or end your turn saying which ones fit.",
            named=[],
        )


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
    """Save a new dashboard, or with `dashboard_id` replace that one whole (an edit, checked
    against `base_version` when given). The author, or the editor, is the run's agent."""
    await _refuse_after_unanswered_question(session, actor)
    if body.dashboard_id:
        await _refuse_unless_named(session, actor, body.dashboard_id)
    else:
        await _refuse_create_after_unnamed(session, actor)
    fields = DashboardIn(
        name=body.name,
        description=body.description,
        panels=body.panels,
        base_version=body.base_version,
    )
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
    return await _read_view(session, await _get(session, actor.project_id, dashboard_id))


@agent_router.patch("/{dashboard_id}")
async def agent_edit_dashboard(
    dashboard_id: str,
    body: EditIn,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Edit a dashboard in place by operations, against the version the agent read."""
    await _refuse_after_unanswered_question(session, actor)
    await _refuse_unless_named(session, actor, dashboard_id)
    return await edit_dashboard(session, actor.project_id, dashboard_id, body, actor.agent)


@agent_router.post("/{dashboard_id}/undo")
async def agent_undo_dashboard(
    dashboard_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    await _refuse_after_unanswered_question(session, actor)
    await _refuse_unless_named(session, actor, dashboard_id)
    return await undo_dashboard(session, actor.project_id, dashboard_id, actor.agent)


@agent_router.get("/{dashboard_id}/run")
async def agent_run_dashboard(
    dashboard_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await run_dashboard(session, actor.project_id, dashboard_id)
