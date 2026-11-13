"""Acceptance drive for `ask-any-agent-for-a-dashboard-and-get-one-that-stays` (spdoc-0d8c0e384a38).

The change's `acceptance-drive` task (AAADG-1), written and recorded failing on today's code before
anything of the feature is built; the change's last task (`run-acceptance-drive`) runs it green.
It checks every acceptance criterion of the document, each as its own check, and ends by printing
one line per check in the drive-baseline form the Hub reads:

    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>

A missing route or tool never stops a check early: each check computes its hand-written reference
first and then compares what the Hub answered with it, so on today's code every check reaches its
assertion and fails there, with the detail naming the missing route or tool.

Two parts, both by default:

  main        Starts its own Hub from this checkout on a free port with a throwaway database and
              bootstrap key (never :8000, never the shared trial :8010), with the real `claude` on
              PATH; the analyst agent is bound to Haiku. Seeds two projects with spec documents,
              tasks, runs, usage, send-backs and reviews, trace spans and agent output (documents
              and projects through the Hub's routes; the rest written into the drive's own database,
              since runs and usage cannot be made by hand through the API). Then every criterion
              except ac-responsive, four Haiku turns, two Hub restarts, and a browser step.
  responsive  ac-responsive (FR-14): a copy of the operator's database taken with SQLite's backup
              API from a `mode=ro` source (the source is never written, and :8000 is never
              contacted), migrated to this checkout's head, with its jobs, loops and queued input
              switched off. A Hub from this checkout serves the copy in this process (uvicorn,
              lifespan off), beside a 10 ms lag probe on the same event loop. A regular-expression
              query over every trace span of the project with the most spans and a query that runs
              into the time limit run together while GET /agents is issued every 200 ms. Prints the
              regex query's time, the worst stall and the worst GET /agents time.

    py -3.11 scripts/drive/dashboards_drive.py                      # both parts
    py -3.11 scripts/drive/dashboards_drive.py --part main [--no-browser]
    py -3.11 scripts/drive/dashboards_drive.py --part responsive [--source-db <path>]

Exit 0 only when every check passes. AW_DRIVE_KEEP=1 leaves the main part's Hub running.

THE CONTRACT this drive assumes (the document's design; a build that names something differently
changes this file, not the spec). Routes under /api/v1/projects/{project_id}:
  GET  /dashboards/query-reference   {"tables": [{"name", "description"|"meaning",
                                       "columns": [{"name", "type", "description"|"meaning"}]}]}
  POST /dashboards/query {"sql"}     {"columns", "rows", "row_count", "truncated", "elapsed_ms"};
                                     422 {"detail": {"code": not_queryable|read_only|timeout|
                                     query_error, "message"}}
  GET  /dashboards                   a list (or {"dashboards": [...]}) of {id, name, author,
                                     created_at, updated_at, ...}
  POST /dashboards {name, description, panels}   409 dashboard_name_taken,
                                     422 {"detail": {"code": "invalid_chart_kind"}}
  GET  /dashboards/{id}, PUT /dashboards/{id}, DELETE /dashboards/{id}
  GET  /dashboards/{id}/run          {"panels": [{"id", "title", "kind", "columns", "rows",
                                     "truncated", "error", "warning"}], ...}
  Panel {"id": "pnl-<12 hex>", "title", "query", "kind": number|table|bar|stacked_bar|line}.
  Regular expressions are SQLite's REGEXP operator: `text REGEXP 'pattern'`.
  Agent tools: dashboard_query_reference, run_dashboard_query(sql), save_dashboard(name,
  description, panels, dashboard_id=""), list_dashboards, read_dashboard(dashboard_id).

The screen's test ids (fixed here for the dashboards-screen task; the project page is reached as
`/?project=<id>&tab=dashboards`):
  dashboards-list                    the list
  dashboard-row                      one per dashboard (data-dashboard-id), showing name, author, date;
                                     clicking it opens the dashboard
  dashboard-view                     the open dashboard (data-dashboard-id)
  dashboard-refresh                  runs every query again
  dashboard-fetched-at               when its data was fetched (data-fetched-at, ISO 8601)
  dashboard-delete                   deletes the open dashboard (a native confirm is accepted; a
                                     `dashboard-delete-confirm` button, if shown, is clicked)
  dashboard-panel                    one per panel (data-panel-id, data-kind), holding at most one of
                                     dashboard-panel-error / dashboard-panel-warning, and when drawn
                                     an <svg>, a <table>, or dashboard-number (the single number)
  dashboard-table-cell               a table panel's cell, holding the value in full
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
STAMP = time.strftime("%Y%m%d-%H%M%S")
TMP = pathlib.Path(tempfile.gettempdir()) / "drive-dashboards" / STAMP
DB = TMP / "hub" / "agentweave.db"
SHOTS = TMP / "shots"
KEY = "aw_live_" + secrets.token_hex(16)
FORBIDDEN_PORTS = {8000, 8010}
OPERATOR_DB = pathlib.Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"
HAIKU = "claude-haiku-4-5-20251001"
ANALYST = "analyst"
KINDS = ("number", "table", "bar", "stacked_bar", "line")
TOOLS = ("dashboard_query_reference", "run_dashboard_query", "save_dashboard", "list_dashboards",
         "read_dashboard")
REGEX_MARKER = "MARK-7731-ZEBRA"
REGEX = "MARK-[0-9]{4}-ZEBRA"
FULL_MARKER = "FULLVALUE-END-4417"
SECRET = "drivesecret" + secrets.token_hex(6)
#: What the document says is never queryable (FR-3), as the queries an agent would write.
FORBIDDEN_QUERIES = {
    "api_keys": "select * from api_keys",
    "operator_credentials": "select * from operator_credentials",
    "capability_token_hash": "select capability_token_hash from runs",  # run tokens
    "otlp_headers": "select otlp_headers from trace_settings",  # the trace exporter's headers
    "working_directory": "select working_directory from projects",  # the project directory
    "workspace_dir": "select workspace_dir from runs",  # run workspaces
    "workspace_fingerprints": "select * from workspace_fingerprints",
}
FORBIDDEN_TABLES = {"api_keys", "operator_credentials", "workspace_fingerprints"}
FORBIDDEN_COLUMNS = {"capability_token_hash", "otlp_headers", "working_directory", "workspace_dir"}
QUERY_TIMEOUT_S = 10
MAX_ROWS = 10000
STALL_LIMIT_MS = 100
AGENTS_LIMIT_MS = 500

PORT = 0
HUB = ""


def p(*a: Any) -> None:
    print(*a, flush=True)


# ------------------------------------------------------------------------------------------ checks


class Check:
    """One acceptance criterion. `judge` is its assertion; an exception before the first `judge`
    leaves it not reached, which the baseline reports as such."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.reached = False
        self.ok = True
        self.details: List[str] = []

    def judge(self, label: str, ok: Any, detail: str = "") -> bool:
        self.reached = True
        ok = bool(ok)
        if not ok:
            self.ok = False
        p(("  PASS " if ok else "  FAIL ") + f"[{self.key}] {label}" + (f" -- {detail}" if detail else ""))
        if not ok:
            self.details.append(f"{label}: {detail}"[:600])
        return ok

    def note(self, text: str) -> None:
        self.details.append(text[:600])


CHECKS: Dict[str, Check] = {}


def run_check(key: str, fn: Callable[[Check], None]) -> Check:
    check = CHECKS.setdefault(key, Check(key))
    p(f"\n== {key}")
    try:
        fn(check)
    except Exception as exc:  # noqa: BLE001 -- a check that blows up is reported, the drive goes on
        tb = traceback.format_exc(limit=3)
        p(f"  ERROR [{key}] {exc!r}\n{tb}")
        check.ok = False
        check.note(f"raised {exc!r}")
    return check


# ----------------------------------------------------------------------------------------- the Hub


def api(method: str, path: str, body: Any = None, timeout: float = 120, base: Optional[str] = None
        ) -> Tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        (base or HUB) + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            try:
                return response.status, json.loads(raw or b"null")
            except ValueError:
                return response.status, raw.decode(errors="replace")[:4000]
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")[:8000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return 0, str(exc)


def said(code: int, out: Any, limit: int = 300) -> str:
    """A short account of an answer, naming a missing route as such."""
    text = json.dumps(out)[:limit] if not isinstance(out, str) else out[:limit]
    if code == 404 and "Not Found" in text:
        return "404 Not Found -- the route does not exist on this Hub"
    return f"{code} {text}"


