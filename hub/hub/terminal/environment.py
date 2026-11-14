"""A shell gets the operator's environment, without what the Hub itself holds (FR-10).

The Hub's environment is the operator's plus the Hub's own configuration: its database location
(`DATABASE_URL`), its bootstrap API key and ticket secret (`AW_*`, `hub/hub/config.py`), and -- a Hub
started inside an agent's run -- that run's credential and identity (`AW_RUN_TOKEN`, ...,
`inherited_run_env.RUN_ENVIRONMENT_NAMES`). None of it may reach whatever runs in the shell, or an
agent reading the shell's output. A value is dropped by its name and, whatever its name, by
carrying one of the Hub's credential shapes, so a key the operator copied into a variable of their
own is not handed on either.

WSL passes Windows variables across only as `WSLENV` names them, so `WSLENV` is filtered by the
same rule: a name dropped here is dropped from it too.
"""

from __future__ import annotations

import os
from typing import Dict, Mapping, Optional

from ..inherited_run_env import RUN_ENVIRONMENT_NAMES

#: Names the Hub reads as its own configuration or a run's identity.
HUB_NAMES = frozenset({"DATABASE_URL", "HUB_URL", *RUN_ENVIRONMENT_NAMES})
#: Every name with one of these prefixes is the Hub's or the CLI's own.
HUB_PREFIXES = ("AW_", "AGENTWEAVE_")
#: The shapes of the Hub's credentials: operator keys, tickets and run credentials.
CREDENTIAL_SHAPES = ("aw_live_", "aw_ticket_", "aw_optick_", "aw_run_")


def is_hub_variable(name: str, value: str, extra_values: tuple = ()) -> bool:
    upper = name.upper()
    if upper in HUB_NAMES or upper.startswith(HUB_PREFIXES):
        return True
    if any(shape in value for shape in CREDENTIAL_SHAPES):
        return True
    return any(secret and secret in value for secret in extra_values)


def _hub_values() -> tuple:
    """The Hub's own secret values as it resolved them, wherever they came from (`.env` too)."""
    from ..config import settings

    values = [settings.aw_bootstrap_api_key, settings.aw_ticket_secret]
    database = getattr(settings, "database_url", "") or ""
    values.append(database)
    # The database file's own path, as a shell would print it.
    if ":///" in database:
        values.append(database.split(":///", 1)[1])
    return tuple(v for v in values if v and len(v) >= 8)


def clean_environment(
    environ: Optional[Mapping[str, str]] = None, *, extra_values: Optional[tuple] = None
) -> Dict[str, str]:
    """The operator's environment from *environ* (the Hub's own by default), less the Hub's."""
    source = os.environ if environ is None else environ
    secrets = _hub_values() if extra_values is None else extra_values
    kept = {k: v for k, v in source.items() if not is_hub_variable(k, v, secrets)}
    dropped = {k.upper() for k in source if k not in kept}
    for key in [k for k in kept if k.upper() == "WSLENV"]:
        entries = [e for e in kept[key].split(":") if e]
        remaining = [e for e in entries if e.split("/", 1)[0].upper() not in dropped]
        remaining = [
            e for e in remaining if not e.split("/", 1)[0].upper().startswith(HUB_PREFIXES)
        ]
        kept[key] = ":".join(remaining)
    return kept
