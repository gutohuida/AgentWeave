"""What a readable task id looks like (`readable_ids`). A leaf, so `schemas.tasks` can refuse the shape
without importing the database models."""

from __future__ import annotations

import re

#: Any case: this is the shape of what a caller might type, not of what is stored.
_READABLE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{1,4})-([0-9]+)$")
#: `task-12` would read as a stored id (`worktrees._TASK_ID_RE`), and a lowercase `sk-12` is destroyed
#: by the secret redactor (`runner_events._SECRET_VALUE_RE`), which cost every task id its name once
#: (F118). Refused whether derived or edited.
RESERVED_ACRONYMS = frozenset({"TASK", "SK"})


def is_readable_shaped(value: str) -> bool:
    """Whether *value* could be taken for a readable id, in any case.

    `TASK-12` and `SK-12` are not: no acronym can be either, so they shadow nothing, and a stored id
    of `task-1` has always been a legal thing for a caller to send.
    """
    matched = _READABLE_RE.match(value)
    return matched is not None and matched.group(1).upper() not in RESERVED_ACRONYMS
