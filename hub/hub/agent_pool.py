"""A profile's pool of runners (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`).

A pool is the list of entries a profile may run on, each a project runner plus an optional
reasoning effort, exactly one of them the default whenever the pool is not empty (FR-1).
`Agent.runner_id` stays and always names the default entry's runner (FR-4), so every reader that
predates pools — the launch path, launchability, dashboards — keeps reading the default.

Every write of a pool, and every write of `Agent.runner_id` by a door that binds a runner, goes
through this module: `replace_pool` for the agents API's `pool` field, `bind_default` for the
legacy binding (`runner_id`, or `provider` and `model`) and for the doors that create an agent.
Keeping both writes here is what keeps the two agreeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Agent, AgentPoolEntry, Runner
from .model_catalog import get_provider
from .utils import short_id

#: What a pool entry in a request may carry. `runner_id`, `effort` and `default` are read; the rest
#: are the read shape's own fields (`hub/ui/src/api/agentPool.ts`), accepted so a caller may send
#: back the entries it read, and ignored, because the runner is what decides them.
_ENTRY_FIELDS = frozenset({"id", "runner_id", "runner_name", "cli", "model", "effort", "default"})

_CLI_LABEL = {"claude": "Claude Code", "codex": "Codex", "copilot": "Copilot"}

EntryKey = Tuple[str, Optional[str]]


@dataclass
class PoolRefusalError(Exception):
    """A pool edit refused, with the sentence that says why. Nothing has been written."""

    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


def _key(entry: AgentPoolEntry) -> EntryKey:
    return (entry.runner_id, entry.effort)


def model_label(runner: Runner) -> str:
    """The runner's model as the catalog names it ("Opus 5.5"), for refusals."""
    provider = get_provider(runner.cli)
    if not runner.model:
        return f"{_CLI_LABEL.get(runner.cli, runner.cli)}'s default model"
    declared = provider.model(runner.model) if provider is not None else None
    return declared.label if declared is not None else runner.model


def entry_label(runner: Optional[Runner], effort: Optional[str]) -> str:
    """ "Opus 5.5 · high", or the runner id when the runner is gone."""
    base = model_label(runner) if runner is not None else "a deleted runner"
    return f"{base} · {effort}" if effort else base


def offered_efforts(cli: str) -> List[str]:
    """The effort values the catalog declares for *cli*; empty when it declares none."""
    provider = get_provider(cli)
    control = provider.control("effort") if provider is not None else None
    return [value.id for value in control.values] if control is not None else []


def effort_refusal(runner: Runner, effort: Optional[str]) -> Optional[str]:
    """Why *effort* cannot go with *runner* (FR-3), naming the effort and the model, or None."""
    if effort is None:
        return None
    offered = offered_efforts(runner.cli)
    if effort in offered:
        return None
    if not offered:
        return f"{model_label(runner)} does not offer the effort {effort!r}: it offers no effort."
    return (
        f"{model_label(runner)} does not offer the effort {effort!r}; it offers "
        f"{', '.join(offered)}."
    )


async def pool_rows(session: AsyncSession, agent_id: str) -> List[AgentPoolEntry]:
    """One agent's entries, in the operator's order."""
    result = await session.execute(
        select(AgentPoolEntry)
        .where(AgentPoolEntry.agent_id == agent_id)
        .order_by(AgentPoolEntry.position, AgentPoolEntry.created_at, AgentPoolEntry.id)
    )
    return list(result.scalars().all())


async def pools_by_agent(
    session: AsyncSession, project_id: str, agent_ids: Iterable[str]
) -> Dict[str, List[AgentPoolEntry]]:
    """Every listed agent's entries, in the operator's order, in one query."""
    ids = list(agent_ids)
    pools: Dict[str, List[AgentPoolEntry]] = {agent_id: [] for agent_id in ids}
    if not ids:
        return pools
    result = await session.execute(
        select(AgentPoolEntry)
        .where(AgentPoolEntry.project_id == project_id, AgentPoolEntry.agent_id.in_(ids))
        .order_by(AgentPoolEntry.position, AgentPoolEntry.created_at, AgentPoolEntry.id)
    )
    for entry in result.scalars().all():
        pools.setdefault(entry.agent_id, []).append(entry)
    return pools


