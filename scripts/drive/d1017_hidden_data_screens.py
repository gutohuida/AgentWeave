"""Acceptance drive for slice remaining-hidden-data: what the Hub records is reachable where the
operator would look for it, in a real browser.

Part A, on the Terra replica (read-only copy of :8000), judges what it holds: a conversation's
checkpoint notes, and the task story's transitions and runs opening their conversation.
Part B, on the scratch Hub `e2e.py hub-up` started, seeds what the replica has none of (check runs
and resolved spec proposals) into that scratch Hub's own database, then judges the drawer's checks
history and the proposals panel's resolved list.

    AW_DEV_HUB=http://127.0.0.1:8130 npx vite --host 127.0.0.1 --port 5179   (replica)
    AW_DEV_HUB=http://127.0.0.1:<scratch> npx vite --host 127.0.0.1 --port 5180
    py -3.11 scripts/drive/d1017_hidden_data_screens.py <scratch-project-id>
"""

import importlib.util
import json
import pathlib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from uiharness import Judge, replica

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

TERRA = "proj-cd006955cbe2"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def part_a():
    _hub, key, db = replica()
    con = sqlite3.connect(pathlib.Path(db).as_uri() + "?mode=ro", uri=True)
    note_id, conversation, agent = con.execute(
        "select n.id, n.conversation_id, n.agent from checkpoint_notes n order by n.created_at limit 1"
    ).fetchone()
    task_id, transition_id, run_conversation = con.execute(
        "select t.task_id, t.id, r.conversation_id from task_transitions t join runs r on r.id = t.run_id "
        "where t.project_id = ? and r.conversation_id is not null order by t.created_at limit 1",
        (TERRA,),
    ).fetchone()
    with Judge("d1017-hidden-data-replica", hub="http://127.0.0.1:5179", key=key) as j:
        page = j.page(TERRA, mode="dark", query=f"agent={agent}&conversation={conversation}")
        page.get_by_test_id("conversation-checkpoints-toggle").wait_for(timeout=30000)
        page.get_by_test_id("conversation-checkpoints-toggle").click()
        page.get_by_test_id("checkpoints-panel").wait_for(timeout=15000)
        page.wait_for_timeout(800)
        check("a conversation's checkpoint notes are readable",
              page.get_by_test_id(f"checkpoint-note-{note_id}").count() == 1)
        j.shot(page, "checkpoints_panel_dark")
        page.context.close()

        story = j.page(TERRA, mode="light", query="tab=tasks")
        story.get_by_test_id(f"task-open-{task_id}").first.wait_for(timeout=30000)
        story.get_by_test_id(f"task-open-{task_id}").first.click()
        link = story.get_by_test_id(f"story-transition-run-{transition_id}")
        link.wait_for(timeout=15000)
        j.shot(story, "transition_link_light")
        link.click()
        story.wait_for_timeout(1500)
        check("a transition opens its run's conversation", f"conversation={run_conversation}" in story.url,
              story.url)
        story.context.close()
        check("no console or page errors (replica)", not j.errors, "; ".join(j.errors[:3]))


def part_b(project):
    con = sqlite3.connect(e2e.db())
    task_id, document_id, path = con.execute(
        "select t.id, d.id, d.path from tasks t join spec_documents d on d.id = t.spec_document_id "
        "where t.project_id = ? order by t.created_at desc limit 1",
        (project,),
    ).fetchone()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    runs = []
    for index, state in enumerate(["failed", "failed", "passed"]):
        run_id = f"tcr-drive-{index}"
        exit_code = 0 if state == "passed" else 1
        results = [
            {"name": "unit", "exit_code": exit_code, "duration_seconds": 12.5 + index,
             "timed_out": False, "output_tail": f"run {index}"},
            {"name": "lint", "exit_code": 0, "duration_seconds": 3.0, "timed_out": False, "output_tail": ""},
        ]
        started = now - timedelta(minutes=30 - index * 10)
        con.execute(
            "insert or replace into task_check_runs (id, project_id, task_id, main_sha, target_shas, "
            "merged_sha, state, results, error, started_at, ended_at) values (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, project, task_id, "a" * 40, json.dumps(["b" * 40]), "c" * 40, state,
             json.dumps(results), "", started.isoformat(" "), (started + timedelta(seconds=20)).isoformat(" ")),
        )
        runs.append(run_id)
    for pid, status, reason in [("sprop-drive-ok", "accepted", "matches the drive's wording"),
                                ("sprop-drive-no", "rejected", "this would narrow FR-1 too far")]:
        con.execute(
            "insert or replace into spec_edit_proposals (id, document_id, unit_kind, unit_key, change_kind, "
            "proposed_payload, previous_payload, status, proposer_actor_kind, proposer_actor_name, created_at, "
            "resolved_at, resolved_by_actor_name, resolution_reason) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, document_id, "requirement", "r1", "modify",
             json.dumps({"key": "r1", "statement": "note.txt MUST exist and be empty.", "modal": "MUST"}),
             None, status, "agent", "builder", now.isoformat(" "), now.isoformat(" "), "operator", reason),
        )
    con.commit()

    with Judge("d1017-hidden-data-scratch", hub="http://127.0.0.1:5180", key=e2e.key()) as j:
        page = j.page(project, mode="light", query="tab=tasks")
        page.get_by_test_id(f"task-open-{task_id}").first.wait_for(timeout=30000)
        page.get_by_test_id(f"task-open-{task_id}").first.click()
        page.get_by_test_id(f"task-view-details-{task_id}").click()
        toggle = page.get_by_test_id(f"task-checks-history-toggle-{task_id}")
        toggle.wait_for(timeout=15000)
        toggle.click()
        page.wait_for_timeout(600)
        earlier = [page.get_by_test_id(f"task-check-run-{run}") for run in runs[:2]]
        check("the checks row lists the earlier runs", all(e.count() == 1 for e in earlier))
        exit_cell = page.get_by_test_id(f"task-check-result-{runs[0]}-unit")
        check("each earlier run shows a check's exit code and duration",
              exit_cell.count() == 1 and "exit 1" in exit_cell.inner_text() and "12.5" in exit_cell.inner_text(),
              exit_cell.inner_text() if exit_cell.count() else "missing")
        j.shot(page, "checks_history_light")
        page.context.close()

        spec = j.page(project, mode="dark", query=f"tab=spec&document={path}")
        spec.get_by_test_id("spec-proposals-resolved-toggle").wait_for(timeout=30000)
        spec.get_by_test_id("spec-proposals-resolved-toggle").click()
        spec.wait_for_timeout(600)
        rejected = spec.get_by_test_id("spec-proposal-resolved-sprop-drive-no")
        check("resolved proposals are listed with their reason",
              rejected.count() == 1 and "narrow FR-1 too far" in rejected.inner_text(),
              rejected.inner_text() if rejected.count() else "missing")
        j.shot(spec, "resolved_proposals_dark")
        spec.context.close()
        check("no console or page errors (scratch)", not j.errors, "; ".join(j.errors[:3]))


if __name__ == "__main__":
    try:
        part_a()
        part_b(sys.argv[1])
    except Exception as exc:  # a broken drive is a failure, never a pass
        failures.append(f"drive raised {exc!r}")
        print(f"[FAIL] drive raised {exc!r}"[:300])
    finally:
        print("FAILED: " + ", ".join(failures) if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
