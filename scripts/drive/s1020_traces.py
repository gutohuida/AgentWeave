"""2026-10-20 day sweep: Traces x Runs x Logs, events & SSE, on a scratch Hub (hub-up 8141).

Phases (each reads back through the routes the app calls, never the echo):
  setup     project with a small library, one Claude Haiku agent
  api       Settings -> Traces routes with no run: counts, kind filter, cursor, refusals, OTLP
            settings (headers never returned), export (range refusals, JSON shape), clear
  turn      a real Haiku turn that runs a command carrying a fake high-entropy token and an
            sk- key under `manual`; the turn's trace vs its events; the permission span vs the
            permission event (redaction); stop a second turn mid-flight
  logs      /events/history filters, F419 (a second project's events), export after clear

Usage: py -3.11 scripts/drive/s1020_traces.py <phase>
"""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-traces1020.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "scratch" / "s1020_traces_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
LIVE = ("running", "queued", "starting", "pending")
#: Fake credentials: one only the entropy catch-all knows, one the named `sk-` pattern knows.
ENTROPY_TOKEN = "ghp_Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4"
SK_TOKEN = "sk-ant-api03-FAKEfake1234567890abcdefXYZ"


def save():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(S, indent=2))


def api(method, path, body=None, **kw):
    if path.startswith("~"):
        path = f"/projects/{S['P']}" + path[1:]
    return e2e.request(method, path, body, **kw)


def say(label, obj=""):
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str, ensure_ascii=False)
    print(f"--- {label}: {text[:2500]}", flush=True)


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


def wait_run(run_id, secs=600):
    end = time.time() + secs
    while time.time() < end:
        rows = ro("select status from runs where id=?", (run_id,))
        if rows and rows[0]["status"] not in LIVE:
            return rows[0]["status"]
        time.sleep(4)
    return "still-running"


def setup():
    d = pathlib.Path(r"C:\Users\huida\Documents\aw-traces-1020")
    d.mkdir(parents=True, exist_ok=True)
    (d / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b  # no zero check\n",
        encoding="utf-8",
    )
    (d / "test_calc.py").write_text(
        "from calc import add, div\n\n\ndef test_add():\n    assert add(2, 2) == 4\n\n\n"
        "def test_div():\n    assert div(4, 2) == 2\n",
        encoding="utf-8",
    )
    if not (d / ".git").is_dir():
        for args in (
            ["init", "-q", "-b", "master"],
            ["add", "-A"],
            ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        ):
            subprocess.run(["git", "-C", str(d), *args], check=True)
    S["P"] = e2e.call("POST", "/projects/open", {"path": str(d)})["id"]
    S["DIR"] = str(d)
    d2 = pathlib.Path(r"C:\Users\huida\Documents\aw-traces-1020b")
    d2.mkdir(parents=True, exist_ok=True)
    (d2 / "README.md").write_text("# b\n", encoding="utf-8")
    if not (d2 / ".git").is_dir():
        for args in (
            ["init", "-q", "-b", "master"],
            ["add", "-A"],
            ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        ):
            subprocess.run(["git", "-C", str(d2), *args], check=True)
    S["P2"] = e2e.call("POST", "/projects/open", {"path": str(d2)})["id"]
    save()
    e2e.cmd_agent(S["P"], "tracer", "-", "claude", "claude-haiku-4-5-20251001")
    say("projects", {"P": S["P"], "P2": S["P2"]})


