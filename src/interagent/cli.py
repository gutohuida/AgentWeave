#!/usr/bin/env python3
"""Command-line interface for InterAgent."""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import __version__
from .constants import (
    VALID_AGENTS, VALID_MODES, INTERAGENT_DIR, TRANSPORT_CONFIG_FILE,
    DEFAULT_AGENTS, DEFAULT_AGENT_ROLES, DEV_ROLE_LABELS,
)
from .session import Session
from .task import Task
from .messaging import Message, MessageBus
from .locking import acquire_lock, release_lock
from .validator import validate_task, validate_message
from .templates import get_template
from .utils import (
    ensure_dirs,
    print_success,
    print_warning,
    print_error,
    print_info,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new session."""
    if INTERAGENT_DIR.exists() and not args.force:
        print_warning(".interagent/ already exists. Use --force to overwrite.")
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
        agents_listed = "\n".join(
            f"# interagent relay --agent {ag}" for ag in session.agent_names
        )
        readme_path = INTERAGENT_DIR / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"""# InterAgent Session: {session.name}

**ID:** {session.id}
**Mode:** {session.mode}
**Principal:** {session.principal}
**Agents:** {', '.join(session.agent_names)}

## Quick Commands

```bash
# Check status
interagent status

# Create task for any agent
interagent task create --title "Task name" --assignee <agent>

# List tasks
interagent task list

# Quick delegation
interagent quick --to <agent> "Implement auth"

# Check inbox
interagent inbox --agent <agent>

# Get relay prompt (for each agent)
{agents_listed}

# Summary
interagent summary
```

## Files

- `session.json` — Session configuration
- `AGENTS.md` — Collaboration guide (read by all agents on session start)
- `ROLES.md` — Agent role assignments (edit freely)
- `agents/` — Agent status
- `tasks/active/` — Active tasks
- `tasks/completed/` — Completed tasks
- `messages/pending/` — Unread messages
- `messages/archive/` — Message history
- `shared/` — Shared context and decisions
""")

        # Write AGENTS.md — collaboration guide read by all agents on session start
        non_principal = [a for a in session.agent_names if a != session.principal]
        agents_list = ", ".join(non_principal) if non_principal else "kimi"
        try:
            agents_guide = (
                get_template("agents_guide")
                .replace("{principal}", session.principal)
                .replace("{agents_list}", agents_list)
                .replace("{mode}", session.mode)
            )
            agents_path = INTERAGENT_DIR / "AGENTS.md"
            with open(agents_path, "w", encoding="utf-8") as f:
                f.write(agents_guide)
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
                role_rows.append(f"| **{ag}** | {dev_role_label} (`{session_role}`) | {responsibility} |")

            roles_content = (
                get_template("roles_template")
                .replace("{project_name}", session.name)
                .replace("{session_id}", session.id)
                .replace("{mode}", session.mode)
                .replace("{principal}", session.principal)
                .replace("{role_rows}", "\n".join(role_rows))
            )
            roles_path = INTERAGENT_DIR / "ROLES.md"
            with open(roles_path, "w", encoding="utf-8") as f:
                f.write(roles_content)
        except FileNotFoundError:
            pass  # Non-fatal

        # Write AI_CONTEXT.md — versioned best-practices template at project root.
        ai_context_path = Path.cwd() / "AI_CONTEXT.md"
        if not ai_context_path.exists():
            try:
                ai_context = get_template("ai_context")
                with open(ai_context_path, "w", encoding="utf-8") as f:
                    f.write(ai_context)
            except FileNotFoundError:
                pass  # Non-fatal

        print_success(f"Initialized session: {session.name}")
        print(f"   ID:      {session.id}")
        print(f"   Mode:    {session.mode}")
        print(f"   Agents:  {', '.join(session.agent_names)}  (principal: {session.principal})")
        print(f"\n[DIR] Created .interagent/")
        print("     AGENTS.md    <- collaboration guide (commands, roles, workflow)")
        print("     ROLES.md     <- agent role assignments (edit freely)")
        print("     shared/context.md  <- fill this with current project state")
        print("\n[FILE] Created AI_CONTEXT.md at project root")
        print("     <- versioned best-practices template; basis for generating CLAUDE.md")
        print("     <- run `interagent update-template --agent claude` to keep it current")
        print("\nNext steps:")
        print("1. Fill in the [Replace with...] sections in AI_CONTEXT.md")
        print("2. Edit .interagent/ROLES.md to assign the right dev roles")
        print("3. Edit .interagent/shared/context.md with current project state")
        print(f"4. Tell {session.principal.capitalize()}: \"Read AI_CONTEXT.md, AGENTS.md, and ROLES.md, then generate CLAUDE.md\"")
        print()
        print("Zero-relay MCP mode (optional):")
        print("  interagent mcp setup   # configure MCP server in both agents (once)")
        print("  interagent start       # launch background watchdog — agents notify each other automatically")
        return 0

    except ValueError as e:
        print_error(str(e))
        return 1


def _role_responsibility(role_key: str) -> str:
    """Return a short responsibility description for a dev role."""
    responsibilities = {
        "tech_lead":         "Architecture decisions, code review, integration",
        "architect":         "System design, data models, API contracts",
        "backend_dev":       "APIs, database, business logic, server-side",
        "frontend_dev":      "UI components, styling, client-side state",
        "fullstack_dev":     "Backend and frontend features",
        "qa_engineer":       "Tests, quality assurance, edge cases",
        "devops_engineer":   "CI/CD, infrastructure, deployment",
        "security_engineer": "Security review, auth/authz, vulnerability audit",
        "data_engineer":     "Data pipelines, ETL, analytics",
        "ml_engineer":       "ML models, training pipelines, inference",
        "technical_writer":  "Documentation, READMEs, API docs",
        "code_reviewer":     "Pull request reviews, style enforcement",
        "project_manager":   "Task tracking, progress coordination",
    }
    return responsibilities.get(role_key, "General development tasks")


def cmd_status(_args: argparse.Namespace) -> int:
    """Show session status."""
    import os as _os
    from .constants import WATCHDOG_PID_FILE, WATCHDOG_LOG_FILE

    session = Session.load()
    if not session:
        print_error("No session found. Run: interagent init")
        return 1

    print(f"[STAT] Session: {session.name}")
    print(f"   ID:        {session.id}")
    print(f"   Mode:      {session.mode}")
    print(f"   Principal: {session.principal}")

    # Watchdog state
    watchdog_status = "stopped"
    watchdog_pid = None
    if WATCHDOG_PID_FILE.exists():
        try:
            watchdog_pid = int(WATCHDOG_PID_FILE.read_text().strip())
            _os.kill(watchdog_pid, 0)
            watchdog_status = f"running (PID {watchdog_pid})"
        except (OSError, ProcessLookupError, ValueError):
            watchdog_status = "stopped (stale PID file)"
    log_hint = f" — logs: {WATCHDOG_LOG_FILE}" if WATCHDOG_LOG_FILE.exists() else ""
    print(f"\n[WATCH] Watchdog: {watchdog_status}{log_hint}")

    # Per-agent info
    all_agents = session.agent_names or ["claude", "kimi"]
    active_tasks = Task.list_all(active_only=True)

    print(f"\n[AGENTS]")
    for agent in all_agents:
        role = session.agents.get(agent, {}).get("role", "unknown")
        inbox = MessageBus.get_inbox(agent)
        agent_tasks = [t for t in active_tasks if t.assignee == agent]
        in_prog = [t for t in agent_tasks if t.status == "in_progress"]
        waiting = [t for t in agent_tasks if t.status in ("pending", "assigned")]
        review  = [t for t in agent_tasks if t.status in ("completed", "under_review")]
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
            print(f"      idle")

    # Overall task summary
    completed_tasks = [t for t in Task.list_all() if t.status in ("completed", "approved")]
    print(f"\n[TASKS] Active: {len(active_tasks)}  |  Completed: {len(completed_tasks)}")

    return 0


def cmd_summary(_args: argparse.Namespace) -> int:
    """Show quick summary for relay decisions."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: interagent init")
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
    all_tasks = Task.list_all()
    all_agents = session.agent_names or ["claude", "kimi"]

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
            print(f"  [WAIT] {ag.capitalize()}: {len(pending_by_agent[ag])} task(s) waiting to start")
        if in_progress_by_agent[ag]:
            print(f"  [WORK] {ag.capitalize()}: {len(in_progress_by_agent[ag])} task(s) in progress")
    if ready_for_review:
        print(f"  [REVIEW] {len(ready_for_review)} task(s) ready for review")
    if approved:
        print(f"  [OK] {len(approved)} task(s) approved")

    any_tasks = any(
        pending_by_agent[ag] or in_progress_by_agent[ag] for ag in all_agents
    ) or ready_for_review or approved
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
            print(f"  -> Tell {ag.capitalize()} to check inbox ({len(pending_by_agent[ag])} new task(s))")
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
        print(f"  interagent task show {task_id}")
    for ag in all_agents:
        if msgs_by_agent[ag]:
            print(f"  interagent relay --agent {ag}")
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
    print(f"@{agent} - You have work in the InterAgent collaboration system.")
    print()
    print(f"Your role: {role}")
    print(f"Collaboration guide: read .interagent/AGENTS.md for commands, workflow, and protocol.")
    print(f"Project context: read .interagent/shared/context.md before starting.")
    print()
    
    if pending_tasks:
        print(f"[TASK] You have {len(pending_tasks)} new task(s):")
        for task in pending_tasks:
            print(f"   - {task.title} ({task.id})")
        print()
        print("Please:")
        print("1. Check .interagent/tasks/active/ for details")
        print("2. Run: interagent task update <task_id> --status in_progress")
        print("3. Do the work")
        print("4. Run: interagent task update <task_id> --status completed")
        print("5. Send a message when done: interagent msg send --to <other> --message 'Done!'")
        print()
    
    if messages:
        print(f"[MSG] You have {len(messages)} unread message(s):")
        for msg in messages[:3]:  # Show first 3
            print(f"   From {msg.sender}: {msg.subject or '(no subject)'}")
        print()
        print("Check your inbox:")
        print(f"  interagent inbox --agent {agent}")
        print()
    
    if not pending_tasks and not messages:
        print("No pending tasks or messages.")
        print()
        print("Useful commands:")
        print(f"  interagent status           # Check overall status")
        print(f"  interagent summary          # Quick summary")
        print()
    
    print("-" * 60)
    print()
    
    return 0


