"""Constants for the AgentWeave framework."""

import re
from enum import Enum
from pathlib import Path

# Directory structure
AGENTWEAVE_DIR = Path(".agentweave")
AGENTS_DIR = AGENTWEAVE_DIR / "agents"
TASKS_DIR = AGENTWEAVE_DIR / "tasks"
MESSAGES_DIR = AGENTWEAVE_DIR / "messages"
SHARED_DIR = AGENTWEAVE_DIR / "shared"

# Task directories
TASKS_ACTIVE_DIR = TASKS_DIR / "active"
TASKS_COMPLETED_DIR = TASKS_DIR / "completed"

# Message directories
MESSAGES_PENDING_DIR = MESSAGES_DIR / "pending"
MESSAGES_ARCHIVE_DIR = MESSAGES_DIR / "archive"

# File paths
SESSION_FILE = AGENTWEAVE_DIR / "session.json"
WATCHDOG_PID_FILE = AGENTWEAVE_DIR / "watchdog.pid"  # gitignored, machine-local
WATCHDOG_LOG_FILE = AGENTWEAVE_DIR / "watchdog.log"  # gitignored, machine-local
WATCHDOG_HEARTBEAT_FILE = AGENTWEAVE_DIR / "watchdog.heartbeat"  # gitignored

# Event log
LOGS_DIR = AGENTWEAVE_DIR / "logs"
EVENTS_LOG_FILE = LOGS_DIR / "events.jsonl"  # gitignored, machine-local


# Transport types
class TransportType(str, Enum):
    """Pluggable transport backends."""

    LOCAL = "local"
    GIT = "git"
    HTTP = "http"


TRANSPORT_CONFIG_FILE = AGENTWEAVE_DIR / "transport.json"
GIT_COLLAB_BRANCH = "agentweave/collab"
GIT_SEEN_DIR = AGENTWEAVE_DIR / ".git_seen"  # local seen-set for git transport (gitignored)

# Agent name validation: alphanumeric / hyphen / underscore, 1-32 chars.
# Replaces the old hardcoded two-item list — any name matching this is accepted.
AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")

# Known agents — used for documentation, suggestions, and default role assignments.
# NOT a validation gate: any name matching AGENT_NAME_RE is accepted.
KNOWN_AGENTS = [
    "claude",  # Claude Code (Anthropic) — claude.ai/code
    "kimi",  # Kimi Code (Moonshot AI)
    "gemini",  # Gemini CLI (Google) — open-source, 1M context
    "codex",  # Codex CLI (OpenAI)
    "aider",  # Aider — git-native AI pair programmer
    "cline",  # Cline — MCP-based VS Code agent
    "cursor",  # Cursor Agent (Anysphere)
    "windsurf",  # Windsurf / Cascade (Codeium)
    "copilot",  # GitHub Copilot Agent (Microsoft)
    "opendevin",  # OpenHands / OpenDevin — open-source autonomous agent
    "gpt",  # Generic ChatGPT / OpenAI assistant
    "qwen",  # Qwen / Tongyi Qianwen (Alibaba)
    "minimax",  # MiniMax — no native CLI, runs via Claude proxy
    "glm",  # GLM (Zhipu AI) — no native CLI, runs via Claude proxy
]

# Default agents when none specified at init (backward-compatible)
DEFAULT_AGENTS = ["claude", "kimi"]

# Backward-compatible alias used in old code paths
VALID_AGENTS = KNOWN_AGENTS

# Software development roles for ROLES.md
VALID_DEV_ROLES = [
    "tech_lead",
    "architect",
    "backend_dev",
    "frontend_dev",
    "fullstack_dev",
    "qa_engineer",
    "devops_engineer",
    "security_engineer",
    "data_engineer",
    "ml_engineer",
    "technical_writer",
    "code_reviewer",
    "project_manager",
]

# Human-readable role labels
DEV_ROLE_LABELS = {
    "tech_lead": "Tech Lead",
    "architect": "Architect",
    "backend_dev": "Backend Developer",
    "frontend_dev": "Frontend Developer",
    "fullstack_dev": "Full Stack Developer",
    "qa_engineer": "QA / Test Engineer",
    "devops_engineer": "DevOps Engineer",
    "security_engineer": "Security Engineer",
    "data_engineer": "Data Engineer",
    "ml_engineer": "ML / AI Engineer",
    "technical_writer": "Technical Writer",
    "code_reviewer": "Code Reviewer",
    "project_manager": "Project Manager",
}

# Default dev role per known agent (suggested starting point for ROLES.md)
DEFAULT_AGENT_ROLES = {
    "claude": "tech_lead",
    "kimi": "backend_dev",
    "gemini": "fullstack_dev",
    "codex": "backend_dev",
    "aider": "code_reviewer",
    "cline": "fullstack_dev",
    "cursor": "frontend_dev",
    "windsurf": "frontend_dev",
    "copilot": "code_reviewer",
    "opendevin": "devops_engineer",
    "gpt": "technical_writer",
    "qwen": "backend_dev",
    "minimax": "backend_dev",
    "glm": "backend_dev",
}

# Mapping from agent name to the root-level context file that agent auto-reads.
# claude → CLAUDE.md, gemini → GEMINI.md, everything else → AGENTS.md.
AGENT_CONTEXT_FILES: dict = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
}
AGENT_CONTEXT_FILES_DEFAULT = "AGENTS.md"

# Agent runner types — how the agent CLI is invoked
RUNNER_TYPES = ["native", "claude_proxy", "manual"]

# Agents that run through Claude CLI with custom env vars (no native CLI of their own)
CLAUDE_PROXY_PROVIDERS: dict = {
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "api_key_var": "MINIMAX_API_KEY",
        "model": "MiniMax-M2.7",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_var": "ZHIPU_API_KEY",
        "model": "glm-4",
    },
}

# Default runner per known agent; agents not listed here default to "native"
AGENT_RUNNER_DEFAULTS: dict = {
    "minimax": "claude_proxy",
    "glm": "claude_proxy",
    "cursor": "manual",
    "windsurf": "manual",
    "copilot": "manual",
}

# Valid session roles
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
