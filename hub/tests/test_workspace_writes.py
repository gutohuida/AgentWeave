"""Which tool calls `workspace_writes` calls a write, and where it reads the path from.

Phase 2a of `a-write-outside-the-workspace-is-recorded`. The module under test has no call site
yet -- `write_paths` on `RunEvent` is phase 2b's and the recorder is phase 4's -- so everything
here is about the two halves the module owns: the writer list, and the input key each writer
declares its path under.

Two of these tests exist because the writer list is **the fourth place in this product that
states which tools write**, and the previous three do not agree with each other. Round 2 of the
proposal reconciled against the wrong one and dropped `MultiEdit`; round 3 measured all three and
put it back (design D3). A list restated in a fourth place with nothing checking it is how the
disagreement gets one member wider, so the reconciliation is asserted rather than described:

* `AgentTimeline.tsx`'s `WRITING_TOOLS` is the same *concept* -- tools whose call is a write,
  across both providers -- and already drives the "wrote to N files" summary an operator reads.
  The sets must be **equal**. Read out of the real `.tsx` source, not restated here, because a
  restatement is exactly the drift being guarded against.
* `mcp_server._PATH_KEYS` is where the permission approver looks for a path in a Claude tool's
  input. The Claude writers' keys must be a **subset**: `_PATH_KEYS` is deliberately wider (it
  also covers readers' `path`), and Codex's nested `changes[].path` is deliberately not in it.
* `runner_commands.restrict_spec_writes` is **not** asserted against, on purpose. See
  `test_restrict_spec_writes_is_not_the_definition_of_a_write_tool` below.
"""

import ast
import inspect
import re
import subprocess
import sys
from pathlib import Path

from hub.workspace_writes import (
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOL,
    WRITE_TOOLS,
    written_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_TIMELINE = REPO_ROOT / "hub" / "ui" / "src" / "components" / "agents" / "AgentTimeline.tsx"


def _ui_writing_tools() -> set:
    """`WRITING_TOOLS` as the shipped UI source actually spells it.

    Parsed rather than restated: the whole point of the assertion is that the two lists cannot
    drift, and a copy of the list in this file drifts with it. A moved or renamed declaration
    fails loudly here instead of quietly asserting nothing -- the anchor was `:573` when the
    tasks were written and is `:615` today, so it moves.
    """
    source = AGENT_TIMELINE.read_text(encoding="utf-8")
    match = re.search(r"const WRITING_TOOLS = new Set\(\[(.*?)\]\)", source, re.S)
    assert match, f"WRITING_TOOLS is no longer declared in {AGENT_TIMELINE.name}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _imports_of(module: str) -> list:
    """Every `hub`/database module a fresh interpreter loads when it imports *module*.

    A subprocess, so nothing pytest already imported can mask a dependency. `hub` itself
    always appears, because importing any submodule runs the package `__init__`.
    """
    probe = "".join(
        (
            "import sys" + chr(10),
            "before = set(sys.modules)" + chr(10),
            "import " + module + chr(10),
            "new = set(sys.modules) - before" + chr(10),
            "roots = {'hub', 'sqlalchemy', 'aiosqlite', 'fastapi', 'pydantic'}" + chr(10),
            "print(repr(sorted(m for m in new if m.split('.')[0] in roots)))" + chr(10),
        )
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT / "hub"),
        capture_output=True,
        text=True,
        check=True,
    )
    return ast.literal_eval(result.stdout.strip())


def test_the_writer_set_equals_the_timelines():
    """Task 2.2b. Equal, not subset, in either direction.

    A tool the UI counts as a write but this module does not is a write the record would miss
    while the operator is being shown a count that includes it. A tool this module counts and the
    UI does not is the reverse. Neither is a difference anyone would choose deliberately without
    changing both.
    """
    assert set(WRITE_TOOLS) == _ui_writing_tools()
    assert "MultiEdit" in WRITE_TOOLS, "round 2 dropped it on a false ground round 3 overturned"
    assert CODEX_WRITE_TOOL in WRITE_TOOLS


