"""Per-agent launchability probe — is the runner's CLI present, authorized, and runnable?

Deliberately reimplemented rather than imported from the CLI's
``agentweave.diagnostics.check_agent_readiness``: the Hub has no dependency on the
``agentweave-ai`` package (it must be probeable even when installed standalone), so this
mirrors that logic's CLI-presence and authorization checks against a small, independent
runner->CLI table instead of ``agentweave.constants.RUNNER_CONFIGS``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .subprocess_windows import no_console_kwargs

# Runner -> CLI binary name. Mirrors the "cli" field of RUNNER_CONFIGS in
# agentweave.constants (kept independent — see module docstring).
RUNNER_CLI: Dict[str, Optional[str]] = {
    "claude": "claude",
    "native": None,  # falls back to the agent name
    "claude_proxy": "claude",
    "kimi": "kimi",
    "opencode": "opencode",
    "codex": "codex",
    "codex_mcp": "codex",
    "manual": None,
    "copilot": "copilot",
}

#: Not a runner, and deliberately not a key of `RUNNER_CLI`: the value `get_agent_config` reports
#: for a roster agent that has **no** `Runner` bound at all. Distinct from `"native"`, whose
#: `RUNNER_CLI` entry is `None` and therefore falls back to the agent's own name — which is exactly
#: the masking this exists to end. Measured on the trial Hub 2026-08-21: an agent with
#: `runner_id IS NULL` was reported as `Runner CLI 'probe-norunner' was not found in PATH`, sending
#: the operator to look for a binary named after their own agent.
RUNNER_UNBOUND = "unbound"


def probe_agent(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a launchability verdict for one agent.

    ``config`` is the agent's merged runner configuration — the session.json
    ``agents.<name>`` entry overlaid with any self-registered ``Agent.config`` — the same
    shape the CLI's ``session.get_runner_config()`` returns.

    Returns a dict with ``runner``, ``cli``, ``present`` (binary found), ``authorized``
    (known auth requirements satisfied), ``runnable`` (both, and not blocked by manual
    mode), and ``reason`` (stated cause when not runnable, else ``None``).
    """
    runner = config.get("runner", "native")

    if runner == "manual":
        return {
            "runner": runner,
            "cli": None,
            "present": False,
            "authorized": True,
            "runnable": False,
            "reason": "Runner is set to manual — no CLI to launch automatically.",
        }

    if runner == RUNNER_UNBOUND:
        # Same shape as `manual` above, for the same reason: there is no CLI to look for, so
        # every question below this point is the wrong question. Says what is actually wrong and
        # what fixes it, because the alternative — falling through to the `name` fallback — names
        # a binary that was never supposed to exist.
        return {
            "runner": runner,
            "cli": None,
            "present": False,
            "authorized": True,
            "runnable": False,
            "reason": "No runner is bound to this agent. Bind one in the Hub UI before it can run.",
        }

    cli_override = config.get("cli")
    cli = str(cli_override) if cli_override else (RUNNER_CLI.get(runner) or name)

    if cli_override:
        present = os.path.isfile(cli_override) and os.access(cli_override, os.X_OK)
        missing_reason = f"Pinned runner CLI {cli_override!r} is not an executable file."
    else:
        present = shutil.which(cli) is not None
        missing_reason = f"Runner CLI {cli!r} was not found in PATH."

    authorized = True
    auth_reason: Optional[str] = None
    if runner == "claude_proxy":
        env_vars = config.get("env_vars") or {}
        api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
        base_url = env_vars.get("ANTHROPIC_BASE_URL")
        if not base_url or not api_key_var:
            authorized = False
            auth_reason = "Proxy runner is missing ANTHROPIC_BASE_URL or ANTHROPIC_API_KEY_VAR."
        elif not os.environ.get(api_key_var):
            authorized = False
            auth_reason = (
                f"Required proxy API key variable ${api_key_var} is not set "
                "in the Hub's environment."
            )
    elif runner == "copilot":
        has_token = bool(
            os.environ.get("COPILOT_GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
        )
        if not has_token:
            authorized = False
            auth_reason = (
                "No GitHub auth token found (COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN)."
            )

    if not present:
        reason = missing_reason
    elif not authorized:
        reason = auth_reason
    else:
        reason = None

    return {
        "runner": runner,
        "cli": cli,
        "present": present,
        "authorized": authorized,
        "runnable": present and authorized,
        "reason": reason,
    }


def resolve_agent_env(runner: str, config: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Build the subprocess environment for spawning *runner*, resolving provider
    credentials from the Hub's own process environment (task 3.11).

    The Hub resolves `env_vars` indirection (`ANTHROPIC_API_KEY_VAR` names an env var
    to read, plain values are passed through, and a value equal to its own key name is
    treated as another env-var-name placeholder) itself, at spawn time.

    Returns `None` when no override is needed at all (`PtySession.spawn` then inherits
    the Hub process's own environment unchanged); otherwise a full environment dict —
    the Hub's own `os.environ`, merged with the agent's resolved `env_vars`.
    """
    env_vars = config.get("env_vars") or {}
    proc_env: Optional[Dict[str, str]] = None
    if env_vars:
        proc_env = dict(os.environ)
        proc_env.update(env_vars)
        api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR")
        if api_key_var:
            resolved = os.environ.get(api_key_var, "")
            if resolved:
                proc_env["ANTHROPIC_API_KEY"] = resolved
            else:
                # Key var declared but not set in the Hub's own environment — clear any
                # inherited key so the failure is an explicit 401, not a silent wrong key.
                proc_env.pop("ANTHROPIC_API_KEY", None)
        for var_name, value in env_vars.items():
            if var_name in ("ANTHROPIC_API_KEY_VAR", "ANTHROPIC_BASE_URL"):
                continue
            if value == var_name:
                resolved = os.environ.get(var_name)
                if resolved:
                    proc_env[var_name] = resolved
                else:
                    proc_env.pop(var_name, None)

    # Claude must not silently inherit a proxy's ANTHROPIC_BASE_URL from whatever shell
    # the Hub itself happened to be started from — its own auth and endpoint selection
    # are Claude Code's to make, not the Hub's. This must strip only an *ambient* value
    # (present in the Hub's own os.environ but not explicitly set by this agent's own
    # env_vars) — an agent that explicitly configures its own ANTHROPIC_BASE_URL (e.g. a
    # proxy provider) is deliberately opting in, and that must survive regardless of
    # which runner-agent-charter-separation Runner record this agent is bound to (Runner
    # only distinguishes `claude` vs `codex`, not the old claude/claude_proxy/native
    # runner-type taxonomy this guard predates).
    if runner == "claude" and "ANTHROPIC_BASE_URL" not in env_vars:
        base = proc_env if proc_env is not None else os.environ
        if base.get("ANTHROPIC_BASE_URL"):
            proc_env = dict(base)
            proc_env.pop("ANTHROPIC_BASE_URL", None)

    return proc_env


# ---------------------------------------------------------------------------
# Access path: tool-protocol (MCP) vs. plain CLI commands
#
# Independent mirror of agentweave.tool_surface's probing logic (same reason this whole
# module is independent of agentweave.constants.RUNNER_CONFIGS — see module docstring).
# Native runtime spawns agents on the Hub host itself, so probing "<cli> mcp list" here
# checks the same CLI installation the Hub is about to launch.
# ---------------------------------------------------------------------------

PROBEABLE_RUNNERS = {"claude", "claude_proxy", "native", "codex"}
MCP_INJECTABLE_RUNNERS = PROBEABLE_RUNNERS

_PROBE_TTL_SECONDS = 300.0
_probe_cache: Dict[str, Tuple[bool, float]] = {}


def probe_mcp_registered(cli: str) -> bool:
    """Best-effort check: is the ``agentweave`` MCP server actually registered for
    *cli* on the Hub host, as opposed to merely theoretically supported?
    """
    now = time.monotonic()
    cached = _probe_cache.get(cli)
    if cached is not None and now - cached[1] < _PROBE_TTL_SECONDS:
        return cached[0]

    if not cli or shutil.which(cli) is None:
        _probe_cache[cli] = (False, now)
        return False

    try:
        result = subprocess.run(
            [cli, "mcp", "list"],
            capture_output=True,
            text=True,
            shell=(os.name == "nt"),
            timeout=10,
            **no_console_kwargs(),
        )
        available = result.returncode == 0 and "agentweave" in (result.stdout or "").lower()
    except Exception:
        available = False

    _probe_cache[cli] = (available, now)
    return available


def resolve_access_path(runner: str, cli: str, override: Optional[str] = None) -> str:
    """Choose the per-run path now that the Hub injects its canonical server."""
    del cli
    if override == "cli":
        return "cli"
    if runner not in MCP_INJECTABLE_RUNNERS:
        return "cli"
    return "mcp"


def spec_turn_notice(phase: Optional[str]) -> Optional[str]:
    """One short block, carried in the **turn prompt**, for a turn with a document open.

    The same instructions are already in the canonical context, and three live runs established
    that being there is not enough. A skill whose description matches the operator's sentence is
    weighed against that sentence; standing context is weighed once, generally, and loses. The
    countermeasure has to arrive in the same channel as the thing it is competing with — beside the
    operator's message, not in a system preamble read before the message existed.

    Observed, all with the context correctly delivered and read: an agent announced *"I'll use the
    OpenSpec exploration workflow"*, ran a questionnaire the floor had just told it not to run, and
    when its questions went unanswered proceeded on invented assumptions rather than stopping. This
    is deliberately blunt and short, because it is competing for attention rather than explaining.

    `None` when no document is open, so an ordinary turn carries nothing.
    """
    if not phase:
        return None
    lines = [
        "[AgentWeave] SPECIFICATION TURN — this overrides any other specification workflow you "
        "know, including one installed on this machine. Do not use it, do not adopt its layout, "
        "and do not create its files. Mention it to the operator if you find one.",
        # F4 (`openspec/changes/2026-08-17-authoring-rigor-and-scope`): mechanically true by the
        # time this notice is read, not aspirational — stated so a refused write is recognized
        # rather than discovered by trial and error.
        "You have no file-write tool this turn. If you notice something in the code that needs "
        "fixing, record it with `create_task` instead of trying to change it directly.",
    ]
    if phase == "exploring":
        lines += [
            "Interview in THIS REPLY, in prose: what you need to know, the plausible directions "
            "with what each makes easier and harder, what reading the code established, and a "
            "short sketch where it helps. Then stop and let the operator answer.",
            "Do not answer your own questions. If you asked and nothing came back, say what is "
            "still open and stop — a guessed requirement is built on before anyone notices it was "
            "a guess.",
            "Write the document only with `submit_spec_document`, and only once you have answers "
            "worth writing down. An incomplete draft is fine; an invented one is not.",
            "The document's name is a placeholder — a colour and an animal, meaning nothing. Call "
            "`rename_spec_document(path, subject)` as soon as this reply establishes what the "
            "document is about, and use the path it returns from then on.",
        ]
    else:
        lines.append(
            "Write the document only with `submit_spec_document`. Never author specification "
            "HTML yourself."
        )
    return "\n".join(lines)


def access_path_notice(access_path: str) -> str:
    """One line telling the agent which access path is in use this turn."""
    if access_path == "mcp":
        return (
            "[AgentWeave] Tool access: the `agentweave` MCP tools are available — call "
            "send_message / create_task / update_task / ask_user directly."
        )
    # No CLI equivalents are offered any more. This branch used to name `agentweave msg send`,
    # `task create`, `question ask` and `agent request`; `2026-08-03-single-runtime` reduced the
    # CLI to five app-lifecycle commands, so every one of those instructions was wrong. Saying so
    # plainly is better than sending an agent after commands that do not exist.
    return (
        "[AgentWeave] Tool access: no AgentWeave tool surface is available this turn, so you "
        "cannot send messages, create or update tasks, or ask the operator. Report what you "
        "would have sent as part of your reply instead. Inbound content is already included in "
        "this turn; no retrieval is needed."
    )


async def get_agent_config(project_id: str, agent: str, db: AsyncSession) -> Dict[str, Any]:
    """Return the merged runner config `probe_agent` expects for one agent.

    Merges three sources, in increasing priority: the session-synced `agents.<name>` entry
    (session.json, pushed by the CLI — has `runner`/`model`/`cli`/`env_vars`/`yolo` for
    CLI-configured agents), any self-registered `Agent.config` JSON, and — since 2026-08-21 —
    **the bound `Runner` record**, which is the roster's own answer and outranks both.

    That third source used to be missing here and was pasted into two call sites instead
    (`api/v1/agents.py` and `api/v1/inbound_queue.py`, which carried byte-identical blocks
    loading the `Agent`, loading its `Runner`, and overwriting `runner`/`model`). Both patched
    the *bound* case only, so the **unbound** case — `runner_id IS NULL` — still fell through
    `RUNNER_CLI["native"] is None` to the agent-name fallback, and reported a missing CLI named
    after the agent. Doing it here fixes both surfaces at once and gives the unbound case a name
    of its own (`RUNNER_UNBOUND`) rather than a wrong one.

    A **self-registered** agent is exempt: it manages its own execution and legitimately has no
    `Runner`, so calling it unbound would refuse something that works.
    """
    from .db.models import Agent, ProjectSession, Runner

    result = await db.execute(select(ProjectSession).where(ProjectSession.project_id == project_id))
    row = result.scalars().first()
    session_data = row.data if row else {}
    session_agents_meta = (session_data.get("agents", {})) or {}
    meta = dict(session_agents_meta.get(agent, {}))
    if "hub_client" not in meta and session_data.get("hub_client"):
        # Session-wide default (session.json's top-level `hub_client`), same fallback
        # order as the CLI's Session.get_agent_hub_client — a per-agent override wins.
        meta["hub_client"] = session_data["hub_client"]

    agent_result = await db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = agent_result.scalars().first()
    if agent_row and agent_row.config:
        meta = {**agent_row.config, **meta}

    if agent_row is not None and not agent_row.self_registered:
        if agent_row.runner_id:
            runner_row = await db.get(Runner, agent_row.runner_id)
            if runner_row is not None:
                # Overwrites rather than defers to session.json: the bound Runner is what
                # `agent_trigger` actually launches, so anything else here would describe an
                # agent nobody is going to start.
                meta["runner"] = runner_row.cli
                meta["model"] = runner_row.model
        elif "runner" not in meta:
            # Unbound means *nothing anywhere says how to launch this* — not merely "no Runner
            # row". A CLI-configured agent carries its runner in session.json and no `Runner` is
            # expected; `test_agent_with_no_bound_runner_has_no_collaboration_verdict` pins that
            # such an agent stays launchable, and `..._reports_configured_agents` pins that one
            # whose session.json says `manual` keeps the manual reason. Both would break under a
            # rule keyed on `runner_id` alone, and both are right: the Hub cannot *trigger* these
            # agents, which is a separate verdict (`collaboration_ready`) that already says so.
            meta["runner"] = RUNNER_UNBOUND

    return meta
