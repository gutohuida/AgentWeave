"""Acceptance drive for `a-task-s-checks-and-merges-use-its-own-work...` (spdoc-ed50fbb03efe), 2026-10-30.

Its `ac-live-replay`, plus what shipped beside it that no one had run live. Drives the trial Hub on
:8010 with Haiku agents in a scratch project, whose non-fast project check is the library's pytest.

  flow     D (drive) -> B (build, deliberately breaks a test) and C (depends on D only). D and B share
           a requirement. Built as the operator built the real one: default builder and checker, no
           per-task people, with an idle agent `Other` on the roster.
  own work B's check runs on B's own commit and fails before any review turn; C is never asked for
           B's commit; each Hub merge names the task that produced the commit.
  people   who actually got each task (DeveloperOpus built only 2 of 4 in the real flow).
  live run a reset of a task whose real run is executing is refused, naming the run.
  mid-build a task added while the build runs takes its default people.
  send-back a reviewer's send-back with no class is refused, with one it reads back from history.
  status   a browser with the spec page open, never reloaded, through Approved, Building, the
           scheduler's automatic stop, Done, a resume and the operator's stop.

The refusal probes use the seeded credential `d1029_build_plan_in_spec.as_agent` uses, because a run
credential exists only inside a spawned turn. Everything else goes through the routes.

    py -3.11 scripts/drive/d1030_own_work_replay.py
"""

import datetime
import json
import subprocess
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1030-own-work" / d.STAMP
DOC = "spec/changes/ledger-rounding/spec.json"
STATUS_DOC = "spec/changes/status-probe/spec.json"
BUILDER, CHECKER, OTHER = "Builder", "Checker", "Other"
DELIVERY = {
    "mode": "flow", "agent": BUILDER, "stop_when_queue_empties": True, "cron": "0 0 1 1 *",
    "reasons": {"mode": "The replay.", "agent": "The default builder."},
}
LIMIT = 35 * 60


def payload():
    def criterion(key, req):
        return {"key": key, "requirement": req, "given": "the repository", "when": "the suite runs",
                "then": "it passes", "how_to_check": "pytest", "checked_by": "agent"}

    tail = " Commit nothing by hand beyond what the turn requires; change no other file."
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Ledger rounding",
        "summary": "A small ledger.", "problem": "The ledger is untested.",
        "scope": {"in_scope": ["ledger.py", "report.py"], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": "ledger", "modal": "MUST", "statement": "The ledger MUST sum its entries."},
            {"key": "report", "modal": "MUST", "statement": "A report MUST print the balance."},
        ],
        "acceptance_criteria": [criterion("sums", "ledger"), criterion("prints", "report")],
        "tasks": [
            {"key": "drive", "title": "Drive test for the ledger",
             "description": "Add tests/test_drive.py asserting `ledger.balance([1, 2]) == 3`. Record "
                            "evidence for the requirement with record_evidence." + tail,
             "requirements": ["ledger"], "files": ["tests/test_drive.py"]},
            {"key": "build", "title": "Change the ledger",
             "description": "This is a scratch project testing a check system, and the broken result "
                            "is wanted. Change `balance` in ledger.py to return `sum(entries) + 1`. "
                            "Do not run or edit the tests. Record evidence for the requirement, then "
                            "complete the task." + tail,
             "requirements": ["ledger"], "files": ["ledger.py"], "depends_on": ["drive"]},
            {"key": "report", "title": "Add the report",
             "description": "Add report.py with `def report(entries): return f'balance: "
                            "{sum(entries)}'`. Record evidence for the requirement." + tail,
             "requirements": ["report"], "files": ["report.py"], "depends_on": ["drive"]},
        ],
        "delivery": DELIVERY,
    }


def seed(root):
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "tests").mkdir()
    (root / "ledger.py").write_text("def balance(entries):\n    return sum(entries)\n", encoding="utf-8")
    (root / "tests" / "test_ledger.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\nimport ledger\n\n\n"
        "def test_balance():\n    assert ledger.balance([2, 2]) == 4\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")