def test_the_claude_path_keys_are_a_subset_of_the_approvers():
    """Task 2.2b, second half. Restate-and-assert, the shape `test_permission_approver.py` uses.

    `mcp_server.py` is spawned standalone and may import only stdlib plus fastmcp, so it cannot
    import this module and this module must not be imported into it. A test that imports both is
    the available way to keep the two readings of "where is the path in this input" from
    diverging.

    Subset rather than equality, and both directions have a reason. `_PATH_KEYS` carries `path`,
    which readers use and no Claude writer declares. Codex's `apply_patch` names its paths at
    `changes[].path`, nested one level down, which `_PATH_KEYS` does not contain and should not --
    `_decide` only ever sees Claude's flat tool inputs.
    """
    from hub import mcp_server

    assert set(CLAUDE_WRITE_TOOLS.values()) <= set(mcp_server._PATH_KEYS)
    assert "path" in mcp_server._PATH_KEYS
    assert "path" not in set(CLAUDE_WRITE_TOOLS.values())


def test_restrict_spec_writes_is_not_the_definition_of_a_write_tool():
    """Task 2.2c -- file the gap, do not inherit it, and do not fix it here.

    `restrict_spec_writes` passes `--disallowedTools Edit,Write,NotebookEdit` and omits
    `MultiEdit`, which the timeline counts as a write. So a spec-authoring agent restricted by
    that flag may still be able to write through `MultiEdit`. That is a real gap and it is
    recorded as F277; it is not this change's to fix.

    What this change must not do is treat that flag as the answer to "which tools write". It is a
    permissions decision about one kind of agent, Claude-only by construction -- a
    `--disallowedTools` argument can never name `apply_patch` -- so round 2's proposed assertion
    (that every writer appears in that list) is false for the Codex half and would have forced
    `MultiEdit` out for a reason that does not hold.

    Asserted as an inequality so that closing the gap upstream does not silently make this file
    start depending on the two lists agreeing.
    """
    from hub.runner_commands import build_command

    command = build_command(runner="claude", cli="claude", prompt="hi", restrict_spec_writes=True)
    disallowed = set(command[command.index("--disallowedTools") + 1].split(","))

    assert "MultiEdit" not in disallowed, "F277 fixed upstream -- retire the finding, not this test"
    assert "MultiEdit" in WRITE_TOOLS
    assert CODEX_WRITE_TOOL not in disallowed
    assert set(WRITE_TOOLS) != disallowed


def test_the_claude_writers_each_name_one_file():
    """Task 2.3, Claude half. `MultiEdit` is the one worth stating.

    Its input is `{file_path, edits: [...]}`: several edits, one file, named once at the top
    level. So it is a writer with exactly one path, not a writer with several, and reading its
    `edits` for paths would find none.
    """
    assert written_paths("Write", {"file_path": "/tmp/a.txt"}) == ("/tmp/a.txt",)
    assert written_paths("Edit", {"file_path": "rel/b.txt", "old_string": "x"}) == ("rel/b.txt",)
    assert written_paths(
        "MultiEdit",
        {"file_path": "C:\\work\\c.py", "edits": [{"old_string": "a"}, {"old_string": "b"}]},
    ) == ("C:\\work\\c.py",)
    assert written_paths("NotebookEdit", {"notebook_path": "/n/d.ipynb"}) == ("/n/d.ipynb",)


def test_a_claude_writer_reads_only_its_own_key():
    """A `Write` that carried `path` instead of `file_path` is not a shape Claude emits, and
    guessing it would be the same invention an unknown tool is refused for."""
    assert written_paths("Write", {"path": "/tmp/a.txt"}) == ()
    assert written_paths("NotebookEdit", {"file_path": "/tmp/a.txt"}) == ()


def test_apply_patch_names_several_files_and_the_tuple_is_load_bearing():
    """Task 2.3, Codex half -- the reason the return type is a tuple rather than an optional str.

    Both Codex transports hand `tool_use_event` the same `{"changes": [...]}`:
    `parse_codex_line`'s `file_change` branch and `map_item_to_events`' `fileChange` branch. The
    element shape is task 2.5b's, and the order is Codex's own.
    """
    changes = [
        {"path": "a.py", "diff": "a patch body"},
        {"path": "sub/b.py", "diff": "another"},
        {"path": "/abs/c.py", "diff": ""},
    ]
    assert written_paths("apply_patch", {"changes": changes}) == ("a.py", "sub/b.py", "/abs/c.py")


def test_the_diff_is_not_a_path():
    """The patch body is already carried in the same event's `input`. What this answers is
    *where*, and a diff pasted into that answer would bury it."""
    extracted = written_paths("apply_patch", {"changes": [{"path": "a.py", "diff": "patch"}]})
    assert extracted == ("a.py",)


