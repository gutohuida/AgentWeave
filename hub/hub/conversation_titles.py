"""Model-generated conversation titles — an opt-in upgrade, never the only source.

Truncation is the floor. A conversation is named the moment its first message lands
(`conversations.name_conversation`), so the rail never shows an identifier and everything here
failing changes nothing structural. That is what lets this whole module be best-effort.

**No `Run` row is recorded, deliberately.** `design.md` reasoned that a titling spawn should be
"a one-shot run bound to no conversation", `Run.conversation_id` being nullable. Recording one
would break the agent: `turn_scheduler.schedule_agent` and `trigger_agent_directly` both gate on
`Run.project_id == p, Run.agent == a, Run.status == "running"`, so a titling run under the
agent's name makes the agent look busy and stalls its queue until the title returns. The spawn is
not a turn — it produces no output rows, no timeline entry, and no context cost — so it is
recorded as an event instead.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import List, Optional

from sqlalchemy import select

from .conversations import title_from_message
from .db.engine import async_session_factory
from .db.models import Agent, AgentOutput, Conversation, InboundQueueEntry, Project, Runner
from .pty_runner import resolve_executable
from .utils import persist_event

logger = logging.getLogger(__name__)

# How long a title is worth waiting for. It runs after the agent's response has already landed,
# so nothing is blocked on it; running out just leaves the truncated title in place.
TITLE_TIMEOUT_SECONDS = 45

# Many conversations can start at once — a fan-out of delegations, a restored session. Without a
# bound, each one spawns a process. Two at a time keeps a burst from becoming a fork bomb while
# still clearing a backlog quickly.
MAX_CONCURRENT_TITLE_RUNS = 2
_gate = asyncio.Semaphore(MAX_CONCURRENT_TITLE_RUNS)

# How much of the exchange the titler sees. Enough to name the thread, bounded so a long first
# message cannot turn a title into an expensive call.
_EXCERPT_LIMIT = 1500

_PROMPT = (
    "Write a short title for the conversation below, naming what it is about.\n\n"
    "Rules: at most 8 words. No quotation marks, no trailing period, no preamble, no "
    "explanation. Reply with the title and nothing else.\n\n"
    "--- conversation ---\n{excerpt}\n--- end ---"
)

# Runners whose CLI can answer a one-shot text prompt. Anything else is a no-op rather than a
# guessed invocation — the same line `runner_commands.build_command` holds.
_SUPPORTED_CLIS = ("claude", "codex")


def build_title_command(*, cli: str, model: Optional[str], prompt: str) -> Optional[List[str]]:
    """The one-shot invocation, or None when this CLI has no supported one.

    Deliberately not `runner_commands.build_command`: that builds an *agent turn* — streaming
    JSON, an MCP server, a permission posture, a context file. None of it applies to a process
    that reads one prompt and prints one line.
    """
    if cli == "claude":
        cmd = [cli]
        if model:
            cmd += ["--model", model]
        return cmd + ["-p", prompt]
    if cli == "codex":
        cmd = [cli, "exec", "--skip-git-repo-check"]
        if model:
            cmd += ["--model", model]
        return cmd + [prompt]
    return None


def title_from_output(output: str) -> str:
    """Pull a usable title out of whatever the CLI printed.

    Takes the last non-empty line, not the first: Codex prints progress and configuration
    ahead of its answer, while Claude prints only the answer. Quotes and a trailing period are
    stripped because models add them despite being asked not to.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    candidate = lines[-1].strip().strip("\"'").rstrip(".").strip()
    return title_from_message(candidate)


