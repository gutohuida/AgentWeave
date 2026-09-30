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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .file_mentions import MENTION_NOTICE, neutralise_file_mentions

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
    if runner == "copilot":
        # Read from Copilot itself (`a-copilot-agent-runs-over-acp` D15): a cached verdict from a
        # model-free ACP handshake, refreshed in the background. Never spawns here, never raises.
        from .copilot_probe import CopilotProbe

        return CopilotProbe.verdict(str(cli_override) if cli_override else None)

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


#: GitHub tokens Copilot reads. An ambient one silently overrides the operator's stored Copilot
#: login (appendix A §E), so a Copilot spawn carries one only when the agent's own `env_vars` name
#: it. The ambient-`ANTHROPIC_BASE_URL` rule below is the same idea for Claude.
COPILOT_TOKEN_ENV_NAMES: Tuple[str, ...] = ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN")

#: Variables that make Copilot approve on its own account or trust the folder (loading its hooks,
#: MCP servers and extensions). Removed from every Copilot spawn -- inherited or named in
#: `env_vars` -- whatever the posture: a per-agent variable must not be a hidden fifth posture
#: (review 2026-09-28, finding 3). Full access is the posture that lets Copilot approve.
COPILOT_TRUST_ENV_NAMES: Tuple[str, ...] = (
    "COPILOT_ALLOW_ALL",
    "COPILOT_ASSISTED_APPROVAL",
    "COPILOT_PLAN_THEN_AUTOPILOT",
    "GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS",
    "GITHUB_COPILOT_PROMPT_MODE_WORKSPACE_MCP",
    "GITHUB_COPILOT_PROMPT_MODE_EXTENSIONS",
)

#: A prefix, not a list: the 1.0.88 bundle reads 15 such names. With `COPILOT_MODEL` and
#: `COPILOT_OFFLINE`, removed from every spawn of a runner without a provider -- which, until
#: slice 5's BYOK, is every Copilot spawn. An ambient `COPILOT_PROVIDER_BASE_URL` would otherwise
#: silently turn a subscription run into a BYOK one.
COPILOT_PROVIDER_ENV_PREFIX = "COPILOT_PROVIDER_"
COPILOT_MODEL_ENV_NAMES: Tuple[str, ...] = ("COPILOT_MODEL", "COPILOT_OFFLINE")


def copilot_env_removal_sentence(name: str) -> str:
    """The `copilot.permission_override_removed` diagnostic's sentence for one removed name."""
    if name.upper().startswith(COPILOT_PROVIDER_ENV_PREFIX) or name.upper() in (
        COPILOT_MODEL_ENV_NAMES
    ):
        return (
            f"{name} was removed from this agent's environment; Copilot's model and provider "
            "come from its runner."
        )
    return (
        f"{name} was removed from this agent's environment; use the Full access posture to let "
        "Copilot approve on its own."
    )


def _copilot_always_stripped(name: str) -> bool:
    upper = name.upper()
    return (
        upper in COPILOT_TRUST_ENV_NAMES
        or upper in COPILOT_MODEL_ENV_NAMES
        or upper.startswith(COPILOT_PROVIDER_ENV_PREFIX)
    )


def copilot_guard_env(
    proc_env: Dict[str, str], env_vars: Dict[str, Any]
) -> Tuple[Dict[str, str], List[str]]:
    """The one Copilot environment filter (design D3; slice 1's `guard_env`). Every Copilot spawn
    -- the turn, the one-shot calls, the launchability probe -- goes through it.

    Removes the GitHub tokens unless `env_vars` name them, and the trust, provider and model
    variables unconditionally, from the inherited environment **and** from `env_vars`. Also drops
    `COPILOT_HOME`: the Hub sets it after this, so no entry can move the run out of the
    Hub-owned home. Returns the filtered environment and the `env_vars` names it removed, which
    the turn reports as `copilot.permission_override_removed` diagnostics.
    """
    named = {str(key).upper() for key in env_vars}
    removed: List[str] = []
    result: Dict[str, str] = {}
    for key, value in proc_env.items():
        upper = key.upper()
        if upper == "COPILOT_HOME":
            continue
        if upper in COPILOT_TOKEN_ENV_NAMES and upper not in named:
            continue
        if _copilot_always_stripped(key):
            if upper in named and key not in removed:
                removed.append(key)
            continue
        result[key] = value
    for key in env_vars:
        if _copilot_always_stripped(str(key)) and str(key) not in removed:
            removed.append(str(key))
    return result, removed


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

    if runner == "copilot":
        # Always a full environment: the strips below apply to the inherited one too.
        base = proc_env if proc_env is not None else dict(os.environ)
        proc_env, _removed = copilot_guard_env(base, env_vars)

    return proc_env


