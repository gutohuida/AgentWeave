"""The Hub-owned `COPILOT_HOME` of a Copilot agent (`a-copilot-agent-runs-over-acp`, design D4).

Each Copilot agent runs with `COPILOT_HOME=~/.agentweave/hub/copilot-home/projects/<pid>/<agent>/`.
The Hub writes two files there (operator decisions `ghcp-d1`, `ghcp-d2`):

- `agents/<agent>.agent.md`, the custom agent file carrying the agent's **stable** context
  (identity, project instructions, charter) behind a precedence statement over the repository's
  own instruction files, with `tools`/`model`/`reasoningEffort` in its frontmatter;
- `agentweave-mcp.json`, the stdio entry for the Hub's own MCP server, named by
  `--additional-mcp-config`. It carries no secret: the server inherits `copilot.exe`'s
  environment, run token included (VERIFIED, design § VERIFIED).

**The home's configuration surface is the Hub's** (review 2026-09-28, finding 8). A hook answers
a permission before the Hub is asked, and settings can trust folders or grant permissions, so
anything that could write into this directory -- an agent under Full access, for one -- could
otherwise leave a file that decides every later Workspace-only turn. Before every spawn
`ensure_copilot_home` therefore sweeps what the Hub did not write: hooks it did not record, user
settings, the permission-shaped keys of `config.json`, MCP configs, plugins, and other agent files.
Copilot's own state (`session-state/`, `session-store.db`, `logs/`) is never touched.

The worker home (`copilot-home/worker/`) serves one-shot calls and the launchability probe. It is
a sibling of `projects/`, so no project id can name it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: `(agents.MAX_WAITING_SECONDS + 60) * 1000`. Copilot's MCP default of 30 s would cut every
#: `ask_user` short; the Hub's longest wait is 600 s. A constant rather than the agent's own
#: setting, so the file does not change when that setting does. `test_copilot_home.py` binds it to
#: `agents.MAX_WAITING_SECONDS`, which cannot be imported here without a cycle.
COPILOT_MCP_TIMEOUT_MS = 660_000

#: The name the Hub registers its MCP server under, and the only name D8 accepts as the Hub's own.
HUB_MCP_SERVER_NAME = "agentweave"

OWNED_RECORD = ".agentweave-owned.json"
MCP_CONFIG_NAME = "agentweave-mcp.json"

PRECEDENCE_STATEMENT = (
    "You are running under GitHub Copilot CLI for the AgentWeave Hub. This context comes from "
    "AgentWeave and takes precedence over repository instruction files (`CLAUDE.md`, `AGENTS.md`, "
    "`.github/copilot-instructions.md`, anything under `.claude/`) wherever they conflict. Where "
    'those files address "Claude" or "Claude Code", they were written for a different harness; '
    "follow their project facts, not their tool names or workflows."
)

#: `config.json` keys Copilot manages itself that can trust a folder or grant a permission.
_CONFIG_PERMISSION_KEYS = (
    "trustedFolders",
    "trusted_folders",
    "allowedUrls",
    "permissions",
    "defaultPermissionMode",
    "defaultMode",
)

_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def copilot_home_root() -> Path:
    """`~/.agentweave/hub/copilot-home`, read at call time so a patched home is honoured."""
    return Path.home() / ".agentweave" / "hub" / "copilot-home"


def copilot_worker_home() -> Path:
    """The home one-shot calls and the launchability probe run under."""
    return copilot_home_root() / "worker"


def _checked_component(value: str, what: str) -> str:
    # A project id is not always `proj-<hex>`: adoption takes whatever a folder's
    # `.agentweave/project.json` names (R2), so a hand-written marker could read `..\..\x`.
    if not isinstance(value, str) or not _COMPONENT_RE.fullmatch(value) or value in (".", ".."):
        raise ValueError(f"{what} {value!r} cannot name a Copilot home directory")
    return value


def copilot_home_path(project_id: str, agent: str) -> Path:
    """`…/copilot-home/projects/<project_id>/<agent>`. Raises `ValueError` for any component that
    is not a single `[A-Za-z0-9_.-]` path component, or a path that resolves outside the root."""
    root = copilot_home_root() / "projects"
    path = (
        root
        / _checked_component(project_id, "Project id")
        / _checked_component(agent, "Agent name")
    )
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents:
        raise ValueError(f"the Copilot home for {project_id!r}/{agent!r} resolves outside {root}")
    return path


def agent_marker(agent: str) -> str:
    """The agent file's `description`, which D6 reads back from the `agent` config option to
    prove the Hub's file, not a same-named repository agent, was selected."""
    return f"AgentWeave agent {agent} — context rendered by the AgentWeave Hub"


