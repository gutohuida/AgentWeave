"""Copilot's one environment filter (`a-copilot-agent-runs-over-acp` D3; slice 1's `guard_env`).

Its own module so that `runner_adapters.copilot` can reach it: that package may not import
`hub.launchability` (`each-runner-cli-is-one-adapter` D1), where this used to live.
`launchability` re-exports every name for its existing importers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

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