def serialize_pool(
    entries: Sequence[AgentPoolEntry], runners_by_id: Dict[str, Runner]
) -> List[Dict[str, Any]]:
    """The entries as the agents API returns them (`AgentPoolEntry` in agentPool.ts).

    An entry whose runner is gone (a row older than the guard in `DELETE /runners`) is left out:
    there is nothing to say about what it runs, and nothing could start on it.
    """
    out: List[Dict[str, Any]] = []
    for entry in entries:
        runner = runners_by_id.get(entry.runner_id)
        if runner is None:
            continue
        out.append(
            {
                "id": entry.id,
                "runner_id": entry.runner_id,
                "runner_name": runner.name,
                "cli": runner.cli,
                "model": runner.model,
                "effort": entry.effort,
                "default": bool(entry.is_default),
            }
        )
    return out


async def pool_out(session: AsyncSession, agent: Agent) -> List[Dict[str, Any]]:
    """One agent's pool as the agents API returns it."""
    entries = await pool_rows(session, agent.id)
    runners: Dict[str, Runner] = {}
    for runner_id in {entry.runner_id for entry in entries}:
        runner = await session.get(Runner, runner_id)
        if runner is not None:
            runners[runner_id] = runner
    return serialize_pool(entries, runners)


async def bind_default(session: AsyncSession, agent: Agent, runner_id: Optional[str]) -> None:
    """Make *runner_id* the pool's default, adding it when it is not there (FR-4).

    The legacy binding — `runner_id`, or `provider` and `model`, on the agent update — and every
    door that creates an agent with a runner come here. A default already on that runner stays as
    it is, effort and all, so re-sending the bound runner changes nothing. Otherwise an entry on
    that runner with no effort is preferred, then any entry on it, then a new entry with no effort.
    `None` unbinds: the pool is emptied, as an agent with no runner has none.
    """
    entries = await pool_rows(session, agent.id) if agent.id else []
    if runner_id is None:
        for entry in entries:
            await session.delete(entry)
        agent.runner_id = None
        return
    current = next((entry for entry in entries if entry.is_default), None)
    if current is None or current.runner_id != runner_id:
        on_runner = [entry for entry in entries if entry.runner_id == runner_id]
        chosen = next((entry for entry in on_runner if entry.effort is None), None) or next(
            iter(on_runner), None
        )
        if chosen is None:
            chosen = AgentPoolEntry(
                id=f"pool-{short_id()}",
                project_id=agent.project_id,
                agent_id=agent.id,
                runner_id=runner_id,
                effort=None,
                is_default=True,
                position=max((entry.position for entry in entries), default=-1) + 1,
            )
            session.add(chosen)
        for entry in entries:
            entry.is_default = entry is chosen
        chosen.is_default = True
    agent.runner_id = runner_id


