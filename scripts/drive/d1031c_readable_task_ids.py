"""Drive for spec `tickets-have-readable-ids` (FR-10), 2026-10-31: a real Haiku turn, a real browser.

A flow build of one task on a spec titled "Note file". Written first: on master a task has only its
`task-<hex>` id, so every readable-id step below fails and the drive exits 1.

  1  the task carries a readable id (ACRONYM-N) on the task route
  2  a real Haiku turn on the task messages agent C about it, and the message names it by that id
  3  in a browser, with a second task on the board, the board is searched for the readable id in
     lower case and then for the hex id (each finds this task and hides the other), a query that
     matches nothing empties the board, the card shows the readable id, and the task's own drawer
     shows both ids
  4  every task tool is called with the lower-case readable id (get_task, task_history, update_task,
     hand_out_task, send_message task_id, create_task depends_on) and each acts on the same task.
     NOT driven: mend_task_branch and mend_reset_task. They answer only the Hub's mender agent
     (hub/hub/api/v1/mender.py get_mender_actor, 403 for anyone else, before the task is looked
     up), and a drive cannot make an agent the mender. Their id resolution is covered by the Hub
     tests the spec's Hub task adds beside hub/tests/test_the_mender_hands_finished_work_to_review.py
     and test_a_live_run_is_never_reset.py, which call both routes with the readable id.
  5  the spec is renamed and the task still reads the same readable id

The board search box is the one the spec's UI task adds: a search field labelled "Search tasks".

Starts the trial Hub on :8010 from this checkout unless one is already there.

    py -3.11 scripts/drive/d1031c_readable_task_ids.py
"""

import re
import sys
import urllib.parse

import d1029_build_plan_in_spec as d
from playwright.sync_api import sync_playwright