def detail_code(out: Any) -> Optional[str]:
    if isinstance(out, dict):
        detail = out.get("detail")
        if isinstance(detail, dict):
            return detail.get("code")
        return out.get("code")
    return None


def free_port() -> int:
    while True:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in FORBIDDEN_PORTS:
            return port


def poll(fn: Callable[[], Any], secs: float, every: float = 1.0) -> Any:
    end = time.time() + secs
    while time.time() < end:
        try:
            value = fn()
            if value:
                return value
        except Exception:  # noqa: BLE001 -- not there yet
            pass
        time.sleep(every)
    return None


class SubprocessHub:
    """A Hub from this checkout on its own port and database, restartable on the same ones."""

    def __init__(self) -> None:
        global PORT, HUB
        PORT = free_port()
        HUB = f"http://127.0.0.1:{PORT}"
        self.proc: Optional[subprocess.Popen] = None
        self.starts = 0

    def start(self) -> None:
        DB.parent.mkdir(parents=True, exist_ok=True)
        # A drive run inside an agent turn inherits that turn's HUB_URL and credentials; the scratch
        # Hub's agents would otherwise call the other Hub.
        env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
        env["AW_BOOTSTRAP_API_KEY"] = KEY
        self.starts += 1
        log = open(TMP / f"hub-{self.starts}.log", "w", encoding="utf-8")  # noqa: SIM115
        self.proc = subprocess.Popen(
            ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
            cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 180):
            self.stop()
            raise SystemExit(f"setup error: the Hub did not come up; see {TMP / f'hub-{self.starts}.log'}")
        p(f"Hub {self.starts} up on :{PORT} from {REPO / 'hub'} over {DB}")

    def stop(self) -> None:
        if self.proc is None:
            return
        subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            pass
        self.proc = None

    def restart(self) -> None:
        self.stop()
        time.sleep(2)
        self.start()


def ro(sql: str, args: Tuple = ()) -> List[Tuple]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def rw(statements: List[Tuple[str, Tuple]]) -> None:
    """Writes into the drive's own scratch database only (seeding, and runs for ac-screen)."""
    con = sqlite3.connect(DB.as_posix(), timeout=60)
    try:
        for sql, args in statements:
            con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def contract_in_checkout() -> Dict[str, Any]:
    """What this checkout declares: the agent tools (and their guidance) and the dashboard routes."""
    code = (
        "import json\n"
        "from hub import mcp_server as m\n"
        "from hub.main import app\n"
        f"tools = {list(TOOLS)!r}\n"
        "out = {'tools': {t: (m._CALLABLE_TOOLS[t].__doc__ or '') for t in tools if t in m._CALLABLE_TOOLS},\n"
        "       'routes': sorted({getattr(r, 'path', '') for r in app.routes if 'dashboard' in getattr(r, 'path', '')})}\n"
        "print('CONTRACT ' + json.dumps(out))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TMP / 'contract.db').as_posix()}"
    r = subprocess.run(["py", "-3.11", "-c", code], cwd=str(REPO / "hub"), env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("CONTRACT ")]
    if not line:
        raise RuntimeError("could not read the checkout's tools and routes: " + (r.stderr or r.stdout)[-800:])
    return json.loads(line[-1][len("CONTRACT "):])


def missing_tools(contract: Dict[str, Any], *names: str) -> List[str]:
    return [n for n in names if n not in contract["tools"]]


# ------------------------------------------------------------------------------------------ seeding


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def hexid(prefix: str, n: int = 12) -> str:
    return prefix + secrets.token_hex(n // 2)


#: Per project: its two spec documents and its tasks as
#: (document index, kind = spec_task_key, final status, build model,
#:  build runs [(seconds, usd micros)], review runs [(seconds, usd micros)], send-back reason classes).
#: Review i sends the work back while i < len(send-backs), else approves it; each build run but an
#: in-progress task's last moves the task to completed.
SEED = {
    "A": {
        "docs": ["Billing export", "Search filters"],
        "tasks": [
            (0, "query-service", "approved", "claude-opus-5-5",
             [(1800, 4_200_000), (600, 1_100_000)], [(300, 500_000), (240, 450_000)], ["defect"]),
            (0, "screen", "approved", "claude-sonnet-5-5", [(1200, 900_000)], [(200, 300_000)], []),
            (0, "drive", "completed", "claude-haiku-4-5", [(400, 80_000), (350, 70_000), (300, 60_000)],
             [(100, 90_000), (120, 95_000)], ["broken-check", "evidence-only"]),
            (1, "query-service", "in_progress", "claude-sonnet-5-5", [(2400, 1_500_000)], [], []),
            (1, "screen", "revision_needed", "claude-sonnet-5-5", [(900, 700_000)], [(150, 200_000)],
             ["regression"]),
            (1, "drive", "pending", None, [], [], []),
        ],
        "outputs_with_marker": 3,
    },
    "B": {
        "docs": ["Mobile login"],
        "tasks": [
            (0, "query-service", "approved", "claude-opus-5-5", [(5000, 9_000_000), (700, 2_000_000)],
             [(400, 600_000), (350, 550_000)], ["defect"]),
            (0, "screen", "assigned", None, [], [], []),
            (0, "drive", "approved", "claude-sonnet-5-5", [(3000, 2_500_000)], [(500, 800_000)], []),
        ],
        "outputs_with_marker": 2,
    },
}
SEEDED_TOOLS = {"A": [("seeded_grep", 3, 2.0), ("seeded_read", 2, 0.5)], "B": [("seeded_grep", 4, 9.0)]}


def seed_project(label: str, pid: str) -> None:
    spec = SEED[label]
    for title in spec["docs"]:
        path = f"spec/changes/{re.sub(r'[^a-z]+', '-', title.lower()).strip('-')}/spec.json"
        code, out = api("POST", f"/projects/{pid}/project/documents",
                        {"title": title, "kind": "change-spec", "path": path})
        if code not in (200, 201):
            raise SystemExit(f"setup error: document {title} in {label}: {said(code, out)}")
    docs = dict(ro("select title, id from spec_documents where project_id=?", (pid,)))
    doc_ids = [docs[t] for t in spec["docs"]]
    base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
    clock = [base]

    def tick(seconds: float = 30) -> datetime:
        clock[0] = clock[0] + timedelta(seconds=seconds)
        return clock[0]

    statements: List[Tuple[str, Tuple]] = []
    for n, (doc, kind, status, model, builds, reviews, sends) in enumerate(spec["tasks"]):
        task_id = hexid("task-")
        created = tick()
        statements.append((
            "insert into tasks (id, project_id, title, description, status, priority, created_at, updated, "
            "spec_document_id, spec_task_key, assignee) values (?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, pid, f"{label} {kind} {n}", "seeded by the dashboards drive", status, "medium",
             ts(created), ts(created), doc_ids[doc], kind, ANALYST if model else None)))

        def run(seconds: float, cost: int, run_model: str, agent: str) -> str:
            run_id = hexid("run-")
            start = tick()
            end = tick(seconds)
            statements.append((
                "insert into runs (id, project_id, agent, task_id, status, started_at, ended_at, initiator, "
                "capability_token_hash, workspace_dir) values (?,?,?,?,?,?,?,?,?,?)",
                (run_id, pid, agent, task_id, "completed", ts(start), ts(end), "autonomous",
                 f"{SECRET}-token-{run_id}", f"C:/{SECRET}/workspaces/{run_id}")))
            statements.append((
                "insert into turn_usage (id, run_id, project_id, agent, status, runner, model, "
                "api_equivalent_usd_micros, input_tokens, output_tokens, total_tokens, observed_at) "
                "values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (hexid("tu-"), run_id, pid, agent, "measured", "claude", run_model, cost, 1000, 200, 1200,
                 ts(end))))
            return run_id

        def move(frm: str, to: str, run_id: Optional[str], agent: str, reason: Optional[str] = None) -> None:
            statements.append((
                "insert into task_transitions (id, project_id, task_id, from_status, to_status, actor_kind, "
                "run_id, actor_agent, origin, created_at, reason_class, reason) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (hexid("tt-"), pid, task_id, frm, to, "run", run_id, agent, "actor", ts(tick(1)), reason,
                 f"seeded {reason}" if reason else None)))

        for i, (secs, cost) in enumerate(builds):
            build_run = run(secs, cost, model, "builder")
            move("assigned" if i == 0 else "revision_needed", "in_progress", build_run, "builder")
            last = i == len(builds) - 1
            if last and status == "in_progress":
                break
            move("in_progress", "completed", build_run, "builder")
            if i < len(reviews):
                review_run = run(reviews[i][0], reviews[i][1], "claude-opus-5-5", "QA")
                move("completed", "under_review", review_run, "QA")
                if i < len(sends):
                    move("under_review", "revision_needed", review_run, "QA", sends[i])
                else:
                    move("under_review", "approved", review_run, "QA")

    for n in range(spec["outputs_with_marker"]):
        statements.append((
            "insert into agent_outputs (id, project_id, agent, content, kind, timestamp) values (?,?,?,?,?,?)",
            (hexid("out-"), pid, "builder", f"line {n}: found {REGEX_MARKER} in the log", "text", ts(tick()))))
    statements.append((
        "insert into agent_outputs (id, project_id, agent, content, kind, timestamp) values (?,?,?,?,?,?)",
        (hexid("out-"), pid, "builder", "no marker here", "text", ts(tick()))))
    if label == "A":
        long = ("x" * 40 + " ") * 48
        long = (long + "y" * 2000)[: 2000 - len(FULL_MARKER)] + FULL_MARKER
        statements.append((
            "insert into agent_outputs (id, project_id, agent, content, kind, timestamp) values (?,?,?,?,?,?)",
            (hexid("out-"), pid, "builder", long, "text", ts(tick()))))

    trace = secrets.token_hex(16)
    started = tick()
    for tool, count, seconds in SEEDED_TOOLS[label]:
        for k in range(count):
            start = tick()
            end = start + timedelta(seconds=seconds)
            attrs = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool,
                     "gen_ai.tool.call.arguments": json.dumps({"pattern": f"{tool}-arg-{k}"}),
                     "gen_ai.tool.call.result": f"{tool} result {k}"}
            statements.append((
                "insert into trace_spans (span_id, trace_id, project_id, name, operation, status, start_time, "
                "end_time, ended, trace_started_at, attributes, events) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (secrets.token_hex(8), trace, pid, f"execute_tool {tool}", "execute_tool", "ok", ts(start),
                 ts(end), 1, ts(started), json.dumps(attrs), "[]")))
    statements.append((
        "insert or replace into trace_settings (project_id, otlp_endpoint, otlp_headers, export_enabled, updated_at) "
        "values (?,?,?,?,?)",
        (pid, "http://127.0.0.1:1/otlp", json.dumps({"authorization": f"Bearer {SECRET}"}), 0, ts(tick()))))
    rw(statements)
    p(f"seeded {label} ({pid}): {len(spec['tasks'])} tasks, {len(statements)} rows")


