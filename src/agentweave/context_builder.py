"""Generated agent context rendering.

This module keeps model-facing context generation in one place so CLI, watchdog,
Hub, and MCP paths do not drift.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .constants import AGENT_CONTEXT_DIR, AGENTWEAVE_DIR, ROLES_DIR

PLACEHOLDER_MARKERS = (
    "[Replace with:",
    "<!-- Explain",
    "<!-- Describe",
    "<!-- requirement",
)


@dataclass
class ContextBuildResult:
    """Rendered context plus status metadata."""

    agent: str
    context: str
    known: bool
    declared: bool
    registered: bool = False
    provisional: bool = False
    roles: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Return a machine-readable API/MCP response."""
        return {
            "agent": self.agent,
            "known": self.known,
            "declared": self.declared,
            "registered": self.registered,
            "provisional": self.provisional,
            "roles": self.roles,
            "missing": self.missing,
            "metadata": self.metadata,
            "context": self.context,
        }


def is_placeholder_ai_context(content: str) -> bool:
    """Return True when ai_context.md still looks like the untouched template."""
    stripped = content.strip()
    if not stripped:
        return False
    return any(marker in stripped for marker in PLACEHOLDER_MARKERS)


def _hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def _read_optional(path: Path) -> tuple[str, str | None]:
    if not path.exists():
        return "", "missing"
    try:
        return path.read_text(encoding="utf-8").strip(), None
    except OSError as exc:
        return "", str(exc)


def _session_dict(session: Any) -> dict[str, Any]:
    if session is None:
        return {}
    if isinstance(session, dict):
        return session
    if hasattr(session, "to_dict"):
        return session.to_dict()
    return {}


def _agent_names(session: Any) -> list[str]:
    if hasattr(session, "agent_names"):
        return list(session.agent_names)
    data = _session_dict(session)
    return list((data.get("agents") or {}).keys())


def _runner_config(session: Any, agent: str) -> dict[str, Any]:
    if hasattr(session, "get_runner_config"):
        return dict(session.get_runner_config(agent))
    data = _session_dict(session)
    agent_data = (data.get("agents") or {}).get(agent, {})
    return {
        "runner": agent_data.get("runner") or "native",
        "model": agent_data.get("model"),
        "env_vars": agent_data.get("env_vars") or {},
    }


def _agent_flags(session: Any, agent: str) -> list[str]:
    data = _session_dict(session)
    agent_data = (data.get("agents") or {}).get(agent, {})
    flags: list[str] = []
    if agent == data.get("principal") or agent_data.get("role") == "principal":
        flags.append("principal")
    if agent_data.get("pilot"):
        flags.append("pilot")
    if agent_data.get("yolo"):
        flags.append("yolo")
    return flags


def _env_names(env_vars: dict[str, Any]) -> list[str]:
    names = set()
    for key, value in env_vars.items():
        key_str = str(key)
        value_str = str(value)
        if key_str.endswith("_VAR") and value_str:
            names.add(value_str)
        elif key_str.isupper():
            names.add(key_str)
        elif value_str.isupper():
            names.add(value_str)
    return sorted(names)


def _load_agentweave_config() -> Any | None:
    try:
        from .config import AGENTWEAVE_YML_PATH, load_agentweave_yml

        if AGENTWEAVE_YML_PATH.exists():
            return load_agentweave_yml()
    except Exception:
        return None
    return None


def _load_roles_config() -> dict[str, Any]:
    try:
        from .roles import load_roles_config

        return load_roles_config() or {}
    except Exception:
        return {}


def _get_agent_roles(agent: str, roles_config: dict[str, Any] | None = None) -> list[str]:
    try:
        from .roles import get_agent_roles

        return get_agent_roles(agent, roles_config)
    except Exception:
        return []


def _available_roles(roles_config: dict[str, Any]) -> list[str]:
    roles = roles_config.get("roles") or {}
    return sorted(role for role in roles if not str(role).startswith("_"))


def _job_summaries(config: Any | None, agent: str | None = None) -> list[str]:
    if not config or not getattr(config, "jobs", None):
        return []
    lines = []
    for name, job in config.jobs.items():
        prefix = f"- `{name}` -> `{job.agent}`" if agent and job.agent != agent else f"- `{name}`"
        state = "enabled" if getattr(job, "enabled", True) else "disabled"
        prompt = str(getattr(job, "prompt", ""))
        if len(prompt) > 96:
            prompt = prompt[:93].rstrip() + "..."
        lines.append(f"{prefix}: `{job.schedule}` ({state}) - {prompt}")
    return lines


