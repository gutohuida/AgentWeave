"""SWEEP ROW 16 — LOGS, EVENTS AND SSE. What crosses the wire, and what any screen can act on.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 t_sweep_row16_logs_events_sse.py
    AW_HUB=... AW_KEY=... py -3.11 t_sweep_row16_logs_events_sse.py --teardown

**Prior coverage was read first.** No harness under `scripts/drive` opens an SSE connection at
all — every one of them polls the database or the REST surface. `FINDINGS.md` has no finding
against `events.py`, `logs.py` or `sse.py`. So this row is unploughed, and the questions it asks
are the ones only a client on the stream can answer:

* **Which broadcasts a screen can act on.** `useSSE.ts` gates dispatch on a hard-coded
  `SSE_EVENT_TYPES` allowlist (`useSSE.ts:335`). Anything not on it is read off the socket and
  dropped before any listener, any buffer, any invalidation. The Hub broadcasts names that are
  not on it.
* **Whether the served bundle agrees with the source.** F215's lesson: what the operator runs is
  `hub/hub/static/ui`, not `hub/ui/src`.
* **What the Logs screen's own request returns.** `useLogs` asks for `limit=500` with no offset;
  `list_logs` orders `timestamp.asc()`.
* **What a malformed `since` does.** `list_logs` catches `ValueError` and `pass`es.
* **What an SSE ticket still unlocks after the project it names is gone.** `_verify_ticket` is an
  HMAC check with no database in it; the stream handler tolerates a missing project.
* **What happens to a subscriber that stops reading.** `SSEManager.broadcast` drops on
  `QueueFull` (256) and says nothing to anyone.

One project, one runner, one agent, one real `claude-haiku-4-5` turn, and a second project that
exists only to be deleted while two streams are watching. Every fixture is created here —
including `git init` and an initial commit, without which no turn can run — and removed by
`--teardown`.

**Re-runnable on the state it leaves.** Every pushed event carries the run tag, every count is a
delta against a baseline captured in its own leg, the doomed project is recreated by setup after
leg 3 deletes it, and no leg leaves a job enabled or a working tree dirty.
"""

import http.client
import json
import os
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api  # noqa: E402

