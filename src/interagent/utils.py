"""Utility functions for InterAgent."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import (
    INTERAGENT_DIR,
    AGENTS_DIR,
    TASKS_ACTIVE_DIR,
    TASKS_COMPLETED_DIR,
    MESSAGES_PENDING_DIR,
    MESSAGES_ARCHIVE_DIR,
    SHARED_DIR,
    LOGS_DIR,
)


def ensure_dirs() -> None:
    """Ensure all required directories exist."""
    for d in [
        INTERAGENT_DIR,
        AGENTS_DIR,
        TASKS_ACTIVE_DIR,
        TASKS_COMPLETED_DIR,
        MESSAGES_PENDING_DIR,
        MESSAGES_ARCHIVE_DIR,
        SHARED_DIR,
        LOGS_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def generate_id(prefix: str = "id") -> str:
    """Generate a unique ID with prefix."""
    return f"{prefix}-{str(uuid.uuid4())[:6]}"


def now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def load_json(filepath: Path) -> Optional[Dict[str, Any]]:
    """Load JSON from file."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_json(filepath: Path, data: Dict[str, Any]) -> bool:
    """Save data to JSON file."""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except IOError:
        return False


def list_json_files(directory: Path) -> list:
    """List all JSON files in directory."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def print_success(message: str) -> None:
    """Print success message."""
    print(f"[OK] {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    print(f"[WARN] {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"[ERR] {message}")


def print_info(message: str) -> None:
    """Print info message."""
    print(f"[INFO] {message}")
