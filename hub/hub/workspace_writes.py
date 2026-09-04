"""Which tool calls write a file, and which file they say they will write.

Pure and stdlib-only, deliberately: no session, no filesystem *writes*, no import of anything
that touches the database. The call site this exists for is `tool_use_event`
(`runner_events.py:134`), which is on the path of every tool call of every run and of all three
transports, so anything that could block, fail or need a connection does not belong here.

`classify`'s `os.path.realpath` is the module's one piece of filesystem contact, and it is
deliberate: it reads links, which is the only reason this and `mcp_server._decide` agree about a
symlinked path. `written_paths`, the half that runs on every tool call, touches nothing --
`classify` runs only for the paths `written_paths` has already picked out as writes.

The module owns the two halves that must not drift apart -- *which tools write*, and *where a
path belongs in each one's input*. Splitting them across two modules is how a writer gains a tool
and loses its path, or the reverse.

`written_paths` returns on the **tool name** before it looks at the input. That is what the
function is -- writers only, everything else empty -- not a cost optimisation: `tool_use_event`
has already committed to `redact_secrets` plus `json.dumps(sort_keys=True)` over the whole input
unconditionally by the time this could be called (design D13), so a tuple-membership test is not
measurable beside it. Stating performance as the reason would invite the next reader to relax the
early return once the cost argument stops applying.

An **unknown tool returns empty rather than guessing from key names**. A detector that invents
coverage is the failure mode this whole change is careful about: a record claiming to have
watched a tool nobody taught it is worse than no record.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

#: Claude's file-writing tools, each mapped to the input key naming the file it writes.
#:
#: `MultiEdit` is here. Its several edits all target the one file named at the top level
#: (`{file_path, edits: [...]}`), so it stays one path, and the timeline, `lib/editDiff.ts` and
#: the timeline's own tests all recognise it (design D3).
CLAUDE_WRITE_TOOLS: Dict[str, str] = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}

#: Codex's single file-writing tool, on both its transports. `parse_codex_line`'s `file_change`
#: branch and `map_item_to_events`' `fileChange` branch each hand `tool_use_event` the same
#: `{"changes": [...]}`, so one entry covers both.
CODEX_WRITE_TOOL = "apply_patch"

#: Every tool whose call *is* a write, across both providers. Reads (`Read`, `Glob`, `Grep`,
#: `LS`) are deliberately absent: the finding is about work landing where nothing will attribute
#: it, and a read leaves nothing behind. Recording reads would also drown the record -- an agent
#: reads outside its workspace constantly and correctly.
WRITE_TOOLS = frozenset(CLAUDE_WRITE_TOOLS) | {CODEX_WRITE_TOOL}


def written_paths(tool: str, input_data: Any) -> Tuple[str, ...]:
    """The path argument(s) a file-writing tool call declares, empty for everything else.

    Raw strings, exactly as the tool declared them -- relative or absolute, in whatever separator
    style the runtime used. Resolving one against a workspace is `classify`'s job, not this one's.

    Total: every input maps to a tuple. Malformed input extracts nothing and raises nothing,
    because this runs inside event parsing on a live turn, and a parser that throws on a shape it
    did not expect loses the whole turn's output rather than one path.
    """
    if tool in CLAUDE_WRITE_TOOLS:
        return _one_path(input_data, CLAUDE_WRITE_TOOLS[tool])
    if tool == CODEX_WRITE_TOOL:
        return _change_paths(input_data)
    return ()


def _one_path(input_data: Any, key: str) -> Tuple[str, ...]:
    if not isinstance(input_data, dict):
        return ()
    value = input_data.get(key)
    if isinstance(value, str) and value:
        return (value,)
    return ()


def _change_paths(input_data: Any) -> Tuple[str, ...]:
    """Codex names several files under `changes[].path`, which is why the return is a tuple.

    The element shape is `{"path": ..., "diff": ...}`, taken from a live item rather than from the
    summariser (F107, and `_changed_paths` in `codex_appserver.py` reads the same field the same
    way). The diff is ignored here: this answers *where*, and the patch body is already carried in
    the same event's `input`.
    """
    if not isinstance(input_data, dict):
        return ()
    changes = input_data.get("changes")
    if not isinstance(changes, list):
        return ()
    paths: List[str] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        path = change.get("path")
        if isinstance(path, str) and path:
            paths.append(path)
    return tuple(paths)


#: The Hub's own directory inside a project root. Restated here rather than imported: `worktrees`
#: reaches `subprocess`, `shutil` and `repo_hygiene`, and this module is on the path of every tool
#: call of every run (see the module docstring). This is the restate-and-assert shape
#: `mcp_server.py` already uses -- `test_workspace_writes.py` binds every name below to
#: `worktrees.worktree_root`/`task_root`/`review_root`, so the two cannot drift silently.
HUB_DIRECTORY = ".agentweave"

#: `<root>/.agentweave/<segment>/<name>` -> the kind of checkout it is. The layout is
#: `worktrees.py`'s (`worktree_path`, `task_worktree_path`, `review_path`); the kind vocabulary is
#: `WorkspaceBranch`'s, which is what `workspace-isolation` already requires an API response
#: describing a checkout to speak.
CHECKOUT_SEGMENTS: Dict[str, str] = {
    "worktrees": "agent",
    "tasks": "task",
    "reviews": "review",
}

#: Every kind `classify` can return.
#:
#: `hub` is a kind of its own and is **not** folded into `project` (design D4). `repo_hygiene`
#: seeds `.agentweave/worktrees|reviews|tasks|logs|evidence|context` into the repository's
#: `info/exclude` on every turn, so that subtree is the one part of the project root git has been
#: told to hide -- the opposite of the tracked tree, whose owner's `git status` shows the write.
#: `.agentweave/evidence/` is the sharp case: the Hub's own record-keeping about the very run
#: doing the writing.
#:
#: `unknown` is not `outside`. When the workspace cannot be resolved the honest answer is that
#: nobody could tell, and a record saying "it wrote outside" would accuse a run of something it
#: may not have done. This is the one place the design deliberately does not copy `_decide`, which
#: refuses when it cannot establish a boundary -- correct for a gate, wrong for a record.
WRITE_LOCATION_KINDS = (
    "inside",
    "agent",
    "task",
    "review",
    "hub",
    "project",
    "outside",
    "unknown",
)


class WriteLocation(NamedTuple):
    """Where a declared path landed: a kind, and the name of the thing it belongs to.

    Two fields rather than a name alone, matching `worktrees.WorkspaceBranch` and the
    `workspace-isolation` requirement it satisfies -- a task id is not an oddly named agent.

    `name` is `None` for the kinds that have no *which one* to answer. There is exactly one
    project directory and one Hub directory per project, and `inside`, `outside` and `unknown`
    name nothing at all; a name there would only repeat the kind.

    Hashable, because the recorder keys its once-per-destination accounting on a whole location.
    """

    kind: str
    name: Optional[str] = None


def classify(
    path: str, *, workspace_dir: Optional[str], project_root: Optional[str]
) -> WriteLocation:
    """Where *path* lands, relative to the run's own workspace and to its project.

    Pure and total: no filesystem writes, no session, and every input maps to a location. The
    only filesystem contact is `os.path.realpath`, which reads links -- the same contact
    `mcp_server._decide` makes for the same comparison, and the reason the two agree about a
    symlink.

    **Joins before it resolves**, which is not an implementation detail of the comparison:

        absolute = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)

    copied whole from `_decide` (`mcp_server.py:938`). `os.path.realpath` resolves a *relative*
    path against the **calling process's** working directory. `_decide` could almost have got away
    without the join because it *is* the spawned MCP server, whose cwd is the run's workspace;
    this runs in the Hub process, whose cwd is wherever uvicorn was started and has nothing to do
    with any project. Without the join a relative `../../x` would classify against the Hub's
    launch directory -- usually `outside` for the wrong reason, and on a Hub started inside a
    project, silently `project`.

    The containment test is `commonpath` + `normcase`, `_decide`'s again: `commonpath` compares
    components, so `/work-other` does not read as inside `/work`, and it raises `ValueError`
    across Windows drives, which is not containment either.
    """
    root = _resolved_directory(workspace_dir)
    if root is None:
        return WriteLocation("unknown")
    absolute = path if os.path.isabs(path) else os.path.join(root, path)
    try:
        resolved = os.path.realpath(absolute)
    except OSError:
        return WriteLocation("unknown")

    if _contains(root, resolved):
        return WriteLocation("inside")

    project = _resolved_directory(project_root)
    if project is None or not _contains(project, resolved):
        return WriteLocation("outside")
    return _within_project(project, resolved)


def _resolved_directory(value: Optional[str]) -> Optional[str]:
    """*value* as a real path, or `None` if there is nothing usable to compare against."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return os.path.realpath(value.strip())
    except OSError:
        return None


def _contains(root: str, resolved: str) -> bool:
    try:
        shared = os.path.commonpath([root, resolved])
    except ValueError:  # different drives on Windows
        return False
    return os.path.normcase(shared) == os.path.normcase(root)


def _within_project(project: str, resolved: str) -> WriteLocation:
    """*resolved* is known to be inside *project*; say which part of it.

    String work only -- containment has already been established against real paths, so
    `relpath` here cannot produce a `..` component and cannot raise.
    """
    relative = os.path.normpath(os.path.relpath(resolved, project))
    parts = [part for part in relative.split(os.sep) if part and part != "."]
    if not parts or os.path.normcase(parts[0]) != os.path.normcase(HUB_DIRECTORY):
        return WriteLocation("project")
    if len(parts) >= 3:
        kind = CHECKOUT_SEGMENTS.get(os.path.normcase(parts[1]))
        if kind is not None:
            return WriteLocation(kind, parts[2])
    return WriteLocation("hub")
