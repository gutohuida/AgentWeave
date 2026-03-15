"""File locking mechanism for preventing race conditions."""

import time
from contextlib import contextmanager

from .constants import AGENTWEAVE_DIR

LOCK_DIR = AGENTWEAVE_DIR / ".locks"
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_RETRY_DELAY = 0.1  # seconds


class LockError(Exception):
    """Raised when lock cannot be acquired."""

    pass


def acquire_lock(lock_name: str, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """Acquire a lock by creating a lock file.

    Args:
        lock_name: Name of the lock (e.g., task_id)
        timeout: Maximum time to wait for lock

    Returns:
        True if lock acquired, False otherwise
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = LOCK_DIR / f"{lock_name}.lock"

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Try to create lock file exclusively
            with open(lock_file, "x") as f:
                f.write(str(time.time()))
            return True
        except FileExistsError:
            # Lock exists, check if stale
            try:
                with open(lock_file) as f:
                    lock_time = float(f.read().strip())

                # If lock is older than 5 minutes, it's stale
                if time.time() - lock_time > 300:
                    lock_file.unlink()
                    continue

            except (OSError, ValueError):
                pass

            # Wait and retry
            time.sleep(DEFAULT_RETRY_DELAY)

    return False


def release_lock(lock_name: str) -> bool:
    """Release a lock by removing the lock file.

    Args:
        lock_name: Name of the lock

    Returns:
        True if lock was released, False if it didn't exist
    """
    lock_file = LOCK_DIR / f"{lock_name}.lock"

    try:
        if lock_file.exists():
            lock_file.unlink()
            return True
    except OSError:
        pass

    return False


@contextmanager
def lock(lock_name: str, timeout: float = DEFAULT_TIMEOUT):
    """Context manager for acquiring and releasing locks.

    Usage:
        with lock("task-123"):
            # Do work on task-123
            pass
    """
    if not acquire_lock(lock_name, timeout):
        raise LockError(f"Could not acquire lock: {lock_name}")

    try:
        yield
    finally:
        release_lock(lock_name)


def is_locked(lock_name: str) -> bool:
    """Check if a resource is currently locked.

    Args:
        lock_name: Name of the lock

    Returns:
        True if locked, False otherwise
    """
    lock_file = LOCK_DIR / f"{lock_name}.lock"

    if not lock_file.exists():
        return False

    # Check if lock is stale (read-only check, no side effects)
    try:
        with open(lock_file) as f:
            lock_time = float(f.read().strip())

        # If lock is older than 5 minutes, treat as not locked
        # (acquire_lock() will clean it up when needed)
        if time.time() - lock_time > 300:
            return False

    except (OSError, ValueError):
        pass

    return True


def wait_for_unlock(lock_name: str, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """Wait for a lock to be released.

    Args:
        lock_name: Name of the lock
        timeout: Maximum time to wait

    Returns:
        True if unlocked (or was never locked), False if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        if not is_locked(lock_name):
            return True
        time.sleep(DEFAULT_RETRY_DELAY)

    return False
