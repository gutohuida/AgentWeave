"""Whether Claude Code's sign-in can still be renewed (F1183).

An expired *access* token is normal: the CLI refreshes it itself. What a run cannot recover from is
a login whose refresh has stopped working ("this login reached its time limit and cannot be
renewed"). That is not visible in `~/.claude/.credentials.json` (the refresh token is still there;
only Anthropic's server refuses it), so two signals are used:

* **the failure itself** -- a run that ended with Claude's own "cannot be renewed" text records it
  here (`mark_unrenewable`), and it stands until the credentials file changes, which is what
  `claude auth login` does;
* **the file** -- an access token past `expiresAt` with no refresh token at all cannot be renewed.

`expiresAt` alone is deliberately not a signal. `claude auth status` was not used: it reports the
stored login (`loggedIn: true`) without asking the server, and it costs a process spawn per probe.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple

LOGIN_COMMAND = "claude auth login"

#: What the operator reads when the sign-in cannot be renewed.
UNRENEWABLE_REASON = (
    "Claude Code's sign-in has expired and cannot be renewed. Run `claude auth login` in a "
    "terminal, then try again."
)

_recorded: Optional[Tuple[str, Tuple[int, int]]] = None  # (credentials path, fingerprint)


def is_login_unrenewable_text(text: str) -> bool:
    """Claude's own words when the login cannot be renewed: "Failed to authenticate: this login
    reached its time limit and cannot be renewed. Run `claude auth login`". Anchored to the start
    and requires the remedy, so a reply that merely quotes or discusses the message is not read as
    the CLI refusing the turn."""
    stripped = text.strip()
    return stripped.startswith("Failed to authenticate") and "claude auth login" in stripped


def credentials_path() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / ".credentials.json"


def _fingerprint(path: Path) -> Tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    return (stat.st_mtime_ns, stat.st_size)


def mark_unrenewable() -> None:
    """Record that a run just failed because the login cannot be renewed."""
    global _recorded
    path = credentials_path()
    if not path.exists():
        # Nothing to fingerprint (keychain, env token, another config dir): a mark here could never
        # be lifted by a re-login, so none is made.
        return
    _recorded = (str(path), _fingerprint(path))


def forget() -> None:
    global _recorded
    _recorded = None


def unrenewable_reason(now_ms: Optional[int] = None) -> Optional[str]:
    """`UNRENEWABLE_REASON` when the sign-in is known not to be renewable, else None."""
    path = credentials_path()
    if _recorded is not None and _recorded == (str(path), _fingerprint(path)):
        return UNRENEWABLE_REASON
    try:
        oauth = json.loads(path.read_text(encoding="utf-8")).get("claudeAiOauth")
    except (OSError, ValueError, AttributeError):
        return None  # no file (API key, env token, keychain): nothing to say
    if not isinstance(oauth, dict):
        return None
    expires_at = oauth.get("expiresAt")
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    if isinstance(expires_at, (int, float)) and expires_at < now and not oauth.get("refreshToken"):
        return UNRENEWABLE_REASON
    return None
