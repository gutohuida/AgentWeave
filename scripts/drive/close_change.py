"""Close an app-authored change's Hub records once its build is committed: record operator
evidence per requirement, then walk each change task pending -> in_progress -> completed -> land.

Commit first: the evidence footprint names HEAD, and integration skips on a dirty tree. A commit
already on the main branch lands as `already integrated`; nothing is merged.

  AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 scripts/drive/close_change.py f440 f450

Then reconcile the change into its capability, commit that, and finish the lifecycle with
`close_change.py --archive f440 f450` (see ARCHIVE: it refuses unless every task is approved and
the reconciled requirement is in the capability).
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]

TESTS = "hub/tests/test_a_decided_task_withdraws_its_waiting_reviews.py"
CLAIM_TESTS = "hub/tests/test_a_run_claims_only_its_agents_or_nobodys_work.py"
READ_ONLY_TESTS = "hub/tests/test_a_read_only_agent_holds_no_task_work.py"
CODEX_SPEC_TESTS = "hub/tests/test_a_codex_app_server_spec_turn_keeps_no_write_tools.py"
DEFAULT_REVIEWER_TESTS = "hub/tests/test_a_document_names_its_default_reviewer.py"
STRICT_MCP_TESTS = "hub/tests/test_a_hub_run_gets_only_the_hubs_tool_server.py"

CHANGES = {
    "f440": {
        "document": "spec/changes/a-decided-task-withdraws-its-waiting-reviews/spec.html",
        "tasks": ["task-3c0c22f24a44", "task-93f9df045c6a", "task-2035432af11f"],
        "evidence": [
            ("FR-1", "task-93f9df045c6a", "test_result", TESTS,
             "Approve, land and revision_needed withdraw the queued review entry in the move's "
             "transaction with the verdict as its reason (4 of 5 tests failed on HEAD 1dbff33..)."),
            ("FR-1", "task-2035432af11f", "manual_observation",
             "scripts/drive/d1007_verdict_withdraws_review.py",
             "Driven on :8010 with a real Haiku reviewer mid-turn: 4/8 before, 8/8 after; landing "
             "withdrew the entry and no delivery was attempted at the reviewer's run end."),
            ("FR-2", "task-93f9df045c6a", "test_result", TESTS,
             "Each withdrawal is announced as queue_entry_withdrawn naming entry, agent, task and "
             "verdict."),
            ("FR-3", "task-93f9df045c6a", "test_result", TESTS,
             "A delivered entry, another task's entry and a work entry's queued state are left "
             "unchanged by an approval."),
        ],
    },
    "f450": {
        "document": "spec/changes/a-run-claims-only-its-agents-or-nobodys-work/spec.html",
        "tasks": ["task-151291e8d5a9", "task-e13de03d6ec0", "task-c89c9d9b17d6"],
        "evidence": [
            ("FR-1", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "An unbound run's claim of another agent's task is refused 403 naming the assignee "
             "and the operator's remedy; task, assignee and binding unchanged (failed on HEAD)."),
            ("FR-1", "task-c89c9d9b17d6", "manual_observation",
             "scripts/drive/d1007_claim_boundary_drive.py",
             "Driven on :8010 with real Haiku beta: 0/3 before (beta took alpha's task to "
             "completed), 3/3 after."),
            ("FR-2", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "A run's claim of an unassigned task makes its agent the assignee in the same "
             "transaction (failed on HEAD); also driven 3/3."),
            ("FR-3", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "Own-task claim, bound run and operator move behave as before (3 control tests), and "
             "test_run_task_binding.py stays green."),
        ],
    },
    "f425": {
        "document": "spec/changes/a-read-only-agent-holds-no-task-work/spec.html",
        "tasks": ["task-e12f21e11f3b", "task-e1bf77c9375a", "task-707ba7cd531f"],
        "evidence": [
            ("FR-1", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "A read-only agent's task-work turn is refused 409 before any workspace, naming the "
             "agent, task and remedy; no run; a review turn and a writing agent's turn are unchanged."),
            ("FR-1", "task-707ba7cd531f", "manual_observation",
             "scripts/drive/d1007_read_only_drive.py",
             "Driven on :8010 with real Haiku: 1/6 before (the turn wrote NOTES.md into the project "
             "checkout), 6/6 after."),
            ("FR-2", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "Create and PATCH naming a read-only assignee answer 422 (the under_review handover "
             "stays allowed); its run's claim answers 403; nothing changes."),
            ("FR-3", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "A flow gives the pending task to the writing agent, both when the read-only agent is "
             "free in the pool and when it is the job's own agent."),
        ],
    },
    "f462": {
        "document": "spec/changes/a-codex-app-server-spec-turn-keeps-no-write-tools/spec.html",
        "tasks": ["task-a329084987ed", "task-c5e910f735b3", "task-b263ff986238"],
        "evidence": [
            ("FR-1", "task-c5e910f735b3", "test_result", CODEX_SPEC_TESTS,
             "The dispatch hands restrict_spec_writes to run_turn (it reached it as False before); "
             "a spec turn's thread starts read-only, on-request or untrusted, in every posture "
             "(20 of 20 failed before the build; Codex is not drivable here)."),
            ("FR-2", "task-c5e910f735b3", "test_result", CODEX_SPEC_TESTS,
             "A file change and a command the posture would allow are declined on a spec turn; "
             "under Ask me a file change shows no card and a command still asks; Full access "
             "grants no permissions."),
            ("FR-3", "task-c5e910f735b3", "test_result", CODEX_SPEC_TESTS,
             "A calls-root .json file change and one aw-tool invocation are accepted in every "
             "posture; a change mixing a calls file with a workspace file is declined."),
            ("FR-4", "task-b263ff986238", "test_result", CODEX_SPEC_TESTS,
             "With no document open Full access starts danger-full-access/never and Workspace only "
             "accepts the command (the controls); MCP elicitation is accepted on a spec turn."),
        ],
    },
    "f531": {
        "document": "spec/changes/a-hub-claude-run-gets-only-the-hubs-tool-server/spec.html",
        "tasks": ["task-c657e94471f5", "task-91d8626ddfe7"],
        "evidence": [
            ("FR-1", "task-91d8626ddfe7", "test_result", STRICT_MCP_TESTS,
             "Every Claude agent argv (Hub server, none, yolo, resume, spec turn) carries "
             "--strict-mcp-config exactly once, the Hub's --mcp-config unchanged, Codex untouched "
             "(6 red before the build); the 52 Claude argv goldens differ by that flag alone."),
            ("FR-1", "task-c657e94471f5", "manual_observation",
             "scripts/drive/d1008_f531_no_connectors_drive.py",
             "Driven on :8010 with a real Haiku turn: 1/3 before (no flag; the agent named eight "
             "mcp__claude_ai_Claude_Docs__* tools), 3/3 after (flag in the spawned argv; 'NONE'); "
             "the Hub's own server still connected."),
            ("FR-2", "task-91d8626ddfe7", "test_result", STRICT_MCP_TESTS,
             "A runner's own --mcp-config flag stays in the argv beside the Hub's; a runner that "
             "already passes --strict-mcp-config is not given it twice. Live read-out of the built "
             "argv with alwaysLoad: system/init lists exactly agentweave and the runner's server."),
        ],
    },
    "f508": {
        "document": "spec/changes/a-document-names-its-default-reviewer/spec.html",
        "tasks": [
            "task-ca5e972926f9",
            "task-3a09c1140b1b",
            "task-cbb027b3387f",
            "task-80ffa8e8b03d",
            "task-f0925c46d9dd",
        ],
        "evidence": [
            ("FR-1", "task-3a09c1140b1b", "test_result", DEFAULT_REVIEWER_TESTS,
             "A task naming no reviewer is staffed from delivery.reviewer (rung declared) over a "
             "free agent sorting first; an unknown or archived default is unresolved with a reason "
             "naming the document's default, never substituted (red before the build)."),
            ("FR-1", "task-f0925c46d9dd", "manual_observation",
             "scripts/drive/d1008_default_reviewer_drive.py",
             "Driven on :8010 with real Haiku agents: 0/3 before (the review went to aaa-stub), "
             "3/3 after (queued to critic, task under_review held by critic)."),
            ("FR-2", "task-3a09c1140b1b", "test_result", DEFAULT_REVIEWER_TESTS,
             "A task's own reviewer wins over delivery.reviewer; with neither, rung 2 is unchanged."),
            ("FR-3", "task-80ffa8e8b03d", "manual_observation",
             "scripts/drive/d1008_default_reviewer_bar.py",
             "delivery_status carries reviewer and reviewer_state; in Chromium on the served bundle "
             "the bar reads 'Reviewed by @critic.' and, for an unknown name, amber with 'its "
             "reviews will come to you' (4/4); vitest 'who reviews' red before."),
            ("FR-4", "task-cbb027b3387f", "test_result", DEFAULT_REVIEWER_TESTS,
             "The exploring duty and submit_spec_document name delivery.reviewer; "
             "reviewer_undeclared is quiet when it is set and names it otherwise."),
        ],
    },
}


def close(name: str) -> None:
    change = CHANGES[name]
    for identifier, task_id, kind, locator, summary in change["evidence"]:
        code, res = api("POST", f"/projects/{P}/project/spec/evidence", {
            "identifier": identifier, "kind": kind, "locator": locator, "summary": summary,
            "task_id": task_id, "document": change["document"],
        })
        footprint = (res.get("footprint") or {}) if isinstance(res, dict) else {}
        print(name, "evidence", identifier, task_id, code,
              footprint.get("commit_sha", "")[:12] if code == 201 else json.dumps(res)[:300])
    for task_id in change["tasks"]:
        code, task = api("GET", f"/projects/{P}/tasks/{task_id}")
        if task["status"] == "approved":
            print(name, task_id, "already approved")
            continue
        for step in ("in_progress", "completed"):
            if task["status"] == step:
                continue
            code, task = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": step})
            if code != 200:
                raise SystemExit(f"{name} {task_id} -> {step}: {code} {json.dumps(task)[:400]}")
        code, task = api("POST", f"/projects/{P}/tasks/{task_id}/land")
        print(name, task_id, "land", code, task.get("status") if code == 200 else json.dumps(task)[:400])


#: The last step of a close-out, run after the change is reconciled: the document id, and one
#: (capability, requirement key) the change was reconciled under. A change is archived only when
#: every task of its document is approved and that key is in the capability, because `archived` has
#: no way back and a shipped change whose requirements live nowhere else must not become history.
#: F509's slices and F510 shipped before `spec/` owned the corpus and are archived from here too.
ARCHIVE = {
    "f440": ("spec/changes/a-decided-task-withdraws-its-waiting-reviews/spec.html", "spdoc-3b1585810681",
             "run-task-binding", "a-decided-task-withdraws-its-waiting-reviews"),
    "f450": ("spec/changes/a-run-claims-only-its-agents-or-nobodys-work/spec.html", "spdoc-02d1259eea94",
             "run-task-binding", "a-run-claims-only-its-agents-or-nobodys-work"),
    "f425": ("spec/changes/a-read-only-agent-holds-no-task-work/spec.html", "spdoc-e7299e2e30ce",
             "run-task-binding", "a-read-only-agent-holds-no-task-work"),
    "f462": ("spec/changes/a-codex-app-server-spec-turn-keeps-no-write-tools/spec.html", "spdoc-4e84aebf7712",
             "spec-document-authority", "a-codex-app-server-spec-turn-keeps-no-write-tools"),
    "f508": ("spec/changes/a-document-names-its-default-reviewer/spec.html", "spdoc-54a29332c4a2",
             "agent-flows", "a-document-names-its-default-reviewer"),
    "f531": ("spec/changes/a-hub-claude-run-gets-only-the-hubs-tool-server/spec.html", "spdoc-721c3e827237",
             "agent-run-sandboxing", "a-hub-claude-run-gets-only-the-hubs-tool-server"),
    "f510": ("spec/changes/a-review-turn-reviews-the-branch-tip-where-evidence-does-not-govern-the-merge/"
             "spec.html", "spdoc-eeaf6a633f2d",
             "agent-conversation-workspace", "where-evidence-does-not-govern-the-merge-a-review-turn-revie"),
    "f509-1": ("spec/changes/same-file-tasks-build-in-order/spec.html", "spdoc-2b89ed059860",
               "spec-document-authority", "unordered-tasks-sharing-a-file-are-warned"),
    "f509-1b": ("spec/changes/same-file-tasks-build-in-order-the-shim-planner-is-told/spec.html",
                "spdoc-4503a507472f", "agent-tool-surface", "aw-tool-help-prints-a-tools-whole-description"),
    "f509-1c": ("spec/changes/submission-warns-when-a-multi-task-planner-declares-no-files/spec.html",
                "spdoc-1612097b4bc3", "spec-document-authority", "a-multi-task-document-without-files-is-warned"),
}


def archive(name: str) -> None:
    path, doc_id, capability, key = ARCHIVE[name]
    _, tasks = api("GET", f"/projects/{P}/tasks")
    rows = tasks if isinstance(tasks, list) else tasks.get("tasks", tasks.get("items", []))
    open_tasks = [(t["id"], t["status"]) for t in rows
                  if t.get("spec_document_id") == doc_id and t["status"] != "approved"]
    if open_tasks or not any(t.get("spec_document_id") == doc_id for t in rows):
        raise SystemExit(f"{name}: not archived, tasks not all approved: {open_tasks or 'none found'}")
    corpus = (REPO / "spec/capabilities" / capability / "spec.html").read_text(encoding="utf-8")
    if f'"key": "{key}"' not in corpus:
        raise SystemExit(f"{name}: not archived, {capability} has no requirement {key}: reconcile first")
    code, res = api("POST", f"/projects/{P}/project/documents/phase?path={path}&to=archived",
                    {"reason": f"shipped; reconciled into {capability} ({key})"})
    print(name, "archive", code, res.get("phase") if code == 200 else json.dumps(res)[:400])


if sys.argv[1:2] == ["--archive"]:
    for arg in sys.argv[2:]:
        archive(arg)
else:
    for arg in sys.argv[1:]:
        close(arg)
