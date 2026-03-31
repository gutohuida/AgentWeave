# Messaging System

AgentWeave's messaging system enables structured communication between agents.

## Message Structure

```python
from agentweave import Message

msg = Message.create(
    sender="claude",
    recipient="kimi",
    subject="Task assignment",
    content="Please implement the auth module...",
    message_type="delegation",
    task_id="task-abc123"
)
MessageBus.send(msg)
```

## Message Types

Common message types include:

- `delegation` — assigning work to another agent
- `discussion` — general back-and-forth
- `review` — code or task review feedback
- `notification` — status updates

## MessageBus

The `MessageBus` abstracts sending and receiving:

```python
from agentweave import MessageBus

# Send a message
MessageBus.send(msg)

# Read inbox
inbox = MessageBus.get_inbox("kimi")

# Archive after processing
MessageBus.mark_read("msg-abc123")
```

## Task Lifecycle Integration

Messages can optionally link to a task via `task_id`. This allows agents to discuss work in context and the Hub dashboard to show related messages inline with tasks.

## Delivery Guarantees

- **LocalTransport**: immediate filesystem write
- **GitTransport**: committed and pushed to remote; polled by recipients
- **HttpTransport**: POST to Hub; delivered via SSE or polling