HUB = os.environ.get("AW_HUB", "")
KEY = os.environ.get("AW_KEY", "")
if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the other trial Hub.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
DIR = os.environ.get("AW_DRIVE_DIR", "C:\\Users\\huida\\Documents\\aw-drive-row16")
DIR_DOOMED = DIR + "-doomed"
NAME = os.path.basename(DIR.rstrip("\\/"))
NAME_DOOMED = os.path.basename(DIR_DOOMED.rstrip("\\/"))
SCRIBE = "scribe"
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
DB = os.environ.get("AW_DB", os.path.expanduser("~/.agentweave/hub/profiles/beta/agentweave.db"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UI_BUNDLE_DIR = os.path.join(ROOT, "hub", "hub", "static", "ui", "assets")
UI_SRC = os.path.join(ROOT, "hub", "ui", "src")
HUB_PY = os.path.join(ROOT, "hub", "hub")

PASS, FAIL = [], []


def ok(label, cond, detail=""):
    (PASS if cond else FAIL).append(label)
    print(
        ("  ok   " if cond else "  FAIL ")
        + label
        + (f"  -- {detail}" if detail and not cond else "")
    )


def note(label, value):
    print(f"  ..   {label}: {value}")


def leg(n, title):
    print(f"\n=== LEG {n}: {title}")


# ---------------------------------------------------------------------------- fixture


def git(path, *args, check=False):
    r = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} in {path}: {r.stderr.strip()}")
    return r


def find_project(name):
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return next((p["id"] for p in rows if p.get("name") == name), None)


def project_count():
    _, body = api("GET", "/projects")
    rows = body if isinstance(body, list) else (body or {}).get("projects") or []
    return len(rows)


def ensure_repo(path):
    """A fixture directory that is a git repository WITH A COMMIT IN IT.

    Copied from `t_sweep_row15_worktrees.py`, and not decoration: a project whose repository has
    no commits cannot run a turn — `git worktree add ... HEAD` fails with "invalid reference:
    HEAD" and `POST /agent/trigger` answers an honest 200 with `run_id: null`.
    """
    os.makedirs(path, exist_ok=True)
    if git(path, "rev-parse", "--git-dir").returncode != 0:
        git(path, "init")
    if git(path, "rev-parse", "HEAD").returncode != 0:
        with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("row 16 logs/events/sse fixture\n")
        git(path, "add", "README.md")
        git(path, "-c", "user.email=drive@local", "-c", "user.name=drive",
            "commit", "-m", "fixture: initial commit so a turn can run")


def ensure_dir_only(path):
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("row 16 doomed fixture -- deleted by leg 3 on every run\n")


def ensure_project(path, name, repo=True):
    found = find_project(name)
    if found:
        return found
    ensure_repo(path) if repo else ensure_dir_only(path)
    code, body = api("POST", "/projects/open", {"path": path, "name": name})
    if code >= 300:
        sys.exit(f"could not open project {name}: {code} {body}")
    return body["id"]


def ensure_runner(project):
    _, body = api("GET", f"/projects/{project}/runners")
    rows = body if isinstance(body, list) else (body or {}).get("runners") or []
    for r in rows:
        if r.get("name") == "Haiku (cheap)":
            return r["id"]
    code, body = api(
        "POST", f"/projects/{project}/runners",
        {"name": "Haiku (cheap)", "cli": "claude", "model": HAIKU},
    )
    if code >= 300:
        sys.exit(f"could not create runner: {code} {body}")
    return body["id"]


def ensure_agent(project, name, runner):
    code, _ = api("POST", f"/projects/{project}/agents", {"name": name, "runner_id": runner})
    if code < 300:
        return name
    _, body = api("GET", f"/projects/{project}/agents")
    rows = body if isinstance(body, list) else (body or {}).get("agents") or []
    if any(a.get("name") == name for a in rows):
        return name
    sys.exit(f"could not create or find agent {name}: {body}")


def teardown():
    for name in (NAME, NAME_DOOMED):
        pid = find_project(name)
        if pid:
            code, _ = api("DELETE", f"/projects/{pid}")
            print(f"deleted {name} ({pid}) -> {code}")
    for path in (DIR, DIR_DOOMED):
        if os.path.isdir(path):
            def _force(func, target, _exc):
                os.chmod(target, stat.S_IWRITE)
                func(target)

            shutil.rmtree(path, onerror=_force)
            print(f"removed {path} -> exists={os.path.isdir(path)}")
    print(f"projects now: {project_count()}")


if "--teardown" in sys.argv:
    teardown()
    sys.exit(0)


P = ensure_project(DIR, NAME, repo=True)
P_DOOMED = ensure_project(DIR_DOOMED, NAME_DOOMED, repo=False)
RUNNER = ensure_runner(P)
ensure_agent(P, SCRIBE, RUNNER)
A = f"/projects/{P}"
print(f"fixture: {NAME}={P}  doomed={NAME_DOOMED}={P_DOOMED}  tag={TAG}")


# ---------------------------------------------------------------------------- helpers


def db_rows(sql, args=()):
    """Read the Hub's database read-only. Observation only; the Hub owns this file."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    try:
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        con.close()


def push_log(event_type, data=None, agent=None, severity="info", project=None):
    return api(
        "POST", f"/projects/{project or P}/logs",
        {"event_type": event_type, "data": data or {}, "agent": agent, "severity": severity},
    )


class Pusher:
    """One keep-alive connection for bulk pushes. 500 events over urllib takes minutes."""

    def __init__(self, project):
        parts = urllib.parse.urlparse(HUB)
        self.conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=30)
        self.path = f"/api/v1/projects/{project}/logs"

    def push(self, event_type, data, severity="info", agent=None):
        body = json.dumps(
            {"event_type": event_type, "data": data, "agent": agent, "severity": severity}
        )
        self.conn.request(
            "POST", self.path, body,
            {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
        )
        r = self.conn.getresponse()
        r.read()
        return r.status

    def close(self):
        self.conn.close()


def parse_frames(buffer, chunk):
    """Exactly `feedSSEChunk` from useSSE.ts:196 — the client's own framing, not a new one."""
    combined = buffer + chunk
    frames = combined.split("\n\n")
    if len(frames) == 1:
        frames = combined.split("\r\n\r\n")
        if len(frames) == 1:
            return combined, []
    remaining = frames.pop()
    out = []
    for frame in frames:
        etype, data_lines, comments = "message", [], []
        for line in frame.replace("\r\n", "\n").split("\n"):
            if line.startswith("event:"):
                etype = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line.startswith(":"):
                comments.append(line)
        if data_lines:
            out.append((etype, "\n".join(data_lines)))
        elif comments:
            out.append((":ping", comments[0]))
    return remaining, out


class Stream:
    """An SSE client. Collects every frame the wire carried, before any allowlist."""

    def __init__(self, url, headers=None, label=""):
        self.url = url
        self.headers = headers or {}
        self.label = label or url
        self.frames = []          # (event_name, parsed_data, monotonic)
        self.raw_names = []       # event names in arrival order, pings included
        self.status = None
        self.error = None
        self._stop = False
        self._resp = None
        self._t = None

    def open(self, timeout=25):
        req = urllib.request.Request(self.url)
        for k, v in self.headers.items():
            req.add_header(k, v)
        try:
            self._resp = urllib.request.urlopen(req, timeout=timeout)
            self.status = self._resp.status
        except urllib.error.HTTPError as e:
            self.status = e.code
            self.error = e.read().decode("utf-8", "replace")[:200]
            return self
        except Exception as e:  # noqa: BLE001
            self.status = 0
            self.error = f"{type(e).__name__}: {e}"
            return self
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()
        return self

    def _read(self):
        buf = ""
        while not self._stop:
            try:
                chunk = self._resp.read1(4096)
            except (socket.timeout, TimeoutError):
                continue
            except Exception:  # noqa: BLE001
                break
            if not chunk:
                break
            buf, events = parse_frames(buf, chunk.decode("utf-8", "replace"))
            for name, raw in events:
                self.raw_names.append(name)
                if name == ":ping":
                    continue
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = raw
                self.frames.append((name, data, time.monotonic()))

    def names(self, since_index=0):
        return [f[0] for f in self.frames[since_index:]]

    def wait_for(self, pred, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for f in list(self.frames):
                if pred(f):
                    return f
            time.sleep(0.2)
        return None

    def close(self):
        self._stop = True
        try:
            if self._resp:
                self._resp.close()
        except Exception:  # noqa: BLE001
            pass


def instance_stream():
    return Stream(f"{HUB}/api/v1/events", {"Authorization": "Bearer " + KEY}, "instance")


def project_ticket(project):
    code, body = api("GET", f"/projects/{project}/events/ticket")
    return code, (body or {}).get("token") if isinstance(body, dict) else None


def project_stream(project, token):
    q = urllib.parse.quote(token, safe="")
    return Stream(f"{HUB}/api/v1/projects/{project}/events?token={q}", {}, f"project:{project}")


def served_allowlist():
    """The SSE_EVENT_TYPES array as it exists in the bundle the Hub actually serves."""
    import glob
    import re

    for path in glob.glob(os.path.join(UI_BUNDLE_DIR, "*.js")):
        text = open(path, encoding="utf-8", errors="replace").read()
        m = re.search(r'\[\s*"message_created"[^\]]*\]', text)
        if m:
            return set(re.findall(r'"([a-z_]+)"', m.group(0))), os.path.basename(path)
    return set(), ""


def source_allowlist():
    import re

    text = open(os.path.join(UI_SRC, "hooks", "useSSE.ts"), encoding="utf-8").read()
    m = re.search(r"SSE_EVENT_TYPES = \[(.*?)\]", text, re.S)
    return set(re.findall(r"'([a-z_]+)'", m.group(1))) if m else set()


def broadcast_types():
    """Every literal event name passed to sse_manager.broadcast under hub/hub."""
    import glob
    import re

    found = {}
    for path in glob.glob(os.path.join(HUB_PY, "**", "*.py"), recursive=True):
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'broadcast\(\s*[^,]+,\s*"([a-z_]+)"', text, re.S):
            found.setdefault(m.group(1), os.path.relpath(path, ROOT).replace("\\", "/"))
    return found


def trigger(agent, message, task_id=None):
    payload = {"agent": agent, "message": message}
    if task_id:
        payload["task_id"] = task_id
    code, body = api("POST", f"{A}/agent/trigger", payload, timeout=60)
    if code not in (200, 201, 202):
        return None, f"trigger {code} {str(body)[:200]}"
    run_id = (body or {}).get("run_id") or (body or {}).get("id")
    return (run_id, "started") if run_id else (None, f"no run: {json.dumps(body)[:200]}")


def wait_run(run_id, wait=420):
    deadline = time.time() + wait
    while time.time() < deadline:
        rows = db_rows("SELECT id, status FROM runs WHERE id = ?", (run_id,))
        if rows and rows[0]["status"] not in ("running", "queued", "starting"):
            return rows[0]["status"]
        time.sleep(5)
    return "timeout"


# ---------------------------------------------------------------------------- LEG 0

leg(0, "preconditions -- asserted, never assumed")
try:
    with urllib.request.urlopen(HUB + "/health", timeout=10) as _r:
        health, hcode = _r.read().decode(), _r.status
except Exception as _e:  # noqa: BLE001
    health, hcode = str(_e), 0
ok("the drive Hub answers /health", hcode == 200, f"{hcode} {health}")
BASE_PROJECTS = project_count()
note("projects before the drive", BASE_PROJECTS)
ok("the fixture project exists", bool(P))
ok("the doomed project exists (leg 3 deletes it)", bool(P_DOOMED))
DOOMED_TICKET_CODE, DOOMED_TICKET = project_ticket(P_DOOMED)
ok("a ticket can be minted for the doomed project", DOOMED_TICKET_CODE == 200 and bool(DOOMED_TICKET))


# ---------------------------------------------------------------------------- LEG 1

leg(1, "the pipeline, end to end -- one write, two streams, two read routes")

inst = instance_stream().open()
ok("the instance operator stream opens with the bearer credential", inst.status == 200,
   f"{inst.status} {inst.error}")
tcode, ticket = project_ticket(P)
proj = project_stream(P, ticket or "").open()
ok("the project stream opens with a minted ticket", proj.status == 200,
   f"{proj.status} {proj.error}")
time.sleep(1.0)
ok("each stream's first frame is `connected`",
   inst.frames and proj.frames and inst.frames[0][0] == "connected" and proj.frames[0][0] == "connected",
   f"inst={inst.names()[:2]} proj={proj.names()[:2]}")

MARK = f"row16-mark-{TAG}"
code, _ = push_log(MARK, {"note": "leg 1", "project_id": "proj-FORGED"}, agent="system")
ok("POST /logs accepts an event", code == 201, str(code))

hit_i = inst.wait_for(lambda f: f[0] == "log_event" and isinstance(f[1], dict)
                      and f[1].get("event_type") == MARK, timeout=15)
hit_p = proj.wait_for(lambda f: f[0] == "log_event" and isinstance(f[1], dict)
                      and f[1].get("event_type") == MARK, timeout=15)
ok("the write reaches the instance stream", hit_i is not None)
ok("the write reaches the project stream", hit_p is not None)
if hit_i:
    ok("the instance envelope is stamped with the project that produced it",
       hit_i[1].get("project_id") == P, json.dumps(hit_i[1])[:200])
    ok("the forged project_id inside `data` did not become the envelope's",
       hit_i[1].get("data", {}).get("project_id") == "proj-FORGED"
       and hit_i[1].get("project_id") == P, json.dumps(hit_i[1])[:200])
if hit_p:
    ok("the project stream's envelope carries no project_id (it does not need one)",
       "project_id" not in hit_p[1], json.dumps(hit_p[1])[:200])

code, rows = api("GET", f"{A}/logs?event_type={MARK}")
ok("GET /logs retrieves the row it wrote", code == 200 and isinstance(rows, list) and len(rows) >= 1,
   f"{code} {str(rows)[:200]}")
code, hist = api("GET", f"{A}/events/history?limit=500")
ok("GET /events/history carries it too",
   code == 200 and any(h.get("type") == MARK for h in (hist or [])), str(code))


# ---------------------------------------------------------------------------- LEG 2

leg(2, "the allowlist -- what the served client will act on")

served, bundle_name = served_allowlist()
src = source_allowlist()
note("served bundle", bundle_name)
note("allowlist size (served / source)", f"{len(served)} / {len(src)}")
ok("the served bundle's allowlist matches the source's, member for member",
   served == src, f"only-served={sorted(served - src)} only-source={sorted(src - served)}")

bcast = broadcast_types()
note("event names broadcast from hub/hub (literal)", len(bcast))
DROPPED = sorted(set(bcast) - served - {"job_id"})
note("broadcast but NOT on the served allowlist", f"{len(DROPPED)}: {DROPPED}")
ok("every broadcast name is on the allowlist the client filters with",
   not DROPPED, f"{len(DROPPED)} dropped: {DROPPED}")

# The sharper half: names the client has WRITTEN HANDLING FOR and still discards.
ui_files = []
for root, _dirs, files in os.walk(UI_SRC):
    if "__tests__" in root:
        continue
    for fn in files:
        if fn.endswith((".ts", ".tsx")) and fn != "useSSE.ts":
            path = os.path.join(root, fn)
            ui_files.append((os.path.relpath(path, UI_SRC).replace("\\", "/"),
                             open(path, encoding="utf-8", errors="replace").read()))
handled = {}
for name in DROPPED:
    hits = [rel for rel, text in ui_files if f"'{name}'" in text or f'"{name}"' in text]
    if hits:
        handled[name] = hits
for name, hits in sorted(handled.items()):
    note(f"handled in the UI yet never dispatched: {name}", ", ".join(hits))
ok("no dropped event name has UI code written to handle it",
   not handled, f"{len(handled)} do: {sorted(handled)}")

ck = open(os.path.join(UI_SRC, "api", "checkpoints.ts"), encoding="utf-8").read()
ok("useCheckpoints' SSE subscription can fire at all",
   not ("checkpoint_ready" in ck and "checkpoint_ready" not in served),
   "useCheckpoints listens for checkpoint_ready / conversation_cut_over; neither is on the "
   "allowlist, so the listener is never called")


# ---------------------------------------------------------------------------- LEG 3

leg(3, "the drop, driven -- real broadcasts of dropped names, on the wire")

i0, p0 = len(inst.frames), len(proj.frames)

code, job = api("POST", f"{A}/jobs", {
    "name": f"row16-job-{TAG}", "cron": "0 4 * * *",
    "agent": SCRIBE, "message": "never fires -- created disabled", "enabled": False,
})
ok("a disabled job can be created", code in (200, 201), f"{code} {str(job)[:200]}")
JOB_ID = (job or {}).get("id") if isinstance(job, dict) else None
if JOB_ID:
    code, _ = api("PATCH", f"{A}/jobs/{JOB_ID}", {"message": f"still disabled {TAG}"})
    ok("the job can be edited (the control: `job_updated` IS on the allowlist)", code == 200, str(code))
    code, _ = api("POST", f"{A}/jobs/{JOB_ID}/archive")
    ok("the job can be archived", code in (200, 204), str(code))

code, _ = api("DELETE", f"/projects/{P_DOOMED}")
ok("the doomed project is deleted", code in (200, 204), str(code))

time.sleep(2.0)
seen = inst.names(i0)
note("names on the instance wire during leg 3", seen)
for name in ("job_updated", "job_archived", "project_deleted"):
    arrived = name in seen
    ok(f"`{name}` crossed the wire", arrived, f"saw {seen}")
    if arrived:
        ok(f"`{name}` survives the served client's filter and can reach a screen",
           name in served, "delivered to the client and discarded before any listener")

dropped_now = [n for n in seen if n not in served and n != "connected"]
note("frames delivered to the client and discarded before any listener", dropped_now)
ok("the client's own filter kept every frame this leg produced", not dropped_now, str(dropped_now))

P_DOOMED_GONE = P_DOOMED


# ---------------------------------------------------------------------------- LEG 4

leg(4, "the Logs screen's own request, on a project with more than 500 events")

code, before = api("GET", f"{A}/logs?limit=500")
BASE_ROWS = len(before) if isinstance(before, list) else -1
note("rows the Logs screen's request returns now", BASE_ROWS)

pusher = Pusher(P)
BULK = f"row16-bulk-{TAG}"
need = max(0, 520 - BASE_ROWS) + 40
t0 = time.time()
statuses = {pusher.push(BULK, {"i": i}) for i in range(need)}
NEWEST = f"row16-newest-{TAG}"
last_status = pusher.push(NEWEST, {"note": "the newest event in the project"})
pusher.close()
note(f"pushed {need + 1} events in", f"{time.time() - t0:.1f}s  statuses={statuses | {last_status}}")

code, rows = api("GET", f"{A}/logs?limit=500")
ok("the Logs screen's request answers 200", code == 200, str(code))
types = [r.get("event_type") for r in rows] if isinstance(rows, list) else []
note("rows returned / first / last", f"{len(types)} / {types[:1]} / {types[-1:]}")
ok("the newest event is somewhere in what the Logs screen renders", NEWEST in types,
   f"{len(types)} rows, newest returned = {types[-1] if types else None}")

code, hist = api("GET", f"{A}/events/history?limit=100")
htypes = [h.get("type") for h in (hist or [])]
ok("`/events/history` — the same table, the other route — does carry the newest",
   NEWEST in htypes, f"{len(htypes)} rows, last={htypes[-1:]}")

code, rows2 = api("GET", f"{A}/logs?limit=500&event_type={NEWEST}")
ok("the newest event IS retrievable when the window is narrowed by a filter",
   code == 200 and isinstance(rows2, list) and len(rows2) >= 1, f"{code} {str(rows2)[:120]}")

# The same question asked of projects this harness did not create, so the condition cannot be
# dismissed as synthetic. `proj-5e960453` and `proj-18e5d4e0` are never *driven* — the standing
# limit — so for those the route's own query is mirrored read-only in SQL instead of requested,
# which is sound only because the API and the mirror were just shown to agree on the fixture.
PROTECTED = ("proj-5e960453", "proj-18e5d4e0")
busy = db_rows(
    "SELECT project_id, COUNT(*) AS n, MAX(timestamp) AS newest FROM event_logs "
    "WHERE project_id != ? GROUP BY project_id HAVING n > 500 ORDER BY n DESC", (P,)
)
note("other projects on this instance holding more than 500 events", len(busy))
for row in busy:
    other, n, newest = row["project_id"], row["n"], row["newest"]
    if other in PROTECTED:
        mirror = db_rows(
            "SELECT timestamp FROM event_logs WHERE project_id = ? ORDER BY timestamp ASC "
            "LIMIT 500", (other,)
        )
        last, how = (mirror[-1]["timestamp"] if mirror else None), "mirrored in SQL, not requested"
    else:
        _, orows = api("GET", f"/projects/{other}/logs?limit=500")
        last, how = (orows[-1]["timestamp"] if isinstance(orows, list) and orows else None), "requested"
    note(f"{other} ({n} events, {how})", f"screen ends {last}, newest is {newest}")
    ok(f"the Logs screen of {other} can reach its own newest event",
       bool(last) and str(last)[:16] >= str(newest)[:16],
       f"screen ends {last}, project's newest is {newest}")

# ---------------------------------------------------------------------------- LEG 5

leg(5, "`since` -- the filter the live view pages with")

code, all_rows = api("GET", f"{A}/logs?limit=5&event_type={NEWEST}")
anchor = all_rows[0]["timestamp"] if isinstance(all_rows, list) and all_rows else None
note("anchor timestamp", anchor)

code, bad = api("GET", f"{A}/logs?limit=500&since=not-a-timestamp")
ok("a malformed `since` is refused rather than silently ignored",
   code >= 400 or (isinstance(bad, list) and len(bad) == 0),
   f"{code}, {len(bad) if isinstance(bad, list) else '?'} rows returned as though no filter was asked for")

code, future = api("GET", f"{A}/logs?limit=500&since=2099-01-01T00:00:00")
ok("a `since` in the future returns nothing", code == 200 and isinstance(future, list)
   and not future, f"{code} {len(future) if isinstance(future, list) else '?'}")

if anchor:
    aware = urllib.parse.quote("2026-01-01T00:00:00+01:00", safe="")
    naive = urllib.parse.quote("2026-01-01T00:00:00", safe="")
    code_a, rows_a = api("GET", f"{A}/logs?limit=500&since={aware}")
    code_n, rows_n = api("GET", f"{A}/logs?limit=500&since={naive}")
    na = len(rows_a) if isinstance(rows_a, list) else -1
    nn = len(rows_n) if isinstance(rows_n, list) else -1
    note("rows for the same instant, offset-aware vs naive", f"{na} vs {nn}")
    ok("the same instant written two legal ISO ways gives the same answer", na == nn,
       f"aware={na} naive={nn}")

    exact = urllib.parse.quote(anchor, safe="")
    code_e, rows_e = api("GET", f"{A}/logs?limit=500&since={exact}&event_type={NEWEST}")
    ne = len(rows_e) if isinstance(rows_e, list) else -1
    note("`since` set to a row's own timestamp returns that row", f"{ne} rows (strict > excludes it)")


# ---------------------------------------------------------------------------- LEG 6

leg(6, "a subscriber that stops reading -- the 256-deep queue and what it says when it drops")

parts = urllib.parse.urlparse(HUB)
sock = socket.create_connection((parts.hostname, parts.port), timeout=10)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 512)
req = (
    f"GET /api/v1/events HTTP/1.1\r\nHost: {parts.hostname}:{parts.port}\r\n"
    f"Authorization: Bearer {KEY}\r\nAccept: text/event-stream\r\n\r\n"
)
sock.sendall(req.encode())
time.sleep(1.5)  # let the subscription register before anything is broadcast

