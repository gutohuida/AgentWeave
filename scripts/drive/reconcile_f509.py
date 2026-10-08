"""Reconcile F509's three trial slices into the capability corpus, through the trial Hub (the corpus is
Hub-owned; never edit the HTML). They shipped on 2026-10-06, the day before `spec/` became the source of
truth, and were reconciled into neither openspec nor `spec/`, so their documents could not be archived:

- `same-file-tasks-build-in-order` (slice 1): task `files`, the unordered-overlap warning;
- `same-file-tasks-build-in-order-the-shim-planner-is-told` (1b): what the planner is taught; `aw-tool --help`;
- `submission-warns-when-a-multi-task-planner-declares-no-files` (1c): the undeclared-files warning.

Statements are the slices' own, merged per behaviour; their "no migration" lines are not behaviour and stay
in the change documents. Live check before reconciling: tests/test_aw_tool_help.py,
test_spec_undeclared_files_warning.py and the overlap tests, 25 passed (2026-10-08).

Run from hub/ so `hub.spec_payload` is importable:
  cd hub && AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 ../scripts/drive/reconcile_f509.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

from hub.spec_payload import extract_payload  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]

ADDITIONS = {
    "spec/capabilities/spec-document-authority/spec.html": (
        [
            {
                "key": "a-task-may-declare-the-files-it-will-edit",
                "modal": "MAY",
                "statement": (
                    "A task declared in a document MAY carry a `files` list of repo-relative paths it "
                    "expects to edit. A document with `files` on its tasks is accepted and stored "
                    "unchanged, and a path that is empty or absolute is refused naming the task. A "
                    "directory path covers every path beneath it."
                ),
                "rationale": "F509 slice 1: the planner's way to say which tasks touch the same file.",
            },
            {
                "key": "unordered-tasks-sharing-a-file-are-warned",
                "modal": "MUST",
                "statement": (
                    "When two tasks declared in one document have overlapping `files` and neither can "
                    "reach the other through `depends_on`, directly or transitively, the "
                    "submit_spec_document response MUST carry a warning (`unordered_file_overlap`) naming "
                    "both task keys and an overlapping path, and `ready_to_propose` is not made false by "
                    "it. No warning is given for a pair ordered by `depends_on`, for a task that declares "
                    "no `files`, or for an imported task entry."
                ),
                "rationale": "F509 slice 1: parallel tasks editing one file conflicted at merge.",
            },
            {
                "key": "the-planner-is-taught-files-and-ordering",
                "modal": "MUST",
                "statement": (
                    "The submit_spec_document tool description, the exploring-phase duty text rendered "
                    "into a specification turn, and the tool section rendered into a run's prompt (shim, "
                    "MCP and HTTP renderings alike) MUST state that a task lists the repo-relative paths "
                    "it will edit in `files` and that tasks sharing a path are chained with `depends_on` "
                    "rather than left parallel."
                ),
                "rationale": (
                    "F509 slices 1 and 1b: a planner on the call command never saw the text that taught "
                    "it, so slice 1 could not fire for it."
                ),
            },
            {
                "key": "a-multi-task-document-without-files-is-warned",
                "modal": "MUST",
                "statement": (
                    "When a submitted document declares two or more local tasks and at least one declares "
                    "no `files` (absent or empty), the submit response MUST carry one advisory warning, "
                    "in the same `warnings` list as `unordered_file_overlap`, naming every such task by "
                    "key and saying to list its paths in `files` and chain tasks sharing a path with "
                    "`depends_on`. It never blocks: `blocking` and `ready_to_propose` are unchanged by it. "
                    "None is given for fewer than two local tasks (imported entries neither count nor are "
                    "named) or when every local task declares `files`."
                ),
                "rationale": "F509 slice 1c: a planner that declares no files defeats the overlap warning silently.",
            },
        ],
        [
            {"key": "f509-files-accepted", "requirement": "a-task-may-declare-the-files-it-will-edit",
             "given": "a payload whose tasks carry `files`, one with an absolute path",
             "when": "it is validated",
             "then": "the valid lists are stored as given; the absolute path is refused naming its task"},
            {"key": "f509-overlap-warned", "requirement": "unordered-tasks-sharing-a-file-are-warned",
             "given": "two tasks both declaring `hub/hub/mcp_server.py`, with and then without depends_on",
             "when": "the document is submitted",
             "then": "unordered: a warning names both keys and the path; ordered: no warning"},
            {"key": "f509-taught", "requirement": "the-planner-is-taught-files-and-ordering",
             "given": "the tool description, the exploring duty, and the shim/MCP/HTTP tool sections",
             "when": "each is read",
             "then": "each names `files` and `depends_on` and the same-path chaining rule"},
            {"key": "f509-undeclared-warned", "requirement": "a-multi-task-document-without-files-is-warned",
             "given": "three local tasks, one declaring `files`",
             "when": "the document is submitted",
             "then": "one warning names the two without `files`; `ready_to_propose` is unchanged"},
        ],
    ),
    "spec/capabilities/agent-tool-surface/spec.html": (
        [
            {
                "key": "aw-tool-help-prints-a-tools-whole-description",
                "modal": "MUST",
                "statement": (
                    "`aw-tool --help <tool>` MUST print the complete description of that tool, and a name "
                    "that is not a callable tool is refused with a usage error naming it; `aw-tool --help` "
                    "alone and `aw-tool --list` are unchanged. The tool-access notice of a run that reaches "
                    "the Hub through `aw-tool` states that `--list` shows only each tool's first line and "
                    "`--help <tool>` shows the whole."
                ),
                "rationale": "F509 slice 1b: `--list` cut descriptions to one line, hiding the task fields.",
            },
        ],
        [
            {"key": "f509-help", "requirement": "aw-tool-help-prints-a-tools-whole-description",
             "given": "`aw-tool --help submit_spec_document` and `aw-tool --help not_a_tool`",
             "when": "each runs in call mode",
             "then": "the first prints the whole description, naming `depends_on` and `files`; the second "
                     "is a usage error naming `not_a_tool`"},
        ],
    ),
}

for path, (requirements, criteria) in ADDITIONS.items():
    payload = extract_payload((REPO / path).read_text(encoding="utf-8"))
    have = {r["key"] for r in payload["requirements"]}
    if any(r["key"] in have for r in requirements):
        print(path, "already reconciled")
        continue
    payload["requirements"] += requirements
    payload["acceptance_criteria"] += criteria
    code, res = api("PUT", f"/projects/{P}/project/documents/{path}/content", {"document": payload})
    print(path, code, json.dumps(res)[:300])