def open_project(label: str) -> Tuple[str, pathlib.Path]:
    root = TMP / f"project-{label}"
    root.mkdir(parents=True)
    (root / "README.md").write_text(f"# dashboards drive {label}\n", encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["add", "README.md"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=drive", *args],
                       cwd=root, check=True, capture_output=True)
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"dash-{label}-{STAMP}"})
    if code not in (200, 201):
        raise SystemExit(f"setup error: project {label}: {said(code, project)}")
    return project["id"], root


# --------------------------------------------------------------------------------- reference queries


def reference_tasks_by_status(pid: str) -> List[List[Any]]:
    return [list(r) for r in ro(
        "select status, count(*) as n from tasks where project_id=? group by status order by status", (pid,))]


def reference_cost_per_spec(pid: str) -> Dict[str, float]:
    """US dollars of every run on a spec's tasks, building and reviewing (the note's second trap)."""
    return {t: v for t, v in ro(
        "select d.title, sum(u.api_equivalent_usd_micros) / 1000000.0 from spec_documents d "
        "join tasks t on t.spec_document_id = d.id join runs r on r.task_id = t.id "
        "join turn_usage u on u.run_id = r.id where d.project_id = ? group by d.title", (pid,))}


def reference_send_backs_per_model(pid: str) -> Dict[str, float]:
    """Moves to revision_needed, counted under the model of the run behind the task's latest move to
    completed (as the Hub's model record attributes them)."""
    return {m: v for m, v in ro(
        "with finished as (select tt.task_id, u.model as model, max(tt.sequence) as seq "
        "  from task_transitions tt join turn_usage u on u.run_id = tt.run_id "
        "  where tt.project_id = ? and tt.to_status = 'completed' group by tt.task_id) "
        "select f.model, count(*) from task_transitions s join finished f on f.task_id = s.task_id "
        "where s.project_id = ? and s.to_status = 'revision_needed' group by f.model", (pid, pid))}


def reference_longest_kinds(pid: str) -> Dict[str, float]:
    """Per kind (spec_task_key), the average over its tasks of the seconds its runs took, building and
    reviewing; tasks with no finished run are left out."""
    return {k: v for k, v in ro(
        "with per_task as (select t.id, t.spec_task_key as kind, "
        "  sum((julianday(r.ended_at) - julianday(r.started_at)) * 86400.0) as secs "
        "  from tasks t join runs r on r.task_id = t.id "
        "  where t.project_id = ? and r.ended_at is not null and t.spec_task_key is not null group by t.id) "
        "select kind, avg(secs) from per_task group by kind", (pid,))}


def reference_spans_by_tool(pid: str) -> Dict[str, Tuple[int, float]]:
    return {n: (c, round(s, 3)) for n, c, s in ro(
        "select name, count(*), sum((julianday(end_time) - julianday(start_time)) * 86400.0) from trace_spans "
        "where project_id = ? and name like 'execute_tool seeded_%' group by name", (pid,))}


def labelled_numbers(columns: List[str], rows: List[List[Any]]) -> Dict[str, float]:
    """A panel's rows as label -> number: the first text cell, the last numeric cell; zeros dropped."""
    out: Dict[str, float] = {}
    for row in rows or []:
        cells = list(row.values()) if isinstance(row, dict) else list(row)
        label = next((c for c in cells if isinstance(c, str) and not _numeric(c)), None)
        nums = [float(c) for c in cells if _numeric(c)]
        if label is not None and nums and nums[-1] != 0:
            out[label] = nums[-1]
    return out


def _numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def same_numbers(got: Dict[str, float], want: Dict[str, float]) -> bool:
    want = {k: v for k, v in want.items() if v}
    if set(got) != set(want):
        return False
    return all(abs(got[k] - want[k]) <= max(0.011, abs(want[k]) * 0.01) for k in want)


def query(pid: str, sql: str, timeout: float = 120) -> Tuple[int, Any]:
    return api("POST", f"/projects/{pid}/dashboards/query", {"sql": sql}, timeout=timeout)


def rows_of(out: Any) -> List[List[Any]]:
    rows = out.get("rows") if isinstance(out, dict) else None
    return [list(r.values()) if isinstance(r, dict) else list(r) for r in (rows or [])]


def dashboards_list(pid: str) -> Tuple[int, List[Dict[str, Any]]]:
    code, out = api("GET", f"/projects/{pid}/dashboards")
    if isinstance(out, dict) and isinstance(out.get("dashboards"), list):
        return code, out["dashboards"]
    return code, out if isinstance(out, list) else []


def panels_of_run(out: Any) -> List[Dict[str, Any]]:
    return out.get("panels", []) if isinstance(out, dict) else []


# --------------------------------------------------------------------------------- the analyst agent


def turn(pid: str, message: str) -> Optional[str]:
    """One real Haiku turn of the analyst; waits for it to end and answers its run id."""
    code, res = api("POST", f"/projects/{pid}/agent/trigger", {"agent": ANALYST, "message": message})
    if code >= 300 or not isinstance(res, dict) or not res.get("run_id"):
        p(f"  the analyst's turn did not start: {said(code, res)}")
        return None
    run_id = res["run_id"]
    live = ("running", "queued", "starting", "pending")
    poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0] not in live, 600, 3)
    status = ro("select status from runs where id=?", (run_id,))[0][0]
    p(f"  the analyst's turn {run_id} ended {status}")
    time.sleep(3)  # the last spans land after the run row moves
    return run_id


SHIM_CALL = re.compile(r"\baw-tool\s+([A-Za-z_]+)\s+['\"]?([^\s'\"]+\.json)")
SHIM_SET_CONTENT = re.compile(
    r"Set-Content\s+-Path\s+'([^']+\.json)'\s+-Value\s+'((?:[^']|'')*)'", re.IGNORECASE)


def calls_file_key(path: str) -> Optional[str]:
    """`.agentweave/calls/<file>` of a path, absolute or relative, whichever separators it uses."""
    norm = path.replace("\\", "/").lower()
    at = norm.rfind(".agentweave/calls/")
    return norm[at:] if at >= 0 else None


