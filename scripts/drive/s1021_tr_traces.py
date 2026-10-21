"""2026-10-21 day sweep: Traces x Runs x Logs, events & SSE, on a scratch Hub (hub-up 8156).

The Hub is started with `testbed/scratch/s1021_copilot_hang` first on PATH: a native `copilot.exe`
stand-in (compiled from `hang.cs` with the Windows C# compiler) that answers `--version` and never
answers an ACP request, so a Copilot run's startup request really times out (F789).

Phases (each reads back through the routes the app calls, never the echo):
  setup     project with a small library + a second project; Claude Haiku `tracer`, Copilot `slowcop`
  f792      a real turn holding a 120 s sleep, stopped mid-flight; its trace root, the list's run_status
  f793      export to a dead endpoint until it backs off, then a live receiver: time to first span
  f789      a Copilot turn against the stand-in: the run's error, its run_failed event, the conversation
  redact    a real turn echoing two fake secrets: trace, events, outputs, export
  ledger    /ledger vs the accounting routes; /events/history filters; F419 on the second project

Usage: py -3.11 scripts/drive/s1021_tr_traces.py <phase>
"""

import json
import os
import pathlib
import subprocess
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-traces1021.json")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

STATE_FILE = ROOT / "testbed" / "scratch" / "s1021_tr_state.json"
S = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
LIVE = ("running", "queued", "starting", "pending")
ENTROPY_TOKEN = "ghp_Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"
SK_TOKEN = "sk-ant-api03-FAKEfake0987654321zyxwvuABC"


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
        time.sleep(3)
    return "still-running"


def _repo(path, files):
    path.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (path / name).write_text(text, encoding="utf-8")
    if not (path / ".git").is_dir():
        for args in (
            ["init", "-q", "-b", "master"],
            ["add", "-A"],
            ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
        ):
            subprocess.run(["git", "-C", str(path), *args], check=True)


def setup():
    d = pathlib.Path(r"C:\Users\huida\Documents\aw-traces-1021")
    _repo(
        d,
        {
            "calc.py": "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n",
            "test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n",
        },
    )
    S["P"] = e2e.call("POST", "/projects/open", {"path": str(d)})["id"]
    S["DIR"] = str(d)
    d2 = pathlib.Path(r"C:\Users\huida\Documents\aw-traces-1021b")
    _repo(d2, {"README.md": "# b\n"})
    S["P2"] = e2e.call("POST", "/projects/open", {"path": str(d2)})["id"]
    save()
    e2e.cmd_agent(S["P"], "tracer", "-", "claude", "claude-haiku-4-5-20251001")
    st, res = api("POST", "~/runners", {"name": "slow copilot", "cli": "copilot"})
    say("copilot runner", (st, res))
    if st < 300:
        S["COP_RUNNER"] = res["id"]
        say("slowcop agent", api("POST", "~/agents", {"name": "slowcop", "runner_id": res["id"]}))
    save()
    say("projects", {"P": S["P"], "P2": S["P2"]})


def trigger(agent, message, perm=None):
    body = {"agent": agent, "message": message}
    if perm:
        body["overrides"] = {"permission_mode": perm}
    st, res = api("POST", "~/agent/trigger", body)
    say(f"trigger {agent}", (st, res))
    return res.get("run_id") if isinstance(res, dict) else None


def root_of(run):
    st, tr = api("GET", f"~/traces/by-run/{run}?limit=2000")
    if st != 200:
        return st, tr
    r = tr["root"]
    return st, {
        "kind": tr.get("kind"),
        "root": {k: r.get(k) for k in ("name", "status", "status_message", "ended")},
        "aw.run.status": (r.get("attributes") or {}).get("aw.run.status"),
        "root events": [e.get("name") for e in r.get("events", [])],
    }


