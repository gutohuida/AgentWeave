"""2026-10-22 evidence sweep (after s1020_v_setup.py), phases:

  nowork   F852 live: master's HEAD is an unrelated FR-1 commit; builder, on t-total in a fresh task
           checkout, edits nothing and records FR-3 with no commit. Mid-run, the operator's decision
           is refused `recording_run_live`. After: the diff answers no files and a reason.
  work     the fix's other side: builder, on t-count, writes count() and leaves it uncommitted, then
           records FR-2 with no commit. The run-end snapshot commits it and the re-stamp re-points
           the footprint: the diff must show todo/items.py, not "no work".
  merge    t-count walked to approved and merged (--no-ff); the FR-2 piece's diff still shows its work.

  AW_E2E_STATE=... py -3.11 scripts/drive/s1022_ev_drive.py <phase>
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1020_v_lib import e2e  # noqa: E402
from s1020_v_lib import commit_file, evidence, git, memo, request, say, show, summary  # noqa: E402

M = memo()
P, DIR, DOC, T = M["project"], M["dir"], M["doc"], M["tasks"]
BASE = f"/projects/{P}/project"
PHASE = sys.argv[1]


def footprint(ev_id):
    row = e2e.ro().execute(
        "select commit_sha, branch, commit_named, reachable_from_main, watched_from"
        " from evidence_footprints where evidence_id=?", (ev_id,)).fetchone()
    return dict(row) if row else None


def diff(ev_id):
    st, d = request("GET", f"{BASE}/spec/evidence/{ev_id}/diff")
    files = [f.get("path") for f in d.get("files", [])] if isinstance(d, dict) else None
    return st, d, files


def run_turn(task, msg, ident, try_live_decide=False):
    before = {e["id"] for e in evidence(P)}
    run_id = e2e.cmd_turn(P, "builder", msg, task=task, fresh=True, perm="workspace")
    live_tried = None
    deadline = time.time() + 600
    while time.time() < deadline:
        st = e2e.ro().execute("select status from runs where id=?", (run_id,)).fetchone()["status"]
        new = [e for e in evidence(P) if e["id"] not in before and (e.get("requirement") or {}).get("identifier") == ident]
        if try_live_decide and new and live_tried is None and st == "running":
            live_tried = request("POST", f"{BASE}/spec/evidence/{new[0]['id']}/decision",
                                 {"decision": "accepted"})
            show("operator decides mid-run", *live_tried)
        if st not in ("running", "queued", "starting", "pending"):
            break
        time.sleep(4)
    print("run", run_id, "->", st)
    e2e.dump_turn(run_id, tools=False)
    new = [e for e in evidence(P) if e["id"] not in before and (e.get("requirement") or {}).get("identifier") == ident]
    return run_id, new, live_tried


if PHASE == "nowork":
    head = commit_file(DIR, "todo/items.py",
                       "ITEMS = [('milk', 3), ('bread', 1), ('eggs', 2)]\n\n\ndef names():\n"
                       "    return sorted(n for n, _ in ITEMS)\n", "sort names (made for FR-1)")
    print("master HEAD (FR-1's work, unrelated to FR-3):", head[:12])
    msg = ("You are on task t-total. Do NOT edit, create or commit any file. Run "
           "`py -3.11 -c \"from todo.total import total; print(total())\"` once, then call the AgentWeave "
           f"tool record_evidence with identifier FR-3, document {DOC}, summary 'total() printed 6', "
           "covers full, and NO commit and NO locator. Then wait by running "
           "`py -3.11 -c \"import time; time.sleep(25)\"` once, and reply DONE.")
    run_id, new, live = run_turn(T["t-total"], msg, "FR-3", try_live_decide=True)
    if live is None:
        say("operator decision refused mid-run (recording_run_live)", False, "no window caught: piece "
            "not seen while the run was running")
    else:
        st, body = live
        say("operator decision refused mid-run (recording_run_live)", st == 409 and "recording_run_live" in str(body),
            f"{st} {str(body)[:300]}")
    for e in new:
        fp = footprint(e["id"])
        print("  footprint:", fp)
        st, d, files = diff(e["id"])
        show(f"diff {e['id']}", st, d)
        say(f"F852: unnamed piece at main's tip ({e['id']}) answers no files + a reason",
            st == 200 and files == [] and bool(d.get("reason")),
            f"files={files} reason={d.get('reason') if isinstance(d, dict) else d}")
    say("a piece was recorded", bool(new), str([e.get("id") for e in new]))
    memo(nowork_head=head, nowork_run=run_id, nowork_pieces=[e["id"] for e in new])

elif PHASE == "work":
    msg = ("You are on task t-count. Edit todo/items.py to add this function at the end:\n\n"
           "def count():\n    return len(ITEMS)\n\nDo NOT run git and do NOT commit. Run "
           "`py -3.11 -c \"from todo.items import count; print(count())\"` once, then call the AgentWeave "
           f"tool record_evidence with identifier FR-2, document {DOC}, summary 'count() printed 3', "
           "covers full, and NO commit and NO locator. Then wait by running "
           "`py -3.11 -c \"import time; time.sleep(25)\"` once, and reply DONE.")
    run_id, new, live = run_turn(T["t-count"], msg, "FR-2", try_live_decide=True)
    st, body = live or (None, "no window caught")
    say("operator decision refused mid-run (recording_run_live)", st == 409 and "recording_run_live" in str(body),
        f"{st} {str(body)[:400]}")
    for e in new:
        fp = footprint(e["id"])
        print("  footprint:", fp)
        st, d, files = diff(e["id"])
        show(f"diff {e['id']}", st, d)
        say(f"unnamed piece with real work ({e['id']}) still diffs its work after the re-stamp",
            st == 200 and files == ["todo/items.py"] and "count" in str(d), f"files={files} reason={d.get('reason')}")
    say("a piece was recorded", bool(new), str([e.get("id") for e in new]))
    memo(work_run=run_id, work_pieces=[e["id"] for e in new])

elif PHASE == "merge":
    ev_id = M["work_pieces"][0]
    st, out = request("POST", f"{BASE}/spec/evidence/{ev_id}/decision", {"decision": "accepted"})
    show("accept FR-2 piece (run ended)", st, out)
    st, task = request("GET", f"/projects/{P}/tasks/{T['t-count']}")
    print("t-count:", task.get("status"))
    for to in ("completed", "under_review", "approved"):
        st, out = request("PATCH", f"/projects/{P}/tasks/{T['t-count']}", {"status": to})
        show(f"t-count -> {to}", st, out if st >= 300 else {"status": out.get("status")})
    for _ in range(20):
        st, task = request("GET", f"/projects/{P}/tasks/{T['t-count']}")
        integ = task.get("integration") or {}
        if integ.get("status") in ("merged", "landed", "failed", "conflict") or "count" in (DIR and git(DIR, "show", "master:todo/items.py")):
            break
        time.sleep(3)
    print("integration:", task.get("integration"))
    print("master log:", git(DIR, "log", "--oneline", "--first-parent", "-4", "master"))
    print("  footprint:", footprint(ev_id))
    st, d, files = diff(ev_id)
    show(f"diff {ev_id} after merge", st, d)
    say("merged unnamed piece still diffs its work", st == 200 and files == ["todo/items.py"] and not d.get("reason"),
        f"files={files} reason={d.get('reason')}")
    nw = M.get("nowork_pieces") or []
    if nw:
        st, d, files = diff(nw[0])
        say("no-work piece still answers no files after an unrelated merge", files == [] and bool(d.get("reason")),
            f"files={files} reason={d.get('reason')}")

summary()
