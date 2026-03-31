# Transport Layer

The transport layer abstracts message and task I/O so the rest of the framework doesn't need to know whether it's running locally, over git, or via HTTP.

## BaseTransport ABC

All transports implement these 6 methods:

```python
class BaseTransport(ABC):
    @abstractmethod
    def send_message(self, message_data: Dict[str, Any]) -> bool: ...
    @abstractmethod
    def get_pending_messages(self, agent: str) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def archive_message(self, message_id: str) -> bool: ...
    @abstractmethod
    def send_task(self, task_data: Dict[str, Any]) -> bool: ...
    @abstractmethod
    def get_active_tasks(self, agent: Optional[str] = None) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def get_transport_type(self) -> str: ...
```

## LocalTransport

Default transport. Uses the `.agentweave/` directory on the local filesystem.

- Messages: `.agentweave/messages/{id}/message.json`
- Tasks: `.agentweave/tasks/{id}/task.json`
- Best for: single-machine collaboration

## GitTransport

Uses git plumbing commands to sync state via an orphan branch (`agentweave/collab`).

- Never touches the working tree or HEAD
- Uses `hash-object`, `mktree`, `commit-tree`, and `push`
- UUID-suffixed filenames prevent concurrent push conflicts
- Best for: cross-machine collaboration without a server

## HttpTransport

Connects to the AgentWeave Hub via REST API.

- Uses `urllib.request` (stdlib only — no new CLI dependencies)
- Pushes events to Hub `/api/v1/logs` when severity ≥ INFO
- Best for: teams, multi-machine, dashboard visibility

## Transport Selection

The active transport is determined by `.agentweave/transport.json`. The factory function in `transport/config.py` instantiates the correct transport based on the `type` field.