def f792():
    run = trigger(
        "tracer",
        'Run exactly this one shell command and nothing else: py -3.11 -c "import time\n'
        'for i in range(120): time.sleep(1)"',
        perm="workspace",
    )
    S["RUN_STOP"] = run
    save()
    end = time.time() + 180
    while time.time() < end:
        tools = ro(
            "select count(*) n from agent_outputs where run_id=? and kind like '%tool%'", (run,)
        )[0]["n"]
        status = ro("select status from runs where id=?", (run,))[0]["status"]
        if tools and status == "running":
            break
        if status not in LIVE:
            break
        time.sleep(3)
    say("before stop", ro("select status from runs where id=?", (run,)))
    time.sleep(6)
    say("stop", api("POST", "~/agent/tracer/stop"))
    say("run end", wait_run(run, 120))
    time.sleep(3)
    say("run row", ro("select status, error, exit_code from runs where id=?", (run,)))
    say("by-run root", root_of(run))
    st, listed = api("GET", f"~/traces?run_id={run}")
    say("list row", (st, [{k: t.get(k) for k in ("name", "status", "run_status", "ended")} for t in listed.get("traces", [])]))
    st, listed = api("GET", "~/traces?operation=invoke_agent")
    say("invoke_agent list", [(t.get("run_id"), t.get("status"), t.get("run_status")) for t in listed.get("traces", [])])


def _receiver_count(out):
    p = pathlib.Path(out)
    if not p.exists():
        return 0
    return sum(1 for _ in p.open(encoding="utf-8"))


def f793():
    say(
        "dead endpoint",
        api("PUT", "~/traces/settings", {"otlp_endpoint": "http://127.0.0.1:9", "export_enabled": True}),
    )
    # Normal operator writes for ~3 minutes, so the dead endpoint fails several passes in a row.
    t0 = time.time()
    while time.time() - t0 < 200:
        api("POST", "~/tasks", {"title": f"write at {int(time.time() - t0)} s"})
        time.sleep(10)
    st, s = api("GET", "~/traces/settings")
    say("settings after dead pushes", {k: s.get(k) for k in ("last_error", "last_export_at", "export_enabled", "otlp_endpoint")})
    out = str(ROOT / "testbed" / "scratch" / "s1021_tr_otlp.jsonl")
    if os.path.exists(out):
        os.remove(out)
    proc = subprocess.Popen(["py", "-3.11", str(ROOT / "scripts" / "drive" / "otlp_receiver.py"), "4421", out])
    time.sleep(2)
    try:
        t_put = time.time()
        say("fix endpoint", api("PUT", "~/traces/settings", {"otlp_endpoint": "http://127.0.0.1:4421"}))
        api("POST", "~/tasks", {"title": "first write after the fix"})
        arrived = None
        while time.time() - t_put < 330:
            if _receiver_count(out):
                arrived = time.time() - t_put
                break
            time.sleep(1)
        say("first OTLP post after the fix (s)", arrived)
        st, s = api("GET", "~/traces/settings")
        say("settings after the fix", {k: s.get(k) for k in ("last_error", "last_export_at", "exported_spans", "span_count")})
        # Vary: a headers-only save also resets (the fix names endpoint, headers, enable).
        say("disable", api("PUT", "~/traces/settings", {"export_enabled": False}))
    finally:
        proc.terminate()


def f789():
    run = trigger("slowcop", "Say hello.")
    S["RUN_COP"] = run
    save()
    if not run:
        return
    t0 = time.time()
    status = wait_run(run, 240)
    say("copilot run end", (status, round(time.time() - t0, 1)))
    say("run row", ro("select status, error, exit_code from runs where id=?", (run,)))
    evs = ro(
        "select event_type, data from event_logs where project_id=? and data like ? order by id",
        (S["P"], f"%{run}%"),
    )
    for e in evs:
        if e["event_type"] in ("run_failed", "run_finished", "agent_run_failed"):
            say(f"event {e['event_type']}", e["data"])
    say("event types", [e["event_type"] for e in evs])
    say("outputs", ro("select kind, substr(content,1,300) c from agent_outputs where run_id=? order by sequence", (run,)))
    say("by-run root", root_of(run))
    conv = ro("select conversation_id from runs where id=?", (run,))[0]["conversation_id"]
    S["CONV_COP"] = conv
    save()
    st, msgs = api("GET", f"~/conversations/{conv}/messages")
    say("conversation messages", (st, msgs if not isinstance(msgs, dict) else {k: msgs[k] for k in list(msgs)[:3]}))
    say("inbound entry", ro("select status, attempts, last_error from inbound_queue where target_agent='slowcop'") if ro("select name from sqlite_master where name='inbound_queue'") else "no inbound_queue table")


