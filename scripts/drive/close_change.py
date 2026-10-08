"""Close an app-authored change's Hub records once its build is committed: record operator
evidence per requirement, then walk each change task pending -> in_progress -> completed -> land.

Commit first: the evidence footprint names HEAD, and integration skips on a dirty tree. A commit
already on the main branch lands as `already integrated`; nothing is merged.

  AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 scripts/drive/close_change.py f440 f450

Then fold the change into the capability it changes, which archives it, through the Hub's fold
route (`a-finished-change-is-folded-into-its-capability`; the app's "Fold into capability" does the
same):  close_change.py --fold fold spec/capabilities/spec-document-authority/spec.html
The Hub refuses the fold while a task is open and on a key collision; nothing is written then.
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
FOLD_TESTS = "hub/tests/test_a_finished_change_is_folded_into_its_capability.py"

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
    "fold": {
        "document": "spec/changes/a-finished-change-is-folded-into-its-capability/spec.html",
        "tasks": ["task-e7c8a583c45c", "task-8a9f0b76ae27", "task-880b8e79d65a"],
        "evidence": [
            ("FR-1", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "The draft appends the change's requirements and criteria under <slug>-<key> (<= 64, "
             "valid keys), reports a key the capability holds as a collision and leaves its text "
             "and the file untouched (red before the build)."),
            ("FR-2", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "A fold writes edited and replacing requirements through the merge (one row, one "
             "merged event) and archives; folded twice across two capabilities it archives on the "
             "second; seven refusals each write nothing (red before the build)."),
            ("FR-3", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "Archiving an approved change with an open task is refused naming it; unfolded it is "
             "refused until no_capability_change comes with a non-blank reason; folded it archives."),
            ("FR-4", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "PUT .../content on a capability is 409 capability_written_through_merge naming the "
             "merge route; a merge naming no change writes it and records an edit event."),
            ("FR-5", "task-880b8e79d65a", "manual_observation",
             "scripts/drive/d1008_fold_change_drive.py",
             "In Chromium on :8010's served bundle: 0/4 before the build (no fold action), 6/6 "
             "after: the bar reads shipped-but-not-in-a-capability, the dialog drafts "
             "widgets-glow-glow, confirm leaves the key in the capability file, one merge row, and "
             "the change archived. vitest specFold 8/8."),
            ("FR-5", "task-e7c8a583c45c", "manual_observation",
             "scripts/drive/d1008_fold_change_drive.py",
             "The acceptance drive, written and run before the build: 0/4 on today's Hub."),
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


def fold(name: str, capability: str) -> None:
    """Fold the change into `capability` through the Hub, archiving it (the close-out's last step)."""
    path = CHANGES[name]["document"]
    code, res = api("POST", f"/projects/{P}/project/documents/{path}/fold", {"into": capability})
    print(name, "fold", code, res.get("phase") if code == 200 else json.dumps(res)[:400])


if sys.argv[1:2] == ["--fold"]:
    fold(sys.argv[2], sys.argv[3])
else:
    for arg in sys.argv[1:]:
        close(arg)