def cmd_quick(args: argparse.Namespace) -> int:
    """Quick mode - single command for task delegation."""
    ensure_dirs()
    
    session = Session.load()
    if not session:
        print_error("No session found. Run: interagent init")
        return 1
    
    sender = args.from_agent or session.principal
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
            
            # Update session
            session.add_task(task.id)
            session.save()
            
        finally:
            release_lock(f"task_{task.id}")
        
        # Create message
        msg = Message.create(
            sender=sender,
            recipient=recipient,
            subject=f"Task: {task.title}",
            content=f"You have been assigned a task: {task_desc}\n\n"
                    f"Task ID: {task.id}\n"
                    f"Priority: {task.priority}\n\n"
                    f"To start: interagent task update {task.id} --status in_progress",
            message_type="delegation",
            task_id=task.id,
        )
        
        # Validate message
        is_valid, errors = validate_message(msg.to_dict())
        if is_valid:
            MessageBus.send(msg)
        
        print_success("Quick delegation complete!")
        print(f"   Task: {task.id}")
        print(f"   Assigned to: {recipient}")
        print()
        print("Next step:")
        print(f"  interagent relay --agent {recipient}")
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
        print(f"\n   File: {INTERAGENT_DIR}/tasks/active/{task.id}.json")
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
            task.update(status=args.status)
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
            notes.append({
                "timestamp": now_iso(),
                "note": args.note,
            })
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
        print(f"\n   @{args.to} - Check your inbox: interagent inbox --agent {args.to}")
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
            messages = (
                MessageBus.get_inbox("claude") +
                MessageBus.get_inbox("kimi")
            )

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
    class QuickArgs:
        pass

    quick_args = QuickArgs()
    quick_args.from_agent = args.from_agent
    quick_args.to = args.to
    quick_args.task = args.task
    quick_args.priority = args.priority

    return cmd_quick(quick_args)