def shim_result(result: Any) -> Any:
    """The call command prints `{"ok": true, "result": ...}`; answer what the tool itself returned."""
    parsed = parsed_result(result)
    if isinstance(parsed, dict) and parsed.get("ok") is True and "result" in parsed:
        inner = parsed["result"]
        return inner if isinstance(inner, str) else json.dumps(inner)
    return result


def tool_calls(run_id: Optional[str], tool: str) -> List[Dict[str, Any]]:
    """The run's calls of *tool*, as its trace recorded them: through MCP or the call command.

    A call through the call command is two spans: a write of the arguments to a file in
    `.agentweave/calls/` (the file-writing tool, or `Set-Content` from the shell), then a shell
    span running `aw-tool <tool> <file>`. Its arguments are that file's last content before the
    call, and its result is the tool's own, out of the command's `{"ok", "result"}` envelope.
    """
    if not run_id:
        return []
    calls = []
    written: Dict[str, str] = {}
    for name, attributes in ro(
            "select name, attributes from trace_spans where run_id=? and operation='execute_tool' "
            "order by start_time", (run_id,)):
        attrs = json.loads(attributes or "{}")
        args = attrs.get("gen_ai.tool.call.arguments")
        try:
            args_obj = json.loads(args) if isinstance(args, str) else args
        except ValueError:
            args_obj = None
        args_text = args if isinstance(args, str) else json.dumps(args)
        name = name.removeprefix("execute_tool ")
        result = attrs.get("gen_ai.tool.call.result") or ""
        if isinstance(args_obj, dict):
            key = calls_file_key(str(args_obj.get("file_path") or ""))
            if key and isinstance(args_obj.get("content"), str):
                written[key] = args_obj["content"]
                continue
            command = str(args_obj.get("command") or "")
            for path, value in SHIM_SET_CONTENT.findall(command):
                if calls_file_key(path):
                    written[calls_file_key(path)] = value.replace("''", "'")
            shim = SHIM_CALL.search(command)
            if shim:
                if shim.group(1) != tool:
                    continue
                key = calls_file_key(shim.group(2))
                calls.append({"name": f"aw-tool {tool}", "arguments": written.get(key or "", command),
                              "result": shim_result(result)})
                continue
        # By name only: a ToolSearch loading the tool's schema names it in its arguments too.
        if re.search(rf"(^|\s|__|[./]){re.escape(tool)}$", name):
            calls.append({"name": name, "arguments": args_text or "", "result": result})
    return calls


def parsed_result(result: Any) -> Any:
    if isinstance(result, (dict, list)):
        return result
    text = str(result or "")
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------------------------------ criteria


