"""Feed a context-usage sample into the Hub the way the product does, now the route is gone.

`POST /agents/{name}/context-usage` was retired (F568): the Hub records usage itself through
`output_recording.record_context_usage`. The tests that used the route to seed readings call this
instead. It validates through `ContextUsageCreate` first, so a legacy-shaped body is still
normalised (and an invalid one still raises `ValidationError`), then records and commits.
"""

from __future__ import annotations

from typing import Any, Dict

from hub.db.engine import async_session_factory
from hub.output_recording import record_context_usage
from hub.schemas.agents import ContextUsageCreate


async def record_usage(agent: str, body: Dict[str, Any], project_id: str = "proj-test") -> str:
    """Returns `record_context_usage`'s verdict: "ok", "ignored" or "unchanged"."""
    payload = ContextUsageCreate.model_validate(body).model_dump(exclude_none=True)
    async with async_session_factory() as db:
        result = await record_context_usage(db, project_id, agent, payload)
        await db.commit()
    return result
