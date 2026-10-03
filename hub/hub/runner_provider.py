"""A Copilot runner's model provider (BYOK): what may be stored, and which model it may name.

`a-copilot-agent-uses-hooks-and-its-own-agents`, design D7. A runner's `provider_config` is
`{type, base_url, api_key_var}`: the provider's address and the *name* of a variable in the Hub's
environment that holds its key. The key itself is never submitted, stored or returned.

Every check here returns a sentence or None; the routes turn a sentence into a 400 with a string
`detail` (design D7, "Validation"). No sentence ever repeats a submitted value: the likeliest
mistake is a pasted key, and a refusal that echoes it would put it in a response body, a log line
and the browser's network history.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, Mapping, Optional
from urllib.parse import urlsplit

from .copilot_env import COPILOT_MODEL_ENV_NAMES, COPILOT_PROVIDER_ENV_PREFIX
from .model_catalog import CATALOG

PROVIDER_CLI = "copilot"
PROVIDER_TYPES = ("anthropic",)
DEFAULT_BASE_URL = "https://api.anthropic.com"
PROVIDER_FIELDS = ("type", "base_url", "api_key_var")

_VARIABLE_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
# Only a field name shaped like one is repeated back; anything else might be the key itself,
# pasted where a name was expected (`{"sk-ant-...": ...}`).
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# The Hub's own credentials. A provider runner sends `api_key_var`'s value to `base_url`, so naming
# one of these would ship it off the machine (review 2026-09-28, finding 15).
_HUB_CREDENTIAL_NAMES = frozenset(
    {"GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN", "DATABASE_URL"}
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def provider_model_ids() -> tuple[str, ...]:
    """The model ids a provider runner may name: the literal `claude` catalog's ids.

    The literal `CATALOG`, not the effective one, and ids only: a declared alias (`haiku`) is a
    Claude Code choice, not an Anthropic API model, and `ProviderDescriptor.model()` resolves
    aliases (design D7, R2).
    """
    return tuple(m.id for m in CATALOG["claude"].models)


def is_provider_model(model: Optional[str]) -> bool:
    return model is not None and model in provider_model_ids()


def provider_model_problem(model: Optional[str]) -> Optional[str]:
    if is_provider_model(model):
        return None
    ids = ", ".join(provider_model_ids())
    if model is None:
        return (
            "A runner with a model provider needs a model: the provider is sent it as is. "
            f"Choose one of the Claude API model ids: {ids}."
        )
    return (
        "A runner with a model provider sends its model to the provider's API as is, so it must "
        f"be a Claude API model id, not an alias or another CLI's model. Choose one of: {ids}."
    )


def _is_model_flag(flag: Any) -> bool:
    return isinstance(flag, str) and (flag == "--model" or flag.startswith("--model="))


def provider_flags_problem(flags: Optional[Iterable[Any]]) -> Optional[str]:
    """A provider runner's `flags` may not carry `--model` (review 2026-09-28, finding 11): they
    are appended after the runner's own `--model`, so one there would reach the API unchecked."""
    if flags and any(_is_model_flag(flag) for flag in flags):
        return (
            "A runner with a model provider cannot set --model in its flags: its model is the "
            "runner's model field, which is checked against the Claude API model ids."
        )
    return None


def provider_override_problem(overrides: Optional[Mapping[str, Any]]) -> Optional[str]:
    """A run on a provider runner may not choose its model (design D7): the provider is sent the
    runner's model, and a per-run one comes from the `copilot` catalog, which the provider's API
    does not know. Other controls are Copilot's either way and validate as on any runner."""
    if overrides and "model" in overrides:
        return (
            "This agent's runner sends its model to a model provider, so every run uses the "
            "runner's own model and a run cannot choose another. Change the runner's model instead."
        )
    return None


def _base_url_problem(base_url: str) -> Optional[str]:
    refusal = (
        "base_url must be an https address, or an http address on this machine (localhost, "
        "127.0.0.1 or [::1]), with no user name or password in it: the provider is sent the key."
    )
    try:
        parts = urlsplit(base_url)
        hostname = parts.hostname
    except ValueError:
        return refusal
    if not hostname or parts.username is not None or parts.password is not None:
        return refusal
    if parts.scheme == "https":
        return None
    if parts.scheme == "http" and hostname in _LOCAL_HOSTS:
        return None
    return refusal


def provider_config_problem(cli: str, raw: Any) -> Optional[str]:
    """Why a submitted `provider_config` cannot be stored, or None.

    Checked by the route rather than by Pydantic (design D7, review finding 15): a schema check
    answers 422 with the offending input repeated in `detail[].input`.
    """
    if cli != PROVIDER_CLI:
        return (
            f"Only a {PROVIDER_CLI} runner can name a model provider; a {cli} runner runs on its "
            "own CLI's sign-in."
        )
    if not isinstance(raw, Mapping):
        return (
            "provider_config must be an object with type, base_url and api_key_var. Put the key "
            "itself in the Hub's environment and name that variable in api_key_var."
        )
    for field in raw:
        if field not in PROVIDER_FIELDS:
            named = (
                f"field '{field}'"
                if isinstance(field, str) and _FIELD_NAME_RE.match(field)
                else "a field"
            )
            return (
                f"provider_config has an unknown {named}; it takes only type, base_url and "
                "api_key_var. Put the key itself in the Hub's environment and name that variable "
                "in api_key_var."
            )
    for field in PROVIDER_FIELDS:
        if field in raw and not isinstance(raw[field], str):
            return f"provider_config's {field} must be a string."
    if raw.get("type") not in PROVIDER_TYPES:
        return (
            "provider_config's type must be 'anthropic', the only provider offered (OpenAI and "
            "Azure are not offered yet)."
        )
    api_key_var = raw.get("api_key_var")
    if not api_key_var or not _VARIABLE_NAME_RE.match(api_key_var):
        return (
            "api_key_var must be the name of an environment variable (capital letters, digits and "
            "underscores, such as MY_ANTHROPIC_KEY), not the key itself. Put the key in the Hub's "
            "environment and name that variable here."
        )
    if api_key_var in _HUB_CREDENTIAL_NAMES or api_key_var.startswith("AW_"):
        return (
            f"api_key_var names one of the Hub's own credentials ({api_key_var}), and a runner "
            "with a model provider sends that variable's value to its base_url. Name a variable "
            "that holds the provider's API key."
        )
    base_url = raw.get("base_url")
    if base_url is not None:
        return _base_url_problem(base_url)
    return None