SLOW = f"row16-slow-{TAG}"
BURST = 3000
pusher = Pusher(P)
t0 = time.time()
for i in range(BURST):
    pusher.push(SLOW, {"i": i})
pusher.close()
note(f"burst of {BURST} events pushed in", f"{time.time() - t0:.1f}s")

time.sleep(2.0)
sock.settimeout(4)
buf = b""
try:
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
except (socket.timeout, TimeoutError, OSError):
    pass
sock.close()
text = buf.decode("utf-8", "replace")
received = text.count(f'"{SLOW}"')
note("events of the burst the stalled subscriber eventually received", f"{received}/{BURST}")
ok("nothing was silently dropped for the slow subscriber, or the gap was signalled",
   received >= BURST or ("id:" in text) or ("dropped" in text.lower()),
   f"{BURST - received} of {BURST} lost; wire carries no `id:` field and no gap marker "
   f"({'no id: lines' if 'id:' not in text else 'has id: lines'})")

code, rows = api("GET", f"{A}/logs?limit=500&event_type={SLOW}")
persisted = len(rows) if isinstance(rows, list) else -1
note("the same burst, as persisted rows", f"{persisted} (capped by limit=500)")
ok("a client that lost events can at least tell that it did",
   received >= BURST, "the stream carries no sequence, so a gap is indistinguishable from quiet")


