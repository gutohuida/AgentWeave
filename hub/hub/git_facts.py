"""Git answers that cannot change, remembered; ref names resolved once per read request (D4).

`GET /loops` asked about twenty git questions on every request (the integrator's measurement on
the 2026-10-25 operator copy: ~1.1-1.5 s for 24 ms of SQL), and almost all of them were the same
questions as the request before: is commit A an ancestor of commit B, does B exist, would A merge
cleanly onto B. For fixed commit ids those answers are facts about immutable objects, so they are
kept for the life of the process (`turn-starts-approvals-and-evidence-never-freeze-the-hub`, D4:
"unchanged facts are not recomputed per request").

**Nothing is ever cached under a ref name.** A branch moves; its name is resolved to a commit id
first, and only the id is a key. A name is resolved at most once per *read* request (`GET`, see
`ReadScopeMiddleware`), and for no longer than `REF_SCOPE_SECONDS` within one, so a commit on the
branch or on the main line changes the very next request's answer. Outside a read request -- a
mutation, a background job -- every name is resolved afresh, as before.

Only the genuine `subprocess.run` is remembered: where a test has replaced it, the replacement's
answers are not facts about any repository, and keeping one would outlive the replacement.
"""

from __future__ import annotations

import contextvars
import os
import re
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Hashable, Optional, Tuple, TypeVar

T = TypeVar("T")

#: Distinct facts kept; the oldest is forgotten first. Each is a few short strings.
MAX_FACTS = 8192
#: How long a ref name resolved within one read request is reused.
REF_SCOPE_SECONDS = 2.0

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_REAL_RUN = subprocess.run
_facts: "OrderedDict[Hashable, Any]" = OrderedDict()
_lock = threading.Lock()
_read_scope: contextvars.ContextVar[
    Optional[Dict[Tuple[str, str], Tuple[float, Optional[str]]]]
] = contextvars.ContextVar("aw_git_read_scope", default=None)


def _remembering() -> bool:
    return subprocess.run is _REAL_RUN


def root_key(root: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(root)))


def is_full_sha(value: Optional[str]) -> bool:
    return bool(value) and bool(_FULL_SHA.match(str(value)))


def fact(
    key: Hashable, compute: Callable[[], T], *, keep: Callable[[T], bool] = lambda _v: True
) -> T:
    """The remembered answer for *key*, or `compute()`'s, kept when *keep* says it is a fact."""
    if not _remembering():
        return compute()
    with _lock:
        if key in _facts:
            _facts.move_to_end(key)
            return _facts[key]
    value = compute()
    if keep(value):
        with _lock:
            _facts[key] = value
            _facts.move_to_end(key)
            while len(_facts) > MAX_FACTS:
                _facts.popitem(last=False)
    return value


def forget() -> None:
    """Drop every remembered fact (tests; nothing in the product needs it)."""
    with _lock:
        _facts.clear()


def resolved(root: Path | str, ref: str, resolve: Callable[[], Optional[str]]) -> Optional[str]:
    """*ref*'s commit id via *resolve* (the caller's own `rev-parse --verify`).

    A full commit id is answered once per process when it exists (an object does not stop
    existing); a name, once per read request at most."""
    if is_full_sha(ref):
        return fact(("exists", root_key(root), ref), resolve, keep=lambda sha: sha is not None)
    scope = _read_scope.get()
    if scope is None or not _remembering():
        return resolve()
    key = (root_key(root), ref)
    now = time.monotonic()
    hit = scope.get(key)
    if hit is not None and now - hit[0] < REF_SCOPE_SECONDS:
        return hit[1]
    value = resolve()
    scope[key] = (now, value)
    return value


class ReadScopeMiddleware:
    """Pure ASGI: a `GET`/`HEAD` request resolves each ref name once (see module docstring).

    Only reads: a mutation can move a branch mid-request (an approval merges, then re-asks
    reachability), and must see the move."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return
        token = _read_scope.set({})
        try:
            await self.app(scope, receive, send)
        finally:
            _read_scope.reset(token)
