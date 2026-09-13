"""D-6 2026-09-13: F328 live -- the operator's DELETE and the Hub's give-up, racing for one entry.

F328 was measured at unit level only (`testbed/scratch/opusf319/test_zz_opusf319.py::test_o2`). This
asks it of a live Hub, through real routes, with a real review dispatch holding the write lock:

  1. A fresh git repository opened as a project; one approved document; N operator-completed tasks,
     each with evidence footprinted at a side commit that is then pruned (F319's leg B1), so every
     review of them is refused by `prepare_review_turn` AFTER the dispatch staged the reviewer.
  2. The reviewer runs one slow Haiku turn (`python slow_step.py`), and N reviews are dispatched to
     it meanwhile: each is answered 200 queued, in a conversation of its own.
  3. The turn ends; its re-drain attempts the head. Then `POST .../continue` passes follow, one at a
     time. Whenever the head of the queue stands at attempt 2 -- the pass that would give it up --
     the pass and the operator's `DELETE /queue/entries/{head}` are fired together, the DELETE
     after an offset that cycles through OFFSETS_MS.

Each such pass is one sample. The answer and the record must name the same winner:
  operator  DELETE 200; the entry withdrawn at 2 attempts, no abandoned_reason, no
            queue_entry_abandoned for it;
  hub       DELETE 409; withdrawn at 3 attempts, "delivery failed 3 times ...", one
            queue_entry_abandoned for it.
Anything else is INCONSISTENT -- F328's shape is DELETE 200 with the Hub's reason and event.

    AW_HUB=http://127.0.0.1:<port> AW_KEY=... AW_DB=<path to the Hub's agentweave.db> \
        AW_EXPECT=prefix|fixed py -3.11 scripts/drive/t_d6_0913_f328_withdraw_race.py [N]

AW_EXPECT=prefix asserts only that the drive ran the race; whether a pre-fix Hub shows F328 on a
given run is timing, so it is reported, not asserted. AW_EXPECT=fixed asserts no sample is
inconsistent. The proof is read from the drive database, read-only. No row inserts. One Haiku turn.
Creates no job.
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import HUB, api  # noqa: E402

if HUB.rstrip("/").endswith((":8000", ":8010")):
    raise SystemExit(f"REFUSING TO RUN against {HUB}: 8000 is real usage and 8010 the trial Hub.")
DB = os.environ["AW_DB"]
EXPECT = os.environ.get("AW_EXPECT", "fixed")
if EXPECT not in ("prefix", "fixed"):
    raise SystemExit(f"AW_EXPECT must be prefix or fixed, not {EXPECT!r}")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
OFFSETS_MS = [0, 30, 60, 100, 150, 250]

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(("  ok   " if cond else "  FAIL ") + label + (f"  -- {detail}" if detail else ""))
    return bool(cond)


def note(label, value):
    print(f"  ..   {label}: {value}")


def rows(sql, *args):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


# --- a fresh repository, opened as a project ---------------------------------------------------

ROOT = pathlib.Path(tempfile.gettempdir()) / f"f328-{TAG}"
ROOT.mkdir(parents=True)


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {args} failed: {r.stderr}")
    return r.stdout.strip(), r.returncode


git("init", "-q", "-b", "main")
git("config", "user.email", "drive@example.com")
git("config", "user.name", "drive")
(ROOT / "README.md").write_text(f"f328 drive {TAG}\n", encoding="utf-8")
(ROOT / "slow_step.py").write_text(
    'import time\n\ntime.sleep(60)\nprint("slow step finished")\n', encoding="utf-8"
)
git("add", "README.md", "slow_step.py")
git("commit", "-q", "-m", "base")

c, proj = api("POST", "/projects/open", {"path": str(ROOT), "name": f"f328-{TAG}"})
if c not in (200, 201):
    raise SystemExit(f"POST /projects/open: {c} {proj}")
P = proj["id"]
A = f"/projects/{P}/project"
note("project", f"{P} at {ROOT}")

c, runner = api("POST", f"/projects/{P}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
assert c in (200, 201), (c, runner)
REV = f"rev{TAG}"
c, b = api("POST", f"/projects/{P}/agents", {"name": REV, "runner_id": runner["id"]})
assert c in (200, 201), (c, b)
api("PATCH", f"/projects/{P}/agents/{REV}", {"default_permission_mode": "bypassPermissions"})

# --- one approved document, N completed tasks whose evidence names a commit about to be pruned ----

document = {
    "schema_version": 1,
    "kind": "change-spec",
    "title": "f328",
    "summary": "A driven fixture document for D-6 2026-09-13, complete enough to approve.",
    "problem": "F328 cannot be driven without a requirement that evidence can name.",
    "scope": {"in_scope": ["Review dispatch"], "non_goals": ["Anything real"]},
    "requirements": [
        {
            "key": "fr-1",
            "statement": "The subject MUST satisfy condition fr-1 exactly as stated here.",
            "modal": "MUST",
            "rationale": "Condition fr-1 is silent when violated, so it needs stating.",
        }
    ],
    "acceptance_criteria": [
        {
            "key": "ac-fr-1",
            "requirement": "fr-1",
            "given": "a fixture project",
            "when": "condition fr-1 is exercised",
            "then": "the behaviour matches fr-1",
        }
    ],
    "tasks": [
        {
            "key": "t-fr-1",
            "title": "Satisfy condition fr-1",
            "description": "Implement condition fr-1, covering ac-fr-1 with a named test.",
            "requirements": ["fr-1"],
            "reviewer": "critic",
        }
    ],
    "design": "One condition, local to its own function.",
    "evidence": {"checked": ["Nothing, fixture"], "limits": ["Describes no software"]},
    "lifecycle": "Deleted with the fixture.",
    "open_questions": [],
}
DOC = f"spec/changes/f328-{TAG}/spec.html"
c, b = api("POST", f"{A}/documents", {"path": DOC, "title": f"f328 {TAG}"})
assert c == 201, (c, b)
c, b = api("PUT", f"{A}/documents/{DOC}/content", {"document": document})
assert c in (200, 201), (c, str(b)[:300])
IDENT = (b.get("identifiers") or {})["fr-1"]
assert api("POST", f"{A}/documents/close-exploration?path={DOC}")[0] == 200
c, b = api("POST", f"{A}/documents/propose?path={DOC}")
assert c == 200 and not b.get("blocking"), (c, str(b)[:300])
assert api("POST", f"{A}/documents/phase?path={DOC}&to=approved", {"reason": ""})[0] == 200

git("checkout", "-q", "-b", f"gone-{TAG}")
git("commit", "-q", "--allow-empty", "-m", "a commit that will be pruned")
GONE, _ = git("rev-parse", "HEAD")
git("checkout", "-q", "main")
TASKS = []
for i in range(N):
    c, t = api("POST", f"/projects/{P}/tasks", {"title": f"B1-{i}", "description": "x", "requirements": [IDENT]})
    assert c in (200, 201), (c, t)
    c, ev = api(
        "POST",
        f"{A}/spec/evidence",
        {
            "identifier": IDENT,
            "document": DOC,
            "task_id": t["id"],
            "kind": "manual_observation",
            "locator": GONE,
            "summary": "operator observed it",
        },
    )
    assert c == 201 and (ev.get("footprint") or {}).get("commit_sha") == GONE, (c, str(ev)[:300])
    for to in ("in_progress", "completed"):
        assert api("PATCH", f"/projects/{P}/tasks/{t['id']}", {"status": to})[0] == 200
    TASKS.append(t["id"])
git("branch", "-q", "-D", f"gone-{TAG}")
git("reflog", "expire", "--expire=now", "--all")
git("gc", "-q", "--prune=now")
ok("the evidence's commit is gone from the repository", git("cat-file", "-e", GONE, check=False)[1] != 0)


def runs_of(agent):
    return rows("select id, status from runs where project_id=? and agent=?", P, agent)


def entry(eid):
    return rows(
        "select id, state, conversation_id, delivery_attempts, waiting_reason, abandoned_reason, "
        "withdrawn_at from inbound_queue_entries where id=?",
        eid,
    )[0]


def head():
    found = rows(
        "select id, conversation_id, delivery_attempts from inbound_queue_entries "
        "where project_id=? and agent=? and state='queued' order by sequence limit 1",
        P,
        REV,
    )
    return found[0] if found else None


def events_for(event_type, eid):
    return len(
        rows(
            "select id from event_logs where project_id=? and event_type=? "
            "and json_extract(data, '$.entry_id')=?",
            P,
            event_type,
            eid,
        )
    )


def wait_until(predicate, limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        if predicate():
            return True
        time.sleep(1)
    return False


# --- the reviewer's own slow turn, and N reviews queued behind it ---------------------------------

c, b = api(
    "POST",
    f"/projects/{P}/agent/trigger",
    {
        "agent": REV,
        "message": (
            "Run the command `python slow_step.py` in your workspace and wait for it to finish; it "
            "takes about a minute. Then reply with the single word done."
        ),
    },
    timeout=90,
)
ok("the reviewer's own turn started", b.get("status") == "running", f"{c} {str(b)[:200]}")
ok("... and is running", wait_until(lambda: any(r["status"] == "running" for r in runs_of(REV)), 60))
ENTRIES = []
for tid in TASKS:
    c, b = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": REV, "review_task_id": tid, "message": f"Review task {tid}. Call no tool."},
        timeout=90,
    )
    ENTRIES.append(b.get("queue_entry_id") if isinstance(b, dict) else None)
    if not (c == 200 and b.get("status") == "queued"):
        ok(f"review of {tid} answered 200 queued", False, f"{c} {str(b)[:300]}")
ok(f"all {N} reviews were queued behind the running turn", all(ENTRIES) and len(set(ENTRIES)) == N)
ok("the reviewer's turn ends", wait_until(lambda: not any(r["status"] == "running" for r in runs_of(REV)), 420))
ok("its re-drain attempted the head (B1, refused)", wait_until(lambda: entry(ENTRIES[0])["delivery_attempts"] >= 1, 60))
note("head after the re-drain", json.dumps(entry(ENTRIES[0]), default=str))


# --- the passes, and the race at every attempt-2 head ---------------------------------------------


def timed(label, out, method, path):
    t0 = time.perf_counter()
    code, body = api(method, path, timeout=90)
    out[label] = (code, body, t0, time.perf_counter())


SAMPLES = []
for n in range(4 * N + 4):
    h = head()
    if h is None:
        break
    cont_path = f"/projects/{P}/conversations/{h['conversation_id']}/continue"
    if h["delivery_attempts"] != 2:
        c, b = api("POST", cont_path, timeout=90)
        if c != 200:
            note(f"pass {n} continue", f"{c} {str(b)[:200]}")
        continue
    offset = OFFSETS_MS[len(SAMPLES) % len(OFFSETS_MS)]
    out: dict = {}
    t_cont = threading.Thread(target=timed, args=("continue", out, "POST", cont_path))
    t_del = threading.Thread(
        target=timed, args=("delete", out, "DELETE", f"/projects/{P}/queue/entries/{h['id']}")
    )
    t_cont.start()
    time.sleep(offset / 1000)
    t_del.start()
    t_cont.join()
    t_del.join()
    row = entry(h["id"])
    d_code, d_body, d0, d1 = out["delete"]
    c_code, _c_body, c0, c1 = out["continue"]
    abandoned = events_for("queue_entry_abandoned", h["id"])
    withdrawn = events_for("queue_entry_withdrawn", h["id"])
    reason = row["abandoned_reason"] or ""
    if d_code == 200 and row["delivery_attempts"] == 2 and not reason and abandoned == 0:
        verdict = "operator"
    elif (
        d_code == 409
        and row["delivery_attempts"] == 3
        and reason.startswith("delivery failed 3 times")
        and abandoned == 1
    ):
        verdict = "hub"
    else:
        verdict = "INCONSISTENT"
    sample = {
        "entry": h["id"],
        "offset_ms": offset,
        "delete": d_code,
        "delete_ms": round((d1 - d0) * 1000),
        "continue": c_code,
        "continue_ms": round((c1 - c0) * 1000),
        "overlap": d0 < c1 and d1 > c0,
        "state": row["state"],
        "attempts": row["delivery_attempts"],
        "reason": reason[:40],
        "abandoned_events": abandoned,
        "withdrawn_events": withdrawn,
        "verdict": verdict,
    }
    SAMPLES.append(sample)
    print("  ..   sample " + json.dumps(sample))

print()
by = {v: sum(1 for s in SAMPLES if s["verdict"] == v) for v in ("operator", "hub", "INCONSISTENT")}
note("samples", f"{len(SAMPLES)}: {by}")
ok("every entry left the queue", head() is None, json.dumps(head()))
ok(f"the race ran {N} times", len(SAMPLES) == N, str(len(SAMPLES)))
ok("at least one DELETE overlapped its pass", any(s["overlap"] for s in SAMPLES))
if EXPECT == "fixed":
    ok(
        "no sample is inconsistent: the DELETE's answer and the record name the same winner",
        by["INCONSISTENT"] == 0,
        json.dumps([s for s in SAMPLES if s["verdict"] == "INCONSISTENT"]),
    )
else:
    note("F328 reached on this pre-fix run", by["INCONSISTENT"] > 0)
ok("the reviewer never ran a review turn (every dispatch refused)", len(runs_of(REV)) == 1, json.dumps(runs_of(REV)))

print(f"\n{len(PASS)} ok, {len(FAIL)} fail")
for f in FAIL:
    print("  FAIL:", f)