def test_reads_and_unknown_tools_extract_nothing():
    """Design D3, and the half of it that matters most.

    Reads are excluded because a read leaves nothing behind to attribute, and because an agent
    reads outside its workspace constantly and correctly -- recording those would drown the
    record. An unknown tool is excluded because a detector that guesses from key names invents
    coverage it does not have, and a record claiming to have watched a tool nobody taught it is
    worse than no record. Both `Read` and `Bash` below carry a perfectly path-shaped value under
    a key this module knows; neither is a writer, so neither yields anything.
    """
    assert written_paths("Read", {"file_path": "/tmp/a.txt"}) == ()
    assert written_paths("Glob", {"path": "/tmp"}) == ()
    assert written_paths("Grep", {"path": "/tmp"}) == ()
    assert written_paths("LS", {"path": "/tmp"}) == ()
    assert written_paths("Bash", {"command": "echo hi > /tmp/a.txt"}) == ()
    assert written_paths("SomeToolShippedNextYear", {"file_path": "/tmp/a.txt"}) == ()
    assert written_paths("mcp__agentweave__submit_spec_document", {"path": "/tmp/a"}) == ()
    assert written_paths("write", {"file_path": "/tmp/a.txt"}) == (), "names are case-sensitive"
    assert written_paths("", None) == ()


def test_malformed_input_extracts_nothing_and_raises_nothing():
    """Task 2.5b -- F107's cases verbatim, because this runs on a live turn.

    `written_paths` sits inside `tool_use_event`, which is on the path of every tool call of every
    run on all three transports. A parser that throws on a shape it did not expect does not lose
    one path, it loses the whole turn's output. So every one of these returns empty, and none of
    them raises.
    """
    for junk in (None, {}, {"changes": "not-a-list"}, {"changes": [{"path": 1}, {}, None]}):
        assert written_paths("apply_patch", junk) == ()

    for junk in (None, {}, [], "a string", 7, {"file_path": None}, {"file_path": 1}):
        assert written_paths("Write", junk) == ()

    assert written_paths("Write", {"file_path": ""}) == (), "an empty path is not a path"
    assert written_paths("apply_patch", {"changes": []}) == ()
    assert written_paths("apply_patch", {"changes": [{"path": "a.py"}, {"path": ""}]}) == ("a.py",)


def test_the_paths_arrive_exactly_as_declared():
    """Raw strings, not resolved ones. Classifying a path against a workspace is phase 3's job,
    and doing any of it here would need a filesystem this module is not allowed to touch."""
    assert written_paths("Write", {"file_path": "../../etc/passwd"}) == ("../../etc/passwd",)
    assert written_paths("Write", {"file_path": "C:/w/a.txt"}) == ("C:/w/a.txt",)
    assert written_paths("Write", {"file_path": "C:\\w\\a.txt"}) == ("C:\\w\\a.txt",)


def test_the_function_takes_no_workspace_and_no_session():
    """Task 2.6, signature half. A workspace parameter here would be the beginning of the
    filesystem access the module docstring rules out, and a session parameter would put a
    database connection on the path of every tool call of every run."""
    parameters = list(inspect.signature(written_paths).parameters)
    assert parameters == ["tool", "input_data"]


def test_importing_the_module_pulls_in_no_other_hub_module_and_no_database():
    """Task 2.6, measured rather than asserted from reading the imports.

    A fresh interpreter, so nothing pytest already imported can mask a dependency. `hub` itself
    appears because importing any submodule runs the package `__init__`; nothing else from `hub`
    may. `sqlalchemy` and `aiosqlite` are named explicitly because "touches the database" is the
    specific claim -- but the `hub`-module assertion is the stronger one, since it also fails for
    a dependency that reaches the database indirectly.

    `hub.runner_parsing` is probed too, because that is where phase 2b's call site lands and
    task 2.6 names it: importing it in isolation is what keeps "the parser stays pure" honest.
    Its own import set is checked rather than pinned to an exact list -- it legitimately pulls
    in `hub.model_catalog` and `hub.runner_events`, and pinning the set would make this test
    fail for a refactor that changes nothing about purity. What it may never pull in is a
    database.
    """
    assert _imports_of("hub.workspace_writes") == ["hub", "hub.workspace_writes"]

    parsing = _imports_of("hub.runner_parsing")
    assert all(module.startswith("hub") for module in parsing), parsing
