#!/usr/bin/env python3
"""Command-line interface for AgentWeave."""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import __version__
from .constants import (
    AGENT_CONTEXT_FILES,
    AGENT_CONTEXT_FILES_DEFAULT,
    AGENTWEAVE_DIR,
    DEFAULT_AGENT_ROLES,
    DEFAULT_AGENTS,
    DEV_ROLE_LABELS,
    SHARED_DIR,
    TRANSPORT_CONFIG_FILE,
    VALID_AGENTS,
    VALID_MODES,
)
from .locking import acquire_lock, release_lock
from .messaging import Message, MessageBus
from .session import Session
from .task import Task
from .templates import get_skill_template, get_template, list_skill_templates
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
    if AGENTWEAVE_DIR.exists() and not args.force:
        if AGENTWEAVE_DIR.is_file():
            print_error(".agentweave exists as a file, not a directory.")
            print_info("Remove it with: rm .agentweave")
            return 1
        print_warning(".agentweave/ already exists. Use --force to overwrite.")
        return 1

    # Handle case where .agentweave exists as a file with --force
    if AGENTWEAVE_DIR.exists() and args.force and AGENTWEAVE_DIR.is_file():
        try:
            AGENTWEAVE_DIR.unlink()
            print_info("Removed existing .agentweave file.")
        except OSError as e:
            print_error(f"Cannot remove .agentweave file: {e}")
            return 1

    ensure_dirs()

    try:
        # Parse agent list: --agents claude,kimi,gemini  OR fall back to default
        agents_arg = getattr(args, "agents", None)
        agent_list = None
        if agents_arg:
            agent_list = [a.strip() for a in agents_arg.split(",") if a.strip()]

        principal = args.principal or "claude"

        session = Session.create(
            name=args.project or "Unnamed Project",
            principal=principal,
            mode=args.mode or "hierarchical",
            agents=agent_list,
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
- `ROLES.md` — Agent role assignments (edit freely)
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

        # Write ROLES.md — agent role assignments (auto-filled, user-editable)
        try:
            role_rows = []
            for ag in session.agent_names:
                dev_role_key = DEFAULT_AGENT_ROLES.get(ag, "fullstack_dev")
                dev_role_label = DEV_ROLE_LABELS.get(dev_role_key, "Full Stack Developer")
                session_role = session.get_agent_role(ag)
                responsibility = _role_responsibility(dev_role_key)
                role_rows.append(
                    f"| **{ag}** | {dev_role_label} (`{session_role}`) | {responsibility} |"
                )

            roles_content = (
                get_template("roles_template")
                .replace("{project_name}", session.name)
                .replace("{session_id}", session.id)
                .replace("{mode}", session.mode)
                .replace("{principal}", session.principal)
                .replace("{role_rows}", "\n".join(role_rows))
            )
            roles_path = AGENTWEAVE_DIR / "ROLES.md"
            with open(roles_path, "w", encoding="utf-8") as f:
                f.write(roles_content)
        except FileNotFoundError:
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
            root_filename = AGENT_CONTEXT_FILES.get(ag, AGENT_CONTEXT_FILES_DEFAULT)
            if root_filename in written_root_files:
                continue  # multiple agents may share AGENTS.md — only write once
            root_path = Path.cwd() / root_filename
            if root_path.exists():
                written_root_files.add(root_filename)
                continue  # never overwrite an existing file
            template_name = "claude_context" if ag == "claude" else "kimi_context"
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
        print("     ROLES.md             <- agent role assignments (edit freely)")
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

        return 0

    except ValueError as e:
        print_error(str(e))
        return 1


def _role_responsibility(role_key: str) -> str:
    """Return a short responsibility description for a dev role."""
    responsibilities = {
        "tech_lead": "Architecture decisions, code review, integration",
        "architect": "System design, data models, API contracts",
        "backend_dev": "APIs, database, business logic, server-side",
        "frontend_dev": "UI components, styling, client-side state",
        "fullstack_dev": "Backend and frontend features",
        "qa_engineer": "Tests, quality assurance, edge cases",
        "devops_engineer": "CI/CD, infrastructure, deployment",
        "security_engineer": "Security review, auth/authz, vulnerability audit",
        "data_engineer": "Data pipelines, ETL, analytics",
        "ml_engineer": "ML models, training pipelines, inference",
        "technical_writer": "Documentation, READMEs, API docs",
        "code_reviewer": "Pull request reviews, style enforcement",
        "project_manager": "Task tracking, progress coordination",
    }
    return responsibilities.get(role_key, "General development tasks")


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

    print("\n[AGENTS]")
    for agent in all_agents:
        role = session.agents.get(agent, {}).get("role", "unknown")
        inbox = MessageBus.get_inbox(agent)
        agent_tasks = [t for t in active_tasks if t.assignee == agent]
        in_prog = [t for t in agent_tasks if t.status == "in_progress"]
        waiting = [t for t in agent_tasks if t.status in ("pending", "assigned")]
        review = [t for t in agent_tasks if t.status in ("completed", "under_review")]
        principal_marker = " [principal]" if agent == session.principal else ""
        print(f"   {agent}{principal_marker} ({role})")
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


def cmd_relay(args: argparse.Namespace) -> int:
    """Generate relay prompt for an agent."""
    agent = args.agent

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

    for ag in agents_to_sync:
        root_filename = AGENT_CONTEXT_FILES.get(ag, AGENT_CONTEXT_FILES_DEFAULT)
        root_path = Path.cwd() / root_filename

        if root_path.exists() and not force:
            skipped_files.append(root_filename)
            continue

        # Select template based on agent
        template_name = "claude_context" if ag == "claude" else "kimi_context"
        try:
            context_content = get_template(template_name).replace("{version}", version_comment)
            with open(root_path, "w", encoding="utf-8") as f:
                f.write(context_content)
            written_files.append(root_filename)
        except FileNotFoundError:
            print_error(f"Template '{template_name}' not found")
            continue

    # Report results
    if written_files:
        print_success(f"Regenerated {len(written_files)} agent context file(s):")
        for fname in written_files:
            print(f"  • {fname}")

    if skipped_files:
        print_warning(f"Skipped {len(skipped_files)} existing file(s) (use --force to overwrite):")
        for fname in skipped_files:
            print(f"  • {fname}")

    if not written_files and not skipped_files:
        print_info("No files changed")

    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """Launch the AgentWeave watchdog as a background daemon.

    Reads all agents from the active session and auto-pings each one when
    a new message arrives. PID is written to .agentweave/watchdog.pid.
    """
    import os
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

    # Check if already running
    if WATCHDOG_PID_FILE.exists():
        try:
            pid = int(WATCHDOG_PID_FILE.read_text().strip())
            os.kill(pid, 0)  # signal 0 = existence check only
            print_warning(f"Watchdog already running (PID {pid}).")
            print_info("Run 'agentweave stop' first to restart it.")
            return 1
        except (OSError, ProcessLookupError, ValueError):
            WATCHDOG_PID_FILE.unlink()

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

    # Build per-agent MCP registration commands.
    # Known CLI interfaces: claude uses `claude mcp add`, kimi uses `kimi mcp add --transport stdio`.
    # Any other agent: try the generic `<agent> mcp add` form.
    def _mcp_args(agent: str) -> list:
        if agent == "claude":
            return ["claude", "mcp", "add", "agentweave", "--", server_cmd]
        if agent == "kimi":
            return ["kimi", "mcp", "add", "--transport", "stdio", "agentweave", "--", server_cmd]
        # Generic fallback — works for agents that follow the claude CLI convention
        return [agent, "mcp", "add", "agentweave", "--", server_cmd]

    # Determine which agents to configure: session agents → DEFAULT_AGENTS fallback
    session = Session.load()
    agent_list = session.agent_names if session else DEFAULT_AGENTS

    results = {}
    for agent in agent_list:
        mcp_args = _mcp_args(agent)
        try:
            check = _sp.run([agent, "--version"], capture_output=True, shell=_shell)
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
            if agent == "kimi":
                print(f"    kimi mcp add --transport stdio agentweave -- {server_cmd}")
            else:
                print(f"    {agent} mcp add agentweave -- {server_cmd}")
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
        help=f"Comma-separated agent list, e.g. claude,kimi,gemini (default: {','.join(DEFAULT_AGENTS)})",
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

    # Status
    subparsers.add_parser("status", help="Show session status")

    # Summary (NEW)
    subparsers.add_parser("summary", help="Quick summary for relay decisions")

    # Relay
    relay_parser = subparsers.add_parser("relay", help="Generate relay prompt for agent")
    relay_parser.add_argument(
        "--agent",
        "-a",
        required=True,
        help="Agent to generate prompt for (e.g. kimi, gemini, codex)",
    )

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
        elif parsed_args.command == "reply":
            return cmd_reply(parsed_args)
        elif parsed_args.command == "hub-heartbeat":
            return cmd_hub_heartbeat(parsed_args)
        elif parsed_args.command == "yolo":
            return cmd_yolo(parsed_args)
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
