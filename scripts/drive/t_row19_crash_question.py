"""Row 19 x row 13: the Hub killed while `ask_user` is blocking a run.

The permission half of this is handled explicitly — `reconcile_interrupted_runs` calls
`expire_pending_for_run`, and driving it showed a pending card becoming `expired`. Questions get
no such pass: nothing in `run_reconciliation.py` mentions them. What they have instead is
`asker_waiting`, computed per read as `created_by_run_id not in (runs whose status != running)`.

So the prediction under test is that the derived field does the job the explicit pass does for
cards, and the question that follows it: with the asking run dead, what happens to an operator who
answers anyway, and can they tell the dead question from the live one the redelivered turn raises?

Usage:  AW_HUB=... AW_KEY=... AW_PROJECT=... AW_AGENT=... py -3.11 t_row19_crash_question.py
"""

import os
import subprocess
import sqlite3
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
AGENT = os.environ.get("AW_AGENT") or "alpha"
PORT = os.environ.get("AW_PORT") or "8011"
DB = os.environ.get(
    "AW_DB", "sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0829/aw0829.db"
)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.environ.get("AW_HUBLOG", "C:/Users/huida/AppData/Local/Temp/aw0829/hub_crash.log")


def step(label):
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)


def ps(script):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True
    )
    return (r.stdout or "").strip()


def hub_pids():
    raw = ps(
        "Get-CimInstance Win32_Process -Filter \"name='python.exe' or name='py.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*uvicorn*--port {PORT}*' }} | "
        "ForEach-Object { $_.ProcessId }"
    )
    return [int(x) for x in raw.split() if x.isdigit()]


def kill_hub():
    pids = hub_pids()
    ps("Stop-Process -Id " + ",".join(str(p) for p in pids) + " -Force")
    time.sleep(3)
    code, _ = api("GET", "/projects", timeout=3)
    print(f"  killed {pids}; GET /projects -> {code}")
    return code == 0


def start_hub():
    subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", PORT, "--host", "127.0.0.1"],
        cwd=os.path.join(REPO, "hub"),
        env={
            **os.environ,
            "DATABASE_URL": DB,
            "AW_BOOTSTRAP_API_KEY": os.environ.get("AW_KEY", ""),
            "AW_TICKET_SECRET": os.environ.get("AW_TICKET_SECRET", "aw0829-ticket-secret"),
        },
        stdout=open(LOG, "ab"),
        stderr=subprocess.STDOUT,
    )
    end = time.time() + 45
    while time.time() < end:
        code, _ = api("GET", "/projects", timeout=3)
        if code == 200:
            return True
        time.sleep(1)
    return False


def sql(q, a=()):
    conn = sqlite3.connect(DB.split("///", 1)[1])
    try:
        cur = conn.execute(q, a)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


def questions():
    _, body = api("GET", f"/projects/{P}/questions")
    rows = body.get("questions") if isinstance(body, dict) else body
    return rows or []


def open_questions():
    return [q for q in questions() if not q.get("answered") and not q.get("declined")]


def wait_for(label, predicate, timeout=120, interval=2):
    end = time.time() + timeout
    while time.time() < end:
        v = predicate()
        if v:
            print(f"  [{time.strftime('%H:%M:%S')}] {label}: yes")
            return v
        time.sleep(interval)
    print(f"  [{time.strftime('%H:%M:%S')}] {label}: TIMED OUT after {timeout}s")
    return None


def main():
    verdicts = []

    step("0. Any question already open would confuse this; list them")
    for q in open_questions():
        print(f"  pre-existing: {q['id']} waiting={q.get('asker_waiting')} {q.get('question','')[:60]}")

    step("1. A run that blocks on ask_user")
    code, body = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {
            "agent": AGENT,
            "message": (
                "Call the ask_user tool exactly once with a single question: "
                "'Which colour should the badge be?' with options 'red' and 'blue'. "
                "When you get the answer back, reply with only the word you were given. "
                "Do not read or write any files."
            ),
        },
    )
    show("trigger", code, body, limit=500)
    if code >= 300:
        return
    run_id = body.get("run_id")

    q = wait_for(
        "a question is blocking the run",
        lambda: next((x for x in open_questions() if x.get("asker_waiting")), None),
        timeout=150,
    )
    if not q:
        print("FAIL -- no blocking question to crash on")
        return
    print(f"  question {q['id']} asker_waiting={q.get('asker_waiting')} run={q.get('created_by_run_id')}")

    step("2. Kill the Hub while the question is on screen")
    verdicts.append(("hub is really dead", kill_hub()))
    if not start_hub():
        print("FAIL -- hub did not come back")
        return

    step("3. The question, after the restart")
    after = next((x for x in questions() if x["id"] == q["id"]), None)
    print(f"  answered={after and after.get('answered')} declined={after and after.get('declined')} "
          f"asker_waiting={after and after.get('asker_waiting')}")
    print("  run:", sql("SELECT id,status,ended_at FROM runs WHERE id = ?", (run_id,)))
    # Nothing expires a question the way expire_pending_for_run expires a card. The claim under
    # test is that `asker_waiting` makes that unnecessary rather than merely unnoticed.
    verdicts.append(("the dead question stops claiming somebody is waiting",
                     bool(after) and after.get("asker_waiting") is False))
    verdicts.append(("and it is still there rather than silently deleted", bool(after)))

    step("4. The operator answers it anyway")
    code, body = api("PATCH", f"/projects/{P}/questions/{q['id']}",
                     {"answer": "blue", "labels": ["blue"]})
    show("PATCH answer (nobody is listening)", code, body, limit=800)
    verdicts.append(("answering a dead question is not a server error", code < 500))

    step("5. The redelivered turn asks again -- can the two be told apart?")
    fresh = wait_for(
        "a second question, from a live run",
        lambda: next((x for x in open_questions()
                      if x["id"] != q["id"] and x.get("asker_waiting")), None),
        timeout=180,
    )
    verdicts.append(("the redelivered turn asks again", bool(fresh)))
    if fresh:
        print(f"  fresh {fresh['id']} run={fresh.get('created_by_run_id')} waiting={fresh.get('asker_waiting')}")
        print("  all open questions now:")
        for x in open_questions():
            print(f"    {x['id']} waiting={x.get('asker_waiting')} run={x.get('created_by_run_id')}")
        code, body = api("PATCH", f"/projects/{P}/questions/{fresh['id']}",
                         {"answer": "blue", "labels": ["blue"]})
        show("PATCH answer (live)", code, body, limit=500)
        settled = wait_for(
            "the released run finished",
            lambda: not sql("SELECT id FROM runs WHERE agent = ? AND status = 'running'", (AGENT,)),
            timeout=180,
        )
        verdicts.append(("answering released the live run", bool(settled)))

    step("6. Questions the operator is left looking at")
    for x in questions()[-6:]:
        print(f"  {x['id']} answered={x.get('answered')} waiting={x.get('asker_waiting')} "
              f"answer={str(x.get('answer'))[:30]}")

    step("VERDICTS")
    for label, ok in verdicts:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")


if __name__ == "__main__":
    main()