def approve(base, path, document):
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": document["title"], "kind": "change-spec", "path": path})
    d.check(f"setup: {path} created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content", {"document": document})
    d.check(f"setup: {path} saved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    quoted = urllib.parse.quote(path)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check(f"setup: {path} approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    return quoted


def transitions(task_id):
    return d.ro("select from_status, to_status, actor_kind, reason_class, reason, note, created_at "
                "from task_transitions where task_id=? order by sequence", (task_id,))


def status(task_id):
    return d.ro("select status from tasks where id=?", (task_id,))[0][0]


def worked_by(task_id):
    return d.handouts(task_id, review=False), d.handouts(task_id, review=True)


def tip(root, task_id):
    out = subprocess.run(["git", "log", f"agentweave/task/{task_id}", "--format=%H %s"], cwd=root,
                         capture_output=True, text=True, encoding="utf-8")
    return out.stdout.splitlines()


def drive_flow(state, root, base, pid):
    quoted = approve(base, DOC, payload())
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                      {"driver": "flow", "level": "reviewed", "builder": BUILDER, "checker": CHECKER,
                       "landing": "main"})
    d.check("setup: built as a flow, default Builder and Checker", code == 200,
            f"{code} {str(out)[:600]}", fatal=True)
    (doc_id,) = d.ro("select id from spec_documents where project_id=? and path=?", (pid, DOC))[0]
    tasks = {k: (t, l) for t, l, k in d.ro(
        "select id, loop_id, spec_task_key from tasks where spec_document_id=?", (doc_id,))}
    D, B, C = tasks["drive"][0], tasks["build"][0], tasks["report"][0]
    job = d.ro("select job_id from loops where id=?", (tasks["drive"][1],))[0][0]
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    state.update(build_id=build_id)
    print(f"D={D} B={B} C={C} job={job} build={build_id}", flush=True)

    reset_tried = added = None
    start = time.time()
    while time.time() - start < LIMIT:
        d.fire(base, job)
        time.sleep(15)
        live = d.ro("select id, agent, task_id from runs where project_id=? and status='running'", (pid,))
        states = {name: status(t) for name, t in (("D", D), ("B", B), ("C", C))}
        print(f"  {int(time.time() - start)}s {states} live={[(a, t) for _, a, t in live]}", flush=True)

        if reset_tried is None and any(t == D and states["D"] == "in_progress" for _, _, t in live):
            run = next(r for r, _, t in live if t == D)
            before = transitions(D)
            code, out = d.api("PATCH", f"{base}/tasks/{D}", {"status": "assigned"})
            text = json.dumps(out)
            still_live = any(r == run for r, in d.ro(
                "select id from runs where id=? and status='running'", (run,)))
            reset_tried = code
            d.check("FR-6 a reset of a task with a live run is refused, naming the run",
                    code == 409 and run in text, f"{code} {text[:400]} live_after={still_live}")
            d.check("FR-6 the task's history is unchanged by the refusal",
                    transitions(D) == before and status(D) == "in_progress", str(status(D)))

        if added is None and states["D"] in ("in_progress", "completed", "under_review"):
            code, out = d.api("POST", f"{base}/tasks", {
                "title": "Mid-build note",
                "description": "Add NOTES.md holding the single line `notes`. Change nothing else.",
                "spec_document": DOC, "requirement_ids": ["FR-2"]})
            added = out.get("id") if isinstance(out, dict) else "failed"
            d.check("FR-7 a task added mid-build is created", code in (200, 201), f"{code} {str(out)[:400]}")
            if code in (200, 201):
                _, read = d.api("GET", f"{base}/tasks/{added}")
                d.check("FR-7 it takes the build's default builder and checker, marked by default",
                        read.get("builder") == BUILDER and read.get("checker") == CHECKER
                        and read.get("builder_by_default") and read.get("checker_by_default"),
                        str({k: read.get(k) for k in ("builder", "checker", "builder_by_default",
                                                      "checker_by_default", "build_id", "assignee")}))
                state["added"] = added

        b_done = any(t[1] == "revision_needed" for t in transitions(B))
        open_rest = [t for t in (D, C, added) if t and t != "failed" and status(t) not in ("approved", "rejected")]
        if b_done and not open_rest:
            break
    else:
        print("  the time limit ended the flow loop", flush=True)

    # What really happened, from the rows.
    d.check("ac-live-replay D was approved", status(D) == "approved", status(D))
    runs = d.ro("select task_id, state, target_shas, error, started_at, ended_at, results "
                "from task_check_runs where task_id=? order by started_at", (B,))
    print("B's check runs:", json.dumps([r[:5] for r in runs], default=str), flush=True)
    b_log = tip(root, B)
    b_shas = {line.split()[0] for line in b_log}
    d_shas = {line.split()[0] for line in tip(root, D)}
    own_only = {s for s in b_shas if s not in d_shas}
    failed = [r for r in runs if r[1] == "failed"]
    first = json.loads(failed[0][2]) if failed else []
    d.check("ac-live-replay B's check failed on B's own commit, not D's",
            bool(failed) and any(s in own_only for s in first) and not any(s in d_shas for s in first),
            f"targets {first}; B's own {sorted(own_only)[:3]}")
    d.check("ac-live-replay the failure names the broken test",
            bool(failed) and "test_balance" in (failed[0][6] or ""), (failed[0][6] or "")[:300] if failed else "")
    history = transitions(B)
    print("B's history:", json.dumps(history, default=str), flush=True)
    backs = [h for h in history if h[1] == "revision_needed"]
    d.check("FR-9 the Hub's send-back records broken-check or flaky, with a sentence",
            bool(backs) and backs[0][3] in ("broken-check", "flaky") and bool(backs[0][4]),
            str(backs[:1]))
    review_entries = d.ro("select agent, arrived_at from inbound_queue_entries where review_task_id=? "
                          "order by sequence", (B,))
    first_fail = failed[0][5] if failed else None
    early = [r for r in review_entries if first_fail and str(r[1]) < str(first_fail)]
    d.check("ac-live-replay no review turn on B started before its check failed", not early and bool(failed),
            f"reviews {review_entries}; check ended {first_fail}")
    c_log = tip(root, C)
    d.check("ac-live-replay C's branch never took B's commit",
            not any(line.split()[0] in own_only for line in c_log), f"C log head {c_log[:4]}")
    merges = [line for line in c_log if "prerequisite" in line.lower()]
    d.check("FR-4 C's prerequisite merges name the producing task",
            all(D in m for m in merges), str(merges))
    c_hist = transitions(C)
    d.check("FR-3 C was not sent back for a merge", not any(h[3] == "merge-needed" for h in c_hist),
            json.dumps(c_hist, default=str)[:500])
    people = {name: worked_by(t) for name, t in (("D", D), ("B", B), ("C", C), ("added", added))
              if t and t != "failed"}
    print("who got each task:", people, flush=True)
    builders = {a for work, _ in people.values() for a in work}
    checkers = {a for _, review in people.values() for a in review}
    d.check("people: only the default builder was given work", builders <= {BUILDER}, str(people))
    d.check("people: only the default checker was given a review", checkers <= {CHECKER}, str(people))
    code, stopped = d.api("POST", f"{base}/project/builds/{build_id}/stop")
    print(f"stopped the flow's build: {code} {str(stopped)[:120]}", flush=True)
    state["build_id"] = None


