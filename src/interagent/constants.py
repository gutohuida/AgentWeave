"""Constants for the InterAgent framework."""

from pathlib import Path

# Directory structure
INTERAGENT_DIR = Path(".interagent")
AGENTS_DIR = INTERAGENT_DIR / "agents"
TASKS_DIR = INTERAGENT_DIR / "tasks"
MESSAGES_DIR = INTERAGENT_DIR / "messages"
SHARED_DIR = INTERAGENT_DIR / "shared"

# Task directories
TASKS_ACTIVE_DIR = TASKS_DIR / "active"
TASKS_COMPLETED_DIR = TASKS_DIR / "completed"

# Message directories
MESSAGES_PENDING_DIR = MESSAGES_DIR / "pending"
MESSAGES_ARCHIVE_DIR = MESSAGES_DIR / "archive"

# File paths
SESSION_FILE = INTERAGENT_DIR / "session.json"
AGENTS_FILE = INTERAGENT_DIR / "agents.json"

# Transport
TRANSPORT_CONFIG_FILE = INTERAGENT_DIR / "transport.json"
GIT_COLLAB_BRANCH = "interagent/collab"
GIT_SEEN_DIR = INTERAGENT_DIR / ".git_seen"  # local seen-set for git transport (gitignored)

# Valid agents
VALID_AGENTS = ["claude", "kimi"]

# Valid roles
VALID_ROLES = ["principal", "delegate", "reviewer", "collaborator"]

# Valid modes
VALID_MODES = ["hierarchical", "peer", "review"]

# Task statuses
TASK_STATUSES = [
    "pending",
    "assigned",
    "in_progress",
    "completed",
    "under_review",
    "revision_needed",
    "approved",
    "rejected",
]

# Message types
MESSAGE_TYPES = ["message", "delegation", "review", "discussion"]

# Priorities
PRIORITIES = ["low", "medium", "high", "critical"]