def render_project_operating_profile(
    session: Any,
    *,
    roles_config: dict[str, Any] | None = None,
    config: Any | None = None,
    target_agent: str | None = None,
) -> str:
    """Render concise project/team/quality facts for model context."""
    data = _session_dict(session)
    roles_config = roles_config if roles_config is not None else _load_roles_config()
    config = config if config is not None else _load_agentweave_config()

    project_name = getattr(getattr(config, "project", None), "name", None) or data.get("name")
    project_mode = getattr(getattr(config, "project", None), "mode", None) or data.get("mode")
    principal = data.get("principal")

    lines = ["## Project Operating Profile", ""]
    if project_name:
        lines.append(f"- Project: {project_name}")
    if project_mode:
        lines.append(f"- Mode: {project_mode}")
    if principal:
        lines.append(f"- Principal: `{principal}`")
    lines.append(
        f"- Canonical runtime context: `.agentweave/context/{target_agent or '<agent>'}.md`"
    )
    lines.append("")

    lines.append("### Team")
    agent_names = _agent_names(session)
    if agent_names:
        for agent in agent_names:
            runner = _runner_config(session, agent)
            runner_name = runner.get("runner") or "native"
            model = runner.get("model")
            roles = _get_agent_roles(agent, roles_config)
            flags = _agent_flags(session, agent)
            env_names = _env_names(runner.get("env_vars") or {})
            details = [f"runner={runner_name}"]
            if model:
                details.append(f"model={model}")
            if roles:
                details.append("roles=" + ",".join(roles))
            if flags:
                details.append("flags=" + ",".join(flags))
            if env_names:
                details.append("env=" + ",".join(env_names))
            marker = " <- you" if agent == target_agent else ""
            lines.append(f"- `{agent}`: " + "; ".join(details) + marker)
    else:
        lines.append("- No declared agents found.")
    lines.append("")

    quality = data.get("quality") or {}
    if quality:
        docs_path = quality.get("docs_path") or ".agentweave/code-docs"
        lines.append("### Quality Gates")
        lines.append(f"- docs_threshold: `{quality.get('docs_threshold', 'never')}`")
        lines.append(f"- docs_path: `{docs_path}/<task-id>.md`")
        lines.append(f"- review_required: `{str(bool(quality.get('review_required'))).lower()}`")
        lines.append(f"- echo_chamber_guard: `{quality.get('echo_chamber_guard', 'off')}`")
        lines.append(f"- attribution_tag: `{str(bool(quality.get('attribution_tag'))).lower()}`")
        lines.append(f"- dependency_check: `{str(bool(quality.get('dependency_check'))).lower()}`")
        lines.append("")
        lines.append("### Definition of Done")
        lines.append("- Run the verification commands relevant to the task before completion.")
        if quality.get("review_required"):
            lines.append("- Request review before marking implementation work complete.")
        if quality.get("docs_threshold", "never") != "never":
            lines.append(
                "- Write a decision doc when the docs threshold applies before marking done."
            )
        if quality.get("echo_chamber_guard") == "enforce":
            lines.append("- Do not review your own implementation work.")
        lines.append("")

    jobs = _job_summaries(config, target_agent)
    if jobs:
        lines.append("### Scheduled Jobs")
        lines.extend(jobs)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _role_sections(agent: str, roles: Iterable[str]) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    missing: list[str] = []
    for role_id in roles:
        role_file = ROLES_DIR / f"{role_id}.md"
        if role_file.exists():
            content, error = _read_optional(role_file)
            if content and not error:
                lines.append(content)
            else:
                missing.append(f".agentweave/roles/{role_id}.md")
                lines.append(f"### {role_id}\n\nRole guide could not be read.")
        else:
            missing.append(f".agentweave/roles/{role_id}.md")
            lines.append(f"### {role_id}\n\nRole guide not found.")
    return lines, missing