def redact():
    run = trigger(
        "tracer",
        "Run exactly this one shell command and nothing else, then reply with its output: "
        f"echo token={ENTROPY_TOKEN} key={SK_TOKEN}",
        perm="workspace",
    )
    S["RUN_RED"] = run
    save()
    say("run end", wait_run(run, 300))
    time.sleep(3)
    st, tr = api("GET", f"~/traces/by-run/{run}?limit=2000")
    blob = json.dumps(tr, ensure_ascii=False)
    say("trace: entropy / sk token", (ENTROPY_TOKEN[4:] in blob, SK_TOKEN in blob, SK_TOKEN[:14] in blob))
    events = ro("select event_type, data from event_logs where project_id=? and data like ?", (S["P"], f"%{run}%"))
    eb = json.dumps(events, ensure_ascii=False)
    say("events: entropy / sk token", (ENTROPY_TOKEN[4:] in eb, SK_TOKEN in eb))
    outs = ro("select kind, content, payload from agent_outputs where run_id=?", (run,))
    ob = json.dumps(outs, ensure_ascii=False)
    say("outputs: entropy / sk token", (ENTROPY_TOKEN[4:] in ob, SK_TOKEN in ob))
    say("calc.py path visible in trace?", "calc.py" in blob or S["DIR"].replace("\\", "\\\\") in blob)
    st, ex = api("GET", "~/traces/export")
    xb = json.dumps(ex, ensure_ascii=False)
    say("export: entropy / sk token", (ENTROPY_TOKEN[4:] in xb, SK_TOKEN in xb))
    st, hist = api("GET", "~/events/history?limit=500")
    hb = json.dumps(hist, ensure_ascii=False)
    say("events/history: entropy / sk token", (ENTROPY_TOKEN[4:] in hb, SK_TOKEN in hb))
    i = blob.find("token=")
    say("what the trace shows for token=", blob[i : i + 120] if i >= 0 else "<absent>")
    say("trace span statuses", [(s["operation"], s["name"], s["status"]) for s in tr.get("spans", [])][:20])
    say("event types of run not on its trace", sorted({e["event_type"] for e in events} - {ev.get("name") for s in tr.get("spans", []) for ev in s.get("events", [])}))


def ledger():
    st, led = api("GET", "~/ledger")
    say("ledger keys", (st, sorted(led) if isinstance(led, dict) else led))
    if isinstance(led, dict):
        say("ledger spend", led.get("spend"))
        lanes = led.get("lanes") or {}
        say("ledger lanes", {k: (len(v) if isinstance(v, list) else v) for k, v in (lanes.items() if isinstance(lanes, dict) else [])})
        say("ledger notices", led.get("notices"))
    for path in ("~/usage", "~/accounting", "~/usage/summary"):
        st, body = api("GET", path)
        if st == 200:
            say(f"accounting {path}", body)
    say("runs", ro("select id, agent, status, cost_usd, input_tokens, output_tokens from runs where project_id=?", (S["P"],)) if ro("select 1 from pragma_table_info('runs') where name='cost_usd'") else ro("select id, agent, status from runs where project_id=?", (S["P"],)))
    for q in ("?limit=5", "?event_type=run_failed", "?event_type=nope", "?limit=0", "?limit=100000", "?before=garbage"):
        st, body = api("GET", f"~/events/history{q}")
        n = len(body) if isinstance(body, list) else (len(body.get("events", [])) if isinstance(body, dict) and "events" in body else body)
        say(f"history {q}", (st, n if not isinstance(n, (dict, str)) else str(n)[:300]))
    st, h2 = api("GET", f"/projects/{S['P2']}/events/history?limit=500")
    b2 = json.dumps(h2, ensure_ascii=False)
    say("P2 history names P's runs?", any(S.get(k, "zz") in b2 for k in ("RUN_STOP", "RUN_RED", "RUN_COP")))
    say("P2 history names P?", S["P"] in b2)


if __name__ == "__main__":
    {"setup": setup, "f792": f792, "f793": f793, "f789": f789, "redact": redact, "ledger": ledger}[sys.argv[1]]()