# ---------------------------------------------------------------------------- LEG 7

leg(7, "one real turn -- every event type it puts on the wire, classified")

i0 = len(inst.frames)
run_id, why = trigger(SCRIBE, f"Reply with exactly: row16 ack {TAG}. Do not use any tools.")
ok("a real Haiku turn starts", run_id is not None, why)
if run_id:
    final = wait_run(run_id)
    ok("the turn reaches a terminal status", final in ("completed", "failed", "stopped"), final)
    time.sleep(2.0)
    during = inst.names(i0)
    kinds = sorted(set(during))
    note("frames during the turn", f"{len(during)} frames, {len(kinds)} kinds")
    note("kinds", kinds)
    invisible = sorted(k for k in kinds if k not in served and k != "connected")
    note("kinds the served client discards", invisible)
    ok("every event kind a real turn produces can reach a screen", not invisible, str(invisible))

    rows = db_rows(
        "SELECT id FROM conversations WHERE project_id = ? ORDER BY created_at DESC LIMIT 1", (P,)
    )
    if rows:
        conv = rows[0]["id"]
        i1 = len(inst.frames)
        code, _ = api("PATCH", f"{A}/agent/{SCRIBE}/conversations/{conv}",
                      {"title": f"row16 renamed {TAG}"})
        time.sleep(1.5)
        after = inst.names(i1)
        note(f"renaming a conversation put on the wire ({code})", after)
        if "conversation_updated" in after:
            ok("`conversation_updated` reaches a screen", "conversation_updated" in served,
               "broadcast, and discarded by the served client's filter")


