#!/usr/bin/env python3
"""
Example: Parallel Workflow

This example demonstrates Claude and Kimi working in parallel
to build different parts of a system simultaneously.
"""

from agentweave import Session, Task, Message, MessageBus


def main():
    print("=" * 60)
    print("AgentWeave Parallel Workflow Example")
    print("=" * 60)
    print()
    print("Scenario: Building a web app with parallel frontend and backend work")
    print()

    # Initialize
    session = Session.create(
        name="Web Application",
        principal="claude",
        mode="hierarchical",
    )
    session.save()

    print("Phase 1: Architecture (Claude)")
    print("-" * 40)

    # Claude designs architecture
    arch_task = Task.create(
        title="Design System Architecture",
        description="Design overall system architecture",
        assignee="claude",
        assigner="claude",
        priority="high",
    )
    arch_task.save()
    arch_task.update(status="in_progress")
    arch_task.save()

    print("Claude is designing architecture...")
    print()

    # Claude completes and splits into parallel tasks
    arch_task.update(status="completed")
    arch_task.save()
    arch_task.move_to_completed()
    session.complete_task(arch_task.id)

    print("Architecture complete!")
    print("Splitting into parallel workstreams...")
    print()

    print("Phase 2: Parallel Implementation")
    print("-" * 40)

    # Backend work for Kimi
    backend_task = Task.create(
        title="Implement Backend API",
        description="Build REST API with FastAPI",
        assignee="kimi",
        assigner="claude",
        priority="high",
    )
    backend_task.save()
    backend_task.update(status="in_progress")
    backend_task.save()

    # Frontend work for Claude
    frontend_task = Task.create(
        title="Design Frontend Components",
        description="Design React component architecture",
        assignee="claude",
        assigner="claude",
        priority="high",
    )
    frontend_task.save()
    frontend_task.update(status="in_progress")
    frontend_task.save()

    session.add_task(backend_task.id)
    session.add_task(frontend_task.id)
    session.save()

    print(f"Backend Task ({backend_task.id}): Kimi - IN_PROGRESS")
    print(f"Frontend Task ({frontend_task.id}): Claude - IN_PROGRESS")
    print()
    print("Both agents working in parallel...")
    print()

    # Both complete
    backend_task.update(status="completed")
    backend_task.save()
    backend_task.move_to_completed()
    session.complete_task(backend_task.id)

    frontend_task.update(status="completed")
    frontend_task.save()
    frontend_task.move_to_completed()
    session.complete_task(frontend_task.id)

    session.save()

    print("Phase 3: Integration")
    print("-" * 40)

    integration_task = Task.create(
        title="Integrate Frontend and Backend",
        description="Connect frontend to backend API",
        assignee="kimi",
        assigner="claude",
        priority="high",
    )
    integration_task.save()
    integration_task.update(status="in_progress")
    integration_task.save()

    print(f"Integration Task ({integration_task.id}): Kimi")
    print()

    integration_task.update(status="completed")
    integration_task.save()
    integration_task.move_to_completed()
    session.complete_task(integration_task.id)
    session.save()

    # Summary
    print("=" * 60)
    print("Parallel Workflow Complete!")
    print("=" * 60)
    print()

    all_tasks = Task.list_all()
    completed = [t for t in all_tasks if t.status in ["completed", "approved"]]

    print(f"Total tasks: {len(all_tasks)}")
    print(f"Completed: {len(completed)}")
    print()
    print("Timeline:")
    print("  1. Architecture (Claude) - Sequential")
    print("  2. Backend (Kimi) -------- Parallel ──┐")
    print("  3. Frontend (Claude) ----- Parallel ──┤")
    print("  4. Integration (Kimi) ---- Sequential │")
    print()
    print("Time saved by parallel work: ~50%")


if __name__ == "__main__":
    main()