def _run_titler(cmd: List[str], cwd: Optional[str]) -> str:
    """Blocking spawn. Returns "" on any failure — this never raises into the caller."""
    try:
        completed = subprocess.run(  # noqa: S603 — argv list, no shell
            resolve_executable(cmd),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TITLE_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("conversation titling spawn failed: %s", exc)
        return ""
    if completed.returncode != 0:
        logger.debug("conversation titling exited %s", completed.returncode)
        return ""
    return completed.stdout or ""


async def _excerpt(db, conversation: Conversation) -> str:
    """The opening message and the agent's first reply, as the titler sees them."""
    first_message = (
        await db.execute(
            select(InboundQueueEntry.content)
            .where(InboundQueueEntry.conversation_id == conversation.id)
            .order_by(InboundQueueEntry.arrived_at, InboundQueueEntry.id)
            .limit(1)
        )
    ).scalar_one_or_none() or ""

    first_reply = (
        await db.execute(
            select(AgentOutput.content)
            .where(
                AgentOutput.conversation_id == conversation.id,
                AgentOutput.kind == "text",
            )
            .order_by(AgentOutput.sequence, AgentOutput.id)
            .limit(1)
        )
    ).scalar_one_or_none() or ""

    parts = []
    if first_message:
        parts.append(f"Operator: {first_message[:_EXCERPT_LIMIT]}")
    if first_reply:
        parts.append(f"Agent: {first_reply[:_EXCERPT_LIMIT]}")
    return "\n\n".join(parts)


async def _resolve_runner(db, project: Project, agent_name: str) -> Optional[Runner]:
    """The runner that does the titling: the project's choice, else the agent's own."""
    if project.conversation_title_runner_id:
        runner = await db.get(Runner, project.conversation_title_runner_id)
        if runner is not None and runner.project_id == project.id:
            return runner
    agent = (
        await db.execute(
            select(Agent).where(Agent.project_id == project.id, Agent.name == agent_name)
        )
    ).scalars().first()
    if agent is not None and agent.runner_id:
        return await db.get(Runner, agent.runner_id)
    return None


async def generate_conversation_title(
    *, project_id: str, conversation_id: str, cwd: Optional[str] = None
) -> Optional[str]:
    """Upgrade a conversation's truncated title to a generated one, if the project asked for it.

    Every exit before the spawn is a silent no-op: off by default, an operator's title is never
    replaced, and an unsupported or unbound runner is not a reason to guess an invocation.
    Returns the stored title, or None when nothing was written.
    """
    async with async_session_factory() as db:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None or conversation.project_id != project_id:
            return None
        if conversation.title_set_by_operator:
            return None

        project = await db.get(Project, project_id)
        if project is None or project.conversation_title_mode != "generate":
            return None

        runner = await _resolve_runner(db, project, conversation.agent)
        if runner is None or runner.cli not in _SUPPORTED_CLIS:
            return None

        excerpt = await _excerpt(db, conversation)
        if not excerpt.strip():
            return None
        agent_name = conversation.agent

    cmd = build_title_command(
        cli=runner.cli, model=runner.model, prompt=_PROMPT.format(excerpt=excerpt)
    )
    if cmd is None:
        return None

    async with _gate:
        output = await asyncio.to_thread(_run_titler, cmd, cwd)

    title = title_from_output(output)
    if not title:
        return None

    async with async_session_factory() as db:
        conversation = await db.get(Conversation, conversation_id)
        # Re-read rather than reuse: the operator may have renamed it while the model thought.
        if conversation is None or conversation.title_set_by_operator:
            return None
        conversation.title = title
        await db.commit()
        await persist_event(
            db,
            project_id,
            "conversation_titled",
            {"conversation_id": conversation_id, "agent": agent_name, "title": title},
            agent=agent_name,
        )
    return title


async def maybe_generate_title(
    *, project_id: str, conversation_id: Optional[str], cwd: Optional[str] = None
) -> None:
    """Fire-and-forget wrapper for the run-completion path. Never raises, never delays a turn."""
    if not conversation_id:
        return
    try:
        await generate_conversation_title(
            project_id=project_id, conversation_id=conversation_id, cwd=cwd
        )
    except Exception:  # noqa: BLE001 — a title is never worth failing a completed run over
        logger.debug("conversation titling failed", exc_info=True)
