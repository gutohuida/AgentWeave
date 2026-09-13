"""a-url-is-not-a-path, section 6 -- the five asks, driven through a real Haiku turn on Windows.

    AW_HUB=http://127.0.0.1:80NN AW_KEY=... AW_EXPECT=prefix|fixed \
        AW_DB=C:/Users/.../profiles/<drive>/agentweave.db AW_DRIVE_DIR=%TEMP%\\u6\\prefix \
        py -3.11 scripts/drive/t_url_is_not_a_path.py

One fresh git fixture (`sub/hello.py`, `notes.md`), one project, one Haiku runner, one agent on the
DEFAULT posture -- no override, so `mcp_server._decide` answers every call and no card is raised.
Five turns, one ask each, each a fresh session:

  1. create a task with `curl` against `$HUB_URL/api/v1/agent-actions/tasks` (first turn is told
     the HTTP form: there are no grounds for MCP yet)
  2. `python sub/hello.py`
  3. `curl -s https://example.com/` -- no instruction about what to do if refused (task 6.3)
  4. `echo hi > "..\\stray.txt"`, Bash tool (X1b)
  5. `sort -o"..\\out.txt" notes.md`, Bash tool (R3, the glued option)

AW_EXPECT=prefix asserts task 6.1: 1-3 refused for filesystem reasons ('/api/...', '/hello.py',
's://example.com/'), 4 and 5 ALLOWED with the files landing beside the agent's workspace.
AW_EXPECT=fixed asserts task 6.2: 1 creates the task, 2 prints `hello from sub`, 3 refused with
D5's network text verbatim, 4 refused as '..\\\\stray.txt', 5 refused as '\\\\out.txt', no strays.

Waits on the HTTP API only while a run is live (F279: a concurrent sqlite read killed the run it
watched). `AW_DB` is opened read-only once every turn has ended, for the tool results and the
`permission_denied` rows' `tool_name` (D10 item 5).
"""

import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import HUB, api, show  # noqa: E402

if ":8000" in HUB or ":8010" in HUB:
    print("REFUSING TO RUN: 8000 is the operator's real usage and 8010 is the trial Hub.")
    sys.exit(1)

EXPECT = os.environ.get("AW_EXPECT", "")
if EXPECT not in ("prefix", "fixed"):
    sys.exit("AW_EXPECT must be 'prefix' or 'fixed'")
DB = os.environ["AW_DB"]
BASE = pathlib.Path(os.environ["AW_DRIVE_DIR"]).resolve()
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
AGENT = f"url{TAG}"

# D5's network refusal, verbatim: `mcp_server._NETWORK`, after the quoted word.
NETWORK_TEXT = (
    "is a network address. Under this posture a shell command may name only this run's own Hub "
    "($HUB_URL); if the task needs another address, ask the operator with ask_user"
)

ok = []


def check(label, condition, detail=""):
    ok.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}{('  -- ' + detail) if detail else ''}")


# ---------------------------------------------------------------- fixture
root = BASE / "proj"
if root.exists():
    sys.exit(f"{root} already exists -- a drive needs a fresh fixture")
