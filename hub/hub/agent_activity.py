"""When each agent was last actually doing something.

`last_seen` used to mean one thing only: the timestamp of the agent's most recent `AgentHeartbeat`
row. Heartbeats are posted by `POST /agents/{name}/heartbeat`, which only a *self-registered* agent
calls — and since the watchdog was deleted the Hub spawns every agent itself and posts none. So the
field was permanently NULL for every agent the product manages, and the rail read "No activity yet"
beside an agent that had just finished nine runs (2026-08-23 stress-test drive, finding F17).

The evidence was always on disk — a run stamps `started_at`, a turn writes `agent_outputs` rows —
it was simply never joined to the roster. This module does that join, in bulk, for a whole page of
agents at once, so a rail with five projects on it does not turn into a query per agent.

`last_seen` therefore now means **"the last time this agent did anything the Hub can see"**, which
is what every surface rendering it already claimed it meant. A heartbeat still counts: a
self-registered agent that only ever heartbeats reads exactly as it did before.

Deliberately *not* used for liveness. `heartbeat_is_stale` and `effective_heartbeat_status` still
read the heartbeat row alone, because "is this agent healthy right now" is a different question
from "when did it last do something", and a two-hour-old run is evidence of the second and not of
the first.
"""

from datetime import datetime, timezone
from typing import Dict, Iterable, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import AgentHeartbeat, AgentOutput, Run


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """Relabel a naive timestamp as UTC.

    `UTCDateTime` already does this for a loaded column, but an aggregate is not always routed
    through the type decorator on every dialect, and comparing an aware value with a naive one
    raises rather than returning a wrong answer. Cheap insurance at the one place the two could
    meet.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _keep_later(into: Dict[str, datetime], agent: Optional[str], value: Optional[datetime]) -> None:
    stamped = _aware(value)
    if not agent or stamped is None:
        return
    current = into.get(agent)
    if current is None or stamped > current:
        into[agent] = stamped


async def latest_activity_by_agent(
    session: AsyncSession,
    project_id: str,
    agent_names: Iterable[str],
    *,
    heartbeats: Optional[Mapping[str, AgentHeartbeat]] = None,
) -> Dict[str, datetime]:
    """The most recent moment each named agent was observed working, keyed by agent name.

    Agents with nothing recorded are absent from the mapping rather than present with `None`, so a
    caller can keep writing `activity.get(name)` and get the same NULL it used to get from a
    missing heartbeat.

    `heartbeats` is the latest-heartbeat map the caller has already fetched — both call sites build
    one for `effective_heartbeat_status` — and passing it avoids a third query for rows already in
    memory. Omit it and this fetches its own.

    Three sources, all maxima:

    * `runs` — `started_at` is the only one of the three guaranteed non-NULL, and it is what makes
      a spawned run count from the moment it begins rather than only once it has produced output.
      `ended_at` and `last_heartbeat_at` extend that to the end of the run.
    * `agent_outputs` — a long turn that streams for an hour keeps reading as recent while it runs.
    * `agent_heartbeats` — unchanged, for the self-registered agents that post them.
    """
    names = [name for name in agent_names if name]
    if not names:
        return {}
    wanted = set(names)

    latest: Dict[str, datetime] = {}

    run_rows = await session.execute(
        select(
            Run.agent,
            func.max(Run.started_at),
            func.max(Run.ended_at),
            func.max(Run.last_heartbeat_at),
        )
        .where(Run.project_id == project_id, Run.agent.in_(names))
        .group_by(Run.agent)
    )
    for agent, started_at, ended_at, beat_at in run_rows:
        _keep_later(latest, agent, started_at)
        _keep_later(latest, agent, ended_at)
        _keep_later(latest, agent, beat_at)

    output_rows = await session.execute(
        select(AgentOutput.agent, func.max(AgentOutput.timestamp))
        .where(AgentOutput.project_id == project_id, AgentOutput.agent.in_(names))
        .group_by(AgentOutput.agent)
    )
    for agent, observed_at in output_rows:
        _keep_later(latest, agent, observed_at)

    if heartbeats is None:
        heartbeat_rows = await session.execute(
            select(AgentHeartbeat.agent, func.max(AgentHeartbeat.timestamp))
            .where(AgentHeartbeat.project_id == project_id, AgentHeartbeat.agent.in_(names))
            .group_by(AgentHeartbeat.agent)
        )
        for agent, observed_at in heartbeat_rows:
            _keep_later(latest, agent, observed_at)
    else:
        # The caller's map is whatever it fetched, which may name agents outside this page —
        # `projects.py` builds one for the whole project. Filtered rather than trusted, so the
        # result never gains a key the caller did not ask about.
        for agent, heartbeat in heartbeats.items():
            if heartbeat is not None and agent in wanted:
                _keep_later(latest, agent, heartbeat.timestamp)

    return latest
