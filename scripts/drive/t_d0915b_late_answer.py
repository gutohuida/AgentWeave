"""DRIVE 2026-09-15 -- a late answer is delivered (F356; openspec change, tasks 5.1-5.7).

`ask_user` gives up at its deadline and the run carries on working. Before this change an operator
who answered after that, while the run still lived, had the answer recorded and delivered to nobody:
the answer route read "the asking run is running" as "the asker is waiting". LoopEngine lost two of
four answers that way on 2026-09-13 (batch 14:38).

Unit tests pin the predicate, the report's delivery and the races. This drives the product: a real
Haiku turn calls the real `ask_user` (spawned from this checkout's `mcp_server.py`), the real tool
times out and files its real expiry report, and the operator answers through the real route while
the run is still working.

  5.2  Two questions, not answered in time; the agent then sleeps well past the wait. Both carry
       `wait_ended_at`, the run is still running, and the list and detail routes read
       `asker_waiting: false`.
  5.3  Both answered while the run lives: one queue entry carrying both. After the run ends, one new
       turn is delivered that entry, and nothing else is queued.
  5.4  Control: a fresh question answered inside the wait. The tool returns it; no entry is queued.
  5.5  Grace window, by clock: answer ~0.3 s after the Hub's deadline. Recorded, not claimed -- the
       tool either returned it (no entry, no `wait_ended_at`) or reported it (entry + record). The
       one outcome that fails is the old one: neither.

`wait_ended_at` and queue rows are read from the drive database with `mode=ro`; the API does not
expose them. Real surface for every write. One Haiku runner. No job is created.

Run (from scripts/drive):
  AW_HUB=http://127.0.0.1:<port> AW_KEY=<key> AW_DB=<drive db path> py -3.11 -u t_d0915b_late_answer.py
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aw  # noqa: E402
from aw import api  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
AGENT = "asker"
FORBIDDEN = ("proj-5e960453", "proj-18e5d4e0")
DB = os.environ["AW_DB"]
RUN = time.strftime("%H%M%S")
LANES = os.environ.get("AW_LANES", "late,control,grace").split(",")
# Not a bare `sleep N`: a long foreground sleep is a command the agent CLI may refuse.
SLEEP = 'py -3.11 -c "import time; time.sleep({})"'

VERDICTS = []
S = {}


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def note(label, detail=""):
    print(f"  [obs] {label}" + (f" -- {detail}" if detail else ""))


def head(t):
    print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)


def blob(x, limit=900):
    return json.dumps(x, default=str)[:limit]


def call(label, method, path, body=None, expect=(200, 201)):
    code, out = api(method, path, body)
    ok = code in expect
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED ' + blob(out, 600)}")
    if not ok:
        raise SystemExit(f"{label} failed")
    return out


def ro(sql, *args):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def P():  # noqa: N802
    return S["P"]


def runs():
    return ro(
        "SELECT id, status, started_at, ended_at FROM runs WHERE project_id=? AND agent=? "
        "ORDER BY started_at",
        P(),
        AGENT,
    )


def running():
    return [r for r in runs() if r["status"] == "running"]


def entries():
    return ro(
        "SELECT id, content, state, delivered_in_run_id, arrived_at, origin_type "
        "FROM inbound_queue_entries WHERE project_id=? AND agent=? ORDER BY sequence",
        P(),
        AGENT,
    )


def questions_of(run_id):
    return ro(
        "SELECT id, question, answered, declined, wait_expires_at, wait_ended_at, answered_at, "
        "batch_index FROM questions WHERE created_by_run_id=? ORDER BY batch_index",
        run_id,
    )


def outputs(run_id):
    rows = ro("SELECT * FROM agent_outputs WHERE run_id=?", run_id)
    return " ".join(str(r.get("content") or r.get("output") or "") for r in rows)


def wait_for(pred, seconds, what, gap=0.5):
    end = time.time() + seconds
    while time.time() < end:
        value = pred()
        if value:
            return value
        time.sleep(gap)
    print(f"      timed out waiting for {what}")
    return None


def parse(ts):
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def trigger(message):
    before = {r["id"] for r in runs()}
    call(
        "trigger",
        "POST",
        f"/projects/{P()}/agent/trigger",
        {"agent": AGENT, "message": message, "session_mode": "new"},
        expect=(200, 201, 202),
    )
    fresh = wait_for(
        lambda: [r for r in runs() if r["id"] not in before and r["status"] == "running"],
        90,
        "the asking run to start",
    )
    return fresh[0]["id"] if fresh else None


def asked(run_id, n, seconds=150):
    return wait_for(lambda: (q := questions_of(run_id)) and len(q) >= n and q, seconds, "questions")


def answer(qid, text):
    return call(
        f"answer {qid}",
        "PATCH",
        f"/projects/{P()}/questions/{qid}",
        {"answer": text, "labels": [text]},
    )


def asker_waiting(qid):
    code, listed = api("GET", f"/projects/{P()}/questions")
    from_list = next((q["asker_waiting"] for q in listed if q["id"] == qid), None)
    code, detail = api("GET", f"/projects/{P()}/questions/{qid}")
    return from_list, detail.get("asker_waiting") if isinstance(detail, dict) else None


def settle(seconds=240):
    return wait_for(lambda: not running(), seconds, "every run to end", gap=2)


# --- setup --------------------------------------------------------------------------------------


def setup():
    head("5.1 SETUP -- fresh project, one Haiku runner, one agent, the smallest question wait")
    root = tempfile.mkdtemp(prefix="aw-d0915b-")
    for args in (
        ("init", "-q"),
        ("config", "user.email", "drive@example.com"),
        ("config", "user.name", "Drive"),
        ("checkout", "-q", "-b", "main"),
    ):
        subprocess.run(["git", "-C", root, *args], check=True, capture_output=True)
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    subprocess.run(["git", "-C", root, "add", "README.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", root, "commit", "-q", "-m", "base"], check=True, capture_output=True
    )
    created = call(
        "open project", "POST", "/projects/open", {"path": root, "name": f"d0915b-{RUN}"}
    )
    S["P"] = created["id"]
    aw.P = S["P"]
    if P() in FORBIDDEN:
        raise SystemExit(f"REFUSING: the Hub handed back {P()}")
    runner = call(
        "runner",
        "POST",
        f"/projects/{P()}/runners",
        {"name": "haiku", "cli": "claude", "model": HAIKU},
    )
    call("agent", "POST", f"/projects/{P()}/agents", {"name": AGENT, "runner_id": runner["id"]})
    # The lanes run a long shell wait after `ask_user`; nothing here is an approval under test.
    call(
        "agent permission",
        "PATCH",
        f"/projects/{P()}/agents/{AGENT}",
        {"default_permission_mode": "bypassPermissions"},
    )
    for seconds in (10, 15, 30):
        code, body = api(
            "PATCH", f"/projects/{P()}/agents/{AGENT}", {"question_timeout_seconds": seconds}
        )
        print(f"  question_timeout_seconds={seconds}: {code}")
        if code == 200:
            S["wait"] = seconds
            break
    else:
        raise SystemExit("no question timeout was accepted")
    print(f"  project {P()} at {root}, wait {S['wait']}s")


# --- lanes --------------------------------------------------------------------------------------


def lane_late():
    head("5.2 + 5.3 -- two questions not answered in time; the run sleeps on; answered late")
    sleep_for = S["wait"] + 75
    run_id = trigger(
        "Call the ask_user tool exactly once, with exactly these two blocking questions in one "
        "call: 'Which colour should the banner be?' with options red and blue, and 'Which size "
        "should the banner be?' with options small and large. Whatever ask_user returns, even if "
        "it says the questions went unanswered, next run exactly this shell command with your Bash "
        f"tool, allowing it the full time: `{SLEEP.format(sleep_for)}` -- then reply with one "
        "sentence saying "
        "which answers, if any, you have received so far. Do not call ask_user a second time."
    )
    check("5.2: the asking run started", run_id, str(run_id))
    if not run_id:
        return
    qs = asked(run_id, 2)
    check("5.2: the run asked two questions", qs and len(qs) == 2, blob(qs))
    if not qs:
        return
    ids = [q["id"] for q in qs]
    ended = wait_for(
        lambda: all(q["wait_ended_at"] for q in questions_of(run_id)) and questions_of(run_id),
        S["wait"] + 60,
        "the tool's expiry report",
    )
    check("5.2: both carry wait_ended_at (the tool's report landed)", ended, blob(ended))
    live = [r for r in running() if r["id"] == run_id]
    check("5.2: the asking run is still running", live, blob(runs()))
    for qid in ids:
        from_list, from_detail = asker_waiting(qid)
        check(
            f"5.2: {qid} reads asker_waiting false on the list and the detail route",
            from_list is False and from_detail is False,
            f"list={from_list} detail={from_detail}",
        )

    before = {e["id"] for e in entries()}
    answer(ids[0], "blue")
    answer(ids[1], "large")
    still = [r for r in running() if r["id"] == run_id]
    check("5.3: the run was still running after both answers", still, blob(runs()))
    new = [e for e in entries() if e["id"] not in before]
    check(
        "5.3: exactly one queue entry, carrying both answers",
        len(new) == 1
        and "Answer: blue" in new[0]["content"]
        and "Answer: large" in new[0]["content"],
        blob(new),
    )
    if len(new) != 1:
        return
    entry_id = new[0]["id"]
    note("5.3: entry state while the asker runs", new[0]["state"])
    check("5.3: the entry waits behind the live run (queued)", new[0]["state"] == "queued")

    done = wait_for(
        lambda: next(
            (e for e in entries() if e["id"] == entry_id and e["delivered_in_run_id"]), None
        ),
        sleep_for + 240,
        "the entry's delivery",
        gap=2,
    )
    check("5.3: the entry was delivered into a new turn", done, blob(done))
    settle()
    if done:
        turn = done["delivered_in_run_id"]
        asking = next(r for r in runs() if r["id"] == run_id)
        delivered_in = next(r for r in runs() if r["id"] == turn)
        check(
            "5.3: that turn started after the asking run ended",
            turn != run_id and parse(delivered_in["started_at"]) >= parse(asking["ended_at"]),
            f"asking ended {asking['ended_at']} / turn started {delivered_in['started_at']}",
        )
        reply = outputs(turn)
        note("5.3: the delivered turn's output mentions", reply[-600:])
    queued = [e for e in entries() if e["state"] == "queued"]
    check("5.3: nothing else is queued", not queued, blob(queued))
    S["late_run"] = run_id


def lane_control():
    head("5.4 CONTROL -- a question answered inside the wait is returned by the tool, not queued")
    run_id = trigger(
        "Call the ask_user tool exactly once with one blocking question: 'Which fruit?' with "
        "options apple and pear. Then reply with one sentence naming the answer you received."
    )
    check("5.4: the asking run started", run_id, str(run_id))
    if not run_id:
        return
    qs = asked(run_id, 1)
    if not check("5.4: the run asked", qs, blob(qs)):
        return
    before = {e["id"] for e in entries()}
    answer(qs[0]["id"], "pear")
    settle()
    row = questions_of(run_id)[0]
    check(
        "5.4: no wait_ended_at (the tool received the answer)", not row["wait_ended_at"], blob(row)
    )
    new = [e for e in entries() if e["id"] not in before]
    check("5.4: no queue entry for an answer the tool returned", not new, blob(new))
    reply = outputs(run_id)
    note("5.4: the asking turn's output", reply[-400:])
    check("5.4: the asking turn saw 'pear'", "pear" in reply.lower(), "")


def lane_grace():
    head("5.5 GRACE WINDOW -- answer ~0.3 s after the Hub's deadline; record which path took it")
    run_id = trigger(
        "Call the ask_user tool exactly once with one blocking question: 'Which number?' with "
        "options one and two. Whatever it returns, then run exactly this shell command with your "
        f"Bash tool: `{SLEEP.format(40)}` -- then reply with one sentence naming the answer you "
        "received, if any."
    )
    if not check("5.5: the asking run started", run_id, str(run_id)):
        return
    qs = asked(run_id, 1)
    if not check("5.5: the run asked", qs, blob(qs)):
        return
    qid = qs[0]["id"]
    deadline = parse(qs[0]["wait_expires_at"])
    delay = (deadline - datetime.now(timezone.utc)).total_seconds() + 0.3
    note("5.5: sleeping until the Hub's deadline + 0.3 s", f"{delay:.2f}s")
    if delay > 0:
        time.sleep(delay)
    before = {e["id"] for e in entries()}
    answer(qid, "two")
    answered_at = datetime.now(timezone.utc)
    note("5.5: answered at deadline +", f"{(answered_at - deadline).total_seconds():.2f}s")
    settle(180)
    row = questions_of(run_id)[0]
    new = [e for e in entries() if e["id"] not in before]
    reply = outputs(run_id)
    tool_took_it = not row["wait_ended_at"]
    note("5.5: wait_ended_at", str(row["wait_ended_at"]))
    note("5.5: entries queued for it", blob(new))
    note("5.5: the asking turn's output", reply[-400:])
    if tool_took_it:
        check("5.5 (tool returned it): no entry queued -- not duplicated", not new, blob(new))
    else:
        check(
            "5.5 (tool reported it): the report delivered it as one entry", len(new) == 1, blob(new)
        )


def teardown():
    head("5.7 TEARDOWN -- no run left running, no job exists")
    settle(300)
    check("5.7: no run is running", not running(), blob(running()))
    code, jobs = api("GET", f"/projects/{P()}/jobs?include_archived=true")
    check("5.7: no job exists or is enabled", not [j for j in jobs if j.get("enabled")], blob(jobs))


def main():
    try:
        setup()
        for lane in LANES:
            {"late": lane_late, "control": lane_control, "grace": lane_grace}[lane]()
    finally:
        if S.get("P"):
            teardown()
    head("VERDICT")
    for label, ok, detail in VERDICTS:
        print(f"  {'OK ' if ok else 'BAD'}  {label}" + (f"  -- {detail}" if detail else ""))
    bad = [v for v in VERDICTS if not v[1]]
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)}   project {S.get('P')}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