# ---------------------------------------------------------------------------
# Access path: tool-protocol (MCP) vs. plain HTTP requests
#
# Two questions, deliberately answered by two functions, because conflating them is what
# `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` §4 exists to end:
#
#   `resolve_access_path`   — what the run is *given*. Decides whether the Hub injects its
#                             canonical MCP server, and through that (see D9) the run's
#                             permission posture. Moved only by the operator.
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

# DEAD (2026-09-20): "claude_proxy"/"native" here, and the non-injectable branch at line 245.
# Why: resolve_access_path's only caller is api/v1/agent_trigger.py:1008, inside
#   trigger_agent_directly, whose `runner` is the bound Runner.cli (agent_trigger.py:677) —
#   validated against RUNNER_CLIS = ("claude", "codex", "copilot") (db/models.py). All three live
#   values are in this set (copilot since `a-copilot-agent-runs-over-acp` D1, without which no
#   Copilot run would be given the Hub's server), so the `not in` arm cannot be taken by any run.
# Live equivalent: none needed — every spawnable runner is MCP-injectable.
# Removal: hub/tests/test_launchability.py:421 asserts the branch using runner "kimi", which
#   no Runner row can hold; that test goes with it.
MCP_INJECTABLE_RUNNERS = {"claude", "claude_proxy", "native", "codex", "copilot"}


def resolve_access_path(runner: str, override: Optional[str] = None) -> str:
    """Choose the path the run is **given**: does the Hub inject its canonical MCP server?

    Unconditional for an injectable runner since `d279d22`, and still unconditional, because
    the Hub adds the server to the command line itself. The operator's `hub_client` is the
    only thing that moves it — and it must stay that way, because this value also decides the
    run's permission posture (`runner_commands.build_command` emits `--permission-prompt-tool`
    only when a server is injected, and falls back to `acceptEdits` when one is not). An
    *inference* that moved this would move containment as a side effect, which the
    `agent-capability-plane` requirement forbids; a *declaration* by the operator is theirs to
    make. What the run is told is `described_access_path`'s answer, not this one.
    """
    if override == "cli":
        return "cli"
    if runner not in MCP_INJECTABLE_RUNNERS:
        return "cli"
    return "mcp"


async def harness_has_honoured_mcp(db: AsyncSession, project_id: str, agent: str) -> bool:
    """Has this agent's harness ever actually started a server the Hub injected?

    The one measurement behind `described_access_path`'s grounds. True from the moment any run of
    this agent has an `mcp_adapter_online_at` — the adapter announcing itself before it serves.

    **Per agent, not per CLI, and that is narrower than the fact it stands for.** Whether a harness
    honours MCP is a property of the machine and the policy on it, so a second agent on the same
    proven `claude` installation starts from no grounds and reads the HTTP form on its first turn.
    A per-CLI grain would need a join through `Agent` to `Runner` for a value that self-corrects on
    the next spawn, and it would also make one agent's harness speak for another's — a per-agent
    runner override is ordinary. The narrow answer is the conservative one in the only direction
    that matters: it under-describes, never over-describes.

    Positive evidence only. There is no negative form to record: a harness that ignores the
    configuration is silent, and silence is exactly what "no grounds" means.
    """
    from .db.models import Run

    result = await db.execute(
        select(Run.id)
        .where(
            Run.project_id == project_id,
            Run.agent == agent,
            Run.mcp_adapter_online_at.is_not(None),
        )
        .limit(1)
    )
    return result.scalars().first() is not None


def described_access_path(
    access_path: str,
    *,
    override: Optional[str] = None,
    harness_honoured_mcp: bool = False,
) -> str:
    """Choose the path the run is **told** about — never one there are no grounds for.

    Grounds are one of two things, and an absence of both is not a tie-break in favour of
    asserting the surface:

    * the operator said so (`hub_client: "mcp"`). A declaration about their own deployment
      outranks anything the Hub can observe, and `resolve_access_path` already honours the
      other direction.
    * the harness has been *seen* honouring an injected server — the MCP adapter reported in
      from a previous run of this agent (`Run.mcp_adapter_online_at`). Providing a harness with
      a server is not the same as that harness offering it: a deployment may forbid
      tool-protocol servers by policy, take the `--mcp-config` and do nothing with it.

    A run given no server (`access_path == "cli"`) is never described as having one, whatever
    else is true.

    The first run against a fresh harness therefore reads the HTTP form while the server is in
    fact injected and its tools are in the model's tool list. That is deliberate and it is the
    safe direction of the two: under-describing a surface costs convenience for one turn, and
    the adapter announces itself at startup rather than waiting for a tool call, so a permitted
    harness earns its grounds on that first spawn rather than never.
    """
    if access_path != "mcp":
        return access_path
    if override == "mcp":
        return "mcp"
    return "mcp" if harness_honoured_mcp else "cli"


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