def drive_send_back(base, pid):
    code, task = d.api("POST", f"{base}/tasks", {"title": "Send-back probe", "assignee": BUILDER})
    d.check("setup: a probe task", code in (200, 201), f"{code} {task}", fatal=True)
    tid = task["id"]
    for to in ("in_progress", "completed", "under_review"):
        code, out = d.api("PATCH", f"{base}/tasks/{tid}", {"status": to})
        if code != 200:
            d.check(f"setup: probe walks to {to}", False, f"{code} {str(out)[:300]}")
            return
    code, out = d.as_agent(pid, CHECKER, "PATCH", f"/tasks/{tid}",
                           {"status": "revision_needed", "notes": "wrong"})
    text = json.dumps(out)
    d.check("FR-9 a reviewer's send-back with no class is refused, naming the classes",
            code == 422 and all(c in text for c in ("defect", "regression", "broken-check",
                                                    "merge-needed", "evidence-only", "flaky")),
            f"{code} {text[:400]}")
    d.check("FR-9 the task did not move", status(tid) == "under_review", status(tid))
    code, out = d.as_agent(pid, CHECKER, "PATCH", f"/tasks/{tid}",
                           {"status": "revision_needed", "notes": "It adds the wrong line.",
                            "reason_class": "defect"})
    d.check("FR-8 a send-back with a class is accepted", code == 200, f"{code} {str(out)[:300]}")
    code, rows = d.api("GET", f"{base}/tasks/{tid}/transitions")
    rows = rows.get("transitions", rows) if isinstance(rows, dict) else rows
    last = rows[-1] if rows else {}
    d.check("FR-8 history reads back the class and the sentence",
            last.get("reason_class") == "defect" and "wrong line" in (last.get("reason") or ""),
            str({k: last.get(k) for k in ("to_status", "reason_class", "reason")}))
    d.api("DELETE", f"{base}/tasks/{tid}")