class Drive:
    def __init__(self, browser: bool) -> None:
        self.browser = browser
        self.hub = SubprocessHub()
        self.a = self.b = ""
        self.contract: Dict[str, Any] = {"tools": {}, "routes": []}
        self.saved_by_agent: Optional[Dict[str, Any]] = None
        self.examples_name = f"Project health {STAMP}"
        self.save_name = f"Drive save check {STAMP}"
        self.ids: Dict[str, str] = {}

    # -- setup

    def setup(self) -> None:
        TMP.mkdir(parents=True, exist_ok=True)
        self.contract = contract_in_checkout()
        p(f"checkout declares tools {sorted(self.contract['tools'])} and dashboard routes {self.contract['routes']}")
        self.hub.start()
        self.a, _ = open_project("A")
        self.b, _ = open_project("B")
        seed_project("A", self.a)
        seed_project("B", self.b)
        code, runner = api("POST", f"/projects/{self.a}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
        if code not in (200, 201):
            raise SystemExit(f"setup error: runner: {said(code, runner)}")
        code, out = api("POST", f"/projects/{self.a}/agents", {"name": ANALYST, "runner_id": runner["id"]})
        if code not in (200, 201):
            raise SystemExit(f"setup error: agent: {said(code, out)}")
        p(f"project A {self.a}, project B {self.b}, agent {ANALYST} on {HAIKU}")

    # -- FR-1

    def ac_run_query(self, c: Check) -> None:
        want = reference_tasks_by_status(self.a)
        sql = "select status, count(*) as n from tasks group by status order by status"
        code, out = query(self.a, sql)
        got_cols = out.get("columns") if isinstance(out, dict) else None
        c.judge("POST /dashboards/query answers the columns and the hand-written count",
                code == 200 and got_cols == ["status", "n"] and rows_of(out) == want,
                f"want {want}; got {said(code, out)}")
        missing = missing_tools(self.contract, "run_dashboard_query")
        run_id = turn(self.a, (
            "Use your AgentWeave tool run_dashboard_query to run exactly this SQL, once, and reply with "
            f"what it returned. Do nothing else.\n\n{sql}")) if not missing else None
        calls = [x for x in tool_calls(run_id, "run_dashboard_query") if "group by status" in x["arguments"]]
        result = parsed_result(calls[-1]["result"]) if calls else None
        c.judge("the analyst's run_dashboard_query receives the same columns and rows",
                isinstance(result, dict) and result.get("columns") == ["status", "n"] and rows_of(result) == want,
                f"want {want}; " + (f"tool missing from the checkout: {missing}" if missing else
                                    f"calls {len(calls)}; result {str(calls[-1]['result'])[:300] if calls else None}"))

    # -- FR-2

    def ac_project_only(self, c: Check) -> None:
        a_tasks = {r[0] for r in ro("select id from tasks where project_id=?", (self.a,))}
        for label, sql, cols in (
            ("tasks with no project filter", "select id, project_id from tasks", (1,)),
            ("a join of tasks and runs",
             "select t.id, t.project_id, r.project_id from tasks t join runs r on r.task_id = t.id", (1, 2)),
            ("the projects list", "select id from projects", (0,)),
        ):
            code, out = query(self.a, sql)
            rows = rows_of(out)
            foreign = [r for r in rows if any(r[i] != self.a for i in cols)]
            extra = ""
            if label.startswith("tasks"):
                extra = f"; task ids equal A's: {({r[0] for r in rows} == a_tasks)}"
            c.judge(f"{label}: rows returned, every one project A's",
                    code == 200 and rows and not foreign and (not label.startswith("tasks") or {r[0] for r in rows} == a_tasks),
                    f"{len(rows)} rows, {len(foreign)} foreign{extra}; {said(code, out, 200)}")

    # -- FR-3

    def ac_never_queryable(self, c: Check) -> None:
        for item, sql in FORBIDDEN_QUERIES.items():
            code, out = query(self.a, sql)
            text = json.dumps(out) if not isinstance(out, str) else out
            detail = out.get("detail") if isinstance(out, dict) else None
            message = str((detail or {}).get("message") or "") if isinstance(detail, dict) else ""
            c.judge(f"{item}: refused not_queryable, the message naming it, no value returned",
                    code == 422 and detail_code(out) == "not_queryable" and item in message
                    and SECRET not in text and KEY not in text,
                    said(code, out, 240))

    # -- FR-4

    def ac_read_only(self, c: Check) -> None:
        def state() -> Tuple:
            schema = ro("select type, name, sql from sqlite_master order by type, name")
            counts = tuple(ro(f"select count(*) from {t}")[0][0] for t in ("tasks", "runs", "projects"))
            return (tuple(schema), counts)

        before = state()
        attach = (TMP / "attached.db").as_posix()
        for label, sql in (
            ("insert", "insert into tasks (id, project_id, title, description, status, priority, created_at, "
                       "updated) values ('task-ro', 'x', 't', 'd', 'pending', 'low', '2026-01-01', '2026-01-01')"),
            ("update", "update tasks set title = 'changed'"),
            ("delete", "delete from runs"),
            ("drop", "drop table tasks"),
            ("attach", f"attach database '{attach}' as other"),
        ):
            code, out = query(self.a, sql)
            c.judge(f"{label} refused read_only", code == 422 and detail_code(out) == "read_only", said(code, out, 200))
        c.judge("the database is unchanged", state() == before and not pathlib.Path(attach).exists(),
                "row counts or schema moved" if state() != before else "an attached file was created")

    # -- FR-5

    def ac_regex(self, c: Check) -> None:
        want = ro("select count(*) from agent_outputs where project_id=? and content like ?",
                  (self.a, f"%{REGEX_MARKER}%"))[0][0]
        sql = f"select count(*) as n from agent_outputs where content regexp '{REGEX}'"
        code, out = query(self.a, sql)
        c.judge(f"the route counts {want} outputs matching {REGEX}",
                want == 3 and code == 200 and rows_of(out) == [[3]], f"seeded {want}; {said(code, out, 200)}")
        missing = missing_tools(self.contract, "run_dashboard_query")
        run_id = turn(self.a, (
            "Use your AgentWeave tool run_dashboard_query to count agent output lines matching the regular "
            f"expression {REGEX}. Run exactly this SQL once and reply with the number:\n\n{sql}")) if not missing else None
        calls = [x for x in tool_calls(run_id, "run_dashboard_query") if "regexp" in x["arguments"].lower()]
        result = parsed_result(calls[-1]["result"]) if calls else None
        c.judge("the analyst's regex count through run_dashboard_query is three",
                isinstance(result, dict) and rows_of(result) == [[3]],
                (f"tool missing from the checkout: {missing}" if missing else
                 f"calls {len(calls)}; result {str(calls[-1]['result'])[:300] if calls else None}"))

    def ac_traces(self, c: Check) -> None:
        want = reference_spans_by_tool(self.a)
        code, out = query(self.a, (
            "select name, count(*) as spans, sum((julianday(end_time) - julianday(start_time)) * 86400.0) as seconds "
            "from trace_spans where name like 'execute_tool seeded_%' group by name order by name"))
        got = {r[0]: (r[1], round(float(r[2]), 3)) for r in rows_of(out) if len(r) == 3 and r[2] is not None}
        c.judge("span count and total duration by tool name equal a direct count",
                code == 200 and got == want, f"want {want}; {said(code, out, 200)}")
        want_args = sorted(json.loads(a)["pattern"] for (a,) in ro(
            "select json_extract(attributes, '$.\"gen_ai.tool.call.arguments\"') from trace_spans "
            "where project_id=? and name like 'execute_tool seeded_%'", (self.a,)))
        code, out = query(self.a, (
            "select json_extract(attributes, '$.\"gen_ai.tool.call.arguments\"') as args from trace_spans "
            "where name like 'execute_tool seeded_%'"))
        got_args = sorted(json.loads(r[0])["pattern"] for r in rows_of(out) if r and r[0])
        c.judge("the text of tool arguments is the project's spans' and only theirs",
                code == 200 and got_args == want_args, f"want {len(want_args)}; {said(code, out, 200)}")

    # -- FR-6

    def ac_timeout(self, c: Check) -> None:
        start = time.time()
        code, out = query(self.a, "with recursive c(x) as (select 1 union all select x + 1 from c) "
                                  "select count(*) from c", timeout=120)
        took = time.time() - start
        c.judge(f"a query running past {QUERY_TIMEOUT_S} s is stopped with timeout",
                code == 422 and detail_code(out) == "timeout" and QUERY_TIMEOUT_S - 1 <= took <= QUERY_TIMEOUT_S + 15,
                f"after {took:.1f} s: {said(code, out, 200)}")

    def ac_row_cap(self, c: Check) -> None:
        code, out = query(self.a, f"with recursive c(x) as (select 1 union all select x + 1 from c where x < {MAX_ROWS + 50}) "
                                  "select x from c")
        ok = code == 200 and isinstance(out, dict) and out.get("row_count") == MAX_ROWS and out.get("truncated") is True \
            and len(out.get("rows") or []) == MAX_ROWS
        c.judge(f"{MAX_ROWS + 50} rows come back as {MAX_ROWS} marked truncated", ok,
                said(code, {k: v for k, v in out.items() if k != "rows"} if isinstance(out, dict) else out, 200))

    # -- FR-7

    def ac_reference(self, c: Check) -> None:
        code, out = api("GET", f"/projects/{self.a}/dashboards/query-reference")
        tables = out.get("tables") if isinstance(out, dict) else None
        c.judge("GET /dashboards/query-reference lists tables, each with typed, described columns",
                code == 200 and isinstance(tables, list) and len(tables) >= 5 and all(
                    t.get("name") and t.get("columns") and all(col.get("name") and col.get("type") and
                                                               (col.get("description") or col.get("meaning"))
                                                               for col in t["columns"]) for t in tables),
                said(code, out, 200))
        tables = tables if isinstance(tables, list) else []
        listed = {t.get("name") for t in tables}
        cols = {col.get("name") for t in tables for col in (t.get("columns") or [])}
        c.judge("nothing never-queryable is listed",
                bool(tables) and not (listed & FORBIDDEN_TABLES) and not (cols & FORBIDDEN_COLUMNS),
                f"tables {sorted(listed & FORBIDDEN_TABLES)} columns {sorted(cols & FORBIDDEN_COLUMNS)}")
        refused = []
        for t in tables:
            names = ", ".join(col["name"] for col in t.get("columns") or [])
            code, res = query(self.a, f"select {names} from {t['name']} limit 1")
            if code != 200:
                refused.append(f"{t['name']}: {said(code, res, 120)}")
        c.judge("a select over every listed table and column is answered",
                bool(tables) and not refused, "; ".join(refused[:5]) or "no tables listed")
        missing = missing_tools(self.contract, "dashboard_query_reference")
        c.judge("agents read it through dashboard_query_reference", not missing, f"tool missing from the checkout: {missing}")

    # -- FR-8

    def note_of(self, pid: str) -> Optional[Dict[str, Any]]:
        code, out = api("GET", f"/projects/{pid}/vault/map")
        for entry in (out or {}).get("entries", []) if isinstance(out, dict) else []:
            if entry.get("kind") == "fact" or str(entry.get("id", "")).startswith("fact"):
                continue
            code, full = api("GET", f"/projects/{pid}/vault/entries/{entry['id']}")
            text = (full or {}).get("content") or "" if isinstance(full, dict) else ""
            low = text.lower()
            if re.search(r"send.?back", low) and "evidence" in low and "cost per spec" in low and "review" in low:
                return {"id": entry["id"], "name": full.get("name") or entry.get("name") or "",
                        "content": text, "version": full.get("version")}
        return None

    def ac_vault_note(self, c: Check) -> None:
        a_note, b_note = self.note_of(self.a), self.note_of(self.b)
        c.judge("both projects hold the data note with both traps, before any dashboard tool is called",
                a_note is not None and b_note is not None,
                f"A {bool(a_note)} B {bool(b_note)} (a vault text source naming the send-back/evidence trap "
                "and the cost-per-spec/review trap)")
        appended = f"\nAgent addition {STAMP}: dashboards drive was here.\n"
        if a_note:
            code, out = api("PUT", f"/projects/{self.a}/vault/sources/{a_note['id']}/text",
                            {"content": a_note["content"] + appended, "version": a_note["version"]})
            p(f"  appended to A's note: {said(code, out, 120)}")
        self.hub.restart()
        a_after, b_after = self.note_of(self.a), self.note_of(self.b)
        c.judge("after a restart the note is in both and A's addition survives",
                a_after is not None and b_after is not None and appended.strip() in (a_after or {}).get("content", ""),
                f"A {bool(a_after)} B {bool(b_after)}")
        name = (a_after or a_note or {}).get("name") or ""
        docs = self.contract["tools"]
        c.judge("every dashboard tool's guidance names the note",
                bool(name) and len(docs) == len(TOOLS) and all(name in d for d in docs.values()),
                f"note name {name!r}; tools present {sorted(docs)}")

    # -- FR-9

    def ac_save(self, c: Check) -> None:
        panels = [
            {"title": "Tasks by status", "query": "select status, count(*) as n from tasks group by status", "kind": "bar"},
            {"title": "Runs", "query": "select count(*) as runs from runs", "kind": "number"},
            {"title": "Broken on purpose", "query": "select no_such_column from tasks", "kind": "table"},
        ]
        missing = missing_tools(self.contract, "save_dashboard")
        run_id = turn(self.a, (
            f"Use your AgentWeave tool save_dashboard once to save a dashboard named \"{self.save_name}\" with the "
            "description \"Drive save check\" and exactly these three panels, as given, including the third whose "
            "query is broken on purpose (do not fix or run it):\n" + json.dumps(panels, indent=1))) if not missing else None
        p(f"  save_dashboard calls: {len(tool_calls(run_id, 'save_dashboard'))}")
        code, listed = dashboards_list(self.a)
        mine = [d for d in listed if d.get("name") == self.save_name]
        before = api("GET", f"/projects/{self.a}/dashboards/{mine[0]['id']}")[1] if mine else None
        self.hub.restart()
        code, listed = dashboards_list(self.a)
        mine = [d for d in listed if d.get("name") == self.save_name]
        row = mine[0] if mine else {}
        c.judge("after a restart the dashboard is listed with its name, the agent's name and the time",
                code == 200 and row.get("author") == ANALYST and row.get("created_at"),
                (f"tool missing from the checkout: {missing}; " if missing else "") + f"list {said(code, listed, 300)}")
        code, after = api("GET", f"/projects/{self.a}/dashboards/{row.get('id', 'none')}")
        got = [(x.get("title"), x.get("query"), x.get("kind")) for x in (after or {}).get("panels", [])] \
            if isinstance(after, dict) else []
        want = [(x["title"], x["query"], x["kind"]) for x in panels]
        c.judge("its panels are unchanged by the restart, the broken one included",
                code == 200 and got == want and before == after and all(
                    re.fullmatch(r"pnl-[0-9a-f]{12}", x.get("id") or "") for x in after.get("panels", [])),
                f"want {want}; got {got}; {said(code, after, 200)}")
        self.saved_by_agent = after if isinstance(after, dict) else None

    # -- FR-10

    def ac_chart_kinds(self, c: Check) -> None:
        code, out = api("POST", f"/projects/{self.a}/dashboards", {
            "name": f"Pie {STAMP}", "description": "refused",
            "panels": [{"title": "Pie", "query": "select 1", "kind": "pie"}]})
        c.judge("a panel of another kind is refused invalid_chart_kind",
                code == 422 and detail_code(out) == "invalid_chart_kind", said(code, out, 200))
        queries = {
            "number": "select count(*) as tasks from tasks",
            "table": "select title, status from tasks order by title",
            "bar": "select status, count(*) as n from tasks group by status",
            "stacked_bar": "select status, coalesce(spec_task_key, 'none') as kind, count(*) as n from tasks group by status, kind",
            "line": "select date(started_at) as day, count(*) as runs from runs group by day order by day",
        }
        code, out = api("POST", f"/projects/{self.a}/dashboards", {
            "name": f"Every kind {STAMP}", "description": "one panel of each chart kind",
            "panels": [{"title": k, "query": q, "kind": k} for k, q in queries.items()]})
        self.ids["kinds"] = out.get("id") if isinstance(out, dict) else None
        c.judge("a dashboard with one panel of each kind is saved",
                code in (200, 201) and bool(self.ids["kinds"]), said(code, out, 200))
        code, run = api("GET", f"/projects/{self.a}/dashboards/{self.ids['kinds'] or 'none'}/run")
        bad = [x.get("kind") for x in panels_of_run(run) if x.get("error") or x.get("warning")]
        c.judge("each of the five runs clean", code == 200 and len(panels_of_run(run)) == 5 and not bad,
                f"errors/warnings on {bad}; {said(code, run, 200)}")
        if self.browser:
            self.browser_kinds(c)

    # -- FR-12

    def ac_panel_error(self, c: Check) -> None:
        code, out = api("POST", f"/projects/{self.a}/dashboards", {
            "name": f"Errors {STAMP}", "description": "one error, one warning, one working panel",
            "panels": [
                {"title": "Missing column", "query": "select no_such_column from tasks", "kind": "table"},
                {"title": "Line of words", "query": "select title from tasks", "kind": "line"},
                {"title": "Working", "query": "select count(*) as n from tasks", "kind": "number"},
            ]})
        self.ids["errors"] = out.get("id") if isinstance(out, dict) else None
        code, run = api("GET", f"/projects/{self.a}/dashboards/{self.ids['errors'] or 'none'}/run")
        panels = panels_of_run(run)
        want_n = ro("select count(*) from tasks where project_id=?", (self.a,))[0][0]
        c.judge("the run answers the error, the warning and the working panel's rows",
                code == 200 and len(panels) == 3 and panels[0].get("error") and not panels[0].get("rows")
                and panels[1].get("warning") and not panels[1].get("error")
                and not panels[2].get("error") and rows_of(panels[2]) == [[want_n]],
                said(code, run, 400))
        if self.browser:
            self.browser_errors(c)

    # -- FR-11

    def ac_examples(self, c: Check) -> None:
        missing = missing_tools(self.contract, "dashboard_query_reference", "run_dashboard_query", "save_dashboard")
        ask = (
            f"Make me a dashboard of this project named \"{self.examples_name}\" with your AgentWeave dashboard "
            "tools. Read dashboard_query_reference first, check every query with run_dashboard_query, then "
            "save it with save_dashboard. Three panels, titled exactly:\n"
            "1. \"Cost per spec\" (kind bar): for each spec document, by its title, the API-equivalent cost in "
            "US dollars of every run on that spec's tasks, building and reviewing runs both.\n"
            "2. \"QA send-backs per model\" (kind bar): the number of times a task was sent back "
            "(moved to revision_needed), counted under the model of the run behind that task's latest move to "
            "completed.\n"
            "3. \"Longest kinds of task\" (kind table): for each kind of task (the task's spec_task_key), the "
            "average over its tasks of the total seconds its runs took (ended minus started, building and "
            "reviewing runs both), longest first; tasks with no finished run are left out.\n"
            "Each panel's query returns a label column then the number.")
        run_id = turn(self.a, ask) if not missing else None
        p(f"  examples turn {run_id}: {len(tool_calls(run_id, 'save_dashboard'))} save_dashboard calls")
        code, listed = dashboards_list(self.a)
        mine = [d for d in listed if d.get("name") == self.examples_name]
        self.ids["examples"] = mine[0]["id"] if mine else None
        code, run = api("GET", f"/projects/{self.a}/dashboards/{self.ids['examples'] or 'none'}/run")
        panels = {str(x.get("title", "")).lower(): x for x in panels_of_run(run)}
        refs = {
            "cost per spec": reference_cost_per_spec(self.a),
            "qa send-backs per model": reference_send_backs_per_model(self.a),
            "longest kinds of task": reference_longest_kinds(self.a),
        }
        for title, want in refs.items():
            panel = panels.get(title) or {}
            got = labelled_numbers(panel.get("columns") or [], panel.get("rows") or [])
            c.judge(f"panel '{title}' equals the hand-written reference",
                    bool(want) and same_numbers(got, want),
                    (f"tools missing from the checkout: {missing}; " if missing else "")
                    + f"want {want}; got {got}; panel error {panel.get('error')!r}")
        if self.browser and self.ids["examples"]:
            self.browser_shot(self.ids["examples"], "examples")

    def ac_screen(self, c: Check) -> None:
        self.add_probe_runs(2)
        code, out = api("POST", f"/projects/{self.a}/dashboards", {
            "name": f"Screen {STAMP}", "description": "runs of the screen probe",
            "panels": [{"title": "Probe runs", "kind": "number",
                        "query": "select count(*) as runs from runs where agent = 'screen-probe'"}]})
        self.ids["screen"] = out.get("id") if isinstance(out, dict) else None
        c.judge("a dashboard for the screen is saved", code in (200, 201) and bool(self.ids["screen"]), said(code, out, 200))
        if not self.browser:
            c.note("browser step skipped (--no-browser)")
            return
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            page = self.page(chromium, "dark")
            opened = self.open_dashboard(page, self.ids["screen"])
            number = page.get_by_test_id("dashboard-number")
            first = poll(lambda: number.first.inner_text().strip(), 20, 0.5) if opened else None
            fetched = page.get_by_test_id("dashboard-fetched-at")
            at1 = fetched.first.get_attribute("data-fetched-at") if opened and fetched.count() else None
            c.judge("opened from the Dashboards screen, it shows the runs recorded before",
                    opened and first == "2" and bool(at1), f"opened {opened}; number {first!r}; fetched-at {at1!r}")
            self.add_probe_runs(1)
            time.sleep(1.1)
            if opened and page.get_by_test_id("dashboard-refresh").count():
                page.get_by_test_id("dashboard-refresh").first.click()
            second = poll(lambda: number.first.inner_text().strip() == "3" and "3", 20, 0.5) if opened else None
            at2 = fetched.first.get_attribute("data-fetched-at") if opened and fetched.count() else None
            c.judge("Refresh shows the new run and moves the fetched-at time",
                    second == "3" and bool(at2) and at2 != at1, f"number {second!r}; fetched-at {at1!r} -> {at2!r}")
            chromium.close()

    def ac_delete(self, c: Check) -> None:
        target = self.ids.get("screen")
        if self.browser and target:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                chromium = pw.chromium.launch()
                page = self.page(chromium, "light")
                page.on("dialog", lambda d: d.accept())
                if self.open_dashboard(page, target) and page.get_by_test_id("dashboard-delete").count():
                    page.get_by_test_id("dashboard-delete").first.click()
                    confirm = page.get_by_test_id("dashboard-delete-confirm")
                    if poll(lambda: confirm.count(), 3, 0.3):
                        confirm.first.click()
                    page.wait_for_timeout(1500)
                chromium.close()
        elif target:
            api("DELETE", f"/projects/{self.a}/dashboards/{target}")
        code, listed = dashboards_list(self.a)
        names = [d.get("name") for d in listed]
        c.judge("the deleted dashboard is gone from the list (the route the screen reads)",
                code == 200 and bool(target) and target not in [d.get("id") for d in listed],
                f"target {target}; {said(code, listed, 300)}")
        missing = missing_tools(self.contract, "list_dashboards")
        run_id = turn(self.a, "Use your AgentWeave tool list_dashboards once and reply with the names it returned. "
                              "Do nothing else.") if not missing else None
        calls = tool_calls(run_id, "list_dashboards")
        result = str(calls[-1]["result"]) if calls else ""
        c.judge("and from the agent's list_dashboards",
                bool(calls) and f"Screen {STAMP}" not in result and any(n and n in result for n in names),
                f"tool missing from the checkout: {missing}" if missing else f"calls {len(calls)}; result {result[:300]}")

    # -- FR-13

    def ac_project_delete(self, c: Check) -> None:
        code, out = api("POST", f"/projects/{self.b}/dashboards", {
            "name": f"B board {STAMP}", "description": "removed with its project",
            "panels": [{"title": "B tasks", "query": "select count(*) from tasks", "kind": "number"}]})
        before = self.dashboard_rows(self.b)
        code_del, out_del = api("DELETE", f"/projects/{self.b}")
        after = self.dashboard_rows(self.b)
        c.judge("deleting project B removes its dashboards",
                code in (200, 201) and before == 1 and code_del in (200, 204) and after == 0,
                f"save {said(code, out, 120)}; rows before {before}, delete {code_del}, rows after {after}")

    def dashboard_rows(self, pid: str) -> Any:
        try:
            return ro("select count(*) from dashboards where project_id=?", (pid,))[0][0]
        except sqlite3.OperationalError as exc:
            return f"({exc})"

    # -- FR-15

    def ac_full_values(self, c: Check) -> None:
        full = ro("select content from agent_outputs where project_id=? and content like ?",
                  (self.a, f"%{FULL_MARKER}"))[0][0]
        code, out = api("POST", f"/projects/{self.a}/dashboards", {
            "name": f"Full values {STAMP}", "description": "a 2,000-character line in a table",
            "panels": [{"title": "Long line", "kind": "table",
                        "query": f"select content from agent_outputs where content like '%{FULL_MARKER}'"}]})
        dash = out.get("id") if isinstance(out, dict) else None
        code, run = api("GET", f"/projects/{self.a}/dashboards/{dash or 'none'}/run")
        panel = (panels_of_run(run) or [{}])[0]
        c.judge("the run returns the 2,000-character value whole", len(full) == 2000 and rows_of(panel) == [[full]],
                f"{said(code, run, 200)}")
        if not self.browser:
            return
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            page = self.page(chromium, "dark")
            opened = self.open_dashboard(page, dash) if dash else False
            cell = page.get_by_test_id("dashboard-table-cell")
            text = poll(lambda: cell.first.text_content(), 15, 0.5) if opened else None
            c.judge("the rendered cell holds the whole value, marker included, unmasked",
                    bool(text) and full in text, f"opened {opened}; cell {len(text or '')} chars")
            chromium.close()

    # -- browser helpers

    def page(self, chromium: Any, scheme: str) -> Any:
        ctx = chromium.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        ctx.add_init_script(
            "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);"
            "localStorage.setItem('agentweave-theme', %r);" % (KEY, HUB, self.a, scheme))
        return ctx.new_page()

    def open_dashboard(self, page: Any, dash_id: str) -> bool:
        page.goto(f"{HUB}/?project={self.a}&tab=dashboards", wait_until="domcontentloaded")
        row = page.locator(f"[data-testid=dashboard-row][data-dashboard-id='{dash_id}']")
        if not poll(lambda: row.count(), 20, 0.5):
            p(f"  no dashboard-row for {dash_id} on the Dashboards screen")
            return False
        row.first.click()
        view = page.locator(f"[data-testid=dashboard-view][data-dashboard-id='{dash_id}']")
        return bool(poll(lambda: view.count(), 20, 0.5))

    def browser_kinds(self, c: Check) -> None:
        from playwright.sync_api import sync_playwright

        SHOTS.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            for scheme in ("light", "dark"):
                page = self.page(chromium, scheme)
                opened = self.open_dashboard(page, self.ids["kinds"]) if self.ids.get("kinds") else False
                panels = page.get_by_test_id("dashboard-panel")
                drawn = []
                if opened:
                    poll(lambda: panels.count() == 5, 20, 0.5)
                    page.wait_for_timeout(1500)
                    for i in range(panels.count()):
                        panel = panels.nth(i)
                        if panel.locator("svg, table, [data-testid=dashboard-number]").count() and not \
                                panel.locator("[data-testid=dashboard-panel-error], [data-testid=dashboard-panel-warning]").count():
                            drawn.append(panel.get_attribute("data-kind"))
                    page.screenshot(path=str(SHOTS / f"kinds-{scheme}.png"), full_page=True)
                c.judge(f"in the {scheme} theme each of the five kinds draws (screenshot for the operator)",
                        sorted(drawn) == sorted(KINDS), f"opened {opened}; drawn {drawn}; shot {SHOTS / f'kinds-{scheme}.png'}")
            chromium.close()

    def browser_errors(self, c: Check) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            page = self.page(chromium, "dark")
            opened = self.open_dashboard(page, self.ids["errors"]) if self.ids.get("errors") else False
            panels = page.get_by_test_id("dashboard-panel")
            ok = False
            if opened and poll(lambda: panels.count() == 3, 20, 0.5):
                page.wait_for_timeout(1000)
                ok = (panels.nth(0).get_by_test_id("dashboard-panel-error").count() == 1
                      and panels.nth(1).get_by_test_id("dashboard-panel-warning").count() == 1
                      and panels.nth(2).get_by_test_id("dashboard-number").count() == 1)
            c.judge("on the screen: the error, the warning saying why, and the working panel drawn", ok,
                    f"opened {opened}; panels {panels.count() if opened else 0}")
            chromium.close()

    def browser_shot(self, dash_id: str, name: str) -> None:
        from playwright.sync_api import sync_playwright

        SHOTS.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            chromium = pw.chromium.launch()
            page = self.page(chromium, "dark")
            if self.open_dashboard(page, dash_id):
                page.wait_for_timeout(2000)
                page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)
                p(f"  screenshot {SHOTS / f'{name}.png'}")
            chromium.close()

    def add_probe_runs(self, n: int) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rw([("insert into runs (id, project_id, agent, status, started_at, ended_at, initiator) values (?,?,?,?,?,?,?)",
             (hexid("run-"), self.a, "screen-probe", "completed", ts(now), ts(now + timedelta(seconds=5)), "operator"))
            for _ in range(n)])

    # -- order

    def run(self) -> None:
        try:
            self.setup()
            # The vault note must be seen before any dashboard tool is called, and it restarts the Hub.
            run_check("ac-vault-note", self.ac_vault_note)
            run_check("ac-run-query", self.ac_run_query)
            run_check("ac-project-only", self.ac_project_only)
            run_check("ac-never-queryable", self.ac_never_queryable)
            run_check("ac-read-only", self.ac_read_only)
            run_check("ac-regex", self.ac_regex)
            run_check("ac-traces", self.ac_traces)
            run_check("ac-timeout", self.ac_timeout)
            run_check("ac-row-cap", self.ac_row_cap)
            run_check("ac-reference", self.ac_reference)
            run_check("ac-save", self.ac_save)
            run_check("ac-chart-kinds", self.ac_chart_kinds)
            run_check("ac-panel-error", self.ac_panel_error)
            run_check("ac-examples", self.ac_examples)
            run_check("ac-screen", self.ac_screen)
            run_check("ac-delete", self.ac_delete)
            run_check("ac-full-values", self.ac_full_values)
            run_check("ac-project-delete", self.ac_project_delete)
        finally:
            if os.environ.get("AW_DRIVE_KEEP"):
                p(f"AW_DRIVE_KEEP: Hub left on {HUB}, key {KEY}, database {DB}")
            else:
                self.hub.stop()