def api_phase():
    say("settings (fresh)", api("GET", "~/traces/settings"))
    # Some operator writes so the request kind has content.
    st, task = api("POST", "~/tasks", {"title": "Guard div against zero", "description": "div(1,0)"})
    say("create task", (st, task.get("id") if isinstance(task, dict) else task))
    S["TASK"] = task.get("id") if isinstance(task, dict) else None
    save()
    say("missing task", api("GET", "~/tasks/task-nope"))
    time.sleep(3)
    for op in ("invoke_agent", "chat", "aw.request", "aw.work", "aw.event", None):
        q = f"?operation={op}" if op else ""
        st, body = api("GET", f"~/traces{q}")
        rows = body.get("traces", []) if isinstance(body, dict) else body
        say(f"list op={op}", (st, len(rows), [(r["kind"], r["name"], r["status"], r["span_count"]) for r in rows[:8]]))
    say("list op=bogus", api("GET", "~/traces?operation=bogus"))
    say("list op too long", api("GET", "~/traces?operation=" + "x" * 40))
    say("list before=garbage", api("GET", "~/traces?before=garbage"))
    say("list before=garbage|x", api("GET", "~/traces?before=garbage|x"))
    say("list limit=0", api("GET", "~/traces?limit=0"))
    say("list limit=1", api("GET", "~/traces?operation=aw.request&limit=1"))
    st, page1 = api("GET", "~/traces?limit=1")
    if isinstance(page1, dict) and page1.get("next_before"):
        say("cursor page2", api("GET", "~/traces?limit=1&before=" + page1["next_before"].replace("+", "%2B")))
        say("cursor page2 unescaped +", api("GET", "~/traces?limit=1&before=" + page1["next_before"]))
    say("unknown trace", api("GET", "~/traces/0123"))
    say("unknown by-run", api("GET", "~/traces/by-run/run-nope"))
    say("run_id filter unknown", api("GET", "~/traces?run_id=run-nope"))
    # One request trace, read whole.
    st, body = api("GET", "~/traces?operation=aw.request&limit=5")
    if body.get("traces"):
        tid = body["traces"][0]["trace_id"]
        say("one request trace", api("GET", f"~/traces/{tid}"))
        say("one trace offset past end", api("GET", f"~/traces/{tid}?offset=99"))
    # Settings refusals.
    say("put ftp endpoint", api("PUT", "~/traces/settings", {"otlp_endpoint": "ftp://x"}))
    say("put enable without endpoint", api("PUT", "~/traces/settings", {"export_enabled": True}))
    say("settings after refusals", api("GET", "~/traces/settings"))
    say("put bad header name", api("PUT", "~/traces/settings", {"otlp_headers": {"A:B": "v"}}))
    say("put unknown field", api("PUT", "~/traces/settings", {"otlp_endpointt": "http://x"}))
    say(
        "put endpoint+header+enable (dead collector)",
        api(
            "PUT",
            "~/traces/settings",
            {
                "otlp_endpoint": "http://127.0.0.1:9",
                "otlp_headers": {"Authorization": "Bearer " + SK_TOKEN},
                "export_enabled": True,
            },
        ),
    )
    api("POST", "~/tasks", {"title": "a write after enabling export"})
    time.sleep(8)
    st, s = api("GET", "~/traces/settings")
    say("settings after a span ended (dead collector)", s)
    say("header value anywhere in settings?", SK_TOKEN in json.dumps(s))
    # Export: refusals, then a real one.
    say("export since=bad", api("GET", "~/traces/export?since=yesterday"))
    say("export until<=since", api("GET", "~/traces/export?since=2026-10-20&until=2026-10-19"))
    st, exported = api("GET", "~/traces/export")
    if isinstance(exported, dict):
        spans = exported["resourceSpans"][0]["scopeSpans"][0]["spans"]
        logs = exported["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        say("export", (st, len(spans), "spans", len(logs), "logs", exported["resourceSpans"][0]["resource"]))
        S["EXPORT_SPANS"] = len(spans)
    else:
        say("export (not json!)", (st, str(exported)[:500]))
    say("export future range", api("GET", "~/traces/export?since=2030-01-01"))
    st, c = api("GET", "~/traces/settings")
    say("counts before clear", {k: c[k] for k in ("span_count", "trace_count", "spans_by_operation", "dropped_spans")})
    say("clear future range", api("DELETE", "~/traces?since=2030-01-01"))
    say("clear bad range", api("DELETE", "~/traces?since=2026-10-21&until=2026-10-20"))
    save()


def _turn(message, perm=None, fresh=True):
    body = {"agent": "tracer", "message": message}
    if perm:
        body["overrides"] = {"permission_mode": perm}
    st, res = api("POST", "~/agent/trigger", body)
    say("trigger", (st, res))
    return res.get("run_id") if isinstance(res, dict) else None


def turn_phase():
    msg = (
        "Run exactly this one shell command and nothing else, then reply with its output: "
        f"echo token={ENTROPY_TOKEN} key={SK_TOKEN}"
    )
    run = _turn(msg, perm="manual")
    S["RUN1"] = run
    save()
    # Approve the permission card(s) as the operator would.
    deadline = time.time() + 240
    approved = 0
    while time.time() < deadline:
        rows = ro("select status from runs where id=?", (run,))
        if rows and rows[0]["status"] not in LIVE:
            break
        st, pending = api("GET", "~/permission-requests")
        items = pending if isinstance(pending, list) else []
        for item in items:
            if item.get("run_id") == run:
                say("permission card", {k: item.get(k) for k in ("id", "tool_name", "tool_input", "status")})
                say("approve", api("POST", f"~/permission-requests/{item['id']}/decide", {"allow": True}))
                approved += 1
        time.sleep(3)
    say("run1 end", wait_run(run, 300))
    time.sleep(3)
    trace_compare(run)


def trace_compare(run):
    st, tr = api("GET", f"~/traces/by-run/{run}?limit=2000")
    if st != 200:
        say("by-run", (st, tr))
        return
    spans = tr["spans"]
    say("trace", {"kind": tr["kind"], "total": tr["total"], "root": {k: tr["root"][k] for k in ("name", "status", "status_message", "ended")}})
    for sp in spans:
        attrs = sp["attributes"]
        say(
            f"span {sp['operation']} {sp['name']}",
            {"status": sp["status"], "events": [e.get("name") for e in sp["events"]][:20], "attr_keys": sorted(attrs)[:30]},
        )
    blob = json.dumps(tr, ensure_ascii=False)
    say("entropy token in trace?", ENTROPY_TOKEN in blob)
    say("entropy token tail in trace?", ENTROPY_TOKEN[4:] in blob)
    say("sk token in trace?", SK_TOKEN in blob)
    events = ro(
        "select event_type, data from event_logs where project_id=? and (data like ? ) order by id",
        (S["P"], f"%{run}%"),
    )
    say("events naming run", [(e["event_type"]) for e in events])
    ev_blob = json.dumps(events, ensure_ascii=False)
    say("entropy token in events?", ENTROPY_TOKEN[4:] in ev_blob)
    say("sk token in events?", SK_TOKEN in ev_blob)
    traced = set()
    for sp in spans:
        for e in sp["events"]:
            traced.add(e.get("name"))
    say("event names on trace", sorted(traced))
    missing = sorted({e["event_type"] for e in events} - traced)
    say("event types of the run NOT on its trace", missing)
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? order by sequence", (run,))
    out_blob = json.dumps(outputs, ensure_ascii=False)
    say("entropy token in agent_outputs?", ENTROPY_TOKEN[4:] in out_blob)
    say("sk token in agent_outputs?", SK_TOKEN in out_blob)
    perms = ro("select tool_name, tool_input, status from permission_requests where run_id=?", (run,))
    say("permission rows", perms)
    say("run row", ro("select status, error, harness_mcp_status from runs where id=?", (run,)))


if __name__ == "__main__":
    phase = sys.argv[1]
    {"setup": setup, "api": api_phase, "turn": turn_phase, "compare": lambda: trace_compare(sys.argv[2])}[phase]()
