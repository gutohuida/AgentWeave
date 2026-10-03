"""Per-agent launchability probe — is the runner's CLI present, authorized, and runnable?

Deliberately reimplemented rather than imported from the CLI's
``agentweave.diagnostics.check_agent_readiness``: the Hub has no dependency on the
``agentweave-ai`` package (it must be probeable even when installed standalone), so this
mirrors that logic's CLI-presence and authorization checks against a small, independent
runner->CLI table instead of ``agentweave.constants.RUNNER_CONFIGS``.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# `copilot_env` holds Copilot's filter so its adapter can reach it (D1); re-exported here.
from .copilot_env import (  # noqa: F401
    COPILOT_MODEL_ENV_NAMES,
    COPILOT_PROVIDER_ENV_PREFIX,
    COPILOT_TOKEN_ENV_NAMES,
    COPILOT_TRUST_ENV_NAMES,
    copilot_env_removal_sentence,
    copilot_guard_env,
)
from .file_mentions import MENTION_NOTICE, neutralise_file_mentions
from .runner_adapters import get_adapter
from .runner_adapters.base import probe_binary
from .runner_provider import runner_probe_config

# DEAD (2026-09-20): 6 of these 8 keys name runner kinds no agent can be bound to any more.
# Why: a Runner's `cli` is validated against RUNNER_CLIS = ("claude", "codex", "copilot")
#   (db/models.py, schemas/runners.py:22) and RunnerUpdate has no `cli` field at all
#   (schemas/runners.py:27), so no runner row can hold another value; every spawn overwrites
#   config["runner"] from the bound Runner (api/v1/agent_trigger.py:677) before probing.
# Live equivalent: RUNNER_CLIS in hub/hub/db/models.py — the only registry that binds.
#   `copilot` has no row here: `probe_agent` asks `CopilotProbe` before this table is read
#   (`a-copilot-agent-runs-over-acp` D15, which deleted the row and its env-token branch).
# Removal: "native" still backs probe_agent's default at line 63 and "manual" still arrives
#   from legacy session.json, so neither is removable; kimi/opencode/codex_mcp/
#   claude_proxy have no writer but a hand-made POST /session/sync (session_sync.py:46) or
#   /agents/register payload (api/v1/agents.py:2209), plus hub/tests/test_launchability.py.
# Runner -> CLI binary name, for a runner string with no adapter (design D14: `probe_agent` asks
# `get_adapter` first and only falls here otherwise). Mirrors the "cli" field of RUNNER_CONFIGS in
# agentweave.constants (kept independent — see module docstring).
LEGACY_RUNNER_CLI: Dict[str, Optional[str]] = {
    "claude": "claude",
    "native": None,  # falls back to the agent name
    "claude_proxy": "claude",
    "kimi": "kimi",
    "opencode": "opencode",
    "codex": "codex",
    "codex_mcp": "codex",
    "manual": None,
}

#: Not a runner, and deliberately not a key of `LEGACY_RUNNER_CLI`: the value `get_agent_config`
#: reports for a roster agent that has **no** `Runner` bound at all. Distinct from `"native"`,
#: whose `LEGACY_RUNNER_CLI` entry is `None` and therefore falls back to the agent's own name —
#: which is exactly the masking this exists to end. Measured on the trial Hub 2026-08-21: an agent
#: with `runner_id IS NULL` was reported as `Runner CLI 'probe-norunner' was not found in PATH`,
#: sending the operator to look for a binary named after their own agent.
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
    # Copilot's adapter reads its verdict from Copilot itself (`a-copilot-agent-runs-over-acp`
    # D15): a cached, model-free ACP handshake that never spawns here and never raises.
    adapter = get_adapter(runner)
    if adapter is not None:
        return adapter.launchability(name, config)

    cli, present, missing_reason = probe_binary(LEGACY_RUNNER_CLI.get(runner), cli_override, name)

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

    # Claude must not silently inherit a proxy's ANTHROPIC_BASE_URL from whatever shell the Hub
    # itself happened to be started from — its own auth and endpoint selection are Claude Code's
    # to make, not the Hub's. `ClaudeAdapter.guard_env` strips only an *ambient* value (present in
    # the Hub's own os.environ but not explicitly set by this agent's own `env_vars`) — an agent
    # that explicitly configures its own ANTHROPIC_BASE_URL (e.g. a proxy provider) is deliberately
    # opting in, and that must survive. `CodexAdapter.guard_env` is the identity (design D10);
    # `CopilotAdapter.guard_env` is Copilot's one filter (`copilot_env.copilot_guard_env`), over
    # the inherited environment too. An unadapted runner (`claude_proxy`, `native`, `kimi`,
    # `opencode`, `codex_mcp`) gets no further guard.
    adapter = get_adapter(runner)
    if adapter is not None:
        proc_env = adapter.guard_env(proc_env, config)

    return proc_env


# ---------------------------------------------------------------------------
# Access path: tool-protocol (MCP) vs. plain HTTP requests
#
# Two questions, deliberately answered separately, because conflating them is what
# `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` §4 exists to end:
#
#   what the run is *given*   — does the Hub inject its canonical MCP server, and through that
#                               (see D9) the run's permission posture. Moved only by the
#                               operator's `hub_client`, never inferred (an inference would move
#                               containment as a side effect, which `agent-capability-plane`
#                               forbids). `resolve_access_path` used to answer this; every live
#                               runner was unconditionally injectable, so it reduced to `"cli" if
#                               override == "cli" else "mcp"`, which each caller now computes
#                               inline (`each-runner-cli-is-one-adapter` task 3.2, F474) pending
#                               `resolve_access_axes` taking it over in task 3.3.
#   `described_access_path` — what the run is *told*. Never asserts a tool-protocol surface
#                             the system has no grounds to believe the harness will honour.
#
# The probe that used to stand here is gone. `probe_mcp_registered` shelled `<cli> mcp list`
# in a *separate* process with no `--mcp-config`, so it could only ever see servers the
# operator had registered by hand — never the one the Hub injects on the turn's own command
# line. A `False` from it resolved the path to `cli`, which suppressed the injection it had
# just been asked about: the probe made its own answer true. It had no production caller from
# `d279d22` until it was deleted, and three test files were written believing it still ran
# (`design.md` D10). Do not restore it. The question is not "is a server registered" but
# "will this harness honour the server we are about to inject", and `mcp list` answers neither
# on a permitted machine nor on a policy-blocked one.
# ---------------------------------------------------------------------------


#: What a source may report about whether this run's harness started the Hub's tool server
#: (`a-run-reaches-the-hub-without-mcp`, design D1). Anything else -- a vendor's `pending`, a
#: Codex `cancelled` -- is not a report, and its caller does not pass it here.
HARNESS_MCP_STATUSES = ("connected", "failed", "absent")
_SOURCE_REPORTS = {
    "harness": frozenset(HARNESS_MCP_STATUSES),  # the harness's own recognised report
    "announce": frozenset({"connected"}),  # the adapter's `POST /mcp-adapter-online`
    "wait": frozenset({"absent"}),  # a runner that tests before its first prompt timed out
}


async def record_harness_mcp_status(
    db: AsyncSession, run_id: str, status: str, *, source: str
) -> None:
    """Record what one source says about this run's tool server, by D1's precedence.

    The result does not depend on the order the sources arrive in:

    1. the harness's own report decides, and a later one replaces an earlier one (Copilot's
       `mcp_server_status_changed` can move a server twice);
    2. otherwise the announce decides `connected`, over NULL and `absent`, never over `failed` --
       it is posted before the server answers `initialize`, so it proves the process started and
       no more, and a harness that then failed the connection has already produced it;
    3. otherwise the wait decides `absent`, over NULL only.

    One column suffices: `failed` only ever comes from a harness report. Does not commit; the
    announce route writes its stamp and this in one commit, and an executor's caller commits in a
    `try` that logs, because a failing record must never fail a run. A run that does not exist is
    left alone. An unrecognised status, or one its source never reports, raises `ValueError`.
    """
    allowed = _SOURCE_REPORTS.get(source)
    if allowed is None or status not in allowed:
        raise ValueError(f"{source!r} does not report harness MCP status {status!r}")
    from .db.models import Run

    run = await db.get(Run, run_id)
    if run is None:
        return
    current = run.harness_mcp_status
    if source == "harness":
        run.harness_mcp_status = status
    elif source == "announce":
        if current in (None, "absent"):
            run.harness_mcp_status = status
    elif current is None:
        run.harness_mcp_status = status


async def latest_mcp_test(db: AsyncSession, project_id: str, agent: str) -> Optional[str]:
    """The `harness_mcp_status` of this agent's most recent *tested* run, or None.

    What the next run is told reads this (`described_access_path`), replacing "any run ever
    announced", which a policy arriving after the first success never revoked (F340). Untested runs
    (NULL) are skipped, so a run that was never given the server, or ended before any source
    reported, neither grants nor revokes grounds. Most recent by `started_at`, then `id`, so two
    runs started in one clock tick still give one answer. Per agent, for the reason
    `harness_has_honoured_mcp` gives below.
    """
    from .db.models import Run

    result = await db.execute(
        select(Run.harness_mcp_status)
        .where(
            Run.project_id == project_id,
            Run.agent == agent,
            Run.harness_mcp_status.is_not(None),
        )
        .order_by(Run.started_at.desc(), Run.id.desc())
        .limit(1)
    )
    return result.scalars().first()


def described_access_path(
    access_path: str,
    *,
    override: Optional[str] = None,
    latest: Optional[str] = None,
) -> str:
    """What the run is **told** it reaches the Hub with: `"mcp"` or `"shim"`, never anything else.

    `a-run-reaches-the-hub-without-mcp` D1. The MCP form is told only on grounds, and grounds are
    one of two things:

    * the operator said so (`hub_client: "mcp"`), a declaration about their own deployment;
    * the latest *tested* run of this agent found the harness `connected`
      (`latest_mcp_test`). Not "any run ever": a policy that arrives after the first success is
      seen by the next test, which the permanent grounds never noticed (F340). An unrecognised
      status is no grounds.

    Otherwise the run is told the call command (`aw-tool`), which every run has: it is the pinned
    server in call mode, on every run's `PATH` (D5), so telling it never asserts a surface the run
    lacks. A run given no server (`access_path != "mcp"`) is told the call command whatever else
    is true. A runner that tests its own run before the first prompt (Copilot, D9) decides from
    that test instead of from here.

    What the run is *given* is not decided here and does not move with this answer: nothing that
    decides containment reads it.
    """
    if access_path != "mcp":
        return "shim"
    if override == "mcp":
        return "mcp"
    return "mcp" if latest == "connected" else "shim"


def spec_turn_notice(
    phase: Optional[str],
    *,
    path: Optional[str] = None,
    is_unwritten: bool = False,
    kind: Optional[str] = None,
) -> Optional[str]:
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

    `path` and `is_unwritten` carry F51's fix: when exploration opens on a document that has never
    been written to, this is the copy that wins competing attention (per the paragraph above), so
    it needs the same "write here, do not create a second one" instruction the canonical context
    grew — naming the open path by name is what stopped the agent from calling
    `create_spec_document` and orphaning the operator's own document, live.

    `None` when no document is open, so an ordinary turn carries nothing.

    `kind`, when `"change-spec"` and `phase == "exploring"`, adds one line asking how the work
    will be built, before the unwritten-path line. `kind=None` adds nothing, keeping the output
    byte-identical to before this parameter existed.
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
        if kind == "change-spec":
            lines.append(
                "Ask how it will be built (a flow, recommended, or no flow) before it is ready "
                "to propose; record the answer as `delivery`, and include it in every later "
                "submission."
            )
        if path and is_unwritten:
            # F409 D9: the path is derived from the operator's document subject, and this notice
            # is composed into the turn prompt, so an at-sign in it would expand into a file
            # attachment. The D6 sentence follows only when the path changed.
            safe_path = neutralise_file_mentions(path)
            lines.append(
                f"This document (`{safe_path}`) is empty and is what you are interviewing for. "
                f"When you call `submit_spec_document`, pass `path='{safe_path}'` — do not call "
                "`create_spec_document`, one already exists for this turn."
            )
            if safe_path != path:
                lines.append(MENTION_NOTICE)
    else:
        lines.append(
            "Write the document only with `submit_spec_document`. Never author specification "
            "HTML yourself."
        )
    return "\n".join(lines)


def access_path_notice(
    access_path: str, tool_prefix: str = "", *, shell_may_lack_network: bool = False
) -> str:
    """What the agent is told, at turn start, about how it reaches the capability plane.

    Exactly two forms (`a-run-reaches-the-hub-without-mcp` D11): the MCP tools, or the call
    command. Any other value raises `ValueError`, so a caller still passing the retired `cli`
    fails loudly instead of rendering the HTTP form no run is told any more -- following that form
    puts the credential into a command the harness stores.

    Neither form names or interpolates a credential: the call command reads `AW_RUN_TOKEN` and
    `HUB_URL` from its own environment, and this text is prepended to the turn prompt, which is
    durable.

    `tool_prefix` names the MCP tools by the full callable name `agents.py:_tool_surface_lines`
    uses for a run whose harness's naming is known (F139); empty reproduces the bare names.
    `shell_may_lack_network` is the adapter's caveat that its shell may not reach the Hub (D10).
    """
    if access_path == "mcp":
        return (
            "[AgentWeave] Tool access: the `agentweave` MCP tools are available — call "
            f"{tool_prefix}send_message / {tool_prefix}create_task / {tool_prefix}update_task / "
            f"{tool_prefix}ask_user directly."
        )
    if access_path != "shim":
        raise ValueError(f"a run is told 'mcp' or 'shim', not {access_path!r}")
    notice = (
        "[AgentWeave] Tool access: reach AgentWeave with the `aw-tool` command, which is on your "
        "PATH and already authenticated for this run. Two steps, as two separate tool calls: "
        "write the tool's arguments as one JSON object to a `.json` file inside "
        "`.agentweave/calls/` in your workspace with your file-writing tool (not from the shell; "
        "if you must, use exactly `Set-Content -Path '.agentweave/calls/<file>.json' -Value "
        "'<json>' -Encoding utf8`, with any `'` in the JSON doubled, as a command of its own), "
        "then run the call "
        "on its own, exactly `aw-tool <tool> .agentweave/calls/<file>.json` from the workspace "
        "root — unquoted, with nothing chained before or after it, which needs no approval in any "
        "posture — for example `aw-tool create_task .agentweave/calls/1.json`. A tool with no "
        "required argument needs "
        "no file (`aw-tool list_tasks`), and `aw-tool --list` names every tool and its arguments. "
        "The result is one JSON object, the last line of the output. Inbound content is already "
        "included in this turn; no retrieval is needed."
    )
    if shell_may_lack_network:
        notice += (
            " Your shell's sandbox may not allow network access to the Hub. If `aw-tool` reports "
            "`unreachable`, say so in your reply rather than retrying."
        )
    return notice


def plane_surface_summary(
    status: str,
    told: Optional[str],
    *,
    declared_mcp: bool = False,
    quoted: Optional[str] = None,
) -> str:
    """The one status event a run gets when its harness did not start the Hub's server (D12).

    The wording follows what the run was **told** (R3): a run told `aw-tool` reached the Hub
    anyway; a run told the MCP tools, from an earlier `connected` or the operator's declaration,
    did not have them, and its next turn is told the call command -- unless the agent is declared
    `hub_client: "mcp"`, whose next turn follows the declaration (review fix 7). `quoted` is the
    runner's own sentence about the server (Copilot's `/mcp list`), shown verbatim.
    """
    if told == "mcp":
        summary = (
            f"The AgentWeave MCP server did not start for this run ({status}), although the run "
            "was told to use it."
        )
        if declared_mcp:
            summary += (
                ' This agent is declared to use MCP (`hub_client: "mcp"`), so its next turn is '
                "told the same; change the declaration to stop that."
            )
        else:
            summary += " Its next turn is told `aw-tool`."
        return summary
    summary = (
        f"The AgentWeave MCP server did not start for this run ({status}); the run was told to "
        "reach the Hub with `aw-tool`."
    )
    if quoted:
        summary += f" The runner reported: {quoted}"
    return summary


def auto_snapshot_notice() -> str:
    """One line telling a writing agent it does not have to commit its own work.

    F52 (`scripts/drive/FINDINGS.md`, 2026-08-26): a live drive found two Haiku/`claude` runs and
    one `codex` run each spend most of a turn fighting a refused `git add`/`git commit` — every
    phrasing tried, including a bare read-only `git --version` — and one gave up on the task
    entirely rather than call `record_evidence`, believing an unrecorded commit meant the work
    was lost. It was not: `worktrees.snapshot_worktree` commits whatever is dirty in the agent's
    worktree unconditionally at the end of *every* turn (`agent_trigger.py`'s finalize path,
    reached whether the run completes or fails), and `record_evidence`'s own `locator` argument
    is free text — "a path, a command, a run id" — never a commit sha the agent must produce
    itself. The agent spending its turn on git was solving a problem the Hub had already solved
    for it. This notice is the fix: said once, up front, before a blocked git command can start
    that spiral — not a workaround for the refusal itself, which stays open (root cause
    unconfirmed; isolated reproduction attempts across several plausible axes did not reproduce
    it, so whatever triggers it in production is narrower than "this posture always refuses
    git").
    """
    return (
        "[AgentWeave] You do not need to `git commit` your own changes. The Hub commits your "
        "worktree's uncommitted changes automatically at the end of this turn, whether or not "
        "any git command you run succeeds. If a git write command is refused, stop trying "
        "variations of it — that turn budget is better spent finishing the work. Call "
        "`record_evidence` when you are done; its `locator` can be a file path or a description "
        "of what you changed, not only a commit sha."
    )


def agent_config(
    session_data: Optional[Dict[str, Any]], agent: str, stored: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """An agent's configuration as its run reads it: the session's per-agent entry, with the
    session-wide `hub_client` filling it in, laid over the agent's own stored `Agent.config`.

    The order matters and is the spawn's: the session-wide `hub_client` is applied to the
    session's entry *before* that entry is laid over `stored`, so it beats a `hub_client` stored on
    the row. Pure, so the agents list can read the same answer `get_agent_config` gives the trigger
    (`the-permissions-pill-shows-the-posture-the-run-gets`, design D2).
    """
    session_data = session_data or {}
    meta = dict(((session_data.get("agents", {})) or {}).get(agent, {}))
    if "hub_client" not in meta and session_data.get("hub_client"):
        # Session-wide default (session.json's top-level `hub_client`), same fallback
        # order as the CLI's Session.get_agent_hub_client — a per-agent override wins.
        meta["hub_client"] = session_data["hub_client"]
    if stored:
        meta = {**stored, **meta}
    return meta


ISOLATION_CHANGE_UNDER_HELD_WORK = "isolation_change_under_held_work"


async def isolation_change_refusal(
    db: AsyncSession,
    project_id: str,
    agent: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Why changing where `agent` works is refused now, or None.

    `before` and `after` are the configuration its turns read (`agent_config`: the synced session
    entry laid over `Agent.config`), as stored and as about to be written. Only a change to
    `worktrees.is_writing_agent` is this rule's question, and it is refused while the agent holds
    work: a turn this Hub is executing, or a task assigned to it that has not reached a terminal
    status. Flipping under either strands work -- the next task-bound turn runs in a checkout the
    earlier ones did not, and nothing commits the difference (F242,
    `isolation-does-not-change-under-held-work`, design D1). Both directions count.
    """
    from . import run_liveness, worktrees
    from .db.models import Run, Task
    from .task_transition_service import TERMINAL_STATUSES

    if worktrees.is_writing_agent(before) == worktrees.is_writing_agent(after):
        return None
    live = run_liveness.live_run_ids()
    runs = []
    if live:
        runs = list(
            (
                await db.execute(
                    select(Run.id)
                    .where(Run.project_id == project_id, Run.agent == agent, Run.id.in_(live))
                    .order_by(Run.id)
                )
            ).scalars()
        )
    tasks = list(
        (
            await db.execute(
                select(Task.id)
                .where(
                    Task.project_id == project_id,
                    Task.assignee == agent,
                    Task.status.not_in(TERMINAL_STATUSES),
                )
                .order_by(Task.id)
            )
        ).scalars()
    )
    if not runs and not tasks:
        return None
    direction = "its own checkout" if worktrees.is_writing_agent(after) else "the shared checkout"
    held = []
    if runs:
        held.append(f"a turn that is running ({', '.join(runs)}); let it end")
    if tasks:
        held.append(f"unfinished tasks ({', '.join(tasks)}); finish, reassign or reject them")
    return {
        "code": ISOLATION_CHANGE_UNDER_HELD_WORK,
        "message": (
            f"{agent} cannot move to {direction} while it holds work, because the work would be "
            f"left where its next turn no longer looks: {'; and '.join(held)}."
        ),
        "held": {"runs": runs, "tasks": tasks},
    }


async def get_agent_config(project_id: str, agent: str, db: AsyncSession) -> Dict[str, Any]:
    """Return the merged runner config `probe_agent` expects for one agent.

    Merges three sources, in increasing priority: the agent's own `Agent.config` JSON, the
    session-synced `agents.<name>` entry (session.json, pushed by the CLI — has
    `runner`/`model`/`cli`/`env_vars`/`yolo` for CLI-configured agents), which outranks it
    (`agent_config`), and — since 2026-08-21 — **the bound `Runner` record**, which is the roster's
    own answer and outranks both.

    That third source used to be missing here and was pasted into two call sites instead
    (`api/v1/agents.py` and `api/v1/inbound_queue.py`, which carried byte-identical blocks
    loading the `Agent`, loading its `Runner`, and overwriting `runner`/`model`). Both patched
    the *bound* case only, so the **unbound** case — `runner_id IS NULL` — still fell through
    `LEGACY_RUNNER_CLI["native"] is None` to the agent-name fallback, and reported a missing CLI named
    after the agent. Doing it here fixes both surfaces at once and gives the unbound case a name
    of its own (`RUNNER_UNBOUND`) rather than a wrong one.

    No agent is exempt by how it came to exist. Self-registration, whose agents were once
    exempted here, was deleted (`agents-no-longer-register-themselves`, F136): the exemption
    told an unbound agent to install a binary named after itself.
    """
    from .db.models import Agent, ProjectSession, Runner

    result = await db.execute(select(ProjectSession).where(ProjectSession.project_id == project_id))
    row = result.scalars().first()
    session_data = row.data if row else {}

    agent_result = await db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = agent_result.scalars().first()
    meta = agent_config(session_data, agent, agent_row.config if agent_row else None)
    # A model provider is a runner's alone (slice 5 D7): one named in an agent's own config or in
    # session.json would turn its runs into provider runs no runner route ever checked.
    meta.pop("provider_config", None)

    if agent_row is not None:
        if agent_row.runner_id:
            # Keyed on `runner_id`, not on how the agent came to exist (F30): the probe must
            # describe what `trigger_agent_directly`, which reads `runner_id`, would launch.
            runner_row = await db.get(Runner, agent_row.runner_id)
            if runner_row is not None:
                # Overwrites rather than defers to session.json: the bound Runner is what
                # `agent_trigger` actually launches, so anything else here would describe an
                # agent nobody is going to start.
                meta.update(runner_probe_config(runner_row))
        elif "runner" not in meta:
            # Unbound means *nothing anywhere says how to launch this* — not merely "no Runner
            # row". A CLI-configured agent carries its runner in session.json and no `Runner` is
            # expected; `test_agent_with_no_bound_runner_has_no_collaboration_verdict` pins that
            # such an agent stays launchable, and `..._reports_configured_agents` pins that one
            # whose session.json says `manual` keeps the manual reason. Both would break under a
            # rule keyed on `runner_id` alone. No agent is exempt by origin (F136).
            meta["runner"] = RUNNER_UNBOUND

    return meta
