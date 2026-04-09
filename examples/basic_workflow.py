#!/usr/bin/env python3
"""
Example: Basic AgentWeave Workflow

This example demonstrates the basic workflow of:
1. Initializing a session
2. Creating and delegating tasks
3. Sending messages between agents
4. Updating task status
"""

from agentweave import Session, Task, Message, MessageBus


def main():
    print("=" * 60)
    print("AgentWeave Basic Workflow Example")
    print("=" * 60)
    print()

    # Step 1: Initialize Session
    print("Step 1: Initialize Session")
    print("-" * 40)

    session = Session.create(
        name="E-commerce API",
        principal="claude",
        mode="hierarchical",
    )
    session.save()

    print(f"Session created: {session.name}")
    print(f"ID: {session.id}")
    print(f"Principal: {session.principal}")
    print(f"Mode: {session.mode}")
    print()

    # Step 2: Principal (Claude) creates tasks
    print("Step 2: Create Tasks")
    print("-" * 40)

    # Task 1: Architecture (Claude does this)
    task1 = Task.create(
        title="Design API Architecture",
        description="Design the REST API architecture for e-commerce platform",
        assignee="claude",
        assigner="claude",
        priority="high",
        requirements=[
            "Define API endpoints",
            "Choose authentication method",
            "Design data models",
        ],
        acceptance_criteria=[
            "Architecture document complete",
            "API contract defined",
            "Database schema designed",
        ],
    )
    task1.save()
    session.add_task(task1.id)

    print(f"Task 1: {task1.title}")
    print(f"  ID: {task1.id}")
    print(f"  Assignee: {task1.assignee}")
    print(f"  Status: {task1.status}")
    print()

    # Task 2: Implementation (Delegate to Kimi)
    task2 = Task.create(
        title="Implement User Service",
        description="Build the user management service with authentication",
        assignee="kimi",
        assigner="claude",
        priority="high",
        requirements=[
            "User registration/login",
            "JWT token authentication",
            "Password hashing",
        ],
        acceptance_criteria=[
            "All endpoints working",
            "Tests passing (>90% coverage)",
            "Documentation complete",
        ],
    )
    task2.save()
    session.add_task(task2.id)

    print(f"Task 2: {task2.title}")
    print(f"  ID: {task2.id}")
    print(f"  Assignee: {task2.assignee}")
    print(f"  Status: {task2.status}")
    print()

    # Task 3: Testing (Delegate to Kimi)
    task3 = Task.create(
        title="Write Integration Tests",
        description="Create comprehensive integration tests",
        assignee="kimi",
        assigner="claude",
        priority="medium",
    )
    task3.save()
    session.add_task(task3.id)

    print(f"Task 3: {task3.title}")
    print(f"  ID: {task3.id}")
    print(f"  Assignee: {task3.assignee}")
    print()

    session.save()
    print(f"Total tasks: 3")
    print()

    # Step 3: Claude sends message to Kimi
    print("Step 3: Send Delegation Message")
    print("-" * 40)

    message = Message.create(
        sender="claude",
        recipient="kimi",
        subject=f"Task Delegation: {task2.title}",
        content=f"""Hi Kimi,

I've assigned you the following task:

**{task2.title}**
{task2.to_dict().get('description', '')}

**Task ID:** {task2.id}
**Priority:** {task2.priority}

Please review and respond with:
- ACCEPT: Will complete
- REJECT: Cannot complete  
- CLARIFY: Need more info

Thanks!
""",
        message_type="delegation",
        task_id=task2.id,
    )
    MessageBus.send(message)

    print(f"Message sent: {message.id}")
    print(f"From: {message.sender}")
    print(f"To: {message.recipient}")
    print(f"Subject: {message.subject}")
    print()

    # Step 4: Kimi checks inbox
    print("Step 4: Kimi Checks Inbox")
    print("-" * 40)

    kimi_messages = MessageBus.get_inbox("kimi")
    print(f"Kimi has {len(kimi_messages)} message(s):")
    for msg in kimi_messages:
        print(f"  - {msg.subject}")
    print()

    # Step 5: Kimi accepts and starts working
    print("Step 5: Kimi Starts Working")
    print("-" * 40)

    task2.update(status="in_progress")
    task2.save()

    print(f"Task {task2.id} status: {task2.status}")
    print("[Kimi implements the user service...]")
    print()

    # Step 6: Kimi completes work
    print("Step 6: Kimi Completes Task")
    print("-" * 40)

    task2.update(
        status="completed",
        deliverables=[
            "src/users/api.py",
            "src/users/service.py",
            "tests/test_users.py",
            "docs/users.md",
        ],
    )
    task2.save()
    task2.move_to_completed()
    session.complete_task(task2.id)
    session.save()

    print(f"Task {task2.id} status: {task2.status}")
    print("Deliverables:")
    for d in task2.to_dict().get("deliverables", []):
        print(f"  - {d}")
    print()

    # Step 7: Kimi requests review
    print("Step 7: Request Review")
    print("-" * 40)

    review_msg = Message.create(
        sender="kimi",
        recipient="claude",
        subject=f"Review Request: {task2.title}",
        content=f"""Hi Claude,

I've completed the task:
**{task2.title}**

Please review the implementation:
- All endpoints working
- Tests passing (94% coverage)
- Documentation complete

Task ID: {task2.id}

Thanks!
""",
        message_type="review",
        task_id=task2.id,
    )
    MessageBus.send(review_msg)

    print(f"Review request sent: {review_msg.id}")
    print()

    # Step 8: Claude reviews and approves
    print("Step 8: Claude Reviews")
    print("-" * 40)

    claude_messages = MessageBus.get_inbox("claude")
    print(f"Claude has {len(claude_messages)} message(s)")

    # Mark as read
    for msg in claude_messages:
        msg.mark_read()
        print(f"  Read: {msg.subject}")

    task2 = Task.load(task2.id)  # Reload from completed
    if task2:
        task2.update(status="approved")
        print(f"\nTask {task2.id} approved!")
    print()

    # Final Summary
    print("=" * 60)
    print("Workflow Complete!")
    print("=" * 60)

    summary = session.get_summary()
    print(f"\nSession: {summary['name']}")
    print(f"Active tasks: {summary['active_tasks_count']}")
    print(f"Completed tasks: {summary['completed_tasks_count']}")
    print()

    # Show all tasks
    print("All Tasks:")
    all_tasks = Task.list_all()
    for task in all_tasks:
        print(f"  [{task.status:12}] {task.title}")
    print()

    print("Check .agentweave/ directory for files created!")


if __name__ == "__main__":
    main()