# ---------------------------------------------------------------------------- LEG 8

leg(8, "attribution and severity on the write route")

GHOST = f"ghost-{TAG}"
code, _ = push_log(f"row16-ghost-{TAG}", {"note": "no such agent"}, agent=GHOST)
ok("POST /logs accepts an agent name that is on no roster", code == 201, str(code))
code, agents = api("GET", f"{A}/logs/agents")
ok("the Logs screen's agent filter then offers the name that does not exist",
   not (isinstance(agents, list) and GHOST in agents),
   f"/logs/agents offers {GHOST}: {isinstance(agents, list) and GHOST in agents}")

code, _ = push_log(f"row16-sev-{TAG}", {"note": "severity"}, severity="banana")
note("POST /logs with severity=banana", code)
rows = db_rows(
    "SELECT severity FROM event_logs WHERE project_id = ? AND event_type = ?",
    (P, f"row16-sev-{TAG}"),
)
note("stored severity", rows[0]["severity"] if rows else "no row")
ok("an unknown severity is refused or normalised to a known one",
   code >= 400 or (rows and rows[0]["severity"] in ("info", "warn", "error", "debug")),
   f"stored as {rows[0]['severity'] if rows else '?'}")

code, filtered = api("GET", f"{A}/logs?limit=10&severity=banana")
ok("filtering by a severity that cannot exist says so rather than answering an empty list",
   code >= 400, f"{code}, {len(filtered) if isinstance(filtered, list) else '?'} rows")


