"""Words a route registered earlier answers for, refused when a name is chosen (F248).

`GET /queue/settings` is registered before `GET /queue/{agent}`, so an agent named `settings` has a
queue panel that shows the settings. The words are refused **at creation only**, where an agent row
or a task is added, and nowhere else: they are not in `worktrees._RESERVED_AGENT_NAMES`, which
`validate_agent_name` checks at every use site, so an agent that already holds one would stop
running. `hub/tests/test_a_chosen_name_is_not_a_route.py` walks the route table and fails on the next
collision. Compared case-insensitively, as the reserved names are, though the route match is exact.
"""

from typing import Dict, Iterable, Optional

#: Agent names, each with the route (relative to a project) that answers for it first.
AGENT_WORDS: Dict[str, str] = {
    "conflicts": "/worktrees/conflicts",
    "settings": "/queue/settings",
    "sessions": "/agent/sessions/{agent}",
}

#: Task ids, each with the route that answers for it before `GET /tasks/{task_id}`.
TASK_WORDS: Dict[str, str] = {
    "board": "/tasks/board",
    "boards": "/tasks/boards",
}


def agent_route_word(name: str) -> Optional[str]:
    """The sentence refusing *name* as an agent name, or None when no route answers for it."""
    route = AGENT_WORDS.get(name.lower())
    if route is None:
        return None
    return (
        f"agent name '{name}' is a route the Hub already answers ({route}), so its own pages "
        "would show that instead; choose another name"
    )


def task_route_word(task_id: str) -> Optional[str]:
    """The sentence refusing *task_id* as a task id, or None when no route answers for it."""
    route = TASK_WORDS.get(task_id.lower())
    if route is None:
        return None
    return (
        f"id '{task_id}' is a route the Hub already answers ({route}), so the task could not be "
        "opened; choose another id"
    )


def agent_case_twin(name: str, existing: Iterable[str]) -> Optional[str]:
    """The sentence refusing *name* because an agent differing from it only in case exists (F811).

    Worktrees live at `.agentweave/worktrees/<name>`, on a filesystem that is case-insensitive by
    default on Windows and macOS, so `EPS` would share `eps`'s checkout and never run. Refused at
    creation only, like the route words, and for archived rows too: an archived agent keeps its
    checkout. An identical name is not a twin; the callers' own "already exists" check owns it.
    """
    for other in existing:
        if other != name and other.lower() == name.lower():
            return (
                f"an agent named '{other}' already exists in this project; names must differ by "
                "more than case, because the two would share one worktree folder on Windows and "
                "macOS"
            )
    return None