def normalised_provider_config(raw: Mapping[str, Any]) -> dict:
    """The stored form of a `provider_config` that passed `provider_config_problem`."""
    return {
        "type": raw["type"],
        "base_url": raw.get("base_url") or DEFAULT_BASE_URL,
        "api_key_var": raw["api_key_var"],
    }


def stored_provider_config(value: Any) -> Optional[dict]:
    """A stored `runners.provider_config`, read defensively: a complete, valid value or None.

    One bad row must never raise in a reader (design D7, "A stored row is read defensively").
    """
    if not isinstance(value, Mapping):
        return None
    if provider_config_problem(PROVIDER_CLI, value) is not None:
        return None
    return normalised_provider_config(value)


def has_provider(value: Any) -> bool:
    """Whether a stored `provider_config` makes this a provider runner (judged on its model).

    Any non-null value counts, valid or not: a damaged row is still a runner its operator meant to
    send to a provider, and is reported unlaunchable rather than quietly run on the subscription.
    """
    return value is not None


def runner_probe_config(runner_row: Any) -> dict:
    """`{runner, model, provider_config}` from a bound `Runner` row: what `probe_agent`, the
    adapter's `launchability` and `resolve_agent_env` read (design D7). Every probe site builds its
    runner half here, so a provider runner is never judged on the subscription's verdict.

    The stored `provider_config` is carried as is; its readers judge it with `has_provider` and
    `stored_provider_config`, so a damaged one is reported, never raised on.
    """
    return {
        "runner": runner_row.cli,
        "model": runner_row.model,
        "provider_config": getattr(runner_row, "provider_config", None),
    }


def _provider_or_model_name(name: str) -> bool:
    upper = name.upper()
    return upper.startswith(COPILOT_PROVIDER_ENV_PREFIX) or upper in COPILOT_MODEL_ENV_NAMES


def copilot_provider_env(
    env: Mapping[str, str], provider_config: Any, model: Optional[str]
) -> Dict[str, str]:
    """A Copilot spawn's model-provider variables (design D7, review findings 3 and 10).

    Strips every `COPILOT_PROVIDER_*` name, `COPILOT_MODEL` and `COPILOT_OFFLINE` from `env` (the
    ambient environment already merged with the agent's `env_vars`), then, only for a valid
    provider, sets exactly `TYPE`, `BASE_URL`, `API_KEY` and `COPILOT_MODEL`. The prefix, not a
    list: a `BEARER_TOKEN`, `WIRE_MODEL`, `API_KEY_COMMAND` or `HEADERS` left in the Hub's shell
    would outrank or bypass the runner's checked settings.

    The key is read with `os.environ.get(..., "")`: this runs inside `guard_env`, which must not
    raise, and an empty key fails with the provider's 401 rather than falling back to the GitHub
    subscription. Launchability reports the missing variable before any spawn.
    """
    result = {key: value for key, value in env.items() if not _provider_or_model_name(key)}
    stored = stored_provider_config(provider_config)
    if stored is None:
        return result
    result["COPILOT_PROVIDER_TYPE"] = stored["type"]
    result["COPILOT_PROVIDER_BASE_URL"] = stored["base_url"]
    result["COPILOT_PROVIDER_API_KEY"] = os.environ.get(stored["api_key_var"], "")
    if model:
        result["COPILOT_MODEL"] = model
    return result


def provider_launch_verdict(probe: Mapping[str, Any], provider_config: Any) -> dict:
    """A provider runner's launchability (design D7): authorized iff the variable it names for the
    key is set in the Hub's environment. A GitHub login is not needed, so Copilot's own cached
    verdict supplies only whether the CLI is present, and its version.

    The reason names the variable, never its value, and does not mention GitHub.
    """
    present = bool(probe.get("present"))
    stored = stored_provider_config(provider_config)
    reason: Optional[str]
    if not present:
        authorized, reason = False, probe.get("reason")
    elif stored is None:
        authorized = False
        reason = (
            "This runner's model provider settings are incomplete or damaged, so it cannot run. "
            "Edit the runner and set its provider again, or remove it."
        )
    elif not os.environ.get(stored["api_key_var"]):
        authorized = False
        reason = (
            "This runner sends its runs to a model provider, and the variable it names for the "
            f"key, ${stored['api_key_var']}, is not set in the Hub's environment. Set it and "
            "restart the Hub."
        )
    else:
        authorized, reason = True, None
    result: Dict[str, Any] = {
        "runner": probe.get("runner", PROVIDER_CLI),
        "cli": probe.get("cli"),
        "present": present,
        "authorized": authorized,
        "runnable": present and authorized,
        "reason": reason,
    }
    if probe.get("version"):
        result["version"] = probe["version"]
    if not present and probe.get("probe_error"):
        result["probe_error"] = probe["probe_error"]
    return result