def _parsed_entries(raw: object) -> List[Tuple[str, Optional[str], bool]]:
    if not isinstance(raw, list):
        raise PoolRefusalError("pool must be a list of entries")
    parsed: List[Tuple[str, Optional[str], bool]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise PoolRefusalError(f"pool[{index}] must be an object")
        unknown = sorted(set(item) - _ENTRY_FIELDS)
        if unknown:
            raise PoolRefusalError(
                f"pool[{index}]: unknown field(s) {', '.join(unknown)}. "
                f"Valid: {', '.join(sorted(_ENTRY_FIELDS))}"
            )
        runner_id = item.get("runner_id")
        if not isinstance(runner_id, str) or not runner_id:
            raise PoolRefusalError(f"pool[{index}] needs a runner_id")
        effort = item.get("effort")
        if effort == "":
            effort = None
        if effort is not None and not isinstance(effort, str):
            raise PoolRefusalError(f"pool[{index}]: effort must be a string or null")
        is_default = item.get("default", False)
        if not isinstance(is_default, bool):
            raise PoolRefusalError(f"pool[{index}]: default must be true or false")
        parsed.append((runner_id, effort, is_default))
    return parsed


async def replace_pool(session: AsyncSession, agent: Agent, raw: object) -> None:
    """Replace the agent's pool with *raw*, the agents API's `pool` (FR-3).

    The whole list is the new pool: an entry left out is removed, one not there is added, and
    `default` names the default. Refused, with nothing written, when an entry names a runner the
    project does not have, an effort its runner's CLI and model do not offer, the same runner and
    effort twice, or more than one default; and when the default is removed from a pool that keeps
    other entries without another being named default. A pool that names no default keeps the
    current one when it is still listed, and a first pool of one entry makes that entry the default.
    An empty list empties the pool, which unbinds the agent's runner.
    """
    parsed = _parsed_entries(raw)
    existing = await pool_rows(session, agent.id)
    runners: Dict[str, Runner] = {}
    for runner_id, _, _ in parsed:
        if runner_id in runners:
            continue
        runner = await session.get(Runner, runner_id)
        if runner is None or runner.project_id != agent.project_id:
            raise PoolRefusalError(f"Runner '{runner_id}' not found", status_code=404)
        runners[runner_id] = runner
    for runner_id, effort, _ in parsed:
        refusal = effort_refusal(runners[runner_id], effort)
        if refusal is not None:
            raise PoolRefusalError(refusal)

    seen: set[EntryKey] = set()
    for runner_id, effort, _ in parsed:
        if (runner_id, effort) in seen:
            raise PoolRefusalError(
                f"{entry_label(runners[runner_id], effort)} on {runners[runner_id].name} is "
                "listed twice; a pool holds each runner and effort once."
            )
        seen.add((runner_id, effort))

    named = [(runner_id, effort) for runner_id, effort, is_default in parsed if is_default]
    if len(named) > 1:
        raise PoolRefusalError(
            "A pool has exactly one default; "
            + " and ".join(entry_label(runners[r], e) for r, e in named)
            + " are both marked default."
        )
    current = next((entry for entry in existing if entry.is_default), None)
    default_key: Optional[EntryKey] = named[0] if named else None
    if default_key is None and parsed:
        if current is not None and _key(current) in seen:
            default_key = _key(current)
        elif current is not None:
            current_runner = runners.get(current.runner_id) or await session.get(
                Runner, current.runner_id
            )
            raise PoolRefusalError(
                f"Removing the default, {entry_label(current_runner, current.effort)}, needs "
                "another entry named default in the same change."
            )
        elif len(parsed) == 1:
            default_key = (parsed[0][0], parsed[0][1])
        else:
            raise PoolRefusalError("Name one entry as the default.")

    by_key = {_key(entry): entry for entry in existing}
    for entry in existing:
        if _key(entry) not in seen:
            await session.delete(entry)
    for position, (runner_id, effort, _) in enumerate(parsed):
        row = by_key.get((runner_id, effort))
        if row is None:
            row = AgentPoolEntry(
                id=f"pool-{short_id()}",
                project_id=agent.project_id,
                agent_id=agent.id,
                runner_id=runner_id,
                effort=effort,
            )
            session.add(row)
        row.position = position
        row.is_default = (runner_id, effort) == default_key
    agent.runner_id = default_key[0] if default_key is not None else None


async def remove_runner_from_pools(session: AsyncSession, project_id: str, runner_id: str) -> None:
    """Drop a runner being deleted from every pool that holds it, keeping each pool's invariant.

    `DELETE /runners` refuses a runner an open agent's pool holds, so only archived agents reach
    here. A pool that loses its default makes its first remaining entry the default, and the
    agent's `runner_id` follows; one left empty unbinds, as an archived agent's runner did before.
    """
    held = (
        (
            await session.execute(
                select(AgentPoolEntry.agent_id).where(
                    AgentPoolEntry.project_id == project_id,
                    AgentPoolEntry.runner_id == runner_id,
                )
            )
        )
        .scalars()
        .all()
    )
    await session.execute(
        delete(AgentPoolEntry).where(
            AgentPoolEntry.project_id == project_id, AgentPoolEntry.runner_id == runner_id
        )
    )
    for agent_id in set(held):
        agent = await session.get(Agent, agent_id)
        if agent is None:
            continue
        remaining = await pool_rows(session, agent_id)
        if remaining and not any(entry.is_default for entry in remaining):
            remaining[0].is_default = True
        default = next((entry for entry in remaining if entry.is_default), None)
        agent.runner_id = default.runner_id if default is not None else None


async def delete_pool(session: AsyncSession, agent_id: str) -> None:
    """Delete an agent's pool, for the one door that deletes an agent row (session sync)."""
    await session.execute(delete(AgentPoolEntry).where(AgentPoolEntry.agent_id == agent_id))