def cmd_update_template(args: argparse.Namespace) -> int:
    """Generate a prompt instructing an agent to update the kickoff template."""
    # Resolve template path
    template_path = getattr(args, "template_path", None)
    if not template_path:
        # Look for AI_CONTEXT.md in cwd (deployed by `interagent init`)
        candidate = Path.cwd() / "AI_CONTEXT.md"
        if candidate.exists():
            template_path = str(candidate)
        if not template_path:
            template_path = (
                "./AI_CONTEXT.md"
                "  (not found — run `interagent init` first or use --template-path)"
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
        print_error("Template 'update_prompt' not found in src/interagent/templates/")
        return 1

    prompt = (
        template
        .replace("{agent}", agent.capitalize())
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



def cmd_start(_args: argparse.Namespace) -> int:
    """Launch the InterAgent watchdog as a background daemon.

    Reads all agents from the active session and auto-pings each one when
    a new message arrives. PID is written to .interagent/watchdog.pid.
    """
    import os
    import subprocess as _sp
    from .constants import WATCHDOG_PID_FILE

    if not INTERAGENT_DIR.exists():
        print_error("No session found. Run: interagent init")
        return 1

    # Check if already running
    if WATCHDOG_PID_FILE.exists():
        try:
            pid = int(WATCHDOG_PID_FILE.read_text().strip())
            os.kill(pid, 0)  # signal 0 = existence check only
            print_warning(f"Watchdog already running (PID {pid}).")
            print_info("Run 'interagent stop' first to restart it.")
            return 1
        except (OSError, ProcessLookupError, ValueError):
            WATCHDOG_PID_FILE.unlink()

    from .constants import WATCHDOG_LOG_FILE

    cmd = ["interagent-watch", "--auto-ping"]

    import os as _os
    spawn_kwargs: dict = (
        {"creationflags": 0x00000008 | 0x08000000}  # DETACHED_PROCESS | CREATE_NO_WINDOW
        if _os.name == "nt"
        else {"start_new_session": True}
    )
    log_fh = open(WATCHDOG_LOG_FILE, "a", encoding="utf-8")
    proc = _sp.Popen(cmd, stdout=log_fh, stderr=log_fh, stdin=_sp.DEVNULL, **spawn_kwargs)

    WATCHDOG_PID_FILE.write_text(str(proc.pid))
    print_success(f"Watchdog started in background (PID {proc.pid})")
    print_info(f"Logs: {WATCHDOG_LOG_FILE}")
    print_info("Run 'interagent stop' to stop it.")
    return 0


def cmd_stop(_args: argparse.Namespace) -> int:
    """Stop the background InterAgent watchdog."""
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
    """Tail the watchdog log file."""
    import os
    from .constants import WATCHDOG_LOG_FILE, WATCHDOG_PID_FILE

    if not WATCHDOG_LOG_FILE.exists():
        print_info("No watchdog log yet. Start the watchdog first: interagent start")
        return 0

    lines = args.lines if hasattr(args, "lines") and args.lines else 50

    # Print the last N lines
    try:
        text = WATCHDOG_LOG_FILE.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        for line in all_lines[-lines:]:
            print(line)
    except OSError as e:
        print_error(f"Cannot read log: {e}")
        return 1

    # If --follow, stream new lines
    if hasattr(args, "follow") and args.follow:
        pid_running = False
        if WATCHDOG_PID_FILE.exists():
            try:
                pid = int(WATCHDOG_PID_FILE.read_text().strip())
                os.kill(pid, 0)
                pid_running = True
            except (OSError, ProcessLookupError, ValueError):
                pass

        if not pid_running:
            print_warning("Watchdog is not running (log may be stale).")

        print_info("--- following log (Ctrl-C to stop) ---")
        try:
            with open(WATCHDOG_LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
                fh.seek(0, 2)  # seek to end
                import time as _time
                while True:
                    line = fh.readline()
                    if line:
                        print(line, end="")
                    else:
                        _time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    return 0


def cmd_mcp_setup(_args: argparse.Namespace) -> int:
    """Configure the InterAgent MCP server for Claude Code and Kimi Code."""
    import os as _os
    import subprocess as _sp

    server_cmd = "interagent-mcp"
    # On Windows, agent CLIs are .cmd files — shell=True is required for subprocess to find them
    _shell = _os.name == "nt"

    results = {}
    for agent_cli, mcp_args in [
        ("claude", ["claude", "mcp", "add", "interagent", "--", server_cmd]),
        ("kimi",   ["kimi",   "mcp", "add", "--transport", "stdio", "interagent", "--", server_cmd]),
    ]:
        try:
            check = _sp.run([agent_cli, "--version"], capture_output=True, shell=_shell)
            if check.returncode != 0:
                results[agent_cli] = "not found"
                continue
        except FileNotFoundError:
            results[agent_cli] = "not found"
            continue
        try:
            result = _sp.run(
                mcp_args, capture_output=True, text=True,
                encoding="utf-8", errors="replace", shell=_shell,
            )
            results[agent_cli] = "ok" if result.returncode == 0 else f"failed: {result.stderr.strip()}"
        except FileNotFoundError:
            results[agent_cli] = "not found"

    print()
    print("InterAgent MCP server setup")
    print("-" * 40)
    for agent_cli, status in results.items():
        icon = "[OK]" if status == "ok" else "[!!]"
        print(f"  {icon} {agent_cli}: {status}")
    print()

    if any(s != "ok" for s in results.values()):
        print("Manual configuration (add to your agent's MCP settings):")
        print()
        print("  Claude Code (.mcp.json or via `claude mcp add`):")
        print('    claude mcp add interagent -- interagent-mcp')
        print()
        print("  Kimi Code:")
        print('    kimi mcp add --transport stdio interagent -- interagent-mcp')
        print()

    print("Start the auto-ping watchdog alongside the MCP server:")
    print("  interagent-watch --auto-ping --agent claude   # in one terminal")
    print("  interagent-watch --auto-ping --agent kimi     # in another terminal")
    print()
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
        branch = args.branch or "interagent/collab"

        # Check if the collab branch already exists on the remote
        result = _sp.run(
            ["git", "ls-remote", "--heads", remote, branch],
            capture_output=True, text=True,
        )
        branch_exists = bool(result.stdout.strip())

        if not branch_exists:
            print_info(f"Creating orphan branch '{branch}' on {remote}...")
            # Build an empty tree and push an initial commit via git plumbing
            proc = _sp.run(["git", "mktree"], input=b"", capture_output=True)
            empty_tree = proc.stdout.decode().strip()
            proc = _sp.run(
                ["git", "commit-tree", empty_tree, "-m", "init: interagent collab branch"],
                capture_output=True, text=True,
            )
            commit_sha = proc.stdout.strip()
            proc = _sp.run(
                ["git", "push", remote, f"{commit_sha}:refs/heads/{branch}"],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                print_error(f"Failed to push branch to {remote}: {proc.stderr.strip()}")
                return 1
            print_success(f"Created orphan branch '{branch}' on {remote}")
        else:
            print_info(f"Using existing branch '{branch}' on {remote}")

        # Write .interagent/transport.json
        INTERAGENT_DIR.mkdir(parents=True, exist_ok=True)
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
            print(f"  2. They run: interagent transport setup --type git --cluster <their-name>")
            print(f"  3. Address messages to them as: <their-cluster>.<their-agent>")
        else:
            print(f"  2. They run: interagent transport setup --remote {remote} --type git")
        print(f"  3. Messages now sync via git branch '{branch}'")
        print()
        print("Start watching for incoming messages:")
        print("  interagent-watch")
        return 0

    elif transport_type == "http":
        print_error("HTTP/MCP transport (InterAgent Hub) is not yet implemented.")
        print_info("See ROADMAP.md for the planned MCP-based Hub architecture.")
        return 1

    print_error(f"Unknown transport type: {transport_type}")
    return 1


def cmd_transport_status(_args: argparse.Namespace) -> int:
    """Show current transport configuration and status."""
    import subprocess as _sp
    from .utils import load_json as _load_json

    config = _load_json(TRANSPORT_CONFIG_FILE)
    if not config:
        print("[TRANSPORT] Type: local (default)")
        print("   No .interagent/transport.json — using local filesystem")
        print("   To enable cross-machine sync:")
        print("     interagent transport setup --type git")
        return 0

    transport_type = config.get("type", "local")
    print(f"[TRANSPORT] Type: {transport_type}")

    if transport_type == "git":
        remote = config.get("remote", "origin")
        branch = config.get("branch", "interagent/collab")
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
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            _sp.run(["git", "fetch", remote, branch, "--quiet"], capture_output=True)
            result2 = _sp.run(
                ["git", "ls-tree", f"{remote}/{branch}", "--name-only"],
                capture_output=True, text=True,
            )
            files = [f for f in result2.stdout.splitlines() if f.strip()]
            msg_files = [f for f in files if "-task-for-" not in f]
            task_files = [f for f in files if "-task-for-" in f]
            print(f"   Status:        connected")
            print(f"   Files on branch: {len(files)} ({len(msg_files)} messages, {len(task_files)} tasks)")
        else:
            print(f"   Status:        cannot reach {remote}/{branch}")

    elif transport_type == "http":
        print(f"   URL:     {config.get('url', '(not set)')}")
        print(f"   Project: {config.get('project_id', '(not set)')}")
        print(f"   Status:  not yet implemented — see ROADMAP.md")

    return 0


def cmd_transport_pull(_args: argparse.Namespace) -> int:
    """Force an immediate fetch from the remote transport."""
    from .transport import get_transport
    from .constants import VALID_AGENTS

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


def cmd_transport_disable(_args: argparse.Namespace) -> int:
    """Disable transport and revert to local filesystem."""
    if not TRANSPORT_CONFIG_FILE.exists():
        print_info("Already using local transport (no transport.json)")
        return 0

    TRANSPORT_CONFIG_FILE.unlink()
    print_success("Transport disabled — reverted to local filesystem")
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="interagent",
        description="InterAgent - Multi-agent AI collaboration framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  interagent init --project "My API" --principal claude --agents claude,kimi,gemini
  interagent quick --to kimi "Implement authentication"
  interagent relay --agent kimi
  interagent summary
  interagent task list
  interagent inbox --agent gemini
  interagent transport setup --type git --cluster alice

For more help: https://github.com/gutohuida/InterAgentFramework
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
        "--agent", "-a",
        required=True,
        help="Agent to generate prompt for (e.g. kimi, gemini, codex)",
    )

    # Quick
    quick_parser = subparsers.add_parser("quick", help="Quick task delegation (single command)")
    quick_parser.add_argument(
        "--to", "-t",
        required=True,
        help="Delegate to (any agent name)",
    )
    quick_parser.add_argument(
        "--from-agent", "-f",
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
        "--assignee", "-a",
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
            "pending", "assigned", "in_progress", "completed",
            "under_review", "revision_needed", "approved", "rejected",
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
        "--to", "-t",
        required=True,
        help="Recipient (any agent name)",
    )
    msg_send.add_argument(
        "--from-agent", "-f",
        help="Sender (any agent name)",
    )
    msg_send.add_argument("--subject", "-s", help="Message subject")
    msg_send.add_argument(
        "--message", "-m",
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
        "--agent", "-a",
        help="Check for specific agent (any agent name)",
    )

    # Delegate shortcut
    delegate_parser = subparsers.add_parser("delegate", help="Quick task delegation")
    delegate_parser.add_argument(
        "--to", "-t",
        required=True,
        help="Delegate to (any agent name)",
    )
    delegate_parser.add_argument(
        "--from-agent", "-f",
        help="Delegate from (any agent name)",
    )
    delegate_parser.add_argument(
        "--task",
        required=True,
        help="Task description",
    )
    delegate_parser.add_argument(
        "--description", "-d",
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
        "--agent", "-a",
        required=True,
        help="Which agent receives and executes the update prompt (e.g. claude, kimi, gemini)",
    )
    update_tmpl_parser.add_argument(
        "--template-path", "-p",
        default=None,
        dest="template_path",
        help="Path to the template file (default: searches parent dirs for template.txt)",
    )
    update_tmpl_parser.add_argument(
        "--focus", "-f",
        default=None,
        help="Optional focus area e.g. 'sub-agents', 'security', 'kimi-capabilities'",
    )


    # Start / stop watchdog daemon
    subparsers.add_parser("start", help="Start the watchdog daemon in the background")
    subparsers.add_parser("stop",  help="Stop the background watchdog daemon")

    # Log viewer
    log_parser = subparsers.add_parser("log", help="View watchdog activity log")
    log_parser.add_argument(
        "-n", "--lines", type=int, default=50,
        help="Number of recent lines to show (default: 50)",
    )
    log_parser.add_argument(
        "-f", "--follow", action="store_true",
        help="Follow log output in real time (like tail -f)",
    )

    # MCP commands
    mcp_parser = subparsers.add_parser("mcp", help="MCP server management")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser(
        "setup",
        help="Configure interagent-mcp in Claude Code and Kimi Code",
    )

    # Transport commands
    transport_parser = subparsers.add_parser(
        "transport",
        help="Configure cross-machine transport (git/http)",
    )
    transport_subparsers = transport_parser.add_subparsers(dest="transport_command")

    # transport setup
    transport_setup = transport_subparsers.add_parser(
        "setup", help="Set up transport backend"
    )
    transport_setup.add_argument(
        "--type", "-t",
        choices=["git", "http"],
        required=True,
        help="Transport type",
    )
    transport_setup.add_argument(
        "--remote", "-r",
        default="origin",
        help="Git remote name (default: origin)",
    )
    transport_setup.add_argument(
        "--branch", "-b",
        default="interagent/collab",
        help="Git orphan branch name (default: interagent/collab)",
    )
    transport_setup.add_argument(
        "--cluster", "-c",
        default=None,
        help=(
            "Your workspace name on the shared branch (e.g. alice). "
            "Use when multiple people/machines share the same git remote. "
            "Messages will be stamped '{cluster}.{agent}' so each workspace "
            "can be addressed individually."
        ),
    )

    # transport status
    transport_subparsers.add_parser("status", help="Show transport status")

    # transport pull
    transport_subparsers.add_parser("pull", help="Force immediate fetch from remote")

    # transport disable
    transport_subparsers.add_parser("disable", help="Disable transport, revert to local")

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
