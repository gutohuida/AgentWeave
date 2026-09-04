"""Which tool calls write a file, and which file they say they will write.

Pure and stdlib-only, deliberately: no session, no filesystem access, no import of anything that
touches the database. The call site this exists for is `tool_use_event`
(`runner_events.py:134`), which is on the path of every tool call of every run and of all three
transports, so anything that could block, fail or need a connection does not belong here.

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

from typing import Any, Dict, List, Tuple

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
