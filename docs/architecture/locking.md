# File Locking

AgentWeave uses file-based locking to prevent race conditions when multiple agents write to the same task or message simultaneously.

## Usage

All task modifications must acquire a lock:

```python
from agentweave.locking import lock

with lock("task-abc123"):
    task = Task.load("task-abc123")
    task.update(status="completed")
    task.save()
```

## Lock Mechanics

- Locks are stored as files in `.agentweave/locks/`
- Each lock has a 5-minute automatic timeout to prevent deadlocks
- `acquire_lock()` cleans stale locks before attempting to acquire
- `is_locked()` is read-only and never deletes files

## Important Rules

1. **Always use locking** for any task file operation that modifies state
2. **Keep lock scope minimal** — acquire, modify, save, release
3. **Never bypass the lock** for task updates

## Example: Safe Status Update

```python
from agentweave.locking import lock
from agentweave.task import Task

def approve_task(task_id: str) -> None:
    with lock(task_id):
        task = Task.load(task_id)
        task.update(status="approved")
        task.save()
```

## Path Traversal Protection

Task IDs are validated with the regex `^[a-zA-Z0-9_-]+$` before any file operation. This prevents path traversal attacks.