def access_path_notice(access_path: str, tool_prefix: str = "") -> str:
    """What the agent is told, at turn start, about how it reaches the capability plane.

    Two renderings of one fact, not a capability and a denial: the MCP branch names the tools,
    and the branch without MCP names the HTTP contract those tools adapt. Neither branch ever
    interpolates a credential — see the comment on the second branch.

    `tool_prefix` names the tools by the same full callable name
    `agents.py:_tool_surface_lines` uses for a Claude-family run whose access path is described as
    MCP — empty everywhere else, which reproduces the previous, unprefixed sentence exactly
    (`2026-09-29-a-claude-run-is-told-its-agentweave-tools-by-their-full-names`, F139).
    """
    if access_path == "mcp":
        return (
            "[AgentWeave] Tool access: the `agentweave` MCP tools are available — call "
            f"{tool_prefix}send_message / {tool_prefix}create_task / {tool_prefix}update_task / "
            f"{tool_prefix}ask_user directly."
        )
    # This branch names no CLI commands, and that part has not changed: it used to instruct
    # `agentweave msg send`, `task create`, `question ask` and `agent request`, and
    # `2026-08-03-single-runtime` reduced the CLI to five app-lifecycle commands, so every one of
    # those instructions was wrong. What was wrong was the conclusion drawn from it — that the
    # run therefore has no way to reach the plane. It has: the MCP tools are a thin adapter over
    # the HTTP contract, the run's credential and the Hub's own address are already in the
    # spawned process's environment (`agent_trigger.py`'s `AW_RUN_TOKEN` / `HUB_URL`), and this
    # branch is exactly the deployment the equal-capability requirement was written for.
    #
    # Variables are NAMED here and their values are NEVER interpolated. This text is prepended to
    # the turn prompt, which is the durable record of the turn, so a credential written into it is
    # a credential in stored turn text. The agent can read its own environment, so the name
    # discloses nothing it does not already hold; the value would be a leak. The difference is one
    # f-string, which is why the spec states it as a prohibition rather than a preference.
    return (
        "[AgentWeave] Tool access: the AgentWeave capability "
        "plane is reachable over HTTP, and this run is already authenticated for it. Its base "
        "address is the value of the `HUB_URL` environment variable, and its operations live "
        "under the route prefix `/api/v1/agent-actions`, so a request goes to "
        "`$HUB_URL/api/v1/agent-actions/...`. Authenticate every request with the run "
        "credential in the `AW_RUN_TOKEN` environment variable, presented as the header "
        "`Authorization: Bearer $AW_RUN_TOKEN`. Read both values from your own process "
        "environment; they are deliberately not written here. Inbound content is already "
        "included in this turn; no retrieval is needed."
    )


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


async def get_agent_config(project_id: str, agent: str, db: AsyncSession) -> Dict[str, Any]:
    """Return the merged runner config `probe_agent` expects for one agent.

    Merges three sources, in increasing priority: the session-synced `agents.<name>` entry
    (session.json, pushed by the CLI — has `runner`/`model`/`cli`/`env_vars`/`yolo` for
    CLI-configured agents), the agent's own `Agent.config` JSON, and — since 2026-08-21 —
    **the bound `Runner` record**, which is the roster's own answer and outranks both.

    That third source used to be missing here and was pasted into two call sites instead
    (`api/v1/agents.py` and `api/v1/inbound_queue.py`, which carried byte-identical blocks
    loading the `Agent`, loading its `Runner`, and overwriting `runner`/`model`). Both patched
    the *bound* case only, so the **unbound** case — `runner_id IS NULL` — still fell through
    `RUNNER_CLI["native"] is None` to the agent-name fallback, and reported a missing CLI named
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

    if agent_row is not None:
        if agent_row.runner_id:
            # Keyed on `runner_id`, not on how the agent came to exist (F30): the probe must
            # describe what `trigger_agent_directly`, which reads `runner_id`, would launch.
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
            # rule keyed on `runner_id` alone. No agent is exempt by origin (F136).
            meta["runner"] = RUNNER_UNBOUND

    return meta
