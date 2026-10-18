"""SPIKE (throwaway, branch spike/2026-10-18-flow-stages): a flow's stage list.

`delivery.stages` on a change document, read per task. Absent: today's behaviour, untouched.
`[]`: dev only -- the flow lands the task itself once it is finished. A list of stages: each is a
review-shaped turn, in order, after the build; `approved` on any stage but the last advances the
task to the next stage instead of landing it.

`Task.stage_index` is the task's position (0 = the first stage after the build).
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SpecDocument, Task
from .project_workspace import ProjectWorkspaceError, resolve_project_workspace
from .spec_documents import parse_stored, read_document
from .spec_manifest import SpecPathError


async def stages_of(session: AsyncSession, task: Task) -> Optional[List[dict]]:
    """The task's document's declared stages, or None when it declares none (today's flow)."""
    if not task.spec_document_id:
        return None
    document = await session.get(SpecDocument, task.spec_document_id)
    if document is None:
        return None
    try:
        workspace = await resolve_project_workspace(session, task.project_id)
        payload = parse_stored(read_document(workspace, document.path))
    except (ProjectWorkspaceError, SpecPathError, OSError):
        return None
    delivery = payload.get("delivery") if isinstance(payload, dict) else None
    if not isinstance(delivery, dict) or delivery.get("mode") != "flow":
        return None
    stages = delivery.get("stages")
    if not isinstance(stages, list):
        return None
    return [s for s in stages if isinstance(s, dict) and s.get("key")]


async def current_stage(session: AsyncSession, task: Task) -> Optional[dict]:
    stages = await stages_of(session, task)
    if not stages:
        return None
    index = min(task.stage_index or 0, len(stages) - 1)
    return {**stages[index], "index": index, "count": len(stages)}