# ---------------------------------------------------------------------------- LEG 9

leg(9, "the SSE ticket -- what it still unlocks")

code, body = api("GET", f"/projects/{P_DOOMED_GONE}/events/ticket")
ok("a ticket cannot be minted for a project that no longer exists", code == 404, str(code))

s = project_stream(P_DOOMED_GONE, DOOMED_TICKET or "").open()
ok("a ticket minted before the project was deleted no longer opens its stream",
   s.status in (401, 403, 404), f"status={s.status} {s.error}")
s.close()

hdr = Stream(f"{HUB}/api/v1/projects/{P_DOOMED_GONE}/events",
             {"Authorization": "Bearer " + KEY}).open()
ok("the header path refuses the deleted project (the contrast)", hdr.status == 404,
   f"status={hdr.status}")
hdr.close()

_, other = project_ticket(P)
s = Stream(f"{HUB}/api/v1/projects/{P_DOOMED_GONE}/events?token={urllib.parse.quote(other or '', safe='')}").open()
ok("a ticket bound to one project is refused on another's stream", s.status == 401,
   f"status={s.status}")
s.close()

s = Stream(f"{HUB}/api/v1/events?token={urllib.parse.quote(other or '', safe='')}").open()
ok("a project ticket is refused on the instance stream", s.status == 401, f"status={s.status}")
s.close()

