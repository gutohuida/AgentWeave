#!/usr/bin/env python3
"""Command-line interface for AgentWeave."""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .config import AgentWeaveConfig

from . import __version__
from .constants import (
    AGENT_CONTEXT_DIR,
    AGENT_CONTEXT_FILES,
    AGENT_CONTEXT_FILES_DEFAULT,
    AGENTWEAVE_DIR,
    DEFAULT_AGENTS,
    ROLES_CONFIG_FILE,
    ROLES_DIR,
    RUNNER_CONFIGS,
    SESSION_FILE,
    SHARED_DIR,
    TRANSPORT_CONFIG_FILE,
    VALID_AGENTS,
    VALID_MODES,
    VALID_ROLE_IDS,
)
from .locking import acquire_lock, release_lock
from .messaging import Message, MessageBus
from .roles import (
    add_role_to_agent,
    copy_role_md_file,
    format_agent_roles,
    get_agent_roles,
    get_available_roles,
    load_roles_config,
    remove_role_from_agent,
    save_roles_config,
    set_agent_roles,
    sync_roles_to_hub,
)
from .session import Session
from .task import Task
from .templates import (
    get_role_md,
    get_skill_template,
    get_template,
    list_skill_templates,
    load_roles_template,
)
from .utils import (
    ensure_dirs,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from .validator import validate_message, validate_task


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new session."""
    import json as _json

    # Check for existing session (migration path)
    existing_session = None
    if SESSION_FILE.exists():
        try:
            existing_session_data = _json.loads(SESSION_FILE.read_text())
            existing_session = Session(existing_session_data)
        except Exception:
            pass

        if existing_session and not args.force:
            print_info("Existing session detected.")
            print_info("Generating agentweave.yml from current configuration...")
            try:
                from .config import generate_agentweave_yml

                generate_agentweave_yml(existing_session)
                print_success("Generated agentweave.yml from existing session")
                print_info("Run 'agentweave activate' to apply configuration")
                return 0
            except Exception as e:
                print_error(f"Failed to generate agentweave.yml: {e}")
                return 1

    if AGENTWEAVE_DIR.exists() and not args.force:
        if AGENTWEAVE_DIR.is_file():
            print_error(".agentweave exists as a file, not a directory.")
            print_info("Remove it with: rm .agentweave")
            return 1
        # Directory exists - check if it has meaningful content (not just logs)
        # The logs directory is created automatically by logging setup
        has_session = SESSION_FILE.exists()
        has_agents_dir = (AGENTWEAVE_DIR / "agents").exists()
        has_tasks_dir = (AGENTWEAVE_DIR / "tasks").exists()
        if has_session or has_agents_dir or has_tasks_dir:
            print_warning(".agentweave/ already exists. Use --force to overwrite.")
            return 1
        # Directory only contains logs/other non-essential files - allow init

    # Handle case where .agentweave exists as a file with --force
    if AGENTWEAVE_DIR.exists() and args.force and AGENTWEAVE_DIR.is_file():
        try:
            AGENTWEAVE_DIR.unlink()
            print_info("Removed existing .agentweave file.")
        except OSError as e:
            print_error(f"Cannot remove .agentweave file: {e}")
            return 1

    # Handle deprecation warning for --agents
    agents_arg = getattr(args, "agents", None)
    if agents_arg:
        print_warning("--agents is deprecated. Define agents in agentweave.yml instead.")

    ensure_dirs()

    try:
        # Parse agent list: --agents claude,kimi,gemini  OR fall back to default
        agent_list = None
        if agents_arg:
            agent_list = [a.strip() for a in agents_arg.split(",") if a.strip()]

        principal = args.principal or (agent_list[0] if agent_list else DEFAULT_AGENTS[0])

        # In the declarative workflow, only create the principal at init time.
        # Additional agents are declared in agentweave.yml and synced by activate.
        effective_agents = agent_list if agent_list else DEFAULT_AGENTS

        session = Session.create(
            name=args.project or "Unnamed Project",
            principal=principal,
            mode=args.mode or "hierarchical",
            agents=effective_agents,
        )
        session.save()

        # Create README
        agents_listed = "\n".join(f"# agentweave relay --agent {ag}" for ag in session.agent_names)
        readme_path = AGENTWEAVE_DIR / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"""# AgentWeave Session: {session.name}

**ID:** {session.id}
**Mode:** {session.mode}
**Principal:** {session.principal}
**Agents:** {', '.join(session.agent_names)}

## Quick Commands

```bash
# Check status
agentweave status

# Create task for any agent
agentweave task create --title "Task name" --assignee <agent>

# List tasks
agentweave task list

# Quick delegation
agentweave quick --to <agent> "Implement auth"

# Check inbox
agentweave inbox --agent <agent>

# Get relay prompt (for each agent)
{agents_listed}

# Summary
agentweave summary
```

## Files

- `session.json` — Session configuration
- `protocol.md` — Collaboration protocol (MCP vs manual relay, workflow)
- `roles.json` — Agent role assignments and role registry (edit freely)
- `roles/` — Per-role behavioral guides (read yours at session start)
- `ai_context.md` — Project DNA source (edit this, then run update-template)
- `agents/` — Agent status
- `tasks/active/` — Active tasks
- `tasks/completed/` — Completed tasks
- `messages/pending/` — Unread messages
- `messages/archive/` — Message history
- `shared/` — Shared context and decisions
""")

        # Write protocol.md — collaboration guide inside .agentweave/
        non_principal = [a for a in session.agent_names if a != session.principal]
        agents_list = ", ".join(non_principal) if non_principal else "kimi"
        try:
            collab_protocol = (
                get_template("collab_protocol")
                .replace("{principal}", session.principal)
                .replace("{agents_list}", agents_list)
                .replace("{mode}", session.mode)
            )
            protocol_path = AGENTWEAVE_DIR / "protocol.md"
            with open(protocol_path, "w", encoding="utf-8") as f:
                f.write(collab_protocol)
        except FileNotFoundError:
            pass  # Non-fatal

        # Write roles.json and copy active role MD files to .agentweave/roles/
        try:
            import json as _json

            roles_template_data = load_roles_template()
            all_role_defs = roles_template_data["roles"]

            # Build default-for map from _default_for metadata in the template
            default_for_map: dict = {}
            for role_id, role_def in all_role_defs.items():
                for ag_name in role_def.get("_default_for", []):
                    default_for_map[ag_name] = role_id

            # Assign roles to this session's agents
            agent_assignments: dict = {}
            active_role_keys: set = set()
            for ag in session.agent_names:
                role_key = default_for_map.get(ag)
                if role_key:
                    agent_assignments[ag] = role_key
                    active_role_keys.add(role_key)
                # Agents not in _default_for start with no role.
                # Use agentweave.yml + `agentweave activate` to assign roles.

            # Build the project roles.json (strip internal _* fields)
            roles_config = {
                "version": 1,
                "agent_assignments": agent_assignments,
                "roles": {
                    k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                    for k, v in all_role_defs.items()
                    if k in active_role_keys
                },
            }
            ROLES_CONFIG_FILE.write_text(
                _json.dumps(roles_config, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Push roles config to Hub if HTTP transport is active
            try:
                from .transport import get_transport

                _t = get_transport()
                if _t.get_transport_type() == "http":
                    _t.push_roles_config(roles_config)
            except Exception:
                pass  # Non-fatal

            # Copy active role MD files
            import contextlib

            ROLES_DIR.mkdir(exist_ok=True)
            for role_key in active_role_keys:
                with contextlib.suppress(FileNotFoundError):
                    (ROLES_DIR / f"{role_key}.md").write_text(
                        get_role_md(role_key), encoding="utf-8"
                    )
        except Exception:
            pass  # Non-fatal

        # Write .agentweave/ai_context.md — hidden source template (agents don't read this directly).
        ai_context_path = AGENTWEAVE_DIR / "ai_context.md"
        if not ai_context_path.exists():
            try:
                ai_context = get_template("ai_context")
                with open(ai_context_path, "w", encoding="utf-8") as f:
                    f.write(ai_context)
            except FileNotFoundError:
                pass  # Non-fatal

        # Write agent-specific context files at project root (auto-read by each agent).
        # claude → CLAUDE.md, gemini → GEMINI.md, everything else → AGENTS.md.
        version_comment = f"AgentWeave v{__version__}"
        written_root_files: set = set()
        for ag in session.agent_names:
            _runner = session.get_runner_config(ag).get("runner", "native")
            if _runner == "claude_proxy":
                root_filename = "CLAUDE.md"
            else:
                root_filename = AGENT_CONTEXT_FILES.get(ag, AGENT_CONTEXT_FILES_DEFAULT)
            if root_filename in written_root_files:
                continue  # multiple agents may share AGENTS.md — only write once
            root_path = Path.cwd() / root_filename
            if root_path.exists():
                written_root_files.add(root_filename)
                continue  # never overwrite an existing file
            template_name = "claude_context" if root_filename == "CLAUDE.md" else "kimi_context"
            try:
                context_content = get_template(template_name).replace("{version}", version_comment)
                with open(root_path, "w", encoding="utf-8") as f:
                    f.write(context_content)
                written_root_files.add(root_filename)
            except FileNotFoundError:
                pass  # Non-fatal

        # Write shared/context.md — current project state (dynamic, changes daily)
        context_md_path = SHARED_DIR / "context.md"
        if not context_md_path.exists():
            context_md_content = f"""# Current Project State

> **Purpose:** What's being worked on right now — today's focus, recent decisions, blockers.
>
> **Update frequency:** Daily, or whenever state changes.
>
> **For project fundamentals:** See your agent context file (CLAUDE.md / AGENTS.md / GEMINI.md) at the project root.

---

## Current Sprint / Phase

[What phase are we in? E.g., "MVP development", "Refactoring auth module", "Preparing for v1.0 release"]

## Active Work

### In Progress
- [Agent name] is working on: [brief description]
- Blockers: [any blockers or "None"]

### Next Up
- [Task or feature name] — assigned to [agent] or unassigned
- [Task or feature name] — waiting for [dependency]

## Recent Decisions (last 3-5)

1. **[Date]** [Decision made] — [rationale]
2. **[Date]** [Decision made] — [rationale]
3. **[Date]** [Decision made] — [rationale]

## Blockers & Needs Attention

- [ ] [Blocker or issue needing attention]

## Notes for Agents

- [Any context that doesn't fit elsewhere]

---

*Last updated: [date]*
*Session: {session.name} ({session.id})*
"""
            context_md_path.write_text(context_md_content, encoding="utf-8")

        # Build list of root files that were created
        root_files_created = sorted(written_root_files)

        print_success(f"Initialized session: {session.name}")
        print(f"   ID:      {session.id}")
        print(f"   Mode:    {session.mode}")
        print(f"   Agents:  {', '.join(session.agent_names)}  (principal: {session.principal})")
        print("\n[DIR] Created .agentweave/")
        print("     protocol.md          <- collaboration protocol (MCP vs manual, workflow)")
        print("     roles.json           <- agent role assignments and role registry (edit freely)")
        print(
            "     roles/               <- per-role behavioral guides (read yours at session start)"
        )
        print(
            "     ai_context.md        <- project DNA source — fill this in, then update agent files"
        )
        print("     shared/context.md    <- current focus, recent decisions (update daily)")
        if root_files_created:
            print("\n[FILES] Created at project root (auto-read by agents each session):")
            for fname in root_files_created:
                print(f"     {fname}")
        print("\nFile purposes:")
        print("  • .agentweave/ai_context.md  — Project DNA source (edit this)")
        for fname in root_files_created:
            print(f"  • {fname:<22} — Auto-loaded by agent; contains full project context")
        print("  • .agentweave/ROLES.md       — Who does what? (per-session)")
        print("  • .agentweave/shared/context.md — What are we doing today? (changes daily)")
        print("\nNext steps:")
        print("1. Fill in the [Replace with...] sections in .agentweave/ai_context.md")
        print("2. Run `agentweave sync-context` to regenerate agent files from ai_context.md")
        print("3. Edit .agentweave/ROLES.md to assign the right dev roles")
        print("4. Update .agentweave/shared/context.md with today's focus")
        print(f"5. Start {session.principal.capitalize()} — it will auto-read its context file")
        print()
        print("Zero-relay MCP mode (optional):")
        print("  agentweave mcp setup   # configure MCP server in both agents (once)")
        print(
            "  agentweave start       # launch background watchdog — agents notify each other automatically"
        )

        # Generate Claude Code skills in .claude/skills/
        skills_count = _generate_claude_skills(session, Path.cwd(), force=args.force)
        if skills_count > 0:
            print(f"\n[SKILLS] Generated {skills_count} Claude Code skills in .claude/skills/")
            print("  Available slash commands:")
            print("    /aw-delegate   delegate a task to another agent")
            print("    /aw-status     full collaboration status overview")
            print("    /aw-done       mark a task complete and notify principal")
            print("    /aw-review     request a code review")
            print("    /aw-relay      generate relay prompt for an agent")
            print("    /aw-sync       sync context files from ai_context.md")
            print("    /aw-revise     accept and begin a revision")
            print("  (aw-collab-start runs automatically at session start)")

        # Generate agentweave.yml configuration file
        try:
            from .config import generate_agentweave_yml

            yml_path = generate_agentweave_yml(session)
            print(f"\n[CONFIG] Created {yml_path}")
            print("  This file defines your project agents and settings.")
            print("  Edit it to add/remove agents, then run 'agentweave activate'")
        except Exception as exc:
            print_warning(f"Could not create agentweave.yml: {exc}")

        return 0

    except ValueError as e:
        print_error(str(e))
        return 1


def _generate_claude_skills(session: "Session", base_dir: Path, force: bool = False) -> int:
    """Generate .claude/skills/ from skill templates, personalized for this session.

    Returns the number of skill files written.
    """
    skills_dir = base_dir / ".claude" / "skills"
    non_principal = [a for a in session.agent_names if a != session.principal]
    reviewer = non_principal[0] if non_principal else session.principal
    agents_list = ", ".join(session.agent_names)

    substitutions = {
        "project_name": session.name,
        "principal": session.principal,
        "agents_list": agents_list,
        "mode": session.mode,
        "reviewer": reviewer,
    }

    skill_names = list_skill_templates()
    if not skill_names:
        return 0

    count = 0
    for name in sorted(skill_names):
        skill_dir = skills_dir / name
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists() and not force:
            continue
        try:
            template = get_skill_template(name)
        except FileNotFoundError:
            continue
        content = template
        for key, value in substitutions.items():
            content = content.replace("{" + key + "}", value)
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(content, encoding="utf-8")
        count += 1

    return count


def cmd_status(_args: argparse.Namespace) -> int:
    """Show session status."""
    import os as _os

    from .constants import WATCHDOG_PID_FILE

    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    print(f"[STAT] Session: {session.name}")
    print(f"   ID:        {session.id}")
    print(f"   Mode:      {session.mode}")
    print(f"   Principal: {session.principal}")

    # Watchdog state
    from .eventlog import get_heartbeat_age

    watchdog_status = "stopped"
    watchdog_pid = None
    if WATCHDOG_PID_FILE.exists():
        try:
            watchdog_pid = int(WATCHDOG_PID_FILE.read_text().strip())
            _os.kill(watchdog_pid, 0)
            watchdog_status = f"running (PID {watchdog_pid})"
        except (OSError, ProcessLookupError, ValueError):
            watchdog_status = "stopped (stale PID file)"
    heartbeat_age = get_heartbeat_age()
    if heartbeat_age is not None:
        if heartbeat_age < 30:
            hb_str = f"last beat {int(heartbeat_age)}s ago"
        elif heartbeat_age < 3600:
            hb_str = f"last beat {int(heartbeat_age / 60)}m ago"
        else:
            hb_str = f"last beat {int(heartbeat_age / 3600)}h ago"
        if heartbeat_age > 60 and "running" not in watchdog_status:
            hb_str = f"DEAD — {hb_str}"
        watchdog_status = f"{watchdog_status}  [{hb_str}]"
    print(f"\n[WATCH] Watchdog: {watchdog_status}")

    # Per-agent info
    from .constants import DEFAULT_AGENTS

    all_agents = session.agent_names or DEFAULT_AGENTS
    active_tasks = Task.list_all(active_only=True)

    # Load roles config for display
    roles_config = load_roles_config()

    print("\n[AGENTS]")
    for agent in all_agents:
        # Get session role (principal/delegate)
        session_role = session.agents.get(agent, {}).get("role", "delegate")
        # Get dev roles (tech_lead, backend_dev, etc.)
        dev_roles = get_agent_roles(agent, roles_config)
        roles_display = ", ".join(dev_roles) if dev_roles else session_role

        inbox = MessageBus.get_inbox(agent)
        agent_tasks = [t for t in active_tasks if t.assignee == agent]
        in_prog = [t for t in agent_tasks if t.status == "in_progress"]
        waiting = [t for t in agent_tasks if t.status in ("pending", "assigned")]
        review = [t for t in agent_tasks if t.status in ("completed", "under_review")]
        principal_marker = " [principal]" if agent == session.principal else ""
        print(f"   {agent}{principal_marker} ({roles_display})")
        if inbox:
            print(f"      inbox:    {len(inbox)} unread message(s)")
        if in_prog:
            print(f"      working:  {len(in_prog)} task(s) in progress")
        if waiting:
            print(f"      waiting:  {len(waiting)} task(s) not yet started")
        if review:
            print(f"      review:   {len(review)} task(s) ready for review")
        if not inbox and not agent_tasks:
            print("      idle")

    # Overall task summary
    completed_tasks = [t for t in Task.list_all() if t.status in ("completed", "approved")]
    print(f"\n[TASKS] Active: {len(active_tasks)}  |  Completed: {len(completed_tasks)}")

    return 0


def cmd_summary(_args: argparse.Namespace) -> int:
    """Show quick summary for relay decisions."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    print("=" * 60)
    print("INTERAGENT SUMMARY")
    print("=" * 60)
    print()

    # Session info
    print(f"Session: {session.name} ({session.mode} mode)")
    print(f"Principal: {session.principal}")
    print()

    # Tasks by status — dynamic across all session agents
    from .constants import DEFAULT_AGENTS

    all_tasks = Task.list_all()
    all_agents = session.agent_names or DEFAULT_AGENTS

    pending_by_agent = {
        ag: [t for t in all_tasks if t.assignee == ag and t.status in ["pending", "assigned"]]
        for ag in all_agents
    }
    in_progress_by_agent = {
        ag: [t for t in all_tasks if t.assignee == ag and t.status == "in_progress"]
        for ag in all_agents
    }
    ready_for_review = [t for t in all_tasks if t.status in ["completed", "under_review"]]
    approved = [t for t in all_tasks if t.status == "approved"]

    print("[TASKS]")
    for ag in all_agents:
        if pending_by_agent[ag]:
            print(
                f"  [WAIT] {ag.capitalize()}: {len(pending_by_agent[ag])} task(s) waiting to start"
            )
        if in_progress_by_agent[ag]:
            print(
                f"  [WORK] {ag.capitalize()}: {len(in_progress_by_agent[ag])} task(s) in progress"
            )
    if ready_for_review:
        print(f"  [REVIEW] {len(ready_for_review)} task(s) ready for review")
    if approved:
        print(f"  [OK] {len(approved)} task(s) approved")

    any_tasks = (
        any(pending_by_agent[ag] or in_progress_by_agent[ag] for ag in all_agents)
        or ready_for_review
        or approved
    )
    if not any_tasks:
        print("  No active tasks")
    print()

    # Messages — dynamic across all agents
    msgs_by_agent = {ag: MessageBus.get_inbox(ag) for ag in all_agents}

    print("[MESSAGES]")
    any_msgs = False
    for ag in all_agents:
        if msgs_by_agent[ag]:
            any_msgs = True
            print(f"  [MSG] {ag.capitalize()}: {len(msgs_by_agent[ag])} unread message(s)")
            for msg in msgs_by_agent[ag]:
                print(f"     - From {msg.sender}: {msg.subject or '(no subject)'}")
    if not any_msgs:
        print("  No unread messages")
    print()

    # Action items
    print("[ACTION ITEMS]")
    if ready_for_review:
        print(f"  -> Tell {session.principal} to review {len(ready_for_review)} completed task(s)")
    non_principal = [ag for ag in all_agents if ag != session.principal]
    for ag in non_principal:
        if pending_by_agent.get(ag):
            print(
                f"  -> Tell {ag.capitalize()} to check inbox ({len(pending_by_agent[ag])} new task(s))"
            )
        if msgs_by_agent.get(ag):
            print(f"  -> Tell {ag.capitalize()} to check messages")
    if msgs_by_agent.get(session.principal):
        print(f"  -> Tell {session.principal.capitalize()} to check messages")
    if not ready_for_review and not any_msgs and not any(pending_by_agent.values()):
        print("  All caught up! No action needed.")
    print()

    # Quick commands
    print("[QUICK COMMANDS]")
    if ready_for_review:
        task_id = ready_for_review[0].id
        print(f"  agentweave task show {task_id}")
    for ag in all_agents:
        if msgs_by_agent[ag]:
            print(f"  agentweave relay --agent {ag}")
    print()

    return 0


def _generate_kimi_agent_yaml(agent: str) -> Path:
    """Generate the kimi --agent-file YAML shim for a pilot agent.

    Creates .agentweave/agent-{agent}.yaml that points system_prompt_path
    at the agent's existing context markdown file. This lets kimi load role
    context on startup via --agent-file without needing prompt injection.

    Returns the path to the generated YAML file.
    """
    yaml_path = AGENTWEAVE_DIR / f"agent-{agent}.yaml"
    # Path is relative to the YAML file's location (.agentweave/), not the project root.
    # So context/kimi-lead.md resolves to .agentweave/context/kimi-lead.md correctly.
    context_rel = f"context/{agent}.md"
    yaml_content = f"""\
# Auto-generated by AgentWeave — do not edit manually.
# Regenerated on: agentweave agent configure {agent} --pilot
# or: agentweave roles add/set {agent} <role>
version: 1
agent:
  extend: default
  system_prompt_path: {context_rel}
"""
    AGENTWEAVE_DIR.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml_content, encoding="utf-8")
    return yaml_path


def _refresh_kimi_pilot_yaml(agent: str, session: "Session") -> None:
    """Regenerate kimi agent YAML + context file if agent is a pilot kimi runner.

    Silent no-op for non-kimi or non-pilot agents.
    """
    runner = session.get_runner_config(agent).get("runner", "native")
    if runner != "kimi" or not session.get_agent_pilot(agent):
        return
    try:
        AGENT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        version_comment = f"AgentWeave v{__version__}"
        ctx_content = _build_agent_context(agent, session, version_comment)
        (AGENT_CONTEXT_DIR / f"{agent}.md").write_text(ctx_content, encoding="utf-8")
        _generate_kimi_agent_yaml(agent)
        print_info(f"Refreshed kimi pilot context: .agentweave/agent-{agent}.yaml")
    except Exception as exc:
        print_warning(f"Could not refresh kimi pilot YAML: {exc}")


def cmd_session_register(args: argparse.Namespace) -> int:
    """Register a session ID for a pilot agent.

    This command:
    1. Registers the session ID with the Hub (if HTTP transport)
    2. Updates local agent session file
    3. Prints the ready-to-use launch command (YAML already generated at configure time)
    """
    agent = args.agent
    session_id = args.session_id

    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1
    if agent not in session.agent_names:
        print_error(f"Agent {agent!r} is not in the current session")
        return 1

    # Register with Hub if HTTP transport
    hub_result = None
    try:
        from .transport import get_transport

        transport = get_transport()
        if transport.get_transport_type() == "http":
            hub_result = transport.register_session(agent, session_id)
            if hub_result:
                print_success(f"Session registered with Hub for {agent}")
            else:
                print_warning("Failed to register with Hub (continuing with local registration)")
    except Exception as exc:
        print_warning(f"Hub registration skipped: {exc}")

    # Update local agent session file
    agent_session_file = AGENTWEAVE_DIR / "agents" / f"{agent}-session.json"
    try:
        agent_session_file.parent.mkdir(parents=True, exist_ok=True)
        import json

        agent_session_data = {"session_id": session_id, "registered_at": datetime.now().isoformat()}
        agent_session_file.write_text(json.dumps(agent_session_data, indent=2), encoding="utf-8")
    except Exception as exc:
        print_error(f"Failed to save local session file: {exc}")
        return 1

    # Print launch command
    runner_cfg = session.get_runner_config(agent)
    runner = runner_cfg.get("runner", "native")

    print()
    print_success(f"Session registered for {agent}")
    print(f"  Session ID: {session_id}")
    print()
    print("Launch command:")

    if runner in ("claude", "native", "claude_proxy"):
        context_file = f".agentweave/context/{agent}.md"
        print(f"  claude --resume {session_id} --append-system-prompt-file {context_file}")
    elif runner == "kimi":
        yaml_path = AGENTWEAVE_DIR / f"agent-{agent}.yaml"
        if not yaml_path.exists():
            # YAML may not exist if --pilot wasn't used; generate it now
            try:
                _generate_kimi_agent_yaml(agent)
            except Exception as exc:
                print_warning(f"Could not generate agent YAML: {exc}")
        print(f"  kimi --agent-file .agentweave/agent-{agent}.yaml --session {session_id}")
    else:
        print(f"  Agent runner: {runner}")
        print(f"  Session ID: {session_id}")
        print(f"  Context file: .agentweave/context/{agent}.md")

    return 0


def cmd_relay(args: argparse.Namespace) -> int:
    """Generate relay prompt for an agent."""
    agent = args.agent
    run_flag = getattr(args, "run", False)

    # If --run is requested, delegate to cmd_run directly
    if run_flag:
        return cmd_run(args)

    # Get pending tasks for this agent
    pending_tasks = Task.list_all(assignee=agent, status="assigned")
    pending_tasks.extend(Task.list_all(assignee=agent, status="pending"))

    # Get messages for this agent
    messages = MessageBus.get_inbox(agent)

    # Get session
    session = Session.load()
    role = session.get_agent_role(agent) if session else "delegate"

    print("=" * 60)
    print(f"RELAY PROMPT FOR {agent.upper()}")
    print("=" * 60)
    print()
    print("Copy and paste this to the agent:")
    print()
    print("-" * 60)
    print()

    # Generate the prompt
    print(f"@{agent} - You have work in the AgentWeave collaboration system.")
    print()
    print(f"Your role: {role}")
    print("Collaboration guide: read .agentweave/protocol.md for commands, workflow, and protocol.")
    print("Project context: read .agentweave/shared/context.md before starting.")
    print()

    if pending_tasks:
        print(f"[TASK] You have {len(pending_tasks)} new task(s):")
        for task in pending_tasks:
            print(f"   - {task.title} ({task.id})")
        print()
        print("Please:")
        print("1. Check .agentweave/tasks/active/ for details")
        print("2. Run: agentweave task update <task_id> --status in_progress")
        print("3. Do the work")
        print("4. Run: agentweave task update <task_id> --status completed")
        print("5. Send a message when done: agentweave msg send --to <other> --message 'Done!'")
        print()

    if messages:
        print(f"[MSG] You have {len(messages)} unread message(s):")
        for msg in messages[:3]:  # Show first 3
            print(f"   From {msg.sender}: {msg.subject or '(no subject)'}")
        print()
        print("Check your inbox:")
        print(f"  agentweave inbox --agent {agent}")
        print()

    if not pending_tasks and not messages:
        print("No pending tasks or messages.")
        print()
        print("Useful commands:")
        print("  agentweave status           # Check overall status")
        print("  agentweave summary          # Quick summary")
        print()

    print("-" * 60)
    print()

    # For claude_proxy agents, show switching instructions
    if session:
        runner_config = session.get_runner_config(agent)
        if runner_config.get("runner") == "claude_proxy":
            from .runner import get_claude_session_id

            session_id = get_claude_session_id(agent)
            env_vars = runner_config.get("env_vars", {})
            api_key_var = env_vars.get("ANTHROPIC_API_KEY_VAR", "?")
            print("─" * 60)
            print(f"  {agent.upper()} is a claude_proxy agent — no native CLI")
            print("─" * 60)
            print(f"  Requires: export {api_key_var}=<your-api-key>")
            print()
            print("  Option 1 — Switch env vars then run manually:")
            print(f"    eval $(agentweave switch {agent})")
            if session_id:
                print(f"    claude --resume {session_id} -p '<paste prompt above>'")
            else:
                print("    claude -p '<paste prompt above>'")
            print()
            print("  Option 2 — Auto-run (sets env + launches Claude with relay prompt):")
            print(f"    agentweave run --agent {agent}")
            print()
            print("  Option 3 — Combined (from relay):")
            print(f"    agentweave relay --agent {agent} --run")
            print("─" * 60)
            print()

    return 0


def cmd_quick(args: argparse.Namespace) -> int:
    """Quick mode - single command for task delegation."""
    ensure_dirs()

    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    # Default sender is "user" (the human) unless explicitly specified
    sender = args.from_agent or "user"
    recipient = args.to
    task_desc = args.task

    try:
        # Create task with lock
        task = Task.create(
            title=task_desc[:100],  # Limit title length
            description=task_desc if len(task_desc) > 100 else "",
            assignee=recipient,
            assigner=sender,
            priority=args.priority or "medium",
        )

        # Validate before saving
        is_valid, errors = validate_task(task.to_dict())
        if not is_valid:
            print_error("Task validation failed:")
            for err in errors:
                print(f"  - {err}")
            return 1

        # Try to acquire lock
        try:
            if not acquire_lock(f"task_{task.id}", timeout=5):
                print_error("Could not create task - another process is working")
                return 1

            task.update(status="assigned")
            task.save()

            # Send task via transport if using HTTP (so Hub sees it)
            from .transport import get_transport

            transport = get_transport()
            if transport.get_transport_type() == "http":
                transport.send_task(task.to_dict())

            # Update session
            session.add_task(task.id)
            session.save()

        finally:
            release_lock(f"task_{task.id}")

        # Create simple message without task reference (cleaner UX)
        msg = Message.create(
            sender=sender,
            recipient=recipient,
            subject=f"Task: {task.title}",
            content=task_desc,
            message_type="delegation",
            task_id=task.id,
        )

        # Validate message
        is_valid, errors = validate_message(msg.to_dict())
        if is_valid:
            MessageBus.send(msg)

        print_success("Quick delegation complete!")
        print(f"   Task: {task.id}")
        print(f"   From: {sender}")
        print(f"   To: {recipient}")
        print()
        print("Next step:")
        print(f"  agentweave relay --agent {recipient}")
        print()
        print("This will generate the prompt to copy to the agent.")

        return 0

    except Exception as e:
        print_error(f"Failed: {e}")
        return 1


def cmd_task_create(args: argparse.Namespace) -> int:
    """Create a new task."""
    ensure_dirs()

    try:
        task = Task.create(
            title=args.title,
            description=args.description or "",
            assignee=args.assignee,
            assigner=args.assigner,
            priority=args.priority or "medium",
            requirements=args.requirements,
            acceptance_criteria=args.criteria,
        )

        # Validate
        is_valid, errors = validate_task(task.to_dict())
        if not is_valid:
            print_error("Task validation failed:")
            for err in errors:
                print(f"  - {err}")
            return 1

        # Lock and save
        if not acquire_lock(f"task_{task.id}", timeout=5):
            print_error("Could not create task - another process is working")
            return 1

        try:
            task.save()

            # Update session
            session = Session.load()
            if session:
                session.add_task(task.id)
                session.save()
        finally:
            release_lock(f"task_{task.id}")

        print_success(f"Created task: {task.id}")
        print(f"   Title: {task.title}")
        print(f"   Assignee: {task.assignee or 'Unassigned'}")
        print(f"   Priority: {task.priority}")
        print(f"\n   File: {AGENTWEAVE_DIR}/tasks/active/{task.id}.json")
        return 0

    except Exception as e:
        print_error(f"Failed to create task: {e}")
        return 1


def cmd_task_list(args: argparse.Namespace) -> int:
    """List tasks."""
    tasks = Task.list_all(
        status=args.status,
        assignee=args.assignee,
        active_only=args.active_only,
    )

    if not tasks:
        print_info("No tasks found.")
        return 0

    print(f"[TASK] Tasks ({len(tasks)}):")
    print("-" * 80)
    for task in tasks:
        print(f"[{task.status:12}] {task.id}: {task.title}")
        print(f"           Assignee: {task.assignee or 'Unassigned'}")
        print(f"           Priority: {task.priority}")
        print()

    return 0


def cmd_task_show(args: argparse.Namespace) -> int:
    """Show task details."""
    task = Task.load(args.task_id)
    if not task:
        print_error(f"Task not found: {args.task_id}")
        return 1

    print(task.to_markdown())
    return 0


def cmd_task_update(args: argparse.Namespace) -> int:
    """Update task status."""
    # Try to acquire lock
    if not acquire_lock(f"task_{args.task_id}", timeout=10):
        print_error("Task is currently being edited by another process")
        return 1

    try:
        task = Task.load(args.task_id)
        if not task:
            print_error(f"Task not found: {args.task_id}")
            return 1

        if args.status:
            old_status = task.status
            agent_name = getattr(args, "agent", None) or task.assignee
            task.update(agent=agent_name, status=args.status)
            print(f"Status: {old_status} -> {args.status}")

            # Move to completed if appropriate
            if args.status in ["completed", "approved"]:
                task.move_to_completed()

                # Update session
                session = Session.load()
                if session:
                    session.complete_task(task.id)
                    session.save()

                print("Moved to completed/")

        if args.note:
            notes = task.to_dict().get("notes", [])
            from .utils import now_iso

            notes.append(
                {
                    "timestamp": now_iso(),
                    "note": args.note,
                }
            )
            task.update(notes=notes)
            print("Added note")

        # Validate before saving
        is_valid, errors = validate_task(task.to_dict())
        if not is_valid:
            print_error("Validation failed:")
            for err in errors:
                print(f"  - {err}")
            return 1

        task.save()
        print_success(f"Updated task: {args.task_id}")
        return 0

    finally:
        release_lock(f"task_{args.task_id}")


def cmd_msg_send(args: argparse.Namespace) -> int:
    """Send a message."""
    ensure_dirs()

    try:
        message = Message.create(
            sender=args.from_agent or "unknown",
            recipient=args.to,
            content=args.message,
            subject=args.subject or "",
            message_type=args.type or "message",
            task_id=args.task_id,
        )

        # Validate
        is_valid, errors = validate_message(message.to_dict())
        if not is_valid:
            print_error("Message validation failed:")
            for err in errors:
                print(f"  - {err}")
            return 1

        MessageBus.send(message)

        print_success(f"Message sent: {message.id}")
        print(f"   To: {args.to}")
        print(f"   Subject: {args.subject or '(no subject)'}")
        print(f"\n   @{args.to} - Check your inbox: agentweave inbox --agent {args.to}")
        return 0

    except Exception as e:
        print_error(f"Failed to send message: {e}")
        return 1


def cmd_inbox(args: argparse.Namespace) -> int:
    """Check inbox."""
    agent = args.agent
    if agent:
        messages = MessageBus.get_inbox(agent)
    else:
        session = Session.load()
        if session:
            print_info("Checking inbox for all agents...")
            messages = []
            for ag in session.agent_names:
                messages += MessageBus.get_inbox(ag)
        else:
            # No session: fall back to default agents
            from .constants import DEFAULT_AGENTS

            messages = []
            for _ag in DEFAULT_AGENTS:
                messages += MessageBus.get_inbox(_ag)

    if not messages:
        print_info(f"No messages for {agent or 'anyone'}")
        return 0

    print(f"[IN] Messages ({len(messages)}):")
    print("-" * 80)
    for msg in messages:
        print(f"From: {msg.sender}")
        print(f"To: {msg.recipient}")
        print(f"Subject: {msg.subject or '(no subject)'}")
        print(f"Time: {msg.timestamp}")
        print(f"\n{msg.content}")
        print("-" * 80)

    return 0


def cmd_msg_read(args: argparse.Namespace) -> int:
    """Mark message as read."""
    if MessageBus.mark_read(args.msg_id):
        print_success(f"Message archived: {args.msg_id}")
        return 0
    else:
        print_error(f"Message not found: {args.msg_id}")
        return 1


def cmd_delegate(args: argparse.Namespace) -> int:
    """Quick delegation command."""

    quick_args = argparse.Namespace(
        from_agent=args.from_agent,
        to=args.to,
        task=args.task,
        priority=args.priority,
    )
    return cmd_quick(quick_args)


def cmd_update_template(args: argparse.Namespace) -> int:
    """Generate a prompt instructing an agent to update the kickoff template."""
    # Resolve template path
    template_path = getattr(args, "template_path", None)
    if not template_path:
        # Look for ai_context.md inside .agentweave/ (deployed by `agentweave init`)
        candidate = Path.cwd() / ".agentweave" / "ai_context.md"
        if candidate.exists():
            template_path = str(candidate)
        if not template_path:
            template_path = (
                ".agentweave/ai_context.md"
                "  (not found — run `agentweave init` first or use --template-path)"
            )

    focus = getattr(args, "focus", None) or (
        "all areas: new agent capabilities, multi-agent collaboration patterns, "
        "updated AI coding tools and best practices"
    )
    agent = args.agent
    today = date.today().isoformat()
    year = str(date.today().year)

    try:
        template = get_template("update_prompt")
    except FileNotFoundError:
        print_error("Template 'update_prompt' not found in src/agentweave/templates/")
        return 1

    prompt = (
        template.replace("{agent}", agent.capitalize())
        .replace("{template_path}", str(template_path))
        .replace("{focus}", focus)
        .replace("{date}", today)
        .replace("{year}", year)
    )

    separator = "=" * 70
    print(separator)
    print(f"[PROMPT] Copy and paste the following into {agent.capitalize()}:")
    print(separator)
    print(prompt)
    print(separator)
    return 0


def cmd_sync_context(args: argparse.Namespace) -> int:
    """Regenerate agent context files from ai_context.md source."""
    if not AGENTWEAVE_DIR.exists():
        print_error("No session found. Run: agentweave init")
        return 1

    # Load session to get agent list
    session = Session.load()
    if not session:
        print_error("Failed to load session. Run: agentweave init")
        return 1

    # Determine which agents to sync
    agent_arg = getattr(args, "agent", None)
    if agent_arg:
        agents_to_sync = [a.strip() for a in agent_arg.split(",") if a.strip()]
        # Validate agents
        for ag in agents_to_sync:
            if ag not in session.agent_names:
                print_warning(f"Agent '{ag}' not in session, skipping")
        agents_to_sync = [ag for ag in agents_to_sync if ag in session.agent_names]
    else:
        agents_to_sync = session.agent_names

    if not agents_to_sync:
        print_warning("No agents to sync")
        return 0

    force = getattr(args, "force", False)
    version_comment = f"AgentWeave v{__version__}"
    written_files: list = []
    skipped_files: list = []

    # Track which root baseline files (CLAUDE.md, AGENTS.md) have been written
    written_root: set = set()

    for ag in agents_to_sync:
        _runner = session.get_runner_config(ag).get("runner", "native")
        if _runner == "claude_proxy":
            root_filename = "CLAUDE.md"
        else:
            root_filename = AGENT_CONTEXT_FILES.get(ag, AGENT_CONTEXT_FILES_DEFAULT)
        root_path = Path.cwd() / root_filename

        # Write shared baseline file (once per unique filename)
        if root_filename not in written_root:
            if root_path.exists() and not force:
                skipped_files.append(root_filename)
            else:
                template_name = "claude_context" if root_filename == "CLAUDE.md" else "kimi_context"
                try:
                    context_content = get_template(template_name).replace(
                        "{version}", version_comment
                    )
                    with open(root_path, "w", encoding="utf-8") as f:
                        f.write(context_content)
                    written_files.append(root_filename)
                except FileNotFoundError:
                    print_error(f"Template '{template_name}' not found")
            written_root.add(root_filename)

        # Generate per-agent context profile in .agentweave/context/<agent>.md
        AGENT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        agent_ctx_path = AGENT_CONTEXT_DIR / f"{ag}.md"

        if agent_ctx_path.exists() and not force:
            skipped_files.append(f".agentweave/context/{ag}.md")
            continue

        agent_ctx_content = _build_agent_context(ag, session, version_comment)
        try:
            agent_ctx_path.write_text(agent_ctx_content, encoding="utf-8")
            written_files.append(f".agentweave/context/{ag}.md")
        except Exception as exc:
            print_error(f"Failed to write context for {ag}: {exc}")

    # Report results
    if written_files:
        print_success(f"Regenerated {len(written_files)} context file(s):")
        for fname in written_files:
            print(f"  • {fname}")

    if skipped_files:
        print_warning(f"Skipped {len(skipped_files)} existing file(s) (use --force to overwrite):")
        for fname in skipped_files:
            print(f"  • {fname}")

    if not written_files and not skipped_files:
        print_info("No files changed")

    return 0


def _build_agent_context(agent: str, session: "Session", version_comment: str) -> str:
    """Build the per-agent context file content for .agentweave/context/<agent>.md.

    Combines:
    - AgentWeave protocol header (session start checklist, MCP tools)
    - Compact team directory (all agents: name, runner, roles)
    - Full role guide(s) for this agent (from .agentweave/roles/)
    - Project context (from ai_context.md if present)
    """
    from .roles import get_agent_roles

    lines = []
    lines.append(f"# {agent} — AgentWeave Context")
    lines.append(
        f"<!-- Generated by {version_comment} — run `agentweave sync-context --force` to regenerate -->"
    )
    lines.append("")

    # --- AgentWeave Protocol section ---
    lines.append("## AgentWeave Protocol")
    lines.append("")
    lines.append(
        "You are participating in a multi-agent collaboration session managed by AgentWeave."
    )
    lines.append("")
    lines.append("### Session Start Checklist (run these steps each new session)")
    lines.append("")
    lines.append("1. Run `get_status()` to check session info and your assigned role")
    lines.append(f"2. Run `get_inbox('{agent}')` to check for unread messages")
    lines.append("3. Run `list_tasks()` to see active tasks assigned to you")
    lines.append("4. Read `.agentweave/shared/context.md` for current focus and decisions")
    lines.append(
        f"5. Check `.agentweave/agents/{agent}-checkpoint.md` for prior checkpoint if it exists"
    )
    lines.append("")
    lines.append("### MCP Tools Available")
    lines.append("")
    lines.append("- `get_inbox(agent)` — retrieve unread messages")
    lines.append("- `send_message(from, to, subject, content)` — send a message to another agent")
    lines.append("- `get_status()` — session overview")
    lines.append("- `list_tasks()` — see all tasks")
    lines.append("- `get_task(task_id)` — task details")
    lines.append("- `create_task(...)` — create a new task")
    lines.append("- `update_task(task_id, ...)` — update task status/assignee")
    lines.append("- `save_checkpoint(agent, content)` — save context before /compact")
    lines.append("- `ask_user(question)` — ask the human a question")
    lines.append("")
    lines.append("**Important:** In MCP mode, do NOT use `agentweave relay` CLI commands.")
    lines.append("Use the MCP tools above for all communication.")
    lines.append("")

    # --- Team Directory ---
    lines.append("## Team Directory")
    lines.append("")
    for ag in session.agent_names:
        runner_type = session.get_runner_config(ag).get("runner", "native")
        display_model = {
            "claude": "Claude",
            "claude_proxy": session.get_runner_config(ag).get("model", "Claude Proxy"),
            "kimi": "Kimi",
            "manual": "Manual",
        }.get(runner_type, runner_type.title())

        ag_roles = get_agent_roles(ag)
        roles_str = ", ".join(ag_roles) if ag_roles else "no role assigned"
        marker = " ← you" if ag == agent else ""
        lines.append(f"- **{ag}** ({display_model}) — {roles_str}{marker}")
    lines.append("")

    # --- Role Guide(s) ---
    agent_roles = get_agent_roles(agent)
    if agent_roles:
        lines.append("## Your Role(s)")
        lines.append("")
        for role_id in agent_roles:
            role_file = ROLES_DIR / f"{role_id}.md"
            if role_file.exists():
                try:
                    role_content = role_file.read_text(encoding="utf-8").strip()
                    lines.append(role_content)
                    lines.append("")
                except Exception:
                    lines.append(f"### {role_id}")
                    lines.append("(role guide file could not be read)")
                    lines.append("")
            else:
                lines.append(f"### {role_id}")
                lines.append(
                    f"(role guide not found — run `agentweave roles add {agent} {role_id}`)"
                )
                lines.append("")
    else:
        lines.append("## Your Role")
        lines.append("")
        lines.append("No role assigned. Ask the principal to assign one with:")
        lines.append(f"  agentweave roles add {agent} <role_id>")
        lines.append("")

    # --- Project Context ---
    ai_context_path = AGENTWEAVE_DIR / "ai_context.md"
    if ai_context_path.exists():
        try:
            ai_context = ai_context_path.read_text(encoding="utf-8").strip()
            if ai_context:
                lines.append("## Project Context")
                lines.append("")
                lines.append(ai_context)
                lines.append("")
        except Exception:
            pass

    return "\n".join(lines) + "\n"


def _kill_stale_watchdogs() -> list:
    """Find and terminate any running agentweave-watch processes.

    Scans /proc on Linux/WSL or uses tasklist on Windows. Safe to call
    before starting a new watchdog — cleans up stale daemons from previous
    sessions or terminals.

    Returns a list of killed PIDs.
    """
    import os

    killed: list = []
    my_pid = os.getpid()

    if os.name == "nt":
        import subprocess as _sp

        result = _sp.run(
            ["tasklist", "/FI", "IMAGENAME eq agentweave-watch.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                try:
                    pid = int(parts[1])
                    if pid != my_pid:
                        _sp.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                        killed.append(pid)
                except (ValueError, OSError):
                    pass
    else:
        proc_dir = "/proc"
        if not os.path.isdir(proc_dir):
            return killed
        for entry in os.listdir(proc_dir):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == my_pid:
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as fh:
                    cmdline = fh.read().decode("utf-8", errors="replace")
                args = cmdline.split("\x00")
                if any("agentweave-watch" in arg for arg in args):
                    import signal

                    os.kill(pid, signal.SIGTERM)
                    killed.append(pid)
            except (OSError, ProcessLookupError, PermissionError):
                pass

    return killed


def cmd_start(args: argparse.Namespace) -> int:
    """Launch the AgentWeave watchdog as a background daemon.

    Reads all agents from the active session and auto-pings each one when
    a new message arrives. PID is written to .agentweave/watchdog.pid.
    Any stale watchdog processes from previous sessions are killed first.
    """
    import subprocess as _sp

    from .constants import WATCHDOG_PID_FILE

    if not AGENTWEAVE_DIR.exists():
        print_error("No session found. Run: agentweave init")
        return 1

    # Check if .agentweave exists as a file (should be a directory)
    if AGENTWEAVE_DIR.is_file():
        print_error(".agentweave exists as a file, not a directory.")
        print_info("Remove it with: rm .agentweave")
        return 1

    # Kill any stale watchdog processes (from previous sessions or terminals)
    stale = _kill_stale_watchdogs()
    if stale:
        print_info(f"Killed {len(stale)} stale watchdog process(es): {stale}")

    # Clean up stale PID file if present
    if WATCHDOG_PID_FILE.exists():
        WATCHDOG_PID_FILE.unlink(missing_ok=True)

    from .constants import WATCHDOG_LOG_FILE

    retry_after = getattr(args, "retry_after", None) or 600  # default 10 min
    cmd = ["agentweave-watch", "--auto-ping", "--retry-after", str(retry_after)]

    import os as _os

    spawn_kwargs: dict = (
        {"creationflags": 0x00000008 | 0x08000000}  # DETACHED_PROCESS | CREATE_NO_WINDOW
        if _os.name == "nt"
        else {"start_new_session": True}
    )

    # Ensure log directory exists (handles edge case where .agentweave/ exists
    # but was created manually without proper subdirectories)
    AGENTWEAVE_DIR.mkdir(parents=True, exist_ok=True)
    WATCHDOG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(WATCHDOG_LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115
    proc = _sp.Popen(cmd, stdout=log_fh, stderr=log_fh, stdin=_sp.DEVNULL, **spawn_kwargs)

    WATCHDOG_PID_FILE.write_text(str(proc.pid))
    print_success(f"Watchdog started in background (PID {proc.pid})")
    print_info(f"Logs: {WATCHDOG_LOG_FILE}")
    print_info("Run 'agentweave stop' to stop it.")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    """Stop the background AgentWeave watchdog."""
    import os

    from .constants import WATCHDOG_PID_FILE

    if not WATCHDOG_PID_FILE.exists():
        print_info("No watchdog PID file found — nothing to stop.")
        return 0

    try:
        pid = int(WATCHDOG_PID_FILE.read_text().strip())
    except ValueError:
        WATCHDOG_PID_FILE.unlink()
        print_error("Corrupt PID file removed.")
        return 1

    try:
        if os.name == "nt":
            import subprocess as _sp2

            _sp2.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            import signal

            os.kill(pid, signal.SIGTERM)
        WATCHDOG_PID_FILE.unlink()
        print_success(f"Watchdog stopped (PID {pid})")
    except (OSError, ProcessLookupError):
        WATCHDOG_PID_FILE.unlink()
        print_warning(f"Process {pid} was already gone — PID file removed.")

    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Show structured activity log (messages, tasks, watchdog events)."""
    from .constants import EVENTS_LOG_FILE
    from .eventlog import format_event, get_events

    n = args.lines if hasattr(args, "lines") and args.lines else 50
    agent_filter = getattr(args, "agent", None)
    event_filter = getattr(args, "type", None)

    events = get_events(n=n, event_type=event_filter, agent=agent_filter)

    if not events:
        if not EVENTS_LOG_FILE.exists():
            print_info(
                "No events yet. Events are recorded automatically when you send messages, update tasks, or start the watchdog."
            )
        else:
            print_info("No events match the current filter.")
        return 0

    for entry in events:
        print(format_event(entry))

    # If --follow, stream new events
    if hasattr(args, "follow") and args.follow:
        import time as _time

        print_info("--- following events (Ctrl-C to stop) ---")
        try:
            with open(EVENTS_LOG_FILE, encoding="utf-8") as fh:
                fh.seek(0, 2)  # seek to end
                while True:
                    line = fh.readline()
                    if line:
                        line = line.strip()
                        if line:
                            try:
                                import json as _json

                                entry = _json.loads(line)
                                if agent_filter and agent_filter not in (
                                    entry.get("from"),
                                    entry.get("to"),
                                    entry.get("agent"),
                                    entry.get("assignee"),
                                ):
                                    continue
                                if event_filter and entry.get("event") != event_filter:
                                    continue
                                print(format_event(entry))
                            except Exception:
                                pass
                    else:
                        _time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    return 0


def cmd_mcp_setup(args: argparse.Namespace) -> int:
    """Configure the AgentWeave MCP server for all session agents."""
    import os as _os
    import subprocess as _sp

    server_cmd = "agentweave-mcp"
    # On Windows, agent CLIs are .cmd files — shell=True is required for subprocess to find them
    _shell = _os.name == "nt"

    # Build per-agent MCP registration commands using runner config.
    def _mcp_args(agent: str) -> list:
        from .constants import RUNNER_CONFIGS

        runner_type = (
            session.get_runner_config(agent).get("runner", "native") if session else "native"
        )
        rc = RUNNER_CONFIGS.get(runner_type, RUNNER_CONFIGS["native"])
        tpl = rc.get("mcp_add_cmd", ["{cli}", "mcp", "add", "{name}", "--", "{server_cmd}"])
        cli = rc.get("cli") or agent
        return [p.format(cli=cli, name="agentweave", server_cmd=server_cmd) for p in tpl]

    # Determine which agents to configure: session agents → DEFAULT_AGENTS fallback
    session = Session.load()
    agent_list = session.agent_names if session else DEFAULT_AGENTS

    results = {}
    for agent in agent_list:
        _runner_type = (
            session.get_runner_config(agent).get("runner", "native") if session else "native"
        )
        _rc = RUNNER_CONFIGS.get(_runner_type, RUNNER_CONFIGS["native"])
        _cli = _rc.get("cli") or agent
        mcp_args = _mcp_args(agent)
        try:
            check = _sp.run([_cli, "--version"], capture_output=True, shell=_shell)
            if check.returncode != 0:
                results[agent] = "not found"
                continue
        except FileNotFoundError:
            results[agent] = "not found"
            continue
        try:
            result = _sp.run(
                mcp_args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=_shell,
            )
            if result.returncode == 0:
                results[agent] = "ok"
            elif (
                "already exists" in result.stderr.lower()
                or "already exists" in result.stdout.lower()
            ):
                results[agent] = "already configured"
            else:
                results[agent] = f"failed: {result.stderr.strip()}"
        except FileNotFoundError:
            results[agent] = "not found"

    print()
    print("AgentWeave MCP server setup")
    print("-" * 40)
    for agent, status in results.items():
        icon = "[OK]" if status in ("ok", "already configured") else "[!!]"
        print(f"  {icon} {agent}: {status}")
    print()

    # Print manual commands only for agents that couldn't be configured automatically
    failed = [a for a, s in results.items() if s not in ("ok", "already configured")]
    if failed:
        print("Manual configuration for agents not found automatically:")
        print()
        for agent in failed:
            manual_args = _mcp_args(agent)
            print(f"    {' '.join(manual_args)}")
        print()

    print("Next step — start the background watchdog (one command, all agents):")
    print("  agentweave start")
    print()
    print("To stop it later:")
    print("  agentweave stop")
    print()

    # If --start flag passed, launch watchdog immediately
    if getattr(args, "start", False):
        print("Launching watchdog now...")
        return cmd_start(args)

    return 0


def cmd_transport_setup(args: argparse.Namespace) -> int:
    """Set up cross-machine transport."""
    import subprocess as _sp

    from .utils import save_json

    transport_type = args.type

    if transport_type == "git":
        # Verify we're inside a git repository
        result = _sp.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
        if result.returncode != 0:
            print_error("Not a git repository. Run `git init` first.")
            return 1

        remote = args.remote or "origin"
        branch = args.branch or "agentweave/collab"

        # Check if the collab branch already exists on the remote
        result = _sp.run(
            ["git", "ls-remote", "--heads", remote, branch],
            capture_output=True,
            text=True,
        )
        branch_exists = bool(result.stdout.strip())

        if not branch_exists:
            print_info(f"Creating orphan branch '{branch}' on {remote}...")
            # Build an empty tree and push an initial commit via git plumbing
            proc_b = _sp.run(["git", "mktree"], input=b"", capture_output=True)
            empty_tree = proc_b.stdout.decode().strip()
            proc_t = _sp.run(
                ["git", "commit-tree", empty_tree, "-m", "init: agentweave collab branch"],
                capture_output=True,
                text=True,
            )
            commit_sha = proc_t.stdout.strip()
            proc = _sp.run(
                ["git", "push", remote, f"{commit_sha}:refs/heads/{branch}"],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print_error(f"Failed to push branch to {remote}: {proc.stderr.strip()}")
                return 1
            print_success(f"Created orphan branch '{branch}' on {remote}")
        else:
            print_info(f"Using existing branch '{branch}' on {remote}")

        # Write .agentweave/transport.json
        AGENTWEAVE_DIR.mkdir(parents=True, exist_ok=True)
        cluster = getattr(args, "cluster", None) or ""
        config = {
            "type": "git",
            "remote": remote,
            "branch": branch,
            "poll_interval": 10,
        }
        if cluster:
            config["cluster"] = cluster
        save_json(TRANSPORT_CONFIG_FILE, config)

        print_success("Git transport configured!")
        print(f"   Remote:   {remote}")
        print(f"   Branch:   {branch}")
        if cluster:
            print(f"   Cluster:  {cluster}  (your workspace identity on the shared branch)")
        print(f"   Config:   {TRANSPORT_CONFIG_FILE}")
        print()
        print("Next steps:")
        print(f"  1. Your collaborator clones/has the repo with remote '{remote}'")
        if cluster:
            print("  2. They run: agentweave transport setup --type git --cluster <their-name>")
            print("  3. Address messages to them as: <their-cluster>.<their-agent>")
        else:
            print(f"  2. They run: agentweave transport setup --remote {remote} --type git")
        print(f"  3. Messages now sync via git branch '{branch}'")
        print()
        print("Start watching for incoming messages:")
        print("  agentweave-watch")
        return 0

    elif transport_type == "http":
        url = getattr(args, "url", None)
        api_key = getattr(args, "api_key", None)
        project_id = getattr(args, "project_id", None)

        if not url or not api_key or not project_id:
            print_error(
                "HTTP transport requires --url, --api-key, and --project-id.\n"
                "Example:\n"
                "  agentweave transport setup --type http \\\n"
                "    --url http://localhost:8000 \\\n"
                "    --api-key aw_live_... \\\n"
                "    --project-id proj-default"
            )
            return 1

        # Connectivity check
        import urllib.error as _urllib_err
        import urllib.request as _urllib_req

        status_url = f"{url.rstrip('/')}/api/v1/status"
        req = _urllib_req.Request(status_url)
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Accept", "application/json")
        try:
            with _urllib_req.urlopen(req, timeout=10) as resp:
                resp.read()
        except _urllib_err.HTTPError as exc:
            if exc.code == 401:
                print_error("Hub rejected the API key (401 Unauthorized). Check --api-key.")
            else:
                print_error(f"Hub returned HTTP {exc.code}. Check --url.")
            return 1
        except _urllib_err.URLError as exc:
            print_error(f"Cannot reach Hub at {url}: {exc.reason}")
            return 1

        # Write transport.json
        AGENTWEAVE_DIR.mkdir(parents=True, exist_ok=True)
        save_json(
            TRANSPORT_CONFIG_FILE,
            {
                "type": "http",
                "url": url,
                "api_key": api_key,
                "project_id": project_id,
            },
        )

        print_success("HTTP transport configured!")
        print(f"   URL:        {url}")
        print(f"   Project ID: {project_id}")
        print(f"   Config:     {TRANSPORT_CONFIG_FILE}")
        print()
        print("Next steps:")
        print("  agentweave quick --to kimi 'Test task'")
        print("  agentweave inbox --agent kimi")
        print()
        print("Human interaction:")
        print("  agentweave reply --id <question_id> 'Your answer'")
        return 0

    print_error(f"Unknown transport type: {transport_type}")
    return 1


def cmd_transport_status(_args: argparse.Namespace) -> int:
    """Show current transport configuration and status."""
    import subprocess as _sp

    from .utils import load_json as _load_json

    config = _load_json(TRANSPORT_CONFIG_FILE)
    if not config:
        print("[TRANSPORT] Type: local (default)")
        print("   No .agentweave/transport.json — using local filesystem")
        print("   To enable cross-machine sync:")
        print("     agentweave transport setup --type git")
        return 0

    transport_type = config.get("type", "local")
    print(f"[TRANSPORT] Type: {transport_type}")

    if transport_type == "git":
        remote = config.get("remote", "origin")
        branch = config.get("branch", "agentweave/collab")
        poll_interval = config.get("poll_interval", 10)
        cluster = config.get("cluster", "")
        print(f"   Remote:        {remote}")
        print(f"   Branch:        {branch}")
        print(f"   Poll interval: {poll_interval}s")
        if cluster:
            print(f"   Cluster:       {cluster}")

        # Connectivity check
        result = _sp.run(
            ["git", "ls-remote", "--heads", remote, branch],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            _sp.run(["git", "fetch", remote, branch, "--quiet"], capture_output=True)
            result2 = _sp.run(
                ["git", "ls-tree", f"{remote}/{branch}", "--name-only"],
                capture_output=True,
                text=True,
            )
            files = [f for f in result2.stdout.splitlines() if f.strip()]
            msg_files = [f for f in files if "-task-for-" not in f]
            task_files = [f for f in files if "-task-for-" in f]
            print("   Status:        connected")
            print(
                f"   Files on branch: {len(files)} ({len(msg_files)} messages, {len(task_files)} tasks)"
            )
        else:
            print(f"   Status:        cannot reach {remote}/{branch}")

    elif transport_type == "http":
        import urllib.error as _uerr
        import urllib.request as _ureq

        url = config.get("url", "")
        api_key = config.get("api_key", "")
        project_id = config.get("project_id", "")
        print(f"   URL:     {url or '(not set)'}")
        print(f"   Project: {project_id or '(not set)'}")
        if url and api_key:
            try:
                req = _ureq.Request(
                    f"{url.rstrip('/')}/api/v1/status",
                    headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                )
                with _ureq.urlopen(req, timeout=5) as resp:
                    import json as _json

                    data = _json.loads(resp.read())
                tasks_active = sum(data.get("task_counts", {}).values())
                msgs_pending = data.get("message_counts", {}).get("pending", 0)
                print("   Status:  connected")
                print(f"   Tasks:   {tasks_active} active")
                print(f"   Messages: {msgs_pending} pending")
            except (_uerr.URLError, _uerr.HTTPError, Exception) as exc:
                print(f"   Status:  unreachable ({exc})")
        else:
            print("   Status:  not configured")

    return 0


def cmd_transport_pull(_args: argparse.Namespace) -> int:
    """Force an immediate fetch from the remote transport."""
    from .transport import get_transport

    t = get_transport()
    if t.get_transport_type() == "local":
        print_info("Local transport — no pull needed")
        return 0

    print_info(f"Pulling from {t.get_transport_type()} transport...")
    session = Session.load()
    pull_agents = session.agent_names if session else VALID_AGENTS
    for agent in pull_agents:
        messages = t.get_pending_messages(agent)
        if messages:
            print(f"   {agent}: {len(messages)} pending message(s)")

    print_success("Pull complete")
    return 0


def cmd_hub_heartbeat(args: argparse.Namespace) -> int:
    """Publish an agent heartbeat to the Hub (HTTP transport only)."""
    from .utils import load_json as _load_json

    config = _load_json(TRANSPORT_CONFIG_FILE)
    if not config or config.get("type") != "http":
        print_info("No HTTP transport configured — hub-heartbeat is a no-op.")
        return 0

    from .transport.http import HttpTransport

    t = HttpTransport(
        url=config["url"],
        api_key=config["api_key"],
        project_id=config["project_id"],
    )
    agent = args.agent
    status = args.status or "active"
    message = args.message

    ok = t.push_heartbeat(agent, status=status, message=message)
    if ok:
        print_success(f"Heartbeat sent: {agent} [{status}]")
    else:
        print_error("Failed to send heartbeat — check Hub connectivity.")
        return 1
    return 0


def cmd_transport_disable(_args: argparse.Namespace) -> int:
    """Disable transport and revert to local filesystem."""
    if not TRANSPORT_CONFIG_FILE.exists():
        print_info("Already using local transport (no transport.json)")
        return 0

    TRANSPORT_CONFIG_FILE.unlink()
    print_success("Transport disabled — reverted to local filesystem")
    return 0


# ---------------------------------------------------------------------------
# Hub lifecycle commands (start, stop, status)
# ---------------------------------------------------------------------------

HUB_DIR = Path.home() / ".agentweave" / "hub"
HUB_COMPOSE_URL = (
    "https://raw.githubusercontent.com/gutohuida/AgentWeave/main/hub/docker-compose.yml"
)
HUB_ENV_URL = "https://raw.githubusercontent.com/gutohuida/AgentWeave/main/hub/.env.example"


def _hub_url(port: int = 8000) -> str:
    """Get the Hub base URL for a given port."""
    return f"http://localhost:{port}"


def _hub_health_url(port: int = 8000) -> str:
    """Get the Hub health endpoint URL for a given port."""
    return f"{_hub_url(port)}/health"


def _hub_setup_token_url(port: int = 8000) -> str:
    """Get the Hub setup token endpoint URL for a given port."""
    return f"{_hub_url(port)}/api/v1/setup/token"


def _docker_available() -> bool:
    """Check if Docker and docker compose are available."""
    if not shutil.which("docker"):
        return False
    # Check for docker compose (v2) or docker-compose (v1)
    result = subprocess.run(["docker", "compose", "version"], capture_output=True)
    if result.returncode == 0:
        return True
    # Fallback to docker-compose
    return bool(shutil.which("docker-compose"))


def _hub_health_check(port: int = 8000, timeout: int = 120) -> bool:
    """Poll Hub health endpoint until it responds or timeout."""
    import time as _time

    start = _time.time()
    while _time.time() - start < timeout:
        try:
            with urllib.request.urlopen(_hub_health_url(port), timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        _time.sleep(1)
    return False


def _fetch_setup_token(port: int = 8000) -> Optional[str]:
    """Fetch the API key from Hub's /setup/token endpoint (localhost only)."""
    import json as _json
    import urllib.request as _req

    try:
        with _req.urlopen(_hub_setup_token_url(port), timeout=5) as resp:
            data = _json.loads(resp.read())
            return data.get("api_key")
    except Exception:
        return None


def cmd_hub_start(args: argparse.Namespace) -> int:
    """Start the AgentWeave Hub Docker container."""
    import subprocess as _sp
    import urllib.request as _req

    port = getattr(args, "port", 8000)
    local = getattr(args, "local", False)
    hub_url = _hub_url(port)
    health_url = _hub_health_url(port)

    if not _docker_available():
        print_error("Docker is not available")
        print_info("Please install Docker: https://docs.docker.com/get-docker/")
        print_info("Docker Desktop is recommended for Windows/Mac users.")
        return 1

    # Check if Hub is already running on this port
    try:
        with _req.urlopen(health_url, timeout=2) as resp:
            if resp.status == 200:
                print_info(f"Hub is already running at {hub_url}")
                return 0
    except Exception:
        pass

    if local:
        # Local dev mode: build and run from ./hub/ in the current directory
        local_hub_dir = Path.cwd() / "hub"
        compose_file = local_hub_dir / "docker-compose.yml"
        if not compose_file.exists():
            print_error(f"Local hub not found: {compose_file}")
            print_info("Run this command from the AgentWeave repository root.")
            return 1

        print_info(f"Building and starting Hub from {local_hub_dir} on port {port}...")
        env = os.environ.copy()
        env["AW_PORT"] = str(port)
        result = _sp.run(
            ["docker", "compose", "up", "--build", "-d"],
            cwd=local_hub_dir,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            print_error(f"Failed to start Hub: {result.stderr}")
            return 1
    else:
        HUB_DIR.mkdir(parents=True, exist_ok=True)

        # Download docker-compose.yml if not present
        compose_file = HUB_DIR / "docker-compose.yml"
        if not compose_file.exists():
            print_info("Downloading Hub configuration...")
            try:
                _req.urlretrieve(HUB_COMPOSE_URL, compose_file)
            except Exception as exc:
                print_error(f"Failed to download docker-compose.yml: {exc}")
                return 1

        # Download .env if not present
        env_file = HUB_DIR / ".env"
        if not env_file.exists():
            try:
                _req.urlretrieve(HUB_ENV_URL, env_file)
            except Exception as exc:
                print_error(f"Failed to download .env: {exc}")
                return 1

        # Update .env with custom port if needed
        if port != 8000:
            try:
                env_content = env_file.read_text()
                # Replace or add HUB_HTTP_PORT
                if "HUB_HTTP_PORT=" in env_content:
                    env_content = env_content.replace("HUB_HTTP_PORT=8000", f"HUB_HTTP_PORT={port}")
                else:
                    env_content += f"\nHUB_HTTP_PORT={port}\n"
                env_file.write_text(env_content)
            except Exception as exc:
                print_warning(f"Could not update port in .env: {exc}")

        # Start the Hub
        print_info(f"Starting AgentWeave Hub on port {port}...")
        result = _sp.run(
            ["docker", "compose", "up", "-d"],
            cwd=HUB_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_error(f"Failed to start Hub: {result.stderr}")
            return 1

    # Wait for Hub to be healthy
    print_info("Waiting for Hub to be ready (this may take a while for first build)...")
    if not _hub_health_check(port=port, timeout=120):
        print_error("Hub failed to start within 120 seconds")
        if local:
            print_info("Check logs with: docker compose -f hub/docker-compose.yml logs")
        else:
            print_info(
                "Check logs with: docker compose -f ~/.agentweave/hub/docker-compose.yml logs"
            )
        return 1

    print_success(f"Hub ready at {hub_url}")
    return 0


def cmd_hub_stop(args: argparse.Namespace) -> int:
    """Stop the AgentWeave Hub Docker container."""
    import subprocess as _sp
    import urllib.request as _req

    port = getattr(args, "port", 8000)
    local = getattr(args, "local", False)
    health_url = _hub_health_url(port)

    # Check if Hub is running
    try:
        with _req.urlopen(health_url, timeout=2) as resp:
            if resp.status != 200:
                print_info("Hub is not running")
                return 0
    except Exception:
        print_info("Hub is not running")
        return 0

    if local:
        compose_dir = Path.cwd() / "hub"
        if not (compose_dir / "docker-compose.yml").exists():
            print_error(f"Local hub not found: {compose_dir / 'docker-compose.yml'}")
            print_info("Run this command from the AgentWeave repository root.")
            return 1
    else:
        if not HUB_DIR.exists():
            print_error("Hub directory not found. Did you run 'agentweave hub start'?")
            return 1
        compose_dir = HUB_DIR

    print_info("Stopping AgentWeave Hub...")
    env = os.environ.copy()
    env["AW_PORT"] = str(port)
    result = _sp.run(
        ["docker", "compose", "down"],
        cwd=compose_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print_error(f"Failed to stop Hub: {result.stderr}")
        return 1

    print_success("Hub stopped")
    return 0


def cmd_hub_status(args: argparse.Namespace) -> int:
    """Check the status of the AgentWeave Hub."""
    import json as _json
    import urllib.error as _uerr
    import urllib.request as _req

    port = getattr(args, "port", 8000)
    hub_url = _hub_url(port)
    health_url = _hub_health_url(port)

    try:
        with _req.urlopen(health_url, timeout=5) as resp:
            if resp.status == 200:
                data = _json.loads(resp.read())
                print("[HUB] Status: running")
                print(f"   URL:    {hub_url}")
                if data.get("version"):
                    print(f"   Version: {data['version']}")
                return 0
    except _uerr.HTTPError as exc:
        print(f"[HUB] Status: error (HTTP {exc.code})")
        return 1
    except Exception:
        pass

    print("[HUB] Status: stopped")
    print("       Run 'agentweave hub start' to start the Hub")
    return 0


def cmd_activate(_args: argparse.Namespace) -> int:
    """Activate the AgentWeave project - reconcile agentweave.yml with runtime state.

    This idempotent command:
    1. Configures transport (fetches API key from Hub if needed)
    2. Syncs agents from agentweave.yml to session.json
    3. Registers MCP server if not already registered
    4. Starts watchdog if not running
    5. Syncs jobs from agentweave.yml to Hub
    """
    from .config import (
        AGENTWEAVE_YML_PATH,
        ConfigValidationError,
        load_agentweave_yml,
    )

    # Check for agentweave.yml
    if not AGENTWEAVE_YML_PATH.exists():
        print_error("No agentweave.yml found. Run 'agentweave init' to create one.")
        return 1

    # Load configuration
    try:
        config = load_agentweave_yml()
    except ConfigValidationError as exc:
        print_error(f"Configuration error: {exc}")
        return 1
    except FileNotFoundError:
        print_error("Configuration file not found.")
        return 1

    print(f"[ACTIVATE] Project: {config.project.name}")
    print(f"           Mode: {config.project.mode}")
    print()

    # Step 1: Configure transport
    transport_result = _activate_transport(config)
    if transport_result != 0:
        return transport_result

    # Step 2: Sync agents
    agents_result = _activate_agents(config)
    if agents_result != 0:
        return agents_result

    # Step 3: MCP setup
    mcp_result = _activate_mcp()
    if mcp_result != 0:
        return mcp_result

    # Step 4: Watchdog
    watchdog_result = _activate_watchdog()
    if watchdog_result != 0:
        return watchdog_result

    # Step 5: Jobs sync (if jobs section exists)
    if config.jobs:
        jobs_result = _activate_jobs(config)
        if jobs_result != 0:
            return jobs_result

    # Step 6: Kimi pilot side effects
    _activate_kimi_pilot(config)

    # Step 7: Regenerate context files to reflect any role changes
    print()
    print("[CONTEXT] Regenerating agent context files...")
    try:
        sync_args = argparse.Namespace(force=False)
        cmd_sync_context(sync_args)
    except Exception as e:
        print(f"[WARNING] Context sync failed: {e}")
        print("          Run 'agentweave sync-context' manually after fixing the issue.")

    print()
    print_success("Activate complete!")
    print("Your project is ready for multi-agent collaboration.")
    print()
    print("Next steps:")
    print("  agentweave status          # Check session status")
    print("  agentweave relay --agent <name>  # Generate relay prompt for an agent")

    return 0


def _activate_transport(config: "AgentWeaveConfig") -> int:
    """Configure transport by fetching API key from Hub if needed."""
    import json as _json

    from .utils import load_json, save_json

    hub_url = config.hub.url

    # Check if transport is already configured with same URL
    existing = load_json(TRANSPORT_CONFIG_FILE)
    if existing and existing.get("type") == "http" and existing.get("url") == hub_url:
        print("[TRANSPORT] Already configured")
        return 0

    # Try to fetch setup token from Hub
    setup_token_url = f"{hub_url.rstrip('/')}/api/v1/setup/token"
    try:
        with urllib.request.urlopen(setup_token_url, timeout=5) as resp:
            data = _json.loads(resp.read())
            api_key = data.get("api_key")
            if api_key:
                # Save transport config
                TRANSPORT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                save_json(
                    TRANSPORT_CONFIG_FILE,
                    {
                        "type": "http",
                        "url": hub_url,
                        "api_key": api_key,
                        "project_id": "proj-default",
                    },
                )
                print(f"[TRANSPORT] Connected to Hub at {hub_url}")
                return 0
    except Exception as exc:
        print_warning(f"Could not auto-configure transport: {exc}")
        print_info("You may need to run 'agentweave transport setup' manually")
        # Continue anyway - transport might be optional for some workflows
        return 0

    return 0


def _activate_agents(config: "AgentWeaveConfig") -> int:
    """Sync agents from agentweave.yml to session.json."""
    session = Session.load()

    # Create session if it doesn't exist
    if not session:
        session = Session.create(
            name=config.project.name,
            principal=list(config.agents.keys())[0] if config.agents else "claude",
            mode=config.project.mode,
            agents=list(config.agents.keys()),
        )
        print(f"[SESSION] Created new session: {session.name}")

    # Build declared agents dict from config
    declared = {
        name: {
            "runner": agent.runner,
            "model": agent.model,
            "roles": agent.roles,
            "yolo": agent.yolo,
            "pilot": agent.pilot,
            "env": agent.env,
            "base_url": agent.base_url,
        }
        for name, agent in config.agents.items()
    }

    # Sync agents
    added, updated, orphaned = session.sync_agents(declared)

    # Print results
    if added:
        for name in added:
            print(f"[AGENTS] Added: {name}")
    if updated:
        for name in updated:
            print(f"[AGENTS] Updated: {name}")
    if orphaned:
        for name in orphaned:
            print(f"[AGENTS] Orphaned (in session, not in YAML): {name}")
            print(f"         Run 'agentweave agent remove {name}' to clean up")

    if not added and not updated and not orphaned:
        print("[AGENTS] Up to date")

    # Save session
    session.save()

    return 0


def _activate_mcp() -> int:
    """Register MCP server if not already registered."""
    import subprocess as _sp

    # Check if MCP is already registered by testing with a dummy call
    # This is a heuristic - we try to check if the mcp command works
    session = Session.load()
    if not session:
        return 0  # No session, skip MCP

    # Try to check if MCP is configured for the principal agent
    principal = session.principal
    runner_cfg = session.get_runner_config(principal)
    runner = runner_cfg.get("runner", "native")

    from .constants import RUNNER_CONFIGS

    rc = RUNNER_CONFIGS.get(runner, RUNNER_CONFIGS["native"])
    cli = rc.get("cli") or principal

    # Check if agentweave-mcp is already in the MCP list
    try:
        check_result = _sp.run(
            [cli, "mcp", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "agentweave" in check_result.stdout:
            print("[MCP] Already registered")
            return 0
    except Exception:
        pass  # Continue to registration attempt

    # Try to register
    try:
        mcp_args_result = cmd_mcp_setup(argparse.Namespace())
        if mcp_args_result == 0:
            print("[MCP] Registered")
        return mcp_args_result
    except Exception as exc:
        print_warning(f"Could not register MCP: {exc}")
        return 0  # Non-fatal


def _activate_watchdog() -> int:
    """Start watchdog if not already running."""
    import os

    from .constants import WATCHDOG_PID_FILE

    # Check if watchdog is running
    if WATCHDOG_PID_FILE.exists():
        try:
            pid = int(WATCHDOG_PID_FILE.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            print("[WATCHDOG] Already running")
            return 0
        except (OSError, ProcessLookupError, ValueError):
            # Stale PID file
            WATCHDOG_PID_FILE.unlink(missing_ok=True)

    # Start watchdog
    try:
        result = cmd_start(argparse.Namespace())
        if result == 0:
            print("[WATCHDOG] Started")
        return result
    except Exception as exc:
        print_warning(f"Could not start watchdog: {exc}")
        return 0  # Non-fatal


def _activate_jobs(config: "AgentWeaveConfig") -> int:
    """Sync jobs from agentweave.yml to Hub."""
    if not config.jobs:
        return 0

    from .transport import get_transport

    transport = get_transport()
    if transport.get_transport_type() != "http":
        print_warning("[JOBS] HTTP transport not configured, skipping job sync")
        return 0

    # Get existing jobs from Hub
    try:
        existing_jobs = transport.list_jobs()
        existing_by_name = {job.get("name", job.get("id")): job for job in existing_jobs}
    except Exception:
        existing_by_name = {}

    for job_name, job_config in config.jobs.items():
        job_data = {
            "name": job_name,
            "agent": job_config.agent,
            "message": job_config.prompt,
            "cron": job_config.schedule,
            "enabled": job_config.enabled,
        }

        if job_name in existing_by_name:
            # Update existing job
            job_id = existing_by_name[job_name]["id"]
            try:
                transport.update_job(job_id, job_data)
                status = "paused" if not job_config.enabled else "active"
                print(f"[JOBS] Updated: {job_name} ({status})")
            except Exception as exc:
                print_warning(f"Could not update job {job_name}: {exc}")
        else:
            # Create new job
            try:
                job_id = transport.create_job(job_data)
                if job_id:
                    print(f"[JOBS] Created: {job_name}")
                    if not job_config.enabled:
                        transport.update_job(job_id, {"enabled": False})
                        print(f"[JOBS] Paused: {job_name}")
            except Exception as exc:
                print_warning(f"Could not create job {job_name}: {exc}")

    return 0


def _activate_kimi_pilot(config: "AgentWeaveConfig") -> int:
    """Generate agent files for kimi pilot agents."""
    for agent_name, agent_config in config.agents.items():
        if agent_config.runner == "kimi" and agent_config.pilot:
            try:
                session = Session.load()
                if session is not None:
                    _refresh_kimi_pilot_yaml(agent_name, session)
                    print(f"[PILOT] Generated files for {agent_name}")
            except Exception:
                pass  # Non-fatal
    return 0


def cmd_reply(args: argparse.Namespace) -> int:
    """Reply to a question asked by an agent (HTTP transport only)."""
    from .utils import load_json as _load_json

    config = _load_json(TRANSPORT_CONFIG_FILE)
    if not config or config.get("type") != "http":
        print_error("The 'reply' command requires HTTP transport to be configured.")
        print_info("Run: agentweave transport setup --type http ...")
        return 1

    url = config["url"].rstrip("/")
    api_key = config["api_key"]
    question_id = args.id
    answer = args.answer

    # Guard: message IDs (msg-...) are not question IDs (q-...)
    if question_id.startswith("msg-"):
        print_error(
            f"'{question_id}' is a message ID, not a question ID.\n"
            "  agentweave reply answers questions created by ask_user() — IDs start with 'q-'.\n"
            "  To reply to a message use the send_message MCP tool, or:\n"
            "    agentweave msg send --to <agent> --message '...'"
        )
        return 1

    import json as _json
    import urllib.error as _uerr
    import urllib.request as _req

    body = _json.dumps({"answer": answer}).encode()
    request = _req.Request(
        f"{url}/api/v1/questions/{question_id}",
        data=body,
        method="PATCH",
    )
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")

    try:
        with _req.urlopen(request, timeout=10) as resp:
            resp.read()
        print_success(f"Answer submitted for question {question_id}")
        return 0
    except _uerr.HTTPError as exc:
        if exc.code == 404:
            print_error(f"Question '{question_id}' not found.")
        else:
            print_error(f"Hub returned HTTP {exc.code}: {exc.read().decode(errors='replace')}")
        return 1
    except _uerr.URLError as exc:
        print_error(f"Cannot reach Hub: {exc.reason}")
        return 1


def cmd_yolo(args: argparse.Namespace) -> int:
    """Enable or disable yolo mode for an agent."""
    from .session import Session

    session = Session.load()
    if not session:
        print_error("No session found. Run 'agentweave init' first.")
        return 1

    agent = args.agent

    # Show status for all agents if no --enable/--disable given
    if not args.enable and not args.disable:
        print_info("Yolo mode status:")
        for name in session.agent_names:
            flag = "ON" if session.get_agent_yolo(name) else "off"
            print(f"  {name}: {flag}")
        return 0

    if args.enable and args.disable:
        print_error("Specify either --enable or --disable, not both.")
        return 1

    try:
        enabled = args.enable
        session.set_agent_yolo(agent, enabled)
    except ValueError as exc:
        print_error(str(exc))
        return 1

    session.save()

    if enabled:
        flag_hint = "--dangerously-skip-permissions" if agent == "claude" else "--yolo"
        print_success(f"Yolo mode ENABLED for {agent} ({flag_hint} will be used)")
    else:
        print_success(f"Yolo mode DISABLED for {agent}")
    return 0


def cmd_agent_configure(args: argparse.Namespace) -> int:
    """Configure runner type for an agent (e.g. minimax/glm as claude_proxy)."""
    from .constants import CLAUDE_PROXY_PROVIDERS
    from .runner import get_claude_session_id
    from .validator import validate_runner_config

    agent = args.agent_name
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1
    if agent not in session.agent_names:
        print_error(
            f"Agent {agent!r} is not in the current session. "
            f"Known agents: {', '.join(session.agent_names)}"
        )
        return 1

    runner = args.runner
    base_url = args.base_url
    api_key_var = args.api_key_var
    model = args.model

    # Apply registry defaults for known claude_proxy providers when flags are omitted
    if runner == "claude_proxy" and agent in CLAUDE_PROXY_PROVIDERS:
        defaults = CLAUDE_PROXY_PROVIDERS[agent]
        if not base_url:
            base_url = defaults["base_url"]
        if not api_key_var:
            api_key_var = defaults["api_key_var"]
        if not model:
            model = defaults.get("model")

    # If runner not specified, use the known default or ask user to specify
    if runner is None:
        from .constants import AGENT_RUNNER_DEFAULTS

        runner = AGENT_RUNNER_DEFAULTS.get(agent, "native")

    env_vars: dict = {}
    if runner == "claude_proxy":
        if not base_url or not api_key_var:
            print_error(
                "claude_proxy runner requires --base-url and --api-key-var. "
                f"Known providers: {list(CLAUDE_PROXY_PROVIDERS.keys())}"
            )
            return 1
        env_vars = {
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_API_KEY_VAR": api_key_var,
        }

    is_valid, errors = validate_runner_config(runner, env_vars)
    if not is_valid:
        print_error("Runner config validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    session.set_runner_config(agent, runner, env_vars, model=model)

    # Handle pilot flag if specified
    if args.pilot is not None:
        session.set_agent_pilot(agent, args.pilot)
        pilot_status = "enabled" if args.pilot else "disabled"
        print_info(f"Pilot mode {pilot_status} for {agent}")

    if not session.save():
        print_error("Failed to save session")
        return 1

    # For kimi pilot agents: generate context file + agent YAML so the launch
    # command is ready before the user ever starts kimi.
    if args.pilot and runner == "kimi":
        try:
            AGENT_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
            agent_ctx_path = AGENT_CONTEXT_DIR / f"{agent}.md"
            version_comment = f"AgentWeave v{__version__}"
            agent_ctx_content = _build_agent_context(agent, session, version_comment)
            agent_ctx_path.write_text(agent_ctx_content, encoding="utf-8")
            _generate_kimi_agent_yaml(agent)
            print_info(f"Generated agent context: .agentweave/context/{agent}.md")
            print_info(f"Generated agent YAML:    .agentweave/agent-{agent}.yaml")
            print()
            print("Start kimi with:")
            print(f"  kimi --agent-file .agentweave/agent-{agent}.yaml")
            print()
            print("After kimi gives you a session ID, register it:")
            print(f"  agentweave session register --agent {agent} --session <session-id>")
        except Exception as exc:
            print_warning(f"Could not generate kimi pilot files: {exc}")

    # Ensure the agent has a root-level context file
    if runner == "claude_proxy":
        root_filename = "CLAUDE.md"
    else:
        root_filename = AGENT_CONTEXT_FILES.get(agent, AGENT_CONTEXT_FILES_DEFAULT)
    root_path = Path.cwd() / root_filename
    if not root_path.exists():
        template_name = "claude_context" if root_filename == "CLAUDE.md" else "kimi_context"
        try:
            context_content = get_template(template_name).replace(
                "{version}", f"AgentWeave v{__version__}"
            )
            root_path.write_text(context_content, encoding="utf-8")
            print_info(f"Created context file: {root_filename}")
        except FileNotFoundError:
            pass  # Non-fatal

    print_success(f"Runner configured: {agent} → {runner}")
    if runner == "claude_proxy":
        print(f"  ANTHROPIC_BASE_URL = {base_url}")
        print(f"  ANTHROPIC_API_KEY  = ${api_key_var}  (resolved from your shell at runtime)")
        print(f"  MODEL              = {model}")
        existing_session = get_claude_session_id(agent)
        if existing_session:
            print(f"  Saved session ID   = {existing_session}")
        print()
        print("  To activate this agent in your shell:")
        print(f"    eval $(agentweave switch {agent})")
        print("  Or to run it directly:")
        print(f"    agentweave run --agent {agent}")
    elif runner == "kimi":
        print()
        print("  This agent uses the Kimi Code CLI.")
        print(f"  Register the MCP server:  agentweave mcp setup --agent {agent}")
        print(f"  Generate context file:    agentweave sync-context --agent {agent}")
    return 0


def cmd_agent_set_session(args: argparse.Namespace) -> int:
    """Manually register a Claude session ID for an agent."""
    from .runner import save_claude_session_id

    agent = args.agent_name
    session_id = args.session_id

    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1
    if agent not in session.agent_names:
        print_error(f"Agent {agent!r} is not in the current session")
        return 1

    save_claude_session_id(agent, session_id)
    print_success(f"Session ID saved for {agent}: {session_id}")
    print(f"  Next run: agentweave run --agent {agent}  (will use --resume {session_id})")
    return 0


def cmd_agent_set_model(args: argparse.Namespace) -> int:
    """Set the model for a claude_proxy agent.

    Usage: agentweave agent set-model <agent_name> <model_name>
    """
    agent = args.agent_name
    model = args.model

    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1
    if agent not in session.agent_names:
        print_error(f"Agent {agent!r} is not in the current session")
        return 1

    runner_config = session.get_runner_config(agent)
    if runner_config.get("runner") != "claude_proxy":
        print_error(
            f"{agent} is not configured as claude_proxy. "
            f"Run 'agentweave agent configure {agent} --runner claude_proxy' first."
        )
        return 1

    # Get existing config
    env_vars = runner_config.get("env_vars", {})

    # Update model
    session.set_runner_config(agent, "claude_proxy", env_vars, model=model)
    if not session.save():
        print_error("Failed to save session")
        return 1

    print_success(f"Model set for {agent}: {model}")
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    """Write a context checkpoint skeleton for an agent before compacting."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    agent = args.agent
    reason = getattr(args, "reason", "manual")
    note = getattr(args, "note", None)

    checkpoints_dir = SHARED_DIR / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    active_tasks = Task.list_all(active_only=True)
    agent_tasks = [t for t in active_tasks if t.assignee == agent]
    task_rows = (
        "\n".join(f"| {t.id} | {t.title[:60]} | {t.status} |" for t in agent_tasks)
        or "| (none) | | |"
    )

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dt_display = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"{agent}-{ts}.md"
    filepath = checkpoints_dir / filename

    note_line = f"*Note: {note}*\n" if note else ""
    content = f"""# Context Checkpoint — {agent} — {dt_display}

## Session Intent
<!-- One paragraph: what was this session trying to accomplish -->

## Active Tasks at Checkpoint
| Task ID | Title | Status |
|---------|-------|--------|
{task_rows}

## Files Modified This Session
<!-- List only files you wrote or edited. Format: `path/to/file` — what changed -->

## Decisions Made
<!-- 1. [Decision] — [why — this is the critical part; the code exists, the rationale does not] -->

## Blockers and Open Questions
<!-- - [ ] [Unresolved item] -->

## Next Steps
<!-- 1. [Exact first action after resuming] -->

## Verification Commands
```bash
# add commands to confirm current state
```

---
*Checkpoint saved by: {agent}*
*AgentWeave session: {session.id} ({session.name})*
*Reason: {reason}*
{note_line}"""

    filepath.write_text(content, encoding="utf-8")

    print_success(f"Checkpoint created: {filepath}")
    print("\nFill in the qualitative sections, then run /compact")
    print("After compacting, re-read this file to resume:")
    print(f"  {filepath}")
    return 0


def cmd_roles_list(_args: argparse.Namespace) -> int:
    """List all agents and their assigned roles."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    config = load_roles_config()

    print("[ROLES] Agent role assignments")
    print("-" * 60)

    for agent in session.agent_names:
        principal_marker = " [principal]" if agent == session.principal else ""
        roles_str = format_agent_roles(agent, config)
        print(f"   {agent}{principal_marker}: {roles_str}")

    print()
    print("Commands:")
    print("  agentweave roles add <agent> <role>")
    print("  agentweave roles remove <agent> <role>")
    print("  agentweave roles set <agent> <role1,role2,...>")
    print("  agentweave roles available")

    return 0


def cmd_jobs_create(args: argparse.Namespace) -> int:
    """Create a new AI job."""
    from .jobs import Job
    from .transport import get_transport

    try:
        job = Job.create(
            name=args.name,
            agent=args.agent,
            message=args.message,
            cron=args.cron,
            session_mode=args.session_mode,
        )
    except ValueError as e:
        print_error(f"Invalid job: {e}")
        return 1

    # Save via transport (local or Hub)
    transport = get_transport()
    try:
        job_id = transport.create_job(job.to_dict())
        if job_id:
            print_success(f"Job created: {job_id}")
            print(f"  Name: {job.name}")
            print(f"  Agent: {job.agent}")
            print(f"  Cron: {job.cron}")
            print(f"  Next run: {job.next_run or 'Not computed'}")
            return 0
        else:
            print_error("Failed to create job via transport")
            return 1
    except Exception as e:
        print_error(f"Failed to create job: {e}")
        return 1


def cmd_jobs_list(args: argparse.Namespace) -> int:
    """List all jobs."""
    from .transport import get_transport

    transport = get_transport()
    try:
        jobs = transport.list_jobs(agent=getattr(args, "agent", None))
    except Exception as e:
        print_error(f"Failed to list jobs: {e}")
        return 1

    if not jobs:
        print_info("No jobs found")
        return 0

    # Print table header
    print(
        f"{'ID':<15} {'Name':<20} {'Agent':<12} {'Cron':<15} {'Enabled':<8} {'Last Run':<20} {'Next Run':<20}"
    )
    print("-" * 120)

    for job in jobs:
        job_id = job.get("id", "unknown")[:14]
        name = job.get("name", "Untitled")[:19]
        agent = job.get("agent", "unknown")[:11]
        cron = job.get("cron", "-")[:14]
        enabled = "Yes" if job.get("enabled", True) else "No"
        last_run = job.get("last_run", "Never")[:19]
        next_run = job.get("next_run", "-")[:19]

        print(
            f"{job_id:<15} {name:<20} {agent:<12} {cron:<15} {enabled:<8} {last_run:<20} {next_run:<20}"
        )

    print(f"\nTotal: {len(jobs)} job(s)")
    return 0


def cmd_jobs_get(args: argparse.Namespace) -> int:
    """Show job details and history."""
    from .transport import get_transport

    transport = get_transport()
    try:
        job = transport.get_job(args.job_id)
    except Exception as e:
        print_error(f"Failed to get job: {e}")
        return 1

    if not job:
        print_error(f"Job not found: {args.job_id}")
        return 1

    print(f"Job: {job.get('name', 'Untitled')}")
    print(f"  ID: {job.get('id')}")
    print(f"  Agent: {job.get('agent')}")
    print(f"  Message: {job.get('message', '-')}")
    print(f"  Cron: {job.get('cron')}")
    print(f"  Session Mode: {job.get('session_mode', 'new')}")
    print(f"  Enabled: {'Yes' if job.get('enabled', True) else 'No'}")
    print(f"  Created: {job.get('created_at', '-')}")
    print(f"  Last Run: {job.get('last_run', 'Never')}")
    print(f"  Next Run: {job.get('next_run', '-')}")
    print(f"  Run Count: {job.get('run_count', 0)}")

    history = job.get("history", [])
    if history:
        print(f"\nLast {len(history)} run(s):")
        print(f"{'Fired At':<25} {'Status':<10} {'Trigger':<10} {'Session ID':<20}")
        print("-" * 70)
        for run in history:
            fired_at = run.get("fired_at", "-")[:24]
            status = run.get("status", "-")
            trigger = run.get("trigger", "-")
            session_id = (run.get("session_id") or "-")[:19]
            print(f"{fired_at:<25} {status:<10} {trigger:<10} {session_id:<20}")
    else:
        print("\nNo run history")

    return 0


def cmd_jobs_pause(args: argparse.Namespace) -> int:
    """Pause/disable a job."""
    from .transport import get_transport

    transport = get_transport()
    try:
        success = transport.update_job(args.job_id, {"enabled": False})
        if success:
            print_success(f"Job paused: {args.job_id}")
            return 0
        else:
            print_error(f"Failed to pause job: {args.job_id}")
            return 1
    except Exception as e:
        print_error(f"Failed to pause job: {e}")
        return 1


def cmd_jobs_resume(args: argparse.Namespace) -> int:
    """Resume/enable a job."""
    from .transport import get_transport

    transport = get_transport()
    try:
        success = transport.update_job(args.job_id, {"enabled": True})
        if success:
            print_success(f"Job resumed: {args.job_id}")
            return 0
        else:
            print_error(f"Failed to resume job: {args.job_id}")
            return 1
    except Exception as e:
        print_error(f"Failed to resume job: {e}")
        return 1


def cmd_jobs_delete(args: argparse.Namespace) -> int:
    """Delete a job."""
    from .transport import get_transport

    if not args.force:
        response = input(f"Delete job {args.job_id}? [y/N]: ")
        if response.lower() != "y":
            print_info("Cancelled")
            return 0

    transport = get_transport()
    try:
        success = transport.delete_job(args.job_id)
        if success:
            print_success(f"Job deleted: {args.job_id}")
            return 0
        else:
            print_error(f"Failed to delete job: {args.job_id}")
            return 1
    except Exception as e:
        print_error(f"Failed to delete job: {e}")
        return 1


def cmd_jobs_run(args: argparse.Namespace) -> int:
    """Run a job immediately."""
    from .transport import get_transport

    transport = get_transport()
    try:
        success = transport.fire_job(args.job_id, trigger="manual")
        if success:
            print_success(f"Job fired: {args.job_id}")
            return 0
        else:
            print_error(f"Failed to fire job: {args.job_id}")
            return 1
    except Exception as e:
        print_error(f"Failed to fire job: {e}")
        return 1


def cmd_roles_add(args: argparse.Namespace) -> int:
    """Add a role to an agent."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    agent = args.agent
    role = args.role

    if agent not in session.agent_names:
        print_error(f"Agent '{agent}' is not in the current session")
        print_info(f"Session agents: {', '.join(session.agent_names)}")
        return 1

    # Load current config
    config = load_roles_config()

    # Add the role
    success, message, updated_config = add_role_to_agent(agent, role, config)
    if not success or updated_config is None:
        print_error(message)
        return 1
    config = updated_config

    # Save config
    if not save_roles_config(config):
        print_error("Failed to save roles configuration")
        return 1

    # Sync to Hub if HTTP transport
    sync_roles_to_hub(config)

    # Copy role markdown file to .agentweave/roles/
    if copy_role_md_file(role):
        print_info(f"Role guide copied: .agentweave/roles/{role}.md")
    else:
        print_warning(f"Role guide not found for: {role}")

    print_success(message)

    # Show updated roles
    current_roles = get_agent_roles(agent, config)
    if current_roles:
        print(f"   Current roles: {', '.join(current_roles)}")

    # Regenerate kimi agent YAML if this agent is a pilot kimi agent
    _refresh_kimi_pilot_yaml(agent, session)

    return 0


def cmd_roles_remove(args: argparse.Namespace) -> int:
    """Remove a role from an agent."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    agent = args.agent
    role = args.role

    if agent not in session.agent_names:
        print_error(f"Agent '{agent}' is not in the current session")
        print_info(f"Session agents: {', '.join(session.agent_names)}")
        return 1

    # Load current config
    config = load_roles_config()
    if not config:
        print_error("No roles configuration found")
        return 1

    # Remove the role
    success, message, updated_config = remove_role_from_agent(agent, role, config)
    if not success or updated_config is None:
        print_error(message)
        return 1
    config = updated_config

    # Save config
    if not save_roles_config(config):
        print_error("Failed to save roles configuration")
        return 1

    # Sync to Hub if HTTP transport
    sync_roles_to_hub(config)

    print_success(message)

    # Show updated roles
    current_roles = get_agent_roles(agent, config)
    if current_roles:
        print(f"   Current roles: {', '.join(current_roles)}")
    else:
        print("   Current roles: none")

    return 0


def cmd_roles_set(args: argparse.Namespace) -> int:
    """Set/replace all roles for an agent."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1

    agent = args.agent
    roles_str = args.roles

    if agent not in session.agent_names:
        print_error(f"Agent '{agent}' is not in the current session")
        print_info(f"Session agents: {', '.join(session.agent_names)}")
        return 1

    # Parse roles
    roles_list = [r.strip() for r in roles_str.split(",") if r.strip()]

    if not roles_list:
        print_error("No valid roles provided")
        return 1

    # Load current config
    config = load_roles_config()

    # Set the roles
    success, message, updated_config = set_agent_roles(agent, roles_list, config)
    if not success or updated_config is None:
        print_error(message)
        return 1
    config = updated_config

    # Save config
    if not save_roles_config(config):
        print_error("Failed to save roles configuration")
        return 1

    # Sync to Hub if HTTP transport
    sync_roles_to_hub(config)

    # Copy role markdown files for all new roles
    roles_copied = []
    roles_missing = []
    for role_id in roles_list:
        if copy_role_md_file(role_id):
            roles_copied.append(f"{role_id}.md")
        else:
            roles_missing.append(role_id)

    if roles_copied:
        print_info(f"Role guides copied: {', '.join(roles_copied)}")
    if roles_missing:
        print_warning(f"Role guides not found: {', '.join(roles_missing)}")

    print_success(message)

    # Regenerate kimi agent YAML if this agent is a pilot kimi agent
    _refresh_kimi_pilot_yaml(agent, session)

    return 0


def cmd_roles_available(_args: argparse.Namespace) -> int:
    """List all available role types."""
    roles = get_available_roles()

    print("[AVAILABLE ROLES]")
    print("-" * 60)

    for role_id, label, description in roles:
        print(f"   {role_id}")
        print(f"      Label: {label}")
        if description:
            print(f"      Responsibilities: {description}")
        print()

    print("Usage:")
    print("  agentweave roles add <agent> <role_id>")
    print("  agentweave roles remove <agent> <role_id>")

    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    """Output eval-able shell export commands to switch env vars for a claude_proxy agent.

    Usage: eval $(agentweave switch minimax)
    """
    from .runner import get_agent_env, get_missing_api_key_var

    agent = args.agent
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1
    if agent not in session.agent_names:
        print_error(f"Agent {agent!r} is not in the current session")
        return 1

    runner_config = session.get_runner_config(agent)
    if runner_config.get("runner") != "claude_proxy":
        print_info(
            f"{agent} uses runner '{runner_config.get('runner', 'native')}' — "
            f"no env var switch needed"
        )
        return 0

    missing = get_missing_api_key_var(session, agent)
    if missing:
        print_error(
            f"${missing} is not set in the current shell. "
            f"Export it first:\n  export {missing}=<your-api-key>"
        )
        return 1

    env_vars = get_agent_env(session, agent)
    for key, value in env_vars.items():
        # Print eval-able export statements
        print(f"export {key}={value}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Set env vars for a claude_proxy agent and launch Claude with a relay prompt."""
    import os
    import subprocess as _subprocess

    from .runner import (
        build_claude_proxy_cmd,
        get_agent_env,
        get_claude_session_id,
        get_missing_api_key_var,
    )

    agent = args.agent
    session = Session.load()
    if not session:
        print_error("No session found. Run: agentweave init")
        return 1
    if agent not in session.agent_names:
        print_error(f"Agent {agent!r} is not in the current session")
        return 1

    runner_config = session.get_runner_config(agent)
    runner = runner_config.get("runner", "native")
    model = runner_config.get("model")

    if runner == "manual":
        print_warning(f"{agent} is configured as a manual agent — use relay and copy-paste instead")
        print(f"  agentweave relay --agent {agent}")
        return 0

    if runner != "claude_proxy":
        print_warning(
            f"{agent} uses runner '{runner}' which has its own CLI. "
            f"Run it directly or use relay."
        )
        return 0

    missing = get_missing_api_key_var(session, agent)
    if missing:
        print_error(
            f"${missing} is not set in the current shell. "
            f"Export it first:\n  export {missing}=<your-api-key>"
        )
        return 1

    env_overrides = get_agent_env(session, agent)
    session_id = get_claude_session_id(agent)

    # Build relay prompt inline (same content as cmd_relay)
    pending_tasks = Task.list_all(assignee=agent, status="assigned")
    pending_tasks.extend(Task.list_all(assignee=agent, status="pending"))
    messages = MessageBus.get_inbox(agent)
    role = session.get_agent_role(agent)

    lines = [f"@{agent} - You have work in the AgentWeave collaboration system."]
    lines.append(f"Your role: {role}")
    lines.append(
        "Collaboration guide: read .agentweave/protocol.md for commands, workflow, and protocol."
    )
    lines.append("Project context: read .agentweave/shared/context.md before starting.")
    if pending_tasks:
        lines.append(f"[TASK] You have {len(pending_tasks)} new task(s):")
        for task in pending_tasks:
            lines.append(f"   - {task.title} ({task.id})")
        lines.append("Run: agentweave task list  to see full details")
    if messages:
        lines.append(f"[MSG] You have {len(messages)} unread message(s).")
        lines.append(f"Run: agentweave inbox --agent {agent}")
    if not pending_tasks and not messages:
        lines.append("No pending tasks or messages. Check agentweave status for context.")
    prompt = "\n".join(lines)

    cmd = build_claude_proxy_cmd(agent, prompt, session_id=session_id, model=model)

    proc_env = {**os.environ, **env_overrides}

    print_info(
        f"Running {agent} via claude proxy "
        f"(ANTHROPIC_BASE_URL={env_overrides.get('ANTHROPIC_BASE_URL', '?')})"
    )
    if session_id:
        print_info(f"Resuming session: {session_id}")
    print(f"Command: {' '.join(cmd)}")
    print()

    result = _subprocess.run(cmd, env=proc_env)
    return result.returncode


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentweave",
        description="AgentWeave - Multi-agent AI collaboration framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agentweave init --project "My API" --principal claude --agents claude,kimi,gemini
  agentweave quick --to kimi "Implement authentication"
  agentweave relay --agent kimi
  agentweave summary
  agentweave task list
  agentweave inbox --agent gemini
  agentweave transport setup --type git --cluster alice

For more help: https://github.com/gutohuida/AgentWeave
        """,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init
    init_parser = subparsers.add_parser("init", help="Initialize session")
    init_parser.add_argument("--project", "-p", help="Project name")
    init_parser.add_argument(
        "--principal",
        default="claude",
        help="Principal (lead) agent, e.g. claude (default: claude)",
    )
    init_parser.add_argument(
        "--agents",
        help=(
            f"[DEPRECATED] Comma-separated agent list. "
            f"Agents are now defined in agentweave.yml. "
            f"Default: {','.join(DEFAULT_AGENTS)}"
        ),
    )
    init_parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        default="hierarchical",
        help="Collaboration mode (default: hierarchical)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing session",
    )

    # Checkpoint
    checkpoint_parser = subparsers.add_parser(
        "checkpoint",
        help="Write a context checkpoint for an agent before compacting",
    )
    checkpoint_parser.add_argument(
        "--agent",
        "-a",
        required=True,
        help="Agent name (e.g. claude, kimi)",
    )
    checkpoint_parser.add_argument(
        "--reason",
        choices=["token_threshold", "phase_complete", "pre_handoff", "pre_sleep", "manual"],
        default="manual",
        help="Why the checkpoint is being written (default: manual)",
    )
    checkpoint_parser.add_argument(
        "--note",
        help="Optional free-text note to include in the checkpoint",
    )

    # Status
    subparsers.add_parser("status", help="Show session status")

    # Summary (NEW)
    subparsers.add_parser("summary", help="Quick summary for relay decisions")

    # Session
    session_parser = subparsers.add_parser("session", help="Session management commands")
    session_subparsers = session_parser.add_subparsers(dest="session_command")

    session_register = session_subparsers.add_parser(
        "register", help="Register a session ID for a pilot agent"
    )
    session_register.add_argument(
        "--agent", "-a", required=True, help="Agent name to register session for"
    )
    session_register.add_argument(
        "--session", "-s", required=True, dest="session_id", help="Session ID to register"
    )

    # Relay
    relay_parser = subparsers.add_parser("relay", help="Generate relay prompt for agent")
    relay_parser.add_argument(
        "--agent",
        "-a",
        required=True,
        help="Agent to generate prompt for (e.g. kimi, gemini, codex)",
    )
    relay_parser.add_argument(
        "--run",
        action="store_true",
        help="For claude_proxy agents: set env vars and launch Claude automatically",
    )

    # Agent configure / set-session
    agent_parser = subparsers.add_parser("agent", help="Agent runner configuration")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    agent_configure = agent_subparsers.add_parser(
        "configure", help="Set runner type and env vars for an agent"
    )
    agent_configure.add_argument("agent_name", help="Agent name (must be in current session)")
    agent_configure.add_argument(
        "--runner",
        choices=["claude", "native", "claude_proxy", "kimi", "manual"],
        help="Runner type (default: auto-detected from known providers)",
    )
    agent_configure.add_argument(
        "--base-url",
        dest="base_url",
        help="ANTHROPIC_BASE_URL for claude_proxy agents (e.g. https://api.minimax.chat/v1)",
    )
    agent_configure.add_argument(
        "--api-key-var",
        dest="api_key_var",
        help="Name of the shell env var holding the API key (e.g. MINIMAX_API_KEY)",
    )
    agent_configure.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name for claude_proxy agents (e.g., MiniMax-M2.5, glm-4)",
    )
    agent_configure.add_argument(
        "--pilot",
        dest="pilot",
        action="store_true",
        default=None,
        help="Enable pilot mode for this agent (manual control, disables auto-execution)",
    )
    agent_configure.add_argument(
        "--no-pilot",
        dest="pilot",
        action="store_false",
        default=None,
        help="Disable pilot mode for this agent (default)",
    )

    agent_set_session = agent_subparsers.add_parser(
        "set-session", help="Manually register a Claude session ID for an agent"
    )
    agent_set_session.add_argument("agent_name", help="Agent name")
    agent_set_session.add_argument("session_id", help="Claude session ID (from claude --list)")

    agent_set_model = agent_subparsers.add_parser(
        "set-model", help="Set the model for a claude_proxy agent"
    )
    agent_set_model.add_argument("agent_name", help="Agent name (e.g., minimax)")
    agent_set_model.add_argument("model", help="Model name (e.g., MiniMax-M2.5)")
    agent_set_model.set_defaults(func=cmd_agent_set_model)

    # Switch env vars for a claude_proxy agent
    switch_parser = subparsers.add_parser(
        "switch",
        help="Output eval-able export commands for a claude_proxy agent",
    )
    switch_parser.add_argument("agent", help="Agent to switch to (e.g. minimax, glm)")

    # Run a claude_proxy agent directly
    run_parser = subparsers.add_parser(
        "run",
        help="Set env vars and launch Claude for a claude_proxy agent",
    )
    run_parser.add_argument("--agent", "-a", required=True, help="Agent to run (e.g. minimax)")

    # Quick
    quick_parser = subparsers.add_parser("quick", help="Quick task delegation (single command)")
    quick_parser.add_argument(
        "--to",
        "-t",
        required=True,
        help="Delegate to (any agent name)",
    )
    quick_parser.add_argument(
        "--from-agent",
        "-f",
        help="Delegate from (any agent name)",
    )
    quick_parser.add_argument(
        "--priority",
        choices=["low", "medium", "high", "critical"],
        default="medium",
        help="Task priority",
    )
    quick_parser.add_argument(
        "task",
        help="Task description",
    )

    # Task commands
    task_parser = subparsers.add_parser("task", help="Task management")
    task_subparsers = task_parser.add_subparsers(dest="task_command")

    # Task create
    task_create = task_subparsers.add_parser("create", help="Create task")
    task_create.add_argument("--title", "-t", required=True, help="Task title")
    task_create.add_argument("--description", "-d", help="Task description")
    task_create.add_argument(
        "--assignee",
        "-a",
        help="Assign to agent (any agent name, e.g. kimi, gemini)",
    )
    task_create.add_argument(
        "--assigner",
        help="Assigned by agent",
    )
    task_create.add_argument(
        "--priority",
        choices=["low", "medium", "high", "critical"],
        default="medium",
        help="Task priority",
    )
    task_create.add_argument(
        "--requirements",
        nargs="+",
        help="Task requirements",
    )
    task_create.add_argument(
        "--criteria",
        nargs="+",
        help="Acceptance criteria",
    )

    # Task list
    task_list = task_subparsers.add_parser("list", help="List tasks")
    task_list.add_argument(
        "--assignee",
        help="Filter by assignee (any agent name)",
    )
    task_list.add_argument(
        "--status",
        help="Filter by status",
    )
    task_list.add_argument(
        "--active-only",
        action="store_true",
        help="Show only active tasks",
    )

    # Task show
    task_show = task_subparsers.add_parser("show", help="Show task details")
    task_show.add_argument("task_id", help="Task ID")

    # Task update
    task_update = task_subparsers.add_parser("update", help="Update task")
    task_update.add_argument("task_id", help="Task ID")
    task_update.add_argument(
        "--status",
        choices=[
            "pending",
            "assigned",
            "in_progress",
            "completed",
            "under_review",
            "revision_needed",
            "approved",
            "rejected",
        ],
        help="New status",
    )
    task_update.add_argument("--note", help="Add a note")

    # Message commands
    msg_parser = subparsers.add_parser("msg", help="Message management")
    msg_subparsers = msg_parser.add_subparsers(dest="msg_command")

    # Send message
    msg_send = msg_subparsers.add_parser("send", help="Send a message")
    msg_send.add_argument(
        "--to",
        "-t",
        required=True,
        help="Recipient (any agent name)",
    )
    msg_send.add_argument(
        "--from-agent",
        "-f",
        help="Sender (any agent name)",
    )
    msg_send.add_argument("--subject", "-s", help="Message subject")
    msg_send.add_argument(
        "--message",
        "-m",
        required=True,
        help="Message content",
    )
    msg_send.add_argument(
        "--type",
        choices=["message", "delegation", "review", "discussion"],
        default="message",
        help="Message type",
    )
    msg_send.add_argument("--task-id", help="Related task ID")

    # Read message
    msg_read = msg_subparsers.add_parser("read", help="Mark message as read")
    msg_read.add_argument("msg_id", help="Message ID")

    # Inbox
    inbox_parser = subparsers.add_parser("inbox", help="Check inbox")
    inbox_parser.add_argument(
        "--agent",
        "-a",
        help="Check for specific agent (any agent name)",
    )

    # Delegate shortcut
    delegate_parser = subparsers.add_parser("delegate", help="Quick task delegation")
    delegate_parser.add_argument(
        "--to",
        "-t",
        required=True,
        help="Delegate to (any agent name)",
    )
    delegate_parser.add_argument(
        "--from-agent",
        "-f",
        help="Delegate from (any agent name)",
    )
    delegate_parser.add_argument(
        "--task",
        required=True,
        help="Task description",
    )
    delegate_parser.add_argument(
        "--description",
        "-d",
        help="Detailed description",
    )
    delegate_parser.add_argument(
        "--priority",
        choices=["low", "medium", "high", "critical"],
        default="medium",
        help="Task priority",
    )

    # update-template
    update_tmpl_parser = subparsers.add_parser(
        "update-template",
        help="Generate a prompt to update the kickoff template with new AI best practices",
    )
    update_tmpl_parser.add_argument(
        "--agent",
        "-a",
        required=True,
        help="Which agent receives and executes the update prompt (e.g. claude, kimi, gemini)",
    )
    update_tmpl_parser.add_argument(
        "--template-path",
        "-p",
        default=None,
        dest="template_path",
        help="Path to the template file (default: searches parent dirs for template.txt)",
    )
    update_tmpl_parser.add_argument(
        "--focus",
        "-f",
        default=None,
        help="Optional focus area e.g. 'sub-agents', 'security', 'kimi-capabilities'",
    )

    # sync-context
    sync_context_parser = subparsers.add_parser(
        "sync-context",
        help="Regenerate agent context files from .agentweave/ai_context.md",
    )
    sync_context_parser.add_argument(
        "--agent",
        "-a",
        default=None,
        help="Comma-separated list of agents to sync (default: all session agents)",
    )
    sync_context_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing agent context files",
    )

    # Start / stop watchdog daemon
    start_parser = subparsers.add_parser(
        "start", help="Start the watchdog daemon in the background"
    )
    start_parser.add_argument(
        "--retry-after",
        type=int,
        default=600,
        metavar="SECONDS",
        help="Re-ping an agent if their message is unread after this many seconds (default: 600 = 10min)",
    )
    subparsers.add_parser("stop", help="Stop the background watchdog daemon")

    # Log viewer
    log_parser = subparsers.add_parser(
        "log", help="View structured activity log (messages, tasks, watchdog)"
    )
    log_parser.add_argument(
        "-n",
        "--lines",
        type=int,
        default=50,
        help="Number of recent events to show (default: 50)",
    )
    log_parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow log in real time (like tail -f)",
    )
    log_parser.add_argument(
        "--agent",
        help="Filter events by agent name",
    )
    log_parser.add_argument(
        "--type",
        help="Filter by event type (msg_sent, msg_read, task_created, task_status, watchdog_started, ...)",
    )

    # MCP commands
    mcp_parser = subparsers.add_parser("mcp", help="MCP server management")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_setup_parser = mcp_subparsers.add_parser(
        "setup",
        help="Configure agentweave-mcp in all session agents",
    )
    mcp_setup_parser.add_argument(
        "--start",
        action="store_true",
        help="Also launch the background watchdog immediately after setup",
    )

    # Transport commands
    transport_parser = subparsers.add_parser(
        "transport",
        help="Configure cross-machine transport (git/http)",
    )
    transport_subparsers = transport_parser.add_subparsers(dest="transport_command")

    # transport setup
    transport_setup = transport_subparsers.add_parser("setup", help="Set up transport backend")
    transport_setup.add_argument(
        "--type",
        "-t",
        choices=["git", "http"],
        required=True,
        help="Transport type",
    )
    transport_setup.add_argument(
        "--remote",
        "-r",
        default="origin",
        help="Git remote name (default: origin)",
    )
    transport_setup.add_argument(
        "--branch",
        "-b",
        default="agentweave/collab",
        help="Git orphan branch name (default: agentweave/collab)",
    )
    transport_setup.add_argument(
        "--cluster",
        "-c",
        default=None,
        help=(
            "Your workspace name on the shared branch (e.g. alice). "
            "Use when multiple people/machines share the same git remote. "
            "Messages will be stamped '{cluster}.{agent}' so each workspace "
            "can be addressed individually."
        ),
    )
    # HTTP transport args
    transport_setup.add_argument(
        "--url",
        default=None,
        help="Hub URL (http transport only), e.g. http://localhost:8000",
    )
    transport_setup.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="Hub API key (http transport only), e.g. aw_live_...",
    )
    transport_setup.add_argument(
        "--project-id",
        dest="project_id",
        default=None,
        help="Hub project ID (http transport only), e.g. proj-default",
    )

    # transport status
    transport_subparsers.add_parser("status", help="Show transport status")

    # transport pull
    transport_subparsers.add_parser("pull", help="Force immediate fetch from remote")

    # transport disable
    transport_subparsers.add_parser("disable", help="Disable transport, revert to local")

    # Activate command
    subparsers.add_parser(
        "activate",
        help="Activate project - reconcile agentweave.yml with runtime state",
    )

    # Hub commands (lifecycle management)
    hub_parser = subparsers.add_parser(
        "hub",
        help="Manage the AgentWeave Hub Docker container",
    )
    hub_subparsers = hub_parser.add_subparsers(dest="hub_command")

    hub_start = hub_subparsers.add_parser(
        "start",
        help="Start the Hub container (downloads config if needed)",
    )
    hub_start.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port to expose the Hub on (default: 8000)",
    )
    hub_start.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Build and run from ./hub/ (for Hub development)",
    )

    hub_stop = hub_subparsers.add_parser(
        "stop",
        help="Stop the Hub container",
    )
    hub_stop.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port the Hub is running on (default: 8000)",
    )
    hub_stop.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Stop the locally-built Hub (for Hub development)",
    )

    hub_status = hub_subparsers.add_parser(
        "status",
        help="Check if the Hub is running",
    )
    hub_status.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port to check for Hub (default: 8000)",
    )

    # Hub heartbeat (http transport only)
    hb_parser = subparsers.add_parser(
        "hub-heartbeat",
        help="Publish agent status to the Hub (requires HTTP transport)",
    )
    hb_parser.add_argument("--agent", "-a", required=True, help="Agent name")
    hb_parser.add_argument(
        "--status",
        "-s",
        choices=["active", "idle", "waiting"],
        default="active",
        help="Agent status (default: active)",
    )
    hb_parser.add_argument("--message", "-m", help="Optional status message")

    # Yolo mode toggle
    yolo_parser = subparsers.add_parser("yolo", help="Enable/disable yolo mode for an agent")
    yolo_parser.add_argument("--agent", required=True, help="Agent name (e.g. claude, kimi)")
    yolo_parser.add_argument("--enable", action="store_true", help="Enable yolo mode")
    yolo_parser.add_argument("--disable", action="store_true", help="Disable yolo mode")

    # Jobs management
    jobs_parser = subparsers.add_parser("jobs", help="Manage AI Jobs (scheduled agent tasks)")
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command")

    # jobs create
    jobs_create = jobs_subparsers.add_parser("create", help="Create a new scheduled job")
    jobs_create.add_argument("--name", "-n", required=True, help="Job name")
    jobs_create.add_argument("--agent", "-a", required=True, help="Target agent name")
    jobs_create.add_argument("--message", "-m", required=True, help="Message to send to agent")
    jobs_create.add_argument(
        "--cron", "-c", required=True, help="Cron expression (e.g., '0 9 * * 1-5')"
    )
    jobs_create.add_argument(
        "--session-mode",
        choices=["new", "resume"],
        default="new",
        help="Session mode: new (fresh session) or resume (continue previous)",
    )

    # jobs list
    jobs_list = jobs_subparsers.add_parser("list", help="List all jobs")
    jobs_list.add_argument("--agent", "-a", help="Filter by agent name")

    # jobs get
    jobs_get = jobs_subparsers.add_parser("get", help="Show job details and history")
    jobs_get.add_argument("job_id", help="Job ID")

    # jobs pause
    jobs_pause = jobs_subparsers.add_parser("pause", help="Pause/disable a job")
    jobs_pause.add_argument("job_id", help="Job ID")

    # jobs resume
    jobs_resume = jobs_subparsers.add_parser("resume", help="Resume/enable a job")
    jobs_resume.add_argument("job_id", help="Job ID")

    # jobs delete
    jobs_delete = jobs_subparsers.add_parser("delete", help="Delete a job")
    jobs_delete.add_argument("job_id", help="Job ID")
    jobs_delete.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    # jobs run
    jobs_run = jobs_subparsers.add_parser("run", help="Run a job immediately")
    jobs_run.add_argument("job_id", help="Job ID")

    # Roles management
    roles_parser = subparsers.add_parser("roles", help="Manage agent roles")
    roles_subparsers = roles_parser.add_subparsers(dest="roles_command")

    # roles list
    roles_subparsers.add_parser("list", help="List all agents and their roles")

    # roles add
    roles_add = roles_subparsers.add_parser("add", help="Add a role to an agent")
    roles_add.add_argument("agent", help="Agent name (e.g., claude, kimi)")
    roles_add.add_argument("role", help=f"Role ID (e.g., {', '.join(VALID_ROLE_IDS[:3])}, ...)")

    # roles remove
    roles_remove = roles_subparsers.add_parser("remove", help="Remove a role from an agent")
    roles_remove.add_argument("agent", help="Agent name")
    roles_remove.add_argument("role", help="Role ID to remove")

    # roles set
    roles_set = roles_subparsers.add_parser("set", help="Set/replace all roles for an agent")
    roles_set.add_argument("agent", help="Agent name")
    roles_set.add_argument(
        "roles", help="Comma-separated role IDs (e.g., 'backend_dev,code_reviewer')"
    )

    # roles available
    roles_subparsers.add_parser("available", help="List all available role types")

    # Reply to agent questions (Hub / http transport only)
    reply_parser = subparsers.add_parser(
        "reply",
        help="Reply to a question asked by an agent (requires HTTP transport)",
    )
    reply_parser.add_argument(
        "--id",
        required=True,
        dest="id",
        help="Question ID (e.g. q-abc123)",
    )
    reply_parser.add_argument(
        "answer",
        help="Your answer text",
    )

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point."""
    # Ensure stdout/stderr handle Unicode (e.g. emoji in messages) on Windows
    import sys as _sys

    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(_sys.stderr, "reconfigure"):
        _sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    from .logging_handlers import _configure_logging

    _configure_logging()

    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if not parsed_args.command:
        parser.print_help()
        return 0

    # Route commands
    try:
        if parsed_args.command == "init":
            return cmd_init(parsed_args)
        elif parsed_args.command == "start":
            return cmd_start(parsed_args)
        elif parsed_args.command == "stop":
            return cmd_stop(parsed_args)
        elif parsed_args.command == "log":
            return cmd_log(parsed_args)
        elif parsed_args.command == "status":
            return cmd_status(parsed_args)
        elif parsed_args.command == "summary":
            return cmd_summary(parsed_args)
        elif parsed_args.command == "relay":
            return cmd_relay(parsed_args)
        elif parsed_args.command == "quick":
            return cmd_quick(parsed_args)
        elif parsed_args.command == "task":
            if parsed_args.task_command == "create":
                return cmd_task_create(parsed_args)
            elif parsed_args.task_command == "list":
                return cmd_task_list(parsed_args)
            elif parsed_args.task_command == "show":
                return cmd_task_show(parsed_args)
            elif parsed_args.task_command == "update":
                return cmd_task_update(parsed_args)
            else:
                parser.parse_args(["task", "--help"])
                return 0
        elif parsed_args.command == "msg":
            if parsed_args.msg_command == "send":
                return cmd_msg_send(parsed_args)
            elif parsed_args.msg_command == "read":
                return cmd_msg_read(parsed_args)
            else:
                parser.parse_args(["msg", "--help"])
                return 0
        elif parsed_args.command == "inbox":
            return cmd_inbox(parsed_args)
        elif parsed_args.command == "delegate":
            return cmd_delegate(parsed_args)
        elif parsed_args.command == "update-template":
            return cmd_update_template(parsed_args)
        elif parsed_args.command == "sync-context":
            return cmd_sync_context(parsed_args)
        elif parsed_args.command == "mcp":
            if parsed_args.mcp_command == "setup":
                return cmd_mcp_setup(parsed_args)
            else:
                parser.parse_args(["mcp", "--help"])
                return 0
        elif parsed_args.command == "transport":
            if parsed_args.transport_command == "setup":
                return cmd_transport_setup(parsed_args)
            elif parsed_args.transport_command == "status":
                return cmd_transport_status(parsed_args)
            elif parsed_args.transport_command == "pull":
                return cmd_transport_pull(parsed_args)
            elif parsed_args.transport_command == "disable":
                return cmd_transport_disable(parsed_args)
            else:
                parser.parse_args(["transport", "--help"])
                return 0
        elif parsed_args.command == "activate":
            return cmd_activate(parsed_args)
        elif parsed_args.command == "hub":
            if parsed_args.hub_command == "start":
                return cmd_hub_start(parsed_args)
            elif parsed_args.hub_command == "stop":
                return cmd_hub_stop(parsed_args)
            elif parsed_args.hub_command == "status":
                return cmd_hub_status(parsed_args)
            else:
                parser.parse_args(["hub", "--help"])
                return 0
        elif parsed_args.command == "reply":
            return cmd_reply(parsed_args)
        elif parsed_args.command == "hub-heartbeat":
            return cmd_hub_heartbeat(parsed_args)
        elif parsed_args.command == "yolo":
            return cmd_yolo(parsed_args)
        elif parsed_args.command == "roles":
            if parsed_args.roles_command == "list":
                return cmd_roles_list(parsed_args)
            elif parsed_args.roles_command == "add":
                return cmd_roles_add(parsed_args)
            elif parsed_args.roles_command == "remove":
                return cmd_roles_remove(parsed_args)
            elif parsed_args.roles_command == "set":
                return cmd_roles_set(parsed_args)
            elif parsed_args.roles_command == "available":
                return cmd_roles_available(parsed_args)
            else:
                parser.parse_args(["roles", "--help"])
                return 0
        elif parsed_args.command == "agent":
            if parsed_args.agent_command == "configure":
                return cmd_agent_configure(parsed_args)
            elif parsed_args.agent_command == "set-session":
                return cmd_agent_set_session(parsed_args)
            else:
                parser.parse_args(["agent", "--help"])
                return 0
        elif parsed_args.command == "session":
            if parsed_args.session_command == "register":
                return cmd_session_register(parsed_args)
            else:
                parser.parse_args(["session", "--help"])
                return 0
        elif parsed_args.command == "switch":
            return cmd_switch(parsed_args)
        elif parsed_args.command == "run":
            return cmd_run(parsed_args)
        elif parsed_args.command == "checkpoint":
            return cmd_checkpoint(parsed_args)
        elif parsed_args.command == "jobs":
            if parsed_args.jobs_command == "create":
                return cmd_jobs_create(parsed_args)
            elif parsed_args.jobs_command == "list":
                return cmd_jobs_list(parsed_args)
            elif parsed_args.jobs_command == "get":
                return cmd_jobs_get(parsed_args)
            elif parsed_args.jobs_command == "pause":
                return cmd_jobs_pause(parsed_args)
            elif parsed_args.jobs_command == "resume":
                return cmd_jobs_resume(parsed_args)
            elif parsed_args.jobs_command == "delete":
                return cmd_jobs_delete(parsed_args)
            elif parsed_args.jobs_command == "run":
                return cmd_jobs_run(parsed_args)
            else:
                parser.parse_args(["jobs", "--help"])
                return 0
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