def pill(page):
    return (page.locator(".aw-sp-phase").first.text_content() or "").strip()


def wait_pill(page, want, secs=8):
    end = time.time() + secs
    while time.time() < end:
        if pill(page).lower() == want.lower():
            return True
        page.wait_for_timeout(250)
    return False


def history_has(pid, event, since):
    rows = d.ro("select count(*) from event_logs where project_id=? and event_type=? and timestamp>=?",
                (pid, event, since))
    return rows[0][0]


def drive_status(root, base, pid):
    document = {
        "schema_version": 1, "kind": "change-spec", "title": "Status probe", "summary": "Status.",
        "problem": "A status.", "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "requirements": [{"key": "x", "modal": "MUST", "statement": "The file MUST exist."}],
        "acceptance_criteria": [{"key": "ax", "requirement": "x", "given": "g", "when": "w", "then": "t",
                                 "how_to_check": "ls", "checked_by": "agent"}],
        "tasks": [{"key": "t", "title": "Probe", "description": "Nobody works this.", "requirements": ["x"],
                   "files": ["x.txt"]}], "delivery": DELIVERY,
    }
    quoted = approve(base, STATUS_DOC, document)
    seed_js = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
               " localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed_js)
        url = f"{d.HUB}/?project={pid}&tab=spec&document={quoted.replace('/', '%2F')}"
        page.goto(url, wait_until="domcontentloaded")
        page.locator(".aw-sp-phase").first.wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        d.check("status: Approved before any build", pill(page).lower() == "approved", pill(page))

        end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=6)
        code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}",
                          {"driver": "flow", "level": "reviewed", "builder": OTHER, "checker": CHECKER,
                           "landing": "main", "window_end": end.isoformat()})
        d.check("setup: a build with a window ending soon", code == 200, f"{code} {str(out)[:400]}", fatal=True)
        build = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
        d.check("status: Building appears live when built", wait_pill(page, "Building"), pill(page))
        (doc_id,) = d.ro("select id from spec_documents where project_id=? and path=?", (pid, STATUS_DOC))[0]
        (task, loop) = d.ro("select id, loop_id from tasks where spec_document_id=?", (doc_id,))[0]
        job = d.ro("select job_id from loops where id=?", (loop,))[0][0] if loop else None
        print(f"  status probe: build {build} task {task} loop {loop} job {job}", flush=True)
        time.sleep(8)
        since = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if job:
            d.fire(base, job)
        d.poll(lambda: d.ro("select state from builds where id=?", (build,))[0][0] == "stopped", 20)
        (state_now, reason) = d.ro("select state, stop_reason from builds where id=?", (build,))[0]
        d.check("status: the scheduler stops the build at its window's end", state_now == "stopped",
                f"{state_now} {reason}")
        page.wait_for_timeout(1500)
        d.check("status: an auto-stopped build with an open task still reads Building, live",
                pill(page).lower() == "building", pill(page))
        print("  build_stopped events:", history_has(pid, "build_stopped", since), flush=True)

        for to in ("in_progress", "completed", "under_review", "rejected"):
            code, out = d.api("PATCH", f"{base}/tasks/{task}", {"status": to})
            print(f"  probe -> {to}: {code} {str(out)[:160] if code != 200 else ''}", flush=True)
        (state_now,) = d.ro("select state from builds where id=?", (build,))[0]
        d.check("status: its last task rejected, it reads Done, live", wait_pill(page, "Done"),
                f"{pill(page)}; build {state_now}")
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
        code, out = d.api("PATCH", f"{base}/project/builds/{build}", {"window_end": later.isoformat()})
        (state_now,) = d.ro("select state from builds where id=?", (build,))[0]
        print(f"  resume: {code} {str(out)[:200]} build now {state_now}", flush=True)
        if state_now == "running":
            d.check("status: a resumed build reads Building, live", wait_pill(page, "Building"), pill(page))
            code, _ = d.api("POST", f"{base}/project/builds/{build}/stop")
            d.check("status: the operator's stop with nothing open reads Done, live",
                    wait_pill(page, "Done"), f"{code} {pill(page)}")
        else:
            d.check("status: the resume left a state the page agrees with",
                    wait_pill(page, "Done"), f"{state_now} {pill(page)}")
        page.reload(wait_until="domcontentloaded")
        page.locator(".aw-sp-phase").first.wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        print("  after a reload:", pill(page), flush=True)
        page.screenshot(path=str(d.TMP / "status_end.png"))
        browser.close()


