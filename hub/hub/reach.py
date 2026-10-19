"""What an agent may reach beyond its workspace: the operator's grants (reach-1019).

The workspace boundary is a guardrail against an agent's mistakes, not containment (reach-D1): the
judge reads what a call says, not what its process does. The operator widens it in two ways. Full
access (allow-all) is the posture `bypassPermissions`, settable as the project's default or per
agent (reach-D2). Grants are the middle setting (reach-D3): Workspace only plus extra roots, each
`read` or `readwrite`, and hosts. A project holds grants; an agent may hold its own, which replace
the project's whole (`None` inherits), so an override can narrow as well as widen.

This module validates grants where they are set and renders them for a run: `{temp}` and
`{project}` resolved, one JSON value in the run's `AW_REACH_GRANTS`, which `mcp_server._decide`
reads (that module is stdlib-only, so it restates the host pattern below; a test pins the two).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

#: The environment variable a run's judge reads its grants from.
REACH_GRANTS_ENV = "AW_REACH_GRANTS"

#: Root spellings the Hub resolves at trigger time rather than storing a machine's path.
TEMP_TOKEN = "{temp}"
PROJECT_TOKEN = "{project}"
ROOT_TOKENS = (TEMP_TOKEN, PROJECT_TOKEN)

#: `host`, `host:port`, `host:*`, `*.domain`, or a bracketed IPv6 host. Restated in
#: `mcp_server._GRANT_HOST_RE`.
GRANT_HOST_RE = re.compile(
    r"^(?P<wild>\*\.)?(?P<host>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*|\[[0-9A-Fa-f:.]+\])"
    r"(?::(?P<port>\*|[0-9]{1,5}))?$"
)

MAX_ROOTS = 32
MAX_HOSTS = 32


class ReachRoot(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    access: Literal["read", "readwrite"]

    model_config = {"extra": "forbid"}

    @field_validator("path")
    @classmethod
    def absolute_or_token(cls, value: str) -> str:
        value = value.strip()
        if value in ROOT_TOKENS:
            return value
        if not os.path.isabs(value):
            raise ValueError(
                f"a granted root is an absolute path, {TEMP_TOKEN} or {PROJECT_TOKEN}: {value!r}"
            )
        return value


class ReachGrants(BaseModel):
    roots: List[ReachRoot] = Field(default_factory=list, max_length=MAX_ROOTS)
    hosts: List[str] = Field(default_factory=list, max_length=MAX_HOSTS)

    model_config = {"extra": "forbid"}

    @field_validator("hosts")
    @classmethod
    def host_patterns(cls, value: List[str]) -> List[str]:
        cleaned = []
        for host in value:
            host = host.strip()
            if not GRANT_HOST_RE.match(host):
                raise ValueError(
                    f"a granted host is host, host:port, host:* or *.domain, not {host!r}"
                )
            cleaned.append(host)
        return cleaned


def validated_grants(value: Any) -> Optional[dict]:
    """`value` as stored grants, or `None`. Raises `ValueError` (pydantic's) when it is not."""
    if value is None:
        return None
    return ReachGrants.model_validate(value).model_dump()


def effective_grants(project_grants: Any, agent_grants: Any) -> Optional[dict]:
    """The agent's own grants when it has any (even empty: that narrows), else the project's."""
    return agent_grants if agent_grants is not None else project_grants


#: The posture id of Full access (allow-all); `model_catalog.FULL_ACCESS_PERMISSION_MODE`.
FULL_ACCESS = "bypassPermissions"
#: The postures whose calls the workspace judge decides, where grants apply.
JUDGED_POSTURES = (None, "workspace", "acceptEdits")


def describe_reach(posture: Optional[str], granted: Optional[str], *, spec_turn: bool) -> str:
    """The turn-context line saying what reaches outside the workspace, for the run's own posture
    and grants (`granted` is the run's `AW_REACH_GRANTS`). The agent must be told what the judge
    will decide: told "files outside it are refused" under Full access, a Copilot agent refused
    itself the work rather than try (drive 2026-10-19)."""
    if posture == FULL_ACCESS:
        line = (
            "- Your permission posture is Full access: a path outside this directory is not "
            "refused. Stay inside it unless the task needs otherwise; a write outside it is "
            "recorded on your run."
        )
        if spec_turn:
            line += " This is a specification turn, so you still write no file."
        return line
    base = "- Resolve every path against this directory. Files outside it are normally refused"
    if posture not in JUDGED_POSTURES or not granted:
        return base + "."
    try:
        data = json.loads(granted)
    except ValueError:
        return base + "."
    roots = data.get("roots") or []
    hosts = data.get("hosts") or []
    parts = []
    writable = [r["path"] for r in roots if r.get("access") == "readwrite"]
    readable = [r["path"] for r in roots if r.get("access") == "read"]
    if writable:
        parts.append(
            "these directories, to read and write: " + ", ".join(f"`{p}`" for p in writable)
        )
    if readable:
        parts.append(
            "these directories, to read with your file-reading tools only (not shell commands): "
            + ", ".join(f"`{p}`" for p in readable)
        )
    if hosts:
        parts.append("these hosts, in a shell command: " + ", ".join(f"`{h}`" for h in hosts))
    return base + ", except what the operator granted you: " + "; ".join(parts) + "."


def grants_env_value(grants: Any, *, project_root: str) -> Optional[str]:
    """The run's `AW_REACH_GRANTS`, with tokens resolved; `None` when nothing is granted.

    Stored grants that no longer validate grant nothing rather than failing the run."""
    try:
        parsed = ReachGrants.model_validate(grants) if grants is not None else None
    except ValueError:
        return None
    if parsed is None or not (parsed.roots or parsed.hosts):
        return None
    roots = []
    for root in parsed.roots:
        path = root.path
        if path == TEMP_TOKEN:
            path = tempfile.gettempdir()
        elif path == PROJECT_TOKEN:
            path = project_root
        roots.append({"path": str(path), "access": root.access})
    return json.dumps({"roots": roots, "hosts": list(parsed.hosts)})
