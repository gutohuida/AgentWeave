"""Task management for AgentWeave."""

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from .constants import PRIORITIES, TASKS_ACTIVE_DIR, TASKS_COMPLETED_DIR
from .utils import generate_id, load_json, now_iso, save_json


class TaskStatus(Enum):
    """Task status enumeration."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    UNDER_REVIEW = "under_review"
    REVISION_NEEDED = "revision_needed"
    APPROVED = "approved"
    REJECTED = "rejected"


class Task:
    """Represents a task in the system."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize task with data."""
        self._data = data

    @property
    def id(self) -> str:
        """Get task ID."""
        return self._data.get("id", "unknown")

    @property
    def title(self) -> str:
        """Get task title."""
        return self._data.get("title", "Untitled")

    @property
    def status(self) -> str:
        """Get task status."""
        return self._data.get("status", "pending")

    @property
    def assignee(self) -> Optional[str]:
        """Get task assignee."""
        return self._data.get("assignee")

    @property
    def assigner(self) -> Optional[str]:
        """Get task assigner."""
        return self._data.get("assigner")

    @property
    def priority(self) -> str:
        """Get task priority."""
        return self._data.get("priority", "medium")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self._data

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [
            f"# Task: {self.title}",
            "",
            f"**ID:** {self.id}",
            f"**Status:** {self.status}",
            f"**Priority:** {self.priority}",
            f"**Assignee:** {self.assignee or 'Unassigned'}",
            f"**Assigner:** {self.assigner or 'Unknown'}",
            "",
            "## Description",
            self._data.get("description", "_No description_"),
            "",
        ]

        if self._data.get("requirements"):
            lines.extend(["## Requirements", ""])
            for req in self._data["requirements"]:
                lines.append(f"- [ ] {req}")
            lines.append("")

        if self._data.get("acceptance_criteria"):
            lines.extend(["## Acceptance Criteria", ""])
            for crit in self._data["acceptance_criteria"]:
                lines.append(f"- [ ] {crit}")
            lines.append("")

        if self._data.get("deliverables"):
            lines.extend(["## Deliverables", ""])
            for d in self._data["deliverables"]:
                lines.append(f"- {d}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def load(cls, task_id: str) -> Optional["Task"]:
        """Load task by ID."""
        # Validate task_id format to prevent path traversal
        if not re.match(r"^[a-zA-Z0-9_-]+$", task_id):
            return None

        # Try active first
        filepath = TASKS_ACTIVE_DIR / f"{task_id}.json"
        data = load_json(filepath)

        if not data:
            # Try completed
            filepath = TASKS_COMPLETED_DIR / f"{task_id}.json"
            data = load_json(filepath)

        if data:
            return cls(data)
        return None

    def save(self) -> bool:
        """Save task to file."""
        from .eventlog import ERROR, log_event

        filepath = TASKS_ACTIVE_DIR / f"{self.id}.json"
        is_new = not filepath.exists()
        result = save_json(filepath, self._data)
        if result and is_new:
            log_event(
                "task_created",
                task_id=self.id,
                title=self.title,
                assignee=self.assignee,
                priority=self.priority,
            )
        elif not result:
            log_event(
                "task_save_failed",
                severity=ERROR,
                task_id=self.id,
                title=self.title,
            )
        return result

    def update(self, agent: Optional[str] = None, **kwargs: Any) -> None:
        """Update task fields."""
        from .eventlog import log_event

        prev_status = self._data.get("status")
        self._data.update(kwargs)
        self._data["updated"] = now_iso()
        new_status = self._data.get("status")
        if "status" in kwargs and new_status != prev_status:
            log_event(
                "task_status",
                task_id=self.id,
                prev=prev_status,
                status=new_status,
                agent=agent,
            )

    def move_to_completed(self) -> bool:
        """Move task from active to completed."""
        active_path = TASKS_ACTIVE_DIR / f"{self.id}.json"
        completed_path = TASKS_COMPLETED_DIR / f"{self.id}.json"

        if active_path.exists():
            save_json(completed_path, self._data)
            active_path.unlink()
            return True
        return False

    @classmethod
    def create(
        cls,
        title: str,
        description: str = "",
        assignee: Optional[str] = None,
        assigner: Optional[str] = None,
        priority: str = "medium",
        requirements: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
    ) -> "Task":
        """Create a new task."""
        if priority not in PRIORITIES:
            priority = "medium"

        data = {
            "id": generate_id("task"),
            "title": title,
            "description": description,
            "status": "pending",
            "priority": priority,
            "assignee": assignee,
            "assigner": assigner,
            "created_at": now_iso(),
            "updated": now_iso(),
            "requirements": requirements or [],
            "acceptance_criteria": acceptance_criteria or [],
            "deliverables": [],
            "notes": [],
        }

        return cls(data)

    @classmethod
    def list_all(
        cls,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        active_only: bool = False,
    ) -> List["Task"]:
        """List all tasks matching criteria."""
        tasks = []

        # Load active tasks
        for filepath in TASKS_ACTIVE_DIR.glob("*.json"):
            data = load_json(filepath)
            if data:
                tasks.append(cls(data))

        # Load completed if not active_only
        if not active_only:
            for filepath in TASKS_COMPLETED_DIR.glob("*.json"):
                data = load_json(filepath)
                if data:
                    tasks.append(cls(data))

        # Filter
        if status:
            tasks = [t for t in tasks if t.status == status]
        if assignee:
            tasks = [t for t in tasks if t.assignee == assignee]

        return tasks