def main():
    which = set(sys.argv[1:]) or {"flow", "send-back", "status"}
    d.TMP.mkdir(parents=True, exist_ok=True)
    state = {}
    root = d.TMP / "proj"
    try:
        seed(root)
        code, project = d.api("POST", "/projects/open", {"path": str(root), "name": f"ownwork-{d.STAMP}"})
        d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
        pid = project["id"]
        base = f"/projects/{pid}"
        state["base"] = base
        d.api("PATCH", base, {"main_branch": "main"})
        code, out = d.api("PATCH", base, {"checks": [
            {"name": "suite", "command": "py -3.11 -m pytest -q", "timeout_seconds": 120}]})
        if code != 200:
            code, out = d.api("PUT", f"{base}/settings", {"checks": [
                {"name": "suite", "command": "py -3.11 -m pytest -q", "timeout_seconds": 120}]})
        d.check("setup: the suite is the project's check", code == 200, f"{code} {str(out)[:300]}", fatal=True)
        code, haiku = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
        d.check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
        for name in (BUILDER, CHECKER, OTHER):
            code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
            d.check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)
        print(f"project {pid} at {root}", flush=True)
        if "send-back" in which:
            drive_send_back(base, pid)
        if "status" in which:
            drive_status(root, base, pid)
        if "flow" in which:
            drive_flow(state, root, base, pid)
    except d.Stop:
        pass
    finally:
        if state.get("build_id"):
            print("stopping the build:", d.api("POST", f"{state['base']}/project/builds/{state['build_id']}/stop")[0])
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on master 4dba06e, 2026-10-30. status 17/17 and send-back 4/4. flow: FR-6, FR-7, FR-9 and
# ac-live-replay held from the rows: B's check failed on B's own 3eb22ac, naming test_balance, 2m28s
# before any review of B, and C's branch held only D's commit. The script's own report stopped at the
# query this version fixes, so the last checks were read from the database; people failed (F1092).