d.TMP = d.TMP.parent.parent / "drive1031c-readable-ids" / d.STAMP
DOC = "spec/changes/note-file/spec.json"
B, C = "B", "C"
READABLE = re.compile(r"\b([A-Z][A-Z0-9]{1,4}-\d+)\b")


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Note file",
        "summary": "One file.", "problem": "There is no note.",
        "scope": {"in_scope": ["NOTE.md"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "note", "modal": "MUST", "statement": "NOTE.md MUST exist."}],
        "acceptance_criteria": [{
            "key": "exists", "requirement": "note", "given": "the repository", "when": "listed",
            "then": "NOTE.md is there", "how_to_check": "ls", "checked_by": "agent"}],
        "tasks": [{"key": "t1", "title": "Write the note", "requirements": ["note"], "builder": B,
                   "description": "Do these in order. 1) Look at the id the turn prompt names this "
                                  "task by. 2) Send ONE message to agent C with the send_message "
                                  "tool: subject `status`, task_id set to this task, and content "
                                  "that says which task you are on, naming it by exactly the id "
                                  "the prompt gave. 3) Create NOTE.md holding the single line "
                                  "`note`. 4) Move this task to completed. Change nothing else.",
                   "files": ["NOTE.md"]}],
        "delivery": {"mode": "flow", "agent": B, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *", "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def readable_of(task_json):
    value = (task_json or {}).get("readable_id")
    return value if isinstance(value, str) and READABLE.fullmatch(value) else None


def board_check(pid, readable, hexid, other):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.add_init_script(
            f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, "
            f"hubUrl: {d.HUB!r}}}));"
            f"localStorage.setItem('agentweave-selected-project', {pid!r});"
        )
        page.goto(f"{d.HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        card = page.get_by_test_id(f"task-open-{hexid}")
        try:
            card.wait_for(timeout=30000)
        except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
            d.check("the board shows the task", False, str(exc)[:200])
            browser.close()
            return
        text = card.inner_text()
        d.check("the board card names the task by its readable id",
                bool(readable) and readable in text, text[:200])
        card_of = lambda tid: page.get_by_test_id(f"task-open-{tid}")  # noqa: E731
        box = page.get_by_role("searchbox", name="Search tasks")
        for label, query in (("readable id, lower case", (readable or "no-readable-id").lower()),
                             ("stored id", hexid)):
            try:
                box.fill(query, timeout=5000)
                card_of(hexid).wait_for(timeout=5000)
                page.wait_for_timeout(500)
                found = card_of(hexid).count() == 1 and card_of(other).count() == 0
                detail = f"this task {card_of(hexid).count()}, the other {card_of(other).count()}"
            except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
                found, detail = False, str(exc)[:200]
            d.check(f"the board search finds only the task by its {label}", found, detail)
        try:
            box.fill("zzz-matches-nothing", timeout=5000)
            page.wait_for_timeout(500)
            gone = card_of(hexid).count() == 0 and card_of(other).count() == 0
            detail = f"this task {card_of(hexid).count()}, the other {card_of(other).count()}"
        except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
            gone, detail = False, str(exc)[:200]
        d.check("the board search hides every card for a query that matches nothing", gone, detail)
        try:
            box.fill("", timeout=5000)
            card_of(hexid).click(timeout=10000)
            details = page.get_by_role("button", name="Details")
            if details.count():
                details.first.click()
            drawer = page.get_by_test_id(f"task-drawer-{hexid}")
            drawer.wait_for(timeout=10000)
            text = drawer.inner_text()
            shown = bool(readable) and readable in text and hexid in text
            detail = text[:200]
        except Exception as exc:  # noqa: BLE001 -- reported as the check's detail
            shown, detail = False, str(exc)[:200]
        d.check("the task's drawer shows both ids", shown, detail)
        page.screenshot(path=str(d.TMP / "board.png"))
        d.check("no page errors", not errors, str(errors[:3]))
        browser.close()


def main():
    hub = d.start_hub()
    root = d.TMP / "proj"
    try:
        root.mkdir(parents=True)
        d.git(root, "init", "-q", "-b", "main")
        (root / "README.md").write_text("Scratch.\n", encoding="utf-8")
        d.git(root, "add", ".")
        d.git(root, "commit", "-q", "-m", "seed")
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"rid-{d.STAMP}"})
        d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        base = f"/projects/{pid}"
        d.api("PATCH", base, {"main_branch": "main"})
        code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
        d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for name in (B, C):
            code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
            d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

        quoted = urllib.parse.quote(DOC)
        code, out = d.api("POST", f"{base}/project/documents",
                          {"title": "Note file", "kind": "change-spec", "path": DOC})
        d.check("setup: document created", code == 201, f"{code} {out}", fatal=True)
        code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
        d.check("setup: document saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                          {"reason": "drive", "approve_anyway": True,
                           "content_version": read.get("content_version")})
        d.check("setup: document approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                          {"driver": "flow", "level": "fast", "builders": [B, C], "landing": "main"})
        d.check("setup: built", code == 200, f"{code} {str(out)[:600]}", fatal=True)
        ((task, loop),) = d.ro("select t.id, t.loop_id from tasks t join spec_documents s "
                               "on t.spec_document_id=s.id where s.project_id=? and s.path=?", (pid, DOC))
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0]

        # 1. the id exists
        _, got = d.api("GET", f"{base}/tasks/{task}")
        readable = readable_of(got)
        d.check("1 the task route carries a readable id (ACRONYM-N)", bool(readable),
                f"readable_id={(got or {}).get('readable_id')!r} on {task}")

        # 2. a real turn names the task by it in a message
        d.fire(base, job)
        d.wait_idle(pid, 6 * 60)
        sent = d.ro("select content, subject from messages where project_id=? and sender=? "
                    "and recipient=? order by timestamp", (pid, B, C))
        named = [m for m in sent if readable and readable in (m[0] or "") + " " + (m[1] or "")]
        d.check("2 a real turn messages C about its task by the readable id", bool(named),
                f"{len(sent)} message(s) from B to C: {[s[0][:120] for s in sent]}")

        # 3. the board, in a browser, with a second task the searches must hide
        code, chore = d.as_agent(pid, B, "POST", "/tasks", {"title": "Unrelated chore"})
        d.check("3 setup: a second task on the board", code in (200, 201) and "id" in (chore or {}),
                f"{code} {str(chore)[:200]}", fatal=True)
        board_check(pid, readable, task, chore["id"])

        # 4. every task tool takes the lower-case readable id
        ref = (readable or "no-readable-id").lower()
        code, out = d.api("GET", f"{base}/tasks/{ref}")
        d.check("4 operator route: GET by readable id acts on the task",
                code == 200 and out.get("id") == task, f"{code} {str(out)[:200]}")
        _, stored_history = d.as_agent(pid, B, "GET", f"/tasks/{task}/transitions")
        for label, method, path, body in (
            ("get_task", "GET", f"/tasks/{ref}", None),
            ("task_history", "GET", f"/tasks/{ref}/transitions", None),
            ("send_message", "POST", "/messages",
             {"recipient": C, "subject": "readable ref", "content": "by id", "task_id": ref}),
            ("update_task", "PATCH", f"/tasks/{ref}", {"notes": "drive: noted by readable id"}),
            ("hand_out_task", "POST", f"/tasks/{ref}/hand-out", {"agent": C, "review": False}),
        ):
            code, out = d.as_agent(pid, B, method, path, body)
            d.check(f"4 tool {label} accepts the readable id", code in (200, 201, 202, 403) and code != 404,
                    f"{code} {str(out)[:200]}")
            if label == "task_history":
                rows = (out or {}).get("transitions") if isinstance(out, dict) else None
                same = rows == (stored_history or {}).get("transitions")
                named = all(r.get("task_id", task) == task for r in rows or [])
                d.check("4 tool task_history answers this task's own rows",
                        bool(rows) and same and named, f"{len(rows or [])} row(s), same as stored: {same}")
            if label == "send_message":
                kept = d.ro("select task_id from messages where project_id=? and subject=?",
                            (pid, "readable ref"))
                d.check("4 tool send_message stores this task's id", [k[0] for k in kept] == [task],
                        f"stored task_id {[k[0] for k in kept]} for {task}")
            if label in ("get_task", "update_task"):
                d.check(f"4 tool {label} acts on the same task", isinstance(out, dict) and out.get("id") == task,
                        f"{code} {str(out)[:200]}")
        code, out = d.as_agent(pid, B, "POST", "/tasks",
                               {"title": "Depends by readable id", "depends_on": [ref]})
        deps = (out or {}).get("depends_on") if isinstance(out, dict) else None
        d.check("4 tool create_task takes the readable id as a prerequisite",
                code in (200, 201) and bool(deps), f"{code} {str(out)[:200]}")

        # 5. retitle the spec: an approved document's path is frozen, so it is reopened and its
        # title changed, which is what renaming a built spec comes to
        _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
        code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=exploring",
                          {"reason": "drive: reopen to rename"})
        d.check("5 the spec reopens", code == 200, f"{code} {str(out)[:300]}")
        renamed = dict(payload(), title="Notes in a file for the operator")
        code, out = d.api("PUT", f"{base}/project/documents/{DOC}/content", {"document": renamed})
        d.check("5 the spec is retitled", code == 200, f"{code} {str(out)[:300]}")
        _, after = d.api("GET", f"{base}/tasks/{task}")
        d.check("5 the readable id is unchanged after the rename",
                bool(readable) and readable_of(after) == readable,
                f"before {readable!r} after {(after or {}).get('readable_id')!r}")
    except d.Stop:
        pass
    finally:
        d.stop_hub(hub)
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
