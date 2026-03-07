#!/usr/bin/env python3
"""Command-line interface for InterAgent."""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import __version__
from .constants import VALID_AGENTS, VALID_MODES, INTERAGENT_DIR
from .session import Session
from .task import Task, TaskStatus
from .messaging import Message, MessageBus
from .locking import acquire_lock, release_lock, LockError
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
        session = Session.create(
            name=args.project or "Unnamed Project",
            principal=args.principal or "claude",
            mode=args.mode or "hierarchical",
        )
        session.save()
        
        # Create README
        readme_path = INTERAGENT_DIR / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"""# InterAgent Session: {session.name}

**ID:** {session.id}  
**Mode:** {session.mode}  
**Principal:** {session.principal}

## Quick Commands

```bash
# Check status
interagent status

# Create task
interagent task create --title "Task name" --assignee kimi

# List tasks
interagent task list

# Quick delegation
interagent quick --to kimi "Implement auth"

# Check inbox
interagent inbox --agent kimi

# Get relay prompt
interagent relay --to kimi

# Summary
interagent summary
```

## Files

- `session.json` - Session configuration
- `agents/` - Agent status
- `tasks/active/` - Active tasks
- `tasks/completed/` - Completed tasks
- `messages/pending/` - Unread messages
- `messages/archive/` - Message history
- `shared/` - Shared context and decisions
""")
        
        # Write AGENTS.md — the collaboration guide both agents read on session start
        delegate = next((a for a in VALID_AGENTS if a != session.principal), "kimi")
        try:
            agents_guide = (
                get_template("agents_guide")
                .replace("{principal}", session.principal)
                .replace("{delegate}", delegate)
                .replace("{mode}", session.mode)
            )
            agents_path = INTERAGENT_DIR / "AGENTS.md"
            with open(agents_path, "w", encoding="utf-8") as f:
                f.write(agents_guide)
        except FileNotFoundError:
            pass  # Non-fatal

        # Write AI_CONTEXT.md — versioned best-practices template at project root.
        # Both agents use this as context; it is the basis for generating CLAUDE.md.
        # Run `interagent update-template` to keep it current with new AI capabilities.
        ai_context_path = Path.cwd() / "AI_CONTEXT.md"
        if not ai_context_path.exists():
            try:
                ai_context = get_template("ai_context")
                with open(ai_context_path, "w", encoding="utf-8") as f:
                    f.write(ai_context)
            except FileNotFoundError:
                pass  # Non-fatal

        print_success(f"Initialized session: {session.name}")
        print(f"   ID: {session.id}")
        print(f"   Mode: {session.mode}")
        print(f"   Principal: {session.principal}")
        print(f"\n[DIR] Created .interagent/ directory")
        print("     .interagent/AGENTS.md    <- collaboration guide (commands, roles, workflow)")
        print("     .interagent/shared/context.md  <- fill this with current project state")
        print("\n[FILE] Created AI_CONTEXT.md at project root")
        print("     <- versioned best-practices template; basis for generating CLAUDE.md")
        print("     <- run `interagent update-template --agent claude` to keep it current")
        print("\nNext steps:")
        print("1. Fill in the [Replace with...] sections in AI_CONTEXT.md")
        print("2. Edit .interagent/shared/context.md with current project state")
        print("3. Tell Claude: \"Read AI_CONTEXT.md and .interagent/AGENTS.md, then generate CLAUDE.md\"")
        return 0
        
    except ValueError as e:
        print_error(str(e))
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show session status."""
    session = Session.load()
    if not session:
        print_error("No session found. Run: interagent init")
        return 1
    
    print(f"[STAT] Session: {session.name}")
    print(f"   ID: {session.id}")
    print(f"   Mode: {session.mode}")
    print(f"   Principal: {session.principal}")
    
    print(f"\n[AGENTS] Agents:")
    for agent, info in session.agents.items():
        print(f"   {agent}: {info.get('role', 'unknown')}")
    
    # Count tasks
    active_tasks = Task.list_all(active_only=True)
    completed_tasks = Task.list_all()
    completed_tasks = [t for t in completed_tasks if t.status in ["completed", "approved"]]
    
    print(f"\n[TASK] Tasks:")
    print(f"   Active: {len(active_tasks)}")
    print(f"   Completed: {len(completed_tasks)}")
    
    # Count messages
    pending = MessageBus.get_inbox("claude") + MessageBus.get_inbox("kimi")
    print(f"\n[MSG] Pending Messages: {len(pending)}")
    
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
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
    
    # Tasks by status
    all_tasks = Task.list_all()
    
    pending_claude = [t for t in all_tasks if t.assignee == "claude" and t.status in ["pending", "assigned"]]
    pending_kimi = [t for t in all_tasks if t.assignee == "kimi" and t.status in ["pending", "assigned"]]
    in_progress_claude = [t for t in all_tasks if t.assignee == "claude" and t.status == "in_progress"]
    in_progress_kimi = [t for t in all_tasks if t.assignee == "kimi" and t.status == "in_progress"]
    ready_for_review = [t for t in all_tasks if t.status in ["completed", "under_review"]]
    approved = [t for t in all_tasks if t.status == "approved"]
    
    print("[TASKS]")
    if pending_claude:
        print(f"  [WAIT] Claude: {len(pending_claude)} task(s) waiting to start")
    if pending_kimi:
        print(f"  [WAIT] Kimi: {len(pending_kimi)} task(s) waiting to start")
    if in_progress_claude:
        print(f"  [WORK] Claude: {len(in_progress_claude)} task(s) in progress")
    if in_progress_kimi:
        print(f"  [WORK] Kimi: {len(in_progress_kimi)} task(s) in progress")
    if ready_for_review:
        print(f"  [REVIEW] {len(ready_for_review)} task(s) ready for review")
    if approved:
        print(f"  [OK] {len(approved)} task(s) approved")
    
    if not any([pending_claude, pending_kimi, in_progress_claude, in_progress_kimi, ready_for_review, approved]):
        print("  No active tasks")
    print()
    
    # Messages
    claude_msgs = MessageBus.get_inbox("claude")
    kimi_msgs = MessageBus.get_inbox("kimi")
    
    print("[MESSAGES]")
    if claude_msgs:
        print(f"  [MSG] Claude: {len(claude_msgs)} unread message(s)")
        for msg in claude_msgs:
            print(f"     - From {msg.sender}: {msg.subject or '(no subject)'}")
    if kimi_msgs:
        print(f"  [MSG] Kimi: {len(kimi_msgs)} unread message(s)")
        for msg in kimi_msgs:
            print(f"     - From {msg.sender}: {msg.subject or '(no subject)'}")
    if not claude_msgs and not kimi_msgs:
        print("  No unread messages")
    print()
    
    # Action items
    print("[ACTION ITEMS]")
    if ready_for_review:
        print(f"  -> Tell {session.principal} to review {len(ready_for_review)} completed task(s)")
    if pending_kimi and session.principal == "claude":
        print(f"  -> Tell Kimi to check inbox ({len(pending_kimi)} new task(s))")
    if pending_claude and session.principal == "kimi":
        print(f"  -> Tell Claude to check inbox ({len(pending_claude)} new task(s))")
    if claude_msgs:
        print("  -> Tell Claude to check messages")
    if kimi_msgs:
        print("  -> Tell Kimi to check messages")
    if not any([ready_for_review, pending_kimi, pending_claude, claude_msgs, kimi_msgs]):
        print("  All caught up! No action needed.")
    print()
    
    # Quick commands
    print("[QUICK COMMANDS]")
    if ready_for_review:
        task_id = ready_for_review[0].id
        print(f"  interagent task show {task_id}")
    if kimi_msgs:
        print(f"  interagent relay --to kimi")
    if claude_msgs:
        print(f"  interagent relay --to claude")
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
        print(f"  interagent relay --to {recipient}")
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
    if not agent:
        # Try to determine current agent from session
        session = Session.load()
        if session:
            print_info("Checking inbox for all agents...")
    
    if agent:
        messages = MessageBus.get_inbox(agent)
    else:
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
    # Create task
    task_id = f"task-xxx"
    task = Task.create(
        title=args.task,
        description=args.description or "",
        assignee=args.to,
        assigner=args.from_agent or "claude",
        priority=args.priority or "medium",
    )
    
    # Use quick command internally
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
        # 1. Look for AI_CONTEXT.md in cwd (deployed by `interagent init`)
        candidate = Path.cwd() / "AI_CONTEXT.md"
        if candidate.exists():
            template_path = str(candidate)
        else:
            # 2. Walk up parent directories for a legacy template.txt
            search = Path.cwd()
            for _ in range(6):
                candidate = search / "template.txt"
                if candidate.exists():
                    template_path = str(candidate)
                    break
                search = search.parent
        if not template_path:
            template_path = (
                "./AI_CONTEXT.md"
                "  (not found — run `interagent init` first or use --template-path)"
            )

    focus = getattr(args, "focus", None) or (
        "all areas: new sub-agent capabilities, collaboration patterns, "
        "updated Claude Code / Kimi Code features"
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
    print(f"[PROMPT] Copy and paste the following into {agent.capitalize()} Code:")
    print(separator)
    print(prompt)
    print(separator)
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="interagent",
        description="InterAgent - Framework for Claude and Kimi collaboration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  interagent init --project "My API" --principal claude
  interagent quick --to kimi "Implement authentication"
  interagent relay --to kimi
  interagent summary
  interagent task list
  interagent inbox --agent kimi

For more help: https://github.com/yourusername/interagent
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
        choices=VALID_AGENTS,
        default="claude",
        help="Principal agent (default: claude)",
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
    
    # Relay (NEW)
    relay_parser = subparsers.add_parser("relay", help="Generate relay prompt for agent")
    relay_parser.add_argument(
        "--agent", "-a",
        required=True,
        choices=VALID_AGENTS,
        help="Agent to generate prompt for",
    )
    
    # Quick (NEW)
    quick_parser = subparsers.add_parser("quick", help="Quick task delegation (single command)")
    quick_parser.add_argument(
        "--to", "-t",
        required=True,
        choices=VALID_AGENTS,
        help="Delegate to",
    )
    quick_parser.add_argument(
        "--from-agent", "-f",
        choices=VALID_AGENTS,
        help="Delegate from",
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
        choices=VALID_AGENTS,
        help="Assign to agent",
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
        choices=VALID_AGENTS,
        help="Filter by assignee",
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
        choices=VALID_AGENTS,
        help="Recipient",
    )
    msg_send.add_argument(
        "--from-agent", "-f",
        choices=VALID_AGENTS,
        help="Sender",
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
        choices=VALID_AGENTS,
        help="Check for specific agent",
    )
    
    # Delegate shortcut
    delegate_parser = subparsers.add_parser("delegate", help="Quick task delegation")
    delegate_parser.add_argument(
        "--to", "-t",
        required=True,
        choices=VALID_AGENTS,
        help="Delegate to",
    )
    delegate_parser.add_argument(
        "--from-agent", "-f",
        choices=VALID_AGENTS,
        help="Delegate from",
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
        choices=VALID_AGENTS,
        help="Which agent receives and executes the update prompt (claude or kimi)",
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

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    if not parsed_args.command:
        parser.print_help()
        return 0
    
    # Route commands
    try:
        if parsed_args.command == "init":
            return cmd_init(parsed_args)
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
