"""A turn whose workspace's runner configuration changed since its last launch waits for the
operator (F737).

The workspace judge refuses the writes to the runner's configuration it can read off a command's
text, and text cannot close that class (`git apply`, a checkout, an archive extraction, a copy into
the directory). This is the structural half: every launch fingerprints the workspace's runner
configuration (`runner_config.fingerprint`) and compares it with what that workspace held at its
last approved launch (`WorkspaceFingerprint`).

* **Unchanged**: the turn starts.
* **No record yet**: the baseline is recorded and the turn starts -- for the project directory
  always, and for any other checkout when every runner-config file in it is one the project
  directory already holds unchanged. A fresh checkout carrying a file the project directory does
  not (an agent's commit to `.claude/settings.json`, checked out for its reviewer) is asked about
  like a change.
* **Changed**: the turn is held -- not started, not destroyed, its input kept queued -- and the
  operator is asked on the permission surface, naming the files (a run-less `PermissionRequest`
  whose `tool_name` is `RUNNER_CONFIG_TOOL`). Allow records the new fingerprint and re-drains the
  queue; Deny keeps the turn held, and is asked again only when new operator input arrives or the
  files change again.

`hold_if_changed` only reads and stages: it runs inside `trigger_agent_directly`, whose session may
hold a refused dispatch's staging that the scheduler rolls back (F319). A hold therefore carries
its write -- opening the question -- as `TriggerAgentError.after_rollback`, which
`turn_scheduler` runs after that rollback. A recorded baseline is staged on the dispatch's own
session and lands with the `Run`'s commit, or not at all.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import runner_config
from .db.models import InboundQueueEntry, PermissionRequest, WorkspaceFingerprint
from .sse import sse_manager
from .utils import short_id

logger = logging.getLogger(__name__)

#: The `tool_name` of the operator's question. Not a tool any runner has, so no run's own
#: permission flow can collide with it.
RUNNER_CONFIG_TOOL = "RunnerConfiguration"


def workspace_key(directory: str) -> str:
    return os.path.normcase(os.path.realpath(directory))


def _changes_sentence(changes: Sequence[Dict[str, str]]) -> str:
    return ", ".join(f"{item['path']} ({item['change']})" for item in changes)


@dataclass
class RunnerConfigHold:
    """Why a launch was held, and the question its `after_rollback` opens."""

    detail: str
    open_question: Any  # Callable[[AsyncSession], Awaitable[None]]


def _held_detail(directory: str, changes: Sequence[Dict[str, str]], refused: bool) -> str:
    what = _changes_sentence(changes)
    if refused:
        return (
            f"Held: the runner configuration in {directory} changed since its last turn ({what}), "
            f"and the operator refused it. Restore those files, or send a new message to be asked "
            f"again."
        )
    return (
        f"Held: the runner configuration in {directory} changed since its last turn ({what}). An "
        f"allow rule, hook or MCP server there would apply to this turn unchecked, so it waits for "
        f"the operator's answer on the permission request."
    )


async def _requests_for(
    session: AsyncSession, project_id: str, key: str
) -> List[PermissionRequest]:
    rows = await session.execute(
        select(PermissionRequest)
        .where(
            PermissionRequest.project_id == project_id,
            PermissionRequest.tool_name == RUNNER_CONFIG_TOOL,
        )
        .order_by(PermissionRequest.created_at.desc())
        .execution_options(populate_existing=True)
    )
    return [row for row in rows.scalars() if (row.tool_input or {}).get("workspace_key") == key]


async def _newer_operator_input(
    session: AsyncSession, entry_ids: Optional[Sequence[str]], since: Optional[datetime]
) -> bool:
    if not entry_ids:
        return False
    if since is None:
        return True
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    rows = await session.execute(
        select(InboundQueueEntry.arrived_at).where(
            InboundQueueEntry.id.in_(list(entry_ids)),
            InboundQueueEntry.origin_type == "operator",
        )
    )
    for (arrived,) in rows:
        if arrived is not None and arrived.tzinfo is None:
            arrived = arrived.replace(tzinfo=timezone.utc)
        if arrived is not None and arrived > since:
            return True
    return False


def _stage_record(
    session: AsyncSession,
    row: Optional[WorkspaceFingerprint],
    *,
    project_id: str,
    key: str,
    directory: str,
    current: runner_config.Fingerprint,
    digest: str,
    by: str,
) -> None:
    now = datetime.now(timezone.utc)
    if row is None:
        session.add(
            WorkspaceFingerprint(
                project_id=project_id,
                workspace_key=key,
                workspace_dir=directory,
                fingerprint=current,
                digest=digest,
                recorded_by=by,
                recorded_at=now,
            )
        )
        return
    row.workspace_dir = directory
    row.fingerprint = current
    row.digest = digest
    row.recorded_by = by
    row.recorded_at = now


async def hold_if_changed(
    session: AsyncSession,
    *,
    project_id: str,
    agent: str,
    conversation_id: Optional[str],
    workspace_dir: str,
    project_root: str,
    queue_entry_ids: Optional[Sequence[str]] = None,
) -> Optional[RunnerConfigHold]:
    """None when the turn may start (any record it needs is staged on *session*), else the hold.

    Total over the filesystem: `runner_config.fingerprint` records an unreadable file rather than
    raising, so an unreadable configuration is a change, never a pass.
    """
    key = workspace_key(workspace_dir)
    current = await asyncio.to_thread(runner_config.fingerprint, workspace_dir)
    digest = runner_config.digest(current)
    row = await session.get(WorkspaceFingerprint, (project_id, key))
    if row is not None and row.digest == digest:
        return None

    if row is None:
        root_key = workspace_key(project_root)
        if key == root_key:
            reference: runner_config.Fingerprint = dict(current)
        else:
            root_row = await session.get(WorkspaceFingerprint, (project_id, root_key))
            reference = (
                dict(root_row.fingerprint or {})
                if root_row is not None
                else await asyncio.to_thread(runner_config.fingerprint, project_root)
            )
        brought = {path: value for path, value in current.items() if reference.get(path) != value}
        if not brought:
            _stage_record(
                session,
                None,
                project_id=project_id,
                key=key,
                directory=workspace_dir,
                current=current,
                digest=digest,
                by="baseline",
            )
            return None
        # Described against the project directory: what this checkout has that it does not.
        changes = [
            {"path": path, "change": "added" if path not in reference else "changed"}
            for path in sorted(brought)
        ]
    else:
        changes = [
            {"path": path, "change": change}
            for path, change in runner_config.changes(dict(row.fingerprint or {}), current)
        ]

    requests = await _requests_for(session, project_id, key)
    same = next((r for r in requests if (r.tool_input or {}).get("digest") == digest), None)
    if same is not None and same.status == "allowed":
        _stage_record(
            session,
            row,
            project_id=project_id,
            key=key,
            directory=workspace_dir,
            current=current,
            digest=digest,
            by="operator",
        )
        return None
    refused = same is not None and same.status == "denied"
    # Asked once per content. A refusal stands until the operator sends something new, which is
    # their way to reconsider; an expired question (the content moved on and back) is asked anew.
    ask = (
        same is None
        or same.status == "expired"
        or (refused and await _newer_operator_input(session, queue_entry_ids, same.decided_at))
    )

    async def open_question(db: AsyncSession) -> None:
        if not ask:
            return
        await _open_question(
            db,
            project_id=project_id,
            agent=agent,
            conversation_id=conversation_id,
            key=key,
            directory=workspace_dir,
            digest=digest,
            changes=changes,
        )

    return RunnerConfigHold(
        detail=_held_detail(workspace_dir, changes, refused and not ask),
        open_question=open_question,
    )


async def _open_question(
    db: AsyncSession,
    *,
    project_id: str,
    agent: str,
    conversation_id: Optional[str],
    key: str,
    directory: str,
    digest: str,
    changes: Sequence[Dict[str, str]],
) -> None:
    """Open the operator's question for this content, unless one is already open for it. A
    question still pending for content the workspace no longer holds is expired: its answer could
    only approve something that is not there."""
    requests = await _requests_for(db, project_id, key)
    if any(
        r.status == "pending" and (r.tool_input or {}).get("digest") == digest for r in requests
    ):
        return
    stale = [r.id for r in requests if r.status == "pending"]
    if stale:
        await db.execute(
            update(PermissionRequest)
            .where(PermissionRequest.id.in_(stale), PermissionRequest.status == "pending")
            .values(status="expired")
            .execution_options(synchronize_session=False)
        )
    what = _changes_sentence(changes)
    request_id = f"perm-{short_id()}"
    db.add(
        PermissionRequest(
            id=request_id,
            project_id=project_id,
            agent=agent,
            run_id=None,
            conversation_id=conversation_id,
            tool_name=RUNNER_CONFIG_TOOL,
            tool_use_id="",
            tool_input={
                "workspace": directory,
                "workspace_key": key,
                "digest": digest,
                "paths": [item["path"] for item in changes],
                "changes": list(changes),
                "reason": (
                    f"The runner configuration in {directory} changed since its last turn: {what}."
                ),
            },
            workspace_verdict={
                "allow": False,
                "reason": (
                    f"{what} changed since this workspace's last turn. An allow rule, hook or MCP "
                    f"server written there applies to the agent's next turn without being checked. "
                    f"Allow starts the held turn with these files as they are now; Deny keeps it "
                    f"held."
                ),
            },
            status="pending",
        )
    )
    await db.commit()
    await sse_manager.broadcast(
        project_id,
        "permission_requested",
        {"id": request_id, "agent": agent, "tool_name": RUNNER_CONFIG_TOOL, "run_id": None},
    )