# --------------------------------------------------------------------------------- ac-responsive


def copy_operator_database(source: pathlib.Path, scratch: pathlib.Path) -> pathlib.Path:
    """The source read through `mode=ro` with SQLite's backup API (never copied as a file: under WAL a
    copy of the .db alone can omit commits), migrated to this checkout's head, scheduling off."""
    if not source.exists():
        raise RuntimeError(f"the source database {source} does not exist")
    dst = scratch / "operator-copy.db"
    if dst.resolve() == source.resolve():
        raise RuntimeError("refusing to use the source as its own copy")
    src = sqlite3.connect("file:" + source.resolve().as_posix() + "?mode=ro", uri=True)
    out = sqlite3.connect(str(dst))
    try:
        src.backup(out)
    finally:
        src.close()
        out.close()
    migrate = (
        "import asyncio, sqlite3, sys\n"
        "from hub.db.engine import _run_alembic_upgrade\n"
        "asyncio.run(_run_alembic_upgrade())\n"
        "print('MIGRATED', sqlite3.connect(sys.argv[1]).execute('select version_num from alembic_version').fetchone()[0])\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + dst.resolve().as_posix()
    r = subprocess.run(["py", "-3.11", "-c", migrate, str(dst)], cwd=str(REPO / "hub"), env=env,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError("could not migrate the copy to head: " + (r.stdout + r.stderr)[-800:])
    p("  " + [ln for ln in r.stdout.splitlines() if ln.startswith("MIGRATED")][-1])
    c = sqlite3.connect(str(dst))
    try:
        c.execute("insert or replace into operator_credentials (id, label, revoked, created_at) "
                  "values (?, 'dashboards drive', 0, datetime('now'))", (KEY,))
        c.execute("update ai_jobs set enabled=0")
        c.execute("delete from apscheduler_jobs")
        c.execute("update loops set stopped_at=coalesce(stopped_at, datetime('now')) where stopped_at is null")
        c.execute("update inbound_queue_entries set state='withdrawn' where state='queued'")
        c.commit()
    finally:
        c.close()
    return dst


def ac_responsive(c: Check, source: pathlib.Path) -> None:
    scratch = TMP / "responsive"
    scratch.mkdir(parents=True, exist_ok=True)
    started = time.time()
    copy = copy_operator_database(source, scratch)
    p(f"  copy of {source} at {copy} ({copy.stat().st_size / 1e6:.0f} MB) in {time.time() - started:.0f} s")
    con = sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True)
    pid, spans = con.execute("select project_id, count(*) from trace_spans group by project_id "
                             "order by 2 desc limit 1").fetchone()
    con.close()
    p(f"  project {pid} holds {spans} trace spans")

    # The Hub from this checkout, in this process, on the copy: DATABASE_URL is bound at import.
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + copy.resolve().as_posix()
    for k in [k for k in os.environ if k.startswith("AW_") or k == "HUB_URL"]:
        os.environ.pop(k)
    sys.path.insert(0, str(REPO / "hub"))
    os.chdir(REPO / "hub")
    import uvicorn

    from hub.main import app

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    report = scratch / "client.json"
    stalls: List[Tuple[float, float]] = []

    async def serve_and_probe() -> None:
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
        serving = asyncio.create_task(server.serve())
        while not server.started:
            await asyncio.sleep(0.1)
        # The client is its own process: in this one its threads would hold the GIL, and the probe
        # would charge the drive's own work to the Hub's event loop.
        client = subprocess.Popen(
            ["py", "-3.11", str(pathlib.Path(__file__).resolve()), "--responsive-client", base, pid, KEY, str(report)],
            cwd=str(REPO))
        loop = asyncio.get_running_loop()
        while client.poll() is None:
            t = loop.time()
            await asyncio.sleep(0.010)
            stalls.append((time.time(), (loop.time() - t - 0.010) * 1000))
        server.should_exit = True
        await asyncio.wait_for(serving, 30)

    asyncio.run(serve_and_probe())
    found = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {"agents": []}
    window = [ms for at, ms in stalls if found.get("window_start", 0) <= at <= found.get("window_end", 0)]
    found["stalls"] = window
    worst_stall = max(found["stalls"] or [0.0])
    worst_agents = max([ms for ms, _ in found["agents"]] or [0.0])
    agents_bad = [code for _, code in found["agents"] if code != 200]
    regex = found.get("regex") or (0, None, 0.0)
    slow = found.get("slow") or (0, None, 0.0)
    p(f"  regex over every span of {pid} ({spans} spans): {said(regex[0], regex[1], 200)} in {regex[2]:.0f} ms")
    p(f"  time-limit query: {said(slow[0], slow[1], 200)} after {slow[2]:.0f} ms")
    p(f"  worst event-loop stall {worst_stall:.1f} ms over {len(found['stalls'])} samples; "
      f"worst GET /agents {worst_agents:.0f} ms over {len(found['agents'])} requests")
    c.judge("the regex query over every trace span answers a count",
            regex[0] == 200 and len(rows_of(regex[1])) == 1, said(regex[0], regex[1], 200))
    c.judge("the time-limit query is stopped with timeout",
            slow[0] == 422 and detail_code(slow[1]) == "timeout", said(slow[0], slow[1], 200))
    c.judge(f"no event-loop stall over {STALL_LIMIT_MS} ms while they run", worst_stall <= STALL_LIMIT_MS,
            f"worst {worst_stall:.1f} ms")
    c.judge(f"every GET /agents meanwhile answers 200 within {AGENTS_LIMIT_MS} ms",
            worst_agents <= AGENTS_LIMIT_MS and not agents_bad and len(found["agents"]) >= 3,
            f"worst {worst_agents:.0f} ms over {len(found['agents'])}; non-200 {agents_bad[:5]}")


def responsive_client(base: str, pid: str, key: str, report: str) -> None:
    """ac-responsive's client, in its own process: both queries at once, GET /agents every 200 ms
    meanwhile and for a second after; writes what it saw, with the window in wall-clock time."""
    global KEY
    KEY = key
    regex_sql = "select count(*) as n from trace_spans where attributes regexp '(?i)(api[_-]?key|secret|password)'"
    slow_sql = "with recursive c(x) as (select 1 union all select x + 1 from c) select count(*) from c"
    # Warm the routes' imports and caches before the window opens; not measured.
    api("GET", f"/projects/{pid}/agents", base=base)
    api("POST", f"/projects/{pid}/dashboards/query", {"sql": "select 1"}, base=base)
    found: Dict[str, Any] = {"agents": [], "window_start": time.time()}

    def one(label: str, sql: str) -> None:
        t = time.perf_counter()
        code, out = api("POST", f"/projects/{pid}/dashboards/query", {"sql": sql}, timeout=300, base=base)
        found[label] = (code, out, (time.perf_counter() - t) * 1000)

    workers = [threading.Thread(target=one, args=("regex", regex_sql)),
               threading.Thread(target=one, args=("slow", slow_sql))]
    for w in workers:
        w.start()
    tail = None
    while True:
        t = time.perf_counter()
        code, _ = api("GET", f"/projects/{pid}/agents", base=base, timeout=60)
        found["agents"].append(((time.perf_counter() - t) * 1000, code))
        if not any(w.is_alive() for w in workers):
            tail = tail or time.time() + 1.0
            if time.time() > tail:
                break
        time.sleep(0.2)
    found["window_end"] = time.time()
    pathlib.Path(report).write_text(json.dumps(found), encoding="utf-8")


# ------------------------------------------------------------------------------------------- main


def main() -> int:
    if len(sys.argv) == 6 and sys.argv[1] == "--responsive-client":
        responsive_client(*sys.argv[2:])
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--part", choices=("main", "responsive", "both"), default="both")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--source-db", type=pathlib.Path, default=OPERATOR_DB,
                    help="the database ac-responsive copies (opened mode=ro, never written)")
    args = ap.parse_args()
    TMP.mkdir(parents=True, exist_ok=True)
    p(f"dashboards drive {STAMP}; scratch {TMP}")
    if args.part in ("main", "both"):
        Drive(browser=not args.no_browser).run()
    if args.part in ("responsive", "both"):
        run_check("ac-responsive", lambda c: ac_responsive(c, args.source_db))

    p("\n== drive baseline")
    for key, check in CHECKS.items():
        failed = check.reached and not check.ok
        detail = "passed" if check.ok and check.reached else ("; ".join(check.details) or "no detail")
        p(f"check {key}: reached={'yes' if check.reached else 'no'} "
          f"failed_at_assertion={'yes' if failed else 'no'} -- {detail[:700]}")
    bad = [k for k, ch in CHECKS.items() if not (ch.reached and ch.ok)]
    p(f"\n{len(CHECKS) - len(bad)} of {len(CHECKS)} checks pass" + (f"; failing: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
