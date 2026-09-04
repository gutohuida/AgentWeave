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
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from hub.mcp_server import _decide
from hub.repo_hygiene import EXCLUDE_PATTERNS
from hub.workspace_writes import (
    CHECKOUT_SEGMENTS,
    CLAUDE_WRITE_TOOLS,
    CODEX_WRITE_TOOL,
    HUB_DIRECTORY,
    WRITE_LOCATION_KINDS,
    WRITE_TOOLS,
    classify,
    written_paths,
)
from hub.worktrees import (
    review_path,
    review_root,
    task_root,
    task_worktree_path,
    worktree_path,
    worktree_root,
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


# --------------------------------------------------------------------------------------------
# Phase 3: classifying a path against the run's workspace.
#
# Still no call site -- the recorder is phase 4's. What is under test is the answer `classify`
# gives, and the two traps rounds 1 and 2 of the proposal both fell into: the join that must
# happen before the resolve, and the `hub` kind that must not be folded into `project`.
# --------------------------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project root, and a working directory that is neither it nor any workspace in it.

    The cwd matters. `classify` runs in the Hub process, which serves many projects from wherever
    uvicorn was started, so a test that happened to run from inside the fixture workspace would
    pass for `realpath`'s reasons rather than for the join's (task 3.2). Every test in this
    section therefore runs from `elsewhere/deep`.
    """
    root = tmp_path / "project"
    (root / ".agentweave").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere" / "deep"
    elsewhere.mkdir(parents=True)
    monkeypatch.chdir(elsewhere)
    return root


def _in(project_root, workspace, path):
    return classify(str(path), workspace_dir=str(workspace), project_root=str(project_root))


def test_a_path_inside_the_runs_own_workspace_is_inside(project):
    """Task 3.3. `inside` is the answer that records nothing, so it is the one the recorder leans
    on hardest -- a file at the top, a file deep down, and the workspace directory itself."""
    workspace = worktree_path(project, "alice")
    assert _in(project, workspace, workspace / "a.txt") == ("inside", None)
    assert _in(project, workspace, workspace / "src" / "deep" / "a.txt") == ("inside", None)
    assert _in(project, workspace, workspace) == ("inside", None)


def test_another_agents_worktree_is_named_by_kind_and_by_agent(project):
    """Task 3.1, and the case whose whole meaning is the destination (task 1.3).

    The path is built by `worktree_path` itself rather than spelled out here -- the classifier
    restates the layout, and this is what binds the restatement to the helper.
    """
    workspace = worktree_path(project, "alice")
    assert _in(project, workspace, worktree_path(project, "bob") / "a.txt") == ("agent", "bob")


def test_a_task_checkout_and_a_review_checkout_are_their_own_kinds(project):
    """Task 3.1. A task id is not an oddly named agent (`workspace-isolation`), and a reviewer's
    detached checkout is neither -- so all three come from their own layout helper."""
    workspace = worktree_path(project, "alice")
    task = task_worktree_path(project, "task-ab12cd34")
    assert _in(project, workspace, task / "a.txt") == ("task", "task-ab12cd34")
    assert _in(project, workspace, review_path(project, "bob") / "a.txt") == ("review", "bob")


def test_the_restated_layout_is_the_one_the_worktree_helpers_use(project):
    """Task 3.1's one-source-of-truth half, asserted rather than described.

    `workspace_writes` may not import `worktrees`: the purity test above runs a fresh interpreter
    and demands the module pull in no other `hub` module, and `worktrees` reaches `subprocess`,
    `shutil` and `repo_hygiene`. So the layout is restated -- the same restate-and-assert shape
    `mcp_server.py` lives under -- and this is the assertion that keeps the copy honest: the
    three roots the classifier believes in are the three roots the helpers compute.
    """
    roots = {
        "worktrees": worktree_root(project),
        "tasks": task_root(project),
        "reviews": review_root(project),
    }
    assert set(roots) == set(CHECKOUT_SEGMENTS)
    for segment, helper_root in roots.items():
        assert helper_root == project / HUB_DIRECTORY / segment
    assert CHECKOUT_SEGMENTS["worktrees"] == "agent"
    assert CHECKOUT_SEGMENTS["tasks"] == "task"
    assert CHECKOUT_SEGMENTS["reviews"] == "review"


def test_every_hub_excluded_path_is_a_checkout_or_the_hub_and_never_the_project(project):
    """Task 3.1b, round 3's correction, and it is not cosmetic.

    `seed_repo_excludes` writes `EXCLUDE_PATTERNS` into the repository's `info/exclude` on every
    turn -- `resolve_agent_workspace` calls it as its first statement -- so every `.agentweave/`
    pattern below names a directory git has been *told to hide*. The requirement justifies
    `project` as the mild destination on the grounds that a write there sits visibly in its
    owner's `git status`. That justification is exactly inverted here, so none of these may
    classify as `project`.

    Walked rather than listed: the classifier derives the three checkouts from the layout helpers
    and not from this list -- one source of truth for the layout -- and this walk is what stops
    the two drifting when a pattern is added.
    """
    workspace = worktree_path(project, "alice")
    hub_patterns = [p for p in EXCLUDE_PATTERNS if p.startswith(HUB_DIRECTORY + "/")]
    assert len(hub_patterns) >= 6, hub_patterns

    for pattern in hub_patterns:
        target = project.joinpath(*pattern.rstrip("/").split("/")) / "x" / "a.txt"
        location = _in(project, workspace, target)
        assert location.kind in {"agent", "task", "review", "hub"}, (pattern, location)
        assert location.kind != "project", pattern


def test_the_hubs_own_record_keeping_about_the_run_is_hub_not_project(project):
    """Task 10.4, the sharp case of 3.1b.

    `.agentweave/evidence/` is where the Hub keeps its own record of runs. A run writing there is
    writing into the bookkeeping about itself, in a directory that appears in no `git status`
    anywhere. Calling that "the project" would attach the mildest reading to the least visible
    destination.
    """
    workspace = worktree_path(project, "alice")
    evidence = project / HUB_DIRECTORY / "evidence" / "x"
    assert _in(project, workspace, evidence) == ("hub", None)
    assert _in(project, workspace, evidence / "footprint.json") == ("hub", None)
    # The residue of the subtree, not only the six excluded directories.
    assert _in(project, workspace, project / HUB_DIRECTORY / "project.json") == ("hub", None)
    # A checkout *root* itself is not a checkout: the layout needs a name under it before the
    # path belongs to anybody. What sits directly under a root *is* read as that name, whatever
    # it turns out to be on disk -- the classifier stats nothing, deliberately, because the path
    # it is handed has usually not been written yet.
    assert _in(project, workspace, worktree_root(project)) == ("hub", None)
    assert _in(project, workspace, worktree_root(project) / "bob") == ("agent", "bob")


def test_the_projects_own_tracked_tree_is_project(project):
    """Task 3.1. The destination the requirement describes as landing where its owner's
    `git status` will show it -- true of the tracked tree and, per 3.1b, of nothing under
    `.agentweave/`."""
    workspace = worktree_path(project, "alice")
    assert _in(project, workspace, project / "src" / "main.py") == ("project", None)
    assert _in(project, workspace, project / "README.md") == ("project", None)


def test_a_path_in_no_project_at_all_is_outside(project, tmp_path):
    workspace = worktree_path(project, "alice")
    assert _in(project, workspace, tmp_path / "somewhere" / "a.txt") == ("outside", None)


def test_without_a_project_root_a_write_is_outside_rather_than_unknown(project):
    """`unknown` is reserved for a workspace that could not be established (task 3.4). A missing
    project root leaves the *destination* unnameable, but the workspace resolved and the write
    did leave it -- which is the fact being recorded."""
    workspace = worktree_path(project, "alice")
    target = str(worktree_path(project, "bob") / "a.txt")
    assert classify(target, workspace_dir=str(workspace), project_root=None) == ("outside", None)
    assert classify(target, workspace_dir=str(workspace), project_root="  ") == ("outside", None)


def test_a_relative_path_is_joined_to_the_workspace_before_it_is_resolved(project):
    """Task 3.2, the trap rounds 1 and 2 both fell into.

    Round 1 asserted `realpath` alone would catch the `..` case. It will not: `realpath` resolves
    a relative path against the *calling process's* cwd, and this runs in the Hub process, not in
    the run. The `project` fixture has chdir'd to `elsewhere/deep`, which is in neither the
    workspace nor the project, so the control below is what makes the first assertion mean
    anything -- resolved against the cwd, the same string lands outside the project entirely and
    would have read as `outside` rather than as another agent's workspace.
    """
    workspace = worktree_path(project, "alice")
    relative = os.path.join("..", "bob", "a.txt")

    assert classify(relative, workspace_dir=str(workspace), project_root=str(project)) == (
        "agent",
        "bob",
    )

    against_cwd = os.path.realpath(relative)
    assert not against_cwd.startswith(str(project))
    assert classify(against_cwd, workspace_dir=str(workspace), project_root=str(project)) == (
        "outside",
        None,
    )


def test_a_relative_path_that_traverses_out_of_the_project_is_outside(project):
    """The delta's scenario *A relative path that traverses outside is caught*, end to end."""
    workspace = worktree_path(project, "alice")
    escape = os.path.join("..", "..", "..", "..", "elsewhere", "a.txt")
    assert classify(escape, workspace_dir=str(workspace), project_root=str(project)) == (
        "outside",
        None,
    )


def test_a_sibling_sharing_a_prefix_does_not_read_as_inside(tmp_path, monkeypatch):
    """Task 3.2's `commonpath` half. `/work-other` does not start inside `/work`, and a string
    prefix test would say it does."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "p"
    workspace = root / "work"
    sibling = root / "work-other"
    workspace.mkdir(parents=True)
    sibling.mkdir()
    assert classify(
        str(sibling / "a.txt"), workspace_dir=str(workspace), project_root=str(root)
    ) == ("project", None)


def test_an_absent_or_unresolvable_workspace_is_unknown_and_never_outside(project):
    """Task 3.4, and the one place the design deliberately does not copy `_decide`.

    `_decide` refuses when it cannot establish a boundary, which is right for a gate. A record is
    not a gate: writing "it wrote outside" when the truth is "nobody could tell" would attribute
    to an agent something it may not have done. Asserted as `!= "outside"` as well as
    `== "unknown"`, because it is the *accusation* that must not happen.
    """
    target = str(project / "src" / "a.txt")
    for absent in (None, "", "   "):
        location = classify(target, workspace_dir=absent, project_root=str(project))
        assert location == ("unknown", None), absent
        assert location.kind != "outside"

    with mock.patch("hub.workspace_writes.os.path.realpath", side_effect=OSError("boom")):
        assert classify(target, workspace_dir=str(project), project_root=str(project)) == (
            "unknown",
            None,
        )


def test_an_unresolvable_written_path_is_unknown_too(project):
    """The same rule, other operand. If the *candidate* cannot be resolved, nobody can tell where
    it would have landed, and the run must not be accused of leaving its workspace."""
    workspace = worktree_path(project, "alice")
    real = os.path.realpath

    def fail_on_candidate(value):
        if "candidate" in str(value):
            raise OSError("boom")
        return real(value)

    with mock.patch("hub.workspace_writes.os.path.realpath", side_effect=fail_on_candidate):
        location = classify(
            str(project / "candidate.txt"),
            workspace_dir=str(workspace),
            project_root=str(project),
        )
    assert location == ("unknown", None)


def test_a_case_only_difference_is_decided_the_same_way_as_the_permission_approver(
    project, monkeypatch
):
    """Task 3.5, half one. Whether two paths differing only in case are one directory is the
    platform's answer, not this module's -- `normcase` gives it, and `_decide` asks the same way.

    Asserted as *agreement with `_decide`* rather than as a fixed expectation, because the whole
    risk is the two disagreeing about the same path: on Windows both must say inside, on POSIX
    both must say outside, and a test pinning either answer would be wrong on one of them.
    """
    workspace = worktree_path(project, "alice")
    workspace.mkdir(parents=True)
    target = os.path.join(str(workspace).swapcase(), "a.txt")

    monkeypatch.setenv("AW_WORKSPACE_DIR", str(workspace))
    approver_allows = _decide("Write", {"file_path": target})["allow"]
    location = classify(target, workspace_dir=str(workspace), project_root=str(project))

    assert (location.kind == "inside") is approver_allows, (location, approver_allows)


@pytest.mark.skipif(os.name != "nt", reason="only Windows has drives for commonpath to raise on")
def test_a_cross_drive_path_is_not_inside_and_the_approver_agrees(project, monkeypatch):
    """Task 3.5, half two. `commonpath` raises `ValueError` across drives; that is not
    containment, and this and `_decide` must read it the same way."""
    workspace = worktree_path(project, "alice")
    workspace.mkdir(parents=True)
    other_drive = "Z:\\elsewhere\\a.txt" if str(workspace)[0].upper() != "Z" else "Y:\\a.txt"

    monkeypatch.setenv("AW_WORKSPACE_DIR", str(workspace))
    assert _decide("Write", {"file_path": other_drive})["allow"] is False
    assert classify(other_drive, workspace_dir=str(workspace), project_root=str(project)) == (
        "outside",
        None,
    )


def test_classify_takes_no_session_and_returns_only_declared_kinds(project):
    """The signature half of task 2.6, extended to phase 3's addition: a session parameter here
    would put a database connection on the path of every tool call of every run.

    The second half walks one path per row of design D4's table and asserts the set of kinds
    reached is exactly `WRITE_LOCATION_KINDS` -- so a kind added to the tuple without a case that
    produces it, or produced without being declared, fails here.
    """
    assert list(inspect.signature(classify).parameters) == [
        "path",
        "workspace_dir",
        "project_root",
    ]
    workspace = worktree_path(project, "alice")
    reached = {
        _in(project, workspace, workspace / "a.txt").kind,
        _in(project, workspace, worktree_path(project, "bob") / "a.txt").kind,
        _in(project, workspace, task_worktree_path(project, "task-ab12") / "a.txt").kind,
        _in(project, workspace, review_path(project, "bob") / "a.txt").kind,
        _in(project, workspace, project / HUB_DIRECTORY / "evidence" / "x").kind,
        _in(project, workspace, project / "src" / "a.txt").kind,
        _in(project, workspace, project.parent / "a.txt").kind,
        classify("a.txt", workspace_dir=None, project_root=None).kind,
    }
    assert reached == set(WRITE_LOCATION_KINDS)