s = Stream(f"{HUB}/api/v1/events?token={urllib.parse.quote(KEY, safe='')}").open()
ok("a raw API key in ?token= is refused on the instance stream", s.status == 401,
   f"status={s.status}")
s.close()

code, ot = api("GET", "/events/ticket")
otok = (ot or {}).get("token") if isinstance(ot, dict) else None
ok("an operator ticket can be minted", code == 200 and bool(otok), str(code))
s = Stream(f"{HUB}/api/v1/projects/{P}/events?token={urllib.parse.quote(otok or '', safe='')}").open()
ok("an operator ticket is refused on a project stream", s.status == 401, f"status={s.status}")
s.close()
s = Stream(f"{HUB}/api/v1/events?token={urllib.parse.quote(otok or '', safe='')}").open()
ok("an operator ticket opens the instance stream", s.status == 200, f"status={s.status}")
s.close()


# ---------------------------------------------------------------------------- LEG 10

leg(10, "cleanliness")

inst.close()
proj.close()

_, jobs = api("GET", f"{A}/jobs")
job_rows = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs") or []
enabled = [j.get("name") for j in job_rows if j.get("enabled")]
ok("no job is left enabled", not enabled, str(enabled))

r = git(DIR, "status", "--porcelain")
# `.agentweave/` is the Hub's own project marker, written by `POST /projects/open`. It is the
# product's, not this harness's, and it is gitignored inside a real project.
stray = [ln for ln in r.stdout.splitlines() if ".agentweave" not in ln]
ok("the fixture working tree is clean", not stray, str(stray)[:200])

note("projects now (doomed deleted by leg 3)", project_count())
orphans = db_rows(
    "SELECT COUNT(*) AS n FROM event_logs WHERE project_id = ?", (P_DOOMED_GONE,)
)
note("event_logs rows still pointing at the deleted project", orphans[0]["n"] if orphans else "?")

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL " + f)