def build_agent_context(
    agent: str,
    session: Any,
    *,
    version_comment: str = "AgentWeave",
    project_instructions: str = "",
    roles_config: dict[str, Any] | None = None,
    config: Any | None = None,
) -> ContextBuildResult:
    """Build canonical context for a declared agent."""
    roles_config = roles_config if roles_config is not None else _load_roles_config()
    config = config if config is not None else _load_agentweave_config()
    roles = _get_agent_roles(agent, roles_config)
    missing: list[str] = []
    metadata: dict[str, Any] = {"sources": {}}

    lines = [
        f"# {agent} - AgentWeave Runtime Context",
        f"<!-- Generated by {version_comment}; canonical path: .agentweave/context/{agent}.md -->",
        "",
        "This is the canonical runtime context for this agent. Prefer this file over manually",
        "re-reading root bootstrap files unless you need to inspect a source file directly.",
        "",
    ]

    lines.append(
        render_project_operating_profile(
            session, roles_config=roles_config, config=config, target_agent=agent
        )
    )

    lines.extend(
        [
            "## Communication Mode",
            "",
            "Use AgentWeave MCP tools for coordination when available: `send_message`,",
            "`get_inbox`, `list_tasks`, `get_task`, `create_task`, `update_task`,",
            "`ask_user`, and `save_checkpoint`.",
            "",
            "In Hub/MCP mode, do not use `agentweave relay` or `agentweave quick` for",
            "delegation; those commands require manual relay and bypass Hub automation.",
            "",
        ]
    )

    if project_instructions:
        lines.extend(["## Project Instructions", "", project_instructions.strip(), "", "---", ""])
        metadata["sources"]["project_instructions"] = _hash_text(project_instructions)
    else:
        missing.append(".agentweave/project_instructions.md")

    if roles:
        role_lines, role_missing = _role_sections(agent, roles)
        missing.extend(role_missing)
        lines.extend(["## Your Role Contracts", ""])
        for section in role_lines:
            lines.append(section)
            lines.append("")
    else:
        missing.append(".agentweave/roles.json agent_roles")
        lines.extend(
            [
                "## Your Role Contracts",
                "",
                "No role is assigned. Ask the principal to assign a role before taking work.",
                "",
            ]
        )

    ai_path = AGENTWEAVE_DIR / "ai_context.md"
    ai_context, ai_error = _read_optional(ai_path)
    if ai_context and not is_placeholder_ai_context(ai_context):
        lines.extend(["## Project Context", "", ai_context, ""])
        metadata["sources"]["ai_context"] = _hash_text(ai_context)
    elif ai_context and is_placeholder_ai_context(ai_context):
        missing.append(".agentweave/ai_context.md contains placeholders")
        lines.extend(
            [
                "## Project Context",
                "",
                "Project context is not complete yet. `.agentweave/ai_context.md` still",
                "contains template placeholders, so it was not injected as project facts.",
                "",
            ]
        )
    elif ai_error:
        missing.append(".agentweave/ai_context.md")

    lines.extend(
        [
            "## Live Session Context",
            "",
            "For Hub/watchdog-triggered work, `.agentweave/shared/context.md` is prepended",
            "to the prompt as current session focus. In manual sessions, read it before",
            "starting work if it exists.",
            "",
        ]
    )

    context = "\n".join(lines).rstrip() + "\n"
    metadata["context_hash"] = _hash_text(context)
    metadata["context_path"] = f".agentweave/context/{agent}.md"
    return ContextBuildResult(
        agent=agent,
        context=context,
        known=agent in _agent_names(session),
        declared=agent in _agent_names(session),
        registered=False,
        provisional=False,
        roles=roles,
        missing=sorted(set(missing)),
        metadata=metadata,
    )


def build_external_agent_context(
    agent: str,
    *,
    session: Any = None,
    roles_config: dict[str, Any] | None = None,
    registered: bool = False,
    requested_roles: list[str] | None = None,
    config: Any | None = None,
) -> ContextBuildResult:
    """Build onboarding context for registered or unknown external agents."""
    roles_config = roles_config if roles_config is not None else _load_roles_config()
    config = config if config is not None else _load_agentweave_config()
    requested_roles = requested_roles or []
    available = _available_roles(roles_config)
    known = registered
    missing: list[str] = []

    lines = [
        f"# {agent} - AgentWeave Onboarding Context",
        "",
        render_project_operating_profile(
            session or {}, roles_config=roles_config, config=config, target_agent=agent
        ),
        "## External Agent Rules",
        "",
    ]
    if registered:
        lines.extend(
            [
                "You are registered with AgentWeave but are not declared in `agentweave.yml`.",
                "Until the principal assigns you work:",
                "- do not modify files",
                "- do not claim tasks",
                "- read inbox and available tasks only",
                "- send a short availability message to the principal",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "You are not registered with AgentWeave yet.",
                "Register before taking work by calling `register_agent(...)` with your",
                "agent name, contact mode, and optional role request.",
                "",
            ]
        )
        missing.append("agent registration")

    if requested_roles:
        lines.extend(["## Requested Role Guidance", ""])
        role_lines, role_missing = _role_sections(agent, requested_roles)
        missing.extend(role_missing)
        for section in role_lines:
            lines.append(section)
            lines.append("")

    if available:
        lines.extend(["## Available Roles", ""])
        for role in available:
            lines.append(f"- `{role}`")
        lines.append("")

    context = "\n".join(lines).rstrip() + "\n"
    return ContextBuildResult(
        agent=agent,
        context=context,
        known=known,
        declared=False,
        registered=registered,
        provisional=True,
        roles=requested_roles,
        missing=sorted(set(missing)),
        metadata={"context_hash": _hash_text(context), "context_path": None},
    )


def write_agent_context_file(result: ContextBuildResult) -> Path:
    """Write a built context result to `.agentweave/context/<agent>.md`."""
    AGENT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    target = AGENT_CONTEXT_DIR / f"{result.agent}.md"
    target.write_text(result.context, encoding="utf-8")
    return target