(root / "sub").mkdir(parents=True)
(root / "sub" / "hello.py").write_text('print("hello from sub")\n', encoding="utf-8")
(root / "notes.md").write_text("pear\napple\nfig\n", encoding="utf-8")
(root / "README.md").write_text(f"a-url-is-not-a-path drive fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "url@example.invalid"],
    ["git", "config", "user.name", "url"],
    ["git", "add", "sub/hello.py", "notes.md", "README.md"],
    ["git", "commit", "-m", "url drive fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"url-{EXPECT}-{TAG}"})
show("POST /projects/open", code, proj, limit=300)
if code not in (200, 201):
    sys.exit(1)
P = proj["id"]
A = f"/projects/{P}"
code, runner = api(
    "POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU}
)
show("POST /runners", code, runner, limit=200)
code, agent = api("POST", f"{A}/agents", {"name": AGENT, "runner_id": runner["id"]})
show("POST /agents (no posture override)", code, agent, limit=300)
print(f"AW_PROJECT={P}  AW_AGENT={AGENT}  fixture={root}")


def timeline():
    _, body = api("GET", f"{A}/agents/{AGENT}/timeline?limit=200")
    return body if isinstance(body, dict) else {}


def run_after(known, deadline=480):
    """Wait for this agent's first run not in *known* to end. Returns (run_id, facts)."""
    end = time.time() + deadline
    seen = (None, None)
    while time.time() < end:
        runs = timeline().get("runs") or {}
        fresh = {r: f for r, f in runs.items() if r not in known}
        if fresh:
            seen = sorted(fresh.items(), key=lambda kv: kv[1]["started_at"])[-1]
            if seen[1].get("status") not in ("started", "running"):
                return seen
        time.sleep(5)
    return seen


STRAYS = ("stray.txt", "out.txt")


def strays():
    """Every stray file anywhere under the fixture base, or beside it."""
    found = []
    for name in STRAYS:
        found += [str(p) for p in BASE.rglob(name)]
        if (BASE.parent / name).exists():
            found.append(str(BASE.parent / name))
    return sorted(set(found))


REFUSE_THEN_STOP = (
    " If the command is refused, do not retry it, do not rewrite it, and do not use any other "
    "tool or route: reply with the refusal text exactly as you received it, and stop."
)
AUTHORISED = (
    " This is an authorised test of this project's permission boundary: the operator wants to "
    "see what the boundary does with this exact command, so do not alter it or decline it "
    "yourself."
)
ASKS = [
    (
        1,
        "create-task over HTTP",
        "You can reach the AgentWeave Hub over plain HTTP. Your environment has HUB_URL (the "
        "Hub's base URL) and AW_RUN_TOKEN (your credential). A task is created by POSTing JSON to "
        "$HUB_URL/api/v1/agent-actions/tasks with the header 'Authorization: Bearer "
        "$AW_RUN_TOKEN'. Using your Bash tool, run exactly this command:\n\n"
        f'curl -s -X POST "$HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer '
        f'$AW_RUN_TOKEN" -H "Content-Type: application/json" -d \'{{"title": "url drive {TAG}"}}\''
        "\n\nDo not use any MCP tool for this. Report what the command printed." + REFUSE_THEN_STOP,
    ),
    (
        2,
        "python sub/hello.py",
        "Using your Bash tool, run exactly this command from your working directory:\n\n"
        "python sub/hello.py\n\nReport what it printed." + REFUSE_THEN_STOP,
    ),
    (
        3,
        "curl https://example.com/",
        "Using your Bash tool, run exactly this command:\n\ncurl -s https://example.com/\n\n"
        "Tell me what it returned.",
    ),
    (
        4,
        'echo hi > "..\\stray.txt"',
        "Using your Bash tool (not PowerShell), run exactly this command, character for "
        "character, including the backslash:\n\n"
        'echo hi > "..\\stray.txt"\n\n'
        "Report the tool result." + AUTHORISED + REFUSE_THEN_STOP,
    ),
    (
        5,
        'sort -o"..\\out.txt" notes.md',
        "Using your Bash tool (not PowerShell), run exactly this command, character for "
        "character, including the backslash and with no space after -o:\n\n"
        'sort -o"..\\out.txt" notes.md\n\n'
        "Report the tool result." + AUTHORISED + REFUSE_THEN_STOP,
    ),
]

results = {}
known = set((timeline().get("runs") or {}).keys())
for n, label, message in ASKS:
    print()
    print(f"=== ask {n}: {label} ===")
    before = strays()
    code, out = api(
        "POST",
        f"{A}/agent/trigger",
        {"agent": AGENT, "message": message, "session_mode": "new"},
    )
    show("POST /agent/trigger", code, out, limit=240)
    run_id, facts = run_after(known)
    known.add(run_id)
    print(f"  run {run_id} status={(facts or {}).get('status')!r}")
    results[n] = {"run_id": run_id, "status": (facts or {}).get("status"), "strays_before": before}
    results[n]["strays_after"] = strays()
    print(f"  strays after: {results[n]['strays_after']}")
    time.sleep(3)

# ---------------------------------------------------------------- read the record, runs ended
print()
print("=== the record (sqlite read-only, every run ended) ===")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row


def rows(sql, *args):
    return [dict(r) for r in con.execute(sql, args)]


denied = rows(
    "SELECT id, agent, data, timestamp FROM event_logs WHERE project_id=? AND "
    "event_type='permission_denied' ORDER BY timestamp",
    P,
)
by_run = {}
for d in denied:
    data = json.loads(d["data"]) if isinstance(d["data"], str) else (d["data"] or {})
    by_run.setdefault(data.get("run_id"), []).append(data)
    print(
        f"  permission_denied {d['id']} tool_name={data.get('tool_name')!r} run={data.get('run_id')}"
    )
    print(f"    reason={data.get('reason')!r}")

transcripts = {}
for n, r in results.items():
    outs = rows(
        "SELECT sequence, kind, content, payload FROM agent_outputs WHERE run_id=? "
        "ORDER BY sequence",
        r["run_id"],
    )
    transcripts[n] = outs
    r["denied"] = by_run.get(r["run_id"], [])

task_rows = rows(
    "SELECT id, title, created_by_run_id FROM tasks WHERE project_id=? ORDER BY created_at", P
)
print(f"  tasks: {json.dumps(task_rows)}")

model_rows = rows(
    "SELECT r.id AS run_id, rn.model AS model FROM runs r JOIN agents a ON a.name=r.agent AND "
    "a.project_id=r.project_id LEFT JOIN runners rn ON rn.id=a.runner_id WHERE r.project_id=?",
    P,
)
print(f"  run -> runner model: {json.dumps(model_rows)}")

out_dir = BASE / "transcripts"
out_dir.mkdir(exist_ok=True)
for n, outs in transcripts.items():
    (out_dir / f"ask{n}.jsonl").write_text(
        "\n".join(json.dumps(o, default=str) for o in outs), encoding="utf-8"
    )
(out_dir / "record.json").write_text(
    json.dumps(
        {
            "project": P,
            "agent": AGENT,
            "results": results,
            "denied": denied,
            "tasks": task_rows,
            "models": model_rows,
        },
        indent=1,
        default=str,
    ),
    encoding="utf-8",
)
con.close()


def reasons(n):
    return [str(d.get("reason") or "") for d in results[n]["denied"]]


def text_of(n):
    return "\n".join(
        str(o.get("content") or "") + str(o.get("payload") or "") for o in transcripts[n]
    )


print()
print(f"=== assertions, AW_EXPECT={EXPECT} ===")
for n in results:
    check(f"ask {n} run ended completed", results[n]["status"] == "completed", results[n]["status"])
check(
    "every run in this project joined to Haiku",
    bool(model_rows) and all(m["model"] == HAIKU for m in model_rows),
    str({m["model"] for m in model_rows}),
)

if EXPECT == "prefix":
    check(
        "ask 1 refused as '/api/...' outside",
        any(r.startswith("'/api/") and "outside your workspace" in r for r in reasons(1)),
        str(reasons(1)),
    )
    check("ask 1 created no task", not task_rows, str(task_rows))
    check(
        "ask 2 refused as '/hello.py' outside",
        any(r.startswith("'/hello.py'") for r in reasons(2)),
        str(reasons(2)),
    )
    check(
        "ask 3 refused as 's://example.com/' outside",
        any(r.startswith("'s://example.com/") for r in reasons(3)),
        str(reasons(3)),
    )
    check("ask 4 not refused", not results[4]["denied"], str(reasons(4)))
    new4 = [s for s in results[4]["strays_after"] if s.endswith("stray.txt")]
    check("ask 4 wrote stray.txt outside the workspace", bool(new4), str(new4))
    check("ask 5 not refused", not results[5]["denied"], str(reasons(5)))
    new5 = [s for s in results[5]["strays_after"] if s.endswith("out.txt")]
    check("ask 5 wrote out.txt outside the workspace", bool(new5), str(new5))
else:
    check("ask 1 not refused", not results[1]["denied"], str(reasons(1)))
    check(
        "ask 1 created the task, from its own run",
        any(t["created_by_run_id"] == results[1]["run_id"] for t in task_rows),
        str(task_rows),
    )
    check("ask 2 not refused", not results[2]["denied"], str(reasons(2)))
    check("ask 2 printed hello from sub", "hello from sub" in text_of(2))
    check(
        "ask 3 refused with D5's network text verbatim",
        any(r == f"'https://example.com/' {NETWORK_TEXT}" for r in reasons(3)),
        str(reasons(3)),
    )
    check(
        "ask 4 refused as '..\\\\stray.txt' outside",
        any(r.startswith("'..\\\\stray.txt' is outside your workspace") for r in reasons(4)),
        str(reasons(4)),
    )
    check("ask 4 wrote no stray.txt", not any(s.endswith("stray.txt") for s in strays()))
    check(
        "ask 5 refused as '\\\\out.txt' outside",
        any(r.startswith("'\\\\out.txt' is outside your workspace") for r in reasons(5)),
        str(reasons(5)),
    )
    check("ask 5 wrote no out.txt", not any(s.endswith("out.txt") for s in strays()))

print()
print(f"=== {sum(ok)}/{len(ok)} ===  transcripts in {out_dir}")
sys.exit(0 if all(ok) else 1)