def _yaml_quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_agent_file(
    agent: str, stable_context: str, *, model: Optional[str], effort: Optional[str]
) -> str:
    lines = [
        "---",
        f"name: {_yaml_quoted(agent)}",
        f"description: {_yaml_quoted(agent_marker(agent))}",
        'tools: ["*"]',
    ]
    if model and model != "auto":
        lines.append(f"model: {_yaml_quoted(model)}")
    if effort:
        lines.append(f"reasoningEffort: {_yaml_quoted(effort)}")
    lines.append("---")
    body = [PRECEDENCE_STATEMENT]
    if stable_context and stable_context.strip():
        body.append(stable_context.strip())
    return "\n".join(lines) + "\n\n" + "\n\n".join(body) + "\n"


def render_mcp_config(mcp_command: Sequence[str]) -> str:
    """Exactly what Claude's `--mcp-config` holds, plus `tools` and the long `timeout`; no `env`."""
    server = {
        "type": "stdio",
        "command": str(mcp_command[0]),
        "args": [str(arg) for arg in mcp_command[1:]],
        "tools": ["*"],
        "timeout": COPILOT_MCP_TIMEOUT_MS,
    }
    return json.dumps({"mcpServers": {HUB_MCP_SERVER_NAME: server}}, indent=2) + "\n"


@dataclass(frozen=True)
class CopilotHome:
    path: Path
    #: What the sweep removed, as home-relative names (`config.json (trustedFolders)` for a key).
    removed: Tuple[str, ...] = ()

    @property
    def mcp_config(self) -> Path:
        return self.path / MCP_CONFIG_NAME


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_if_changed(path: Path, content: str) -> bool:
    data = content.encode("utf-8")
    try:
        if path.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return True


def _read_owned(home: Path) -> Dict[str, str]:
    try:
        data = json.loads((home / OWNED_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def record_owned_file(home: Path, relative: str, content: str) -> Path:
    """Write a file the Hub owns inside a home and record its hash, so the sweep keeps it.

    Slice 5 writes its hooks through this; this slice records only its own agent file."""
    target = home / relative
    _write_if_changed(target, content)
    owned = _read_owned(home)
    digest = _sha256(content.encode("utf-8"))
    if owned.get(relative) != digest:
        owned[relative] = digest
        _write_if_changed(home / OWNED_RECORD, json.dumps(owned, indent=2, sort_keys=True) + "\n")
    return target


def _is_owned(home: Path, path: Path, owned: Dict[str, str]) -> bool:
    relative = path.relative_to(home).as_posix()
    digest = owned.get(relative)
    if digest is None:
        return False
    try:
        return _sha256(path.read_bytes()) == digest
    except OSError:
        return False


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _sweep(home: Path, agent: str) -> List[str]:
    """Remove what can decide a permission and the Hub did not write. Returns what went."""
    owned = _read_owned(home)
    removed: List[str] = []

    def gone(path: Path) -> None:
        _remove(path)
        name = path.relative_to(home).as_posix()
        logger.warning("Removed %s from the Copilot home %s: the Hub did not write it", name, home)
        removed.append(name)

    hooks = home / "hooks"
    if hooks.is_dir():
        for path in sorted(hooks.rglob("*")):
            if path.is_file() and not _is_owned(home, path, owned):
                gone(path)

    for name in ("settings.json", "mcp-config.json", "installed-plugins"):
        path = home / name
        if path.exists() or path.is_symlink():
            gone(path)

    config = home / "config.json"
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            # JSONC or damaged: Copilot recreates it.
            gone(config)
        else:
            dropped = [key for key in _CONFIG_PERMISSION_KEYS if key in data]
            if dropped:
                for key in dropped:
                    data.pop(key)
                _write_if_changed(config, json.dumps(data, indent=2) + "\n")
                note = f"config.json ({', '.join(dropped)})"
                logger.warning("Dropped %s from the Copilot home %s", note, home)
                removed.append(note)

    agents_dir = home / "agents"
    if agents_dir.is_dir():
        own = f"{agent}.agent.md"
        for path in sorted(agents_dir.iterdir()):
            if path.name == own or _is_owned(home, path, owned):
                continue
            gone(path)
    return removed


def ensure_copilot_home(
    project_id: str,
    agent: str,
    *,
    stable_context: str,
    model: Optional[str],
    effort: Optional[str],
    mcp_command: Optional[Sequence[str]],
) -> CopilotHome:
    """Make the agent's home current and return it. Idempotent: a file is rewritten only when its
    content differs. Raises `ValueError` (an unsafe path component) or `OSError`."""
    home = copilot_home_path(project_id, agent)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(home, 0o700)
    removed = _sweep(home, agent)
    record_owned_file(
        home,
        f"agents/{agent}.agent.md",
        render_agent_file(agent, stable_context, model=model, effort=effort),
    )
    if mcp_command:
        # Written only when the run's access path is MCP. An existing file is left alone when it
        # is not: it is harmless unless `--additional-mcp-config` names it.
        _write_if_changed(home / MCP_CONFIG_NAME, render_mcp_config(mcp_command))
    return CopilotHome(path=home, removed=tuple(removed))
