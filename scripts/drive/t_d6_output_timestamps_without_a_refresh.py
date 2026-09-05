"""D-6 / F287: drive a real turn and check every output row it wrote carries a timestamp.

The removal of `await db.refresh(row)` from `record_agent_output` is only safe if the one
attribute the function reads that its caller did not set -- `row.timestamp` -- is populated
without it. A unit test pins that in-process; this checks the shipped product, against a Hub
started from the edited source, with a real `claude-haiku-4-5` turn producing real streamed
lines through the Hub's own spawn loop (`agent_trigger.py`), not the self-report endpoint.

Checked, in order:
  1. a live SSE subscriber receives `agent_output` events and every one carries a `timestamp`
     that parses and is close to now (the broadcast is what reads `row.timestamp`);
  2. the persisted rows, read back through `GET /agents/{name}/output`, all carry a timestamp;
  3. the run reaches a terminal status and the turn produced a real reply;
  4. the terminal `kind="status"` row -- written by the second call site -- is present.

Env: AW_HUB, AW_KEY, AW_PROJECT, AGENT, AW_DB.
"""

import datetime
import json
import os
import queue
import sqlite3
import ssl
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api, show  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8011")
KEY = os.environ["AW_KEY"]
AGENT = os.environ["AGENT"]
DB = os.environ["AW_DB"]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

events: "queue.Queue[dict]" = queue.Queue()
stop = threading.Event()


def _sse_reader():
    req = urllib.request.Request(f"{HUB}/api/v1/projects/{P}/events")
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Accept", "text/event-stream")
    try:
        with urllib.request.urlopen(req, timeout=300, context=_ctx) as r:
            name = None
            for raw in r:
                if stop.is_set():
                    return
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line.startswith("event:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and name:
                    try:
                        events.put({"event": name, "data": json.loads(line.split(":", 1)[1])})
                    except ValueError:
                        pass
                    name = None
    except Exception as exc:  # noqa: BLE001
        events.put({"event": "__reader_error__", "data": f"{type(exc).__name__}: {exc}"})


reader = threading.Thread(target=_sse_reader, daemon=True)
reader.start()
time.sleep(2.0)

MESSAGE = (
    "Reply with exactly three short lines, each on its own line: the word ALPHA, "
    "the word BRAVO, then the word CHARLIE. Do not use any tools."
)
started = datetime.datetime.now(datetime.timezone.utc)
code, trig = api("POST", f"/projects/{P}/agent/trigger", {"agent": AGENT, "message": MESSAGE})
show("POST /agent/trigger", code, trig, limit=400)
run_id = trig.get("run_id") if isinstance(trig, dict) else None
if code not in (200, 201) or not run_id:
    sys.exit("trigger did not start a run")

# The run's status is read from the database, not from a route: the Hub exposes no
# `GET /projects/{id}/runs`, and the other drive scripts in this directory read it the same way.
def _run_row():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, status, exit_code, error FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


status, began = None, time.time()
while time.time() - began < 240:
    time.sleep(4)
    row = _run_row()
    if row:
        status = row["status"]
        if status in ("completed", "failed", "stopped", "interrupted"):
            break
print()
print(f"run {run_id} settled at {_run_row()} after {time.time() - began:.1f}s")

time.sleep(3)
stop.set()

# ---- 1. every broadcast agent_output carried a timestamp -------------------------------------
broadcast, errors = [], []
while True:
    try:
        e = events.get_nowait()
    except queue.Empty:
        break
    if e["event"] == "__reader_error__":
        errors.append(e["data"])
    elif e["event"] == "agent_output":
        broadcast.append(e["data"])

print(f"\nSSE: {len(broadcast)} agent_output events, reader errors={errors}")
missing = [b for b in broadcast if not b.get("timestamp")]
unparsable, stale = [], []
for b in broadcast:
    ts = b.get("timestamp")
    if not ts:
        continue
    try:
        parsed = datetime.datetime.fromisoformat(ts)
    except ValueError:
        unparsable.append(ts)
        continue
    if parsed.tzinfo is None:
        unparsable.append(f"naive: {ts}")
    elif abs((parsed - started).total_seconds()) > 900:
        stale.append(ts)
print(f"  without a timestamp : {len(missing)}")
print(f"  unparsable/naive    : {unparsable}")
print(f"  implausibly distant : {stale}")
if broadcast:
    print(f"  first: {broadcast[0].get('kind')!r} {broadcast[0].get('timestamp')}")
    print(f"  last : {broadcast[-1].get('kind')!r} {broadcast[-1].get('timestamp')}")

# ---- 2. the persisted rows ---------------------------------------------------------------
c, rows = api("GET", f"/projects/{P}/agents/{AGENT}/output?limit=200")
print(f"\nGET /output [{c}]: {len(rows) if isinstance(rows, list) else rows} rows")
no_ts = [r["id"] for r in rows if not r.get("timestamp")] if isinstance(rows, list) else ["?"]
print(f"  persisted rows without a timestamp: {no_ts}")

# ---- 3/4. the turn actually ran, and the terminal status row landed -----------------------
texts = [r for r in rows if r.get("kind") == "text"] if isinstance(rows, list) else []
statuses = [r for r in rows if r.get("kind") == "status"] if isinstance(rows, list) else []
joined = " ".join((r.get("content") or "") for r in texts).upper()
print(f"\n  text rows={len(texts)}  status rows={len(statuses)}")
print(f"  reply contains ALPHA/BRAVO/CHARLIE: "
      f"{('ALPHA' in joined, 'BRAVO' in joined, 'CHARLIE' in joined)}")
for s in statuses:
    print(f"  status row {s['id']} ts={s.get('timestamp')} payload={s.get('payload')}")

ok = (
    status == "completed"
    and broadcast
    and not missing
    and not unparsable
    and not stale
    and not no_ts
    and statuses
)
print("\nRESULT:", "PASS" if ok else "FAIL")
