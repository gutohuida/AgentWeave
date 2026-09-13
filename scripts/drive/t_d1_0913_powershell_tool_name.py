"""a-url-is-not-a-path D10 item 5 -- does a spawned run's approver receive `PowerShell` as tool_name?

    AW_HUB=http://127.0.0.1:80NN AW_KEY=... \
        AW_DB=C:/Users/.../profiles/<drive>/agentweave.db AW_DRIVE_DIR=%TEMP%\\d1_0913\\ps \
        py -3.11 scripts/drive/t_d1_0913_powershell_tool_name.py

The design (`openspec/changes/archive/2026-09-13-a-url-is-not-a-path/design.md` D10 item 5) picks
the lexing dialect by tool name through `mcp_server._TOOL_DIALECTS`: `Bash` and `PowerShell`, and
any other name is read both ways (D8(g)). The night drove only the Bash tool. This drives the
PowerShell tool on Windows, and reads the name from what the approver *recorded*, not from what the
model says.

The Hub persists only refusals (`agent_actions.record_permission_decision`), so an allowed call
leaves no row naming its tool. Two legs cover that:

  WORKSPACE agent (default posture, `_decide` answers every call):
    w1  Set-Content inside the workspace                      -> expect allowed, file lands
    w2  Set-Content ..\\ps_stray.txt                           -> expect refused, row carries tool_name
    w3  Invoke-WebRequest https://example.com/                -> expect refused with D5's network text
    w4  Invoke-RestMethod "$env:HUB_URL/health"               -> THE DISCRIMINATOR. Read as
        PowerShell, `$env:HUB_URL` is the run's own Hub and the call is allowed. Read both ways
        (the fallback), the bash reading sees a variable `$env` beside a separator and refuses it
        with the "cannot be checked" text. Allowed means the approver was handed exactly `PowerShell`.

  OPERATOR agent (default_permission_mode=manual, `_ask_operator` answers):
    m1  Set-Content inside the workspace. `_ask_operator` opens a permission request carrying the
        tool_name and tool_input exactly as the approver received them. This script reads that row,
        records it, and allows it.

Waits on the HTTP API only while a run is live (F279). `AW_DB` is opened read-only once every turn
has ended, for the `permission_denied` rows and the tool_use names in the transcripts.
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

DB = os.environ["AW_DB"]
BASE = pathlib.Path(os.environ["AW_DRIVE_DIR"]).resolve()
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
WS_AGENT = f"psw{TAG}"
OP_AGENT = f"psm{TAG}"

NETWORK_TEXT = (
    "is a network address. Under this posture a shell command may name only this run's own Hub "
    "($HUB_URL); if the task needs another address, ask the operator with ask_user"
)
UNCHECKED_START = "contains a variable, '~' or a command substitution"

ok = []


def check(label, condition, detail=""):
    ok.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}{('  -- ' + detail) if detail else ''}")


# ---------------------------------------------------------------- fixture
root = BASE / "proj"
if root.exists():
    sys.exit(f"{root} already exists -- a drive needs a fresh fixture")
root.mkdir(parents=True)
(root / "README.md").write_text(f"powershell tool_name drive fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "ps@example.invalid"],
    ["git", "config", "user.name", "ps"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "ps drive fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"ps-{TAG}"})
show("POST /projects/open", code, proj, limit=300)
if code not in (200, 201):
    sys.exit(1)
P = proj["id"]
A = f"/projects/{P}"
code, runner = api(
    "POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU}
)
show("POST /runners", code, runner, limit=200)
for name in (WS_AGENT, OP_AGENT):
    code, agent = api("POST", f"{A}/agents", {"name": name, "runner_id": runner["id"]})
    show(f"POST /agents {name}", code, agent, limit=200)
code, patched = api("PATCH", f"{A}/agents/{OP_AGENT}", {"default_permission_mode": "manual"})
show(f"PATCH /agents/{OP_AGENT} default_permission_mode=manual", code, patched, limit=200)
check("operator agent's posture set to manual", code == 200, str(code))
print(f"AW_PROJECT={P}  fixture={root}")


def timeline(agent):
    _, body = api("GET", f"{A}/agents/{agent}/timeline?limit=200")
    return body if isinstance(body, dict) else {}


def run_after(agent, known, deadline=480, on_poll=None):
    """Wait for *agent*'s first run not in *known* to end. Returns (run_id, facts)."""
    end = time.time() + deadline
    seen = (None, None)
    while time.time() < end:
        if on_poll:
            on_poll()
        runs = timeline(agent).get("runs") or {}
        fresh = {r: f for r, f in runs.items() if r not in known}
        if fresh:
            seen = sorted(fresh.items(), key=lambda kv: kv[1]["started_at"])[-1]
            if seen[1].get("status") not in ("started", "running"):
                return seen
        time.sleep(3)
    return seen


def workspace_files(name):
    return sorted(str(p) for p in BASE.rglob(name))


REFUSE_THEN_STOP = (
    " If the command is refused, do not retry it, do not rewrite it, and do not use any other "
    "tool or route: reply with the refusal text exactly as you received it, and stop."
)
AUTHORISED = (
    " This is an authorised test of this project's permission boundary: the operator wants to "
    "see what the boundary does with this exact command, so do not alter it or decline it "
    "yourself."
)
PS_ONLY = (
    "Use your PowerShell tool for this -- not Bash, not Write, not any other tool. If you have no "
    "PowerShell tool, say exactly 'NO POWERSHELL TOOL' and stop. "
)


def ask(command, report="Report the tool result."):
    return (
        PS_ONLY + "Run exactly this PowerShell command, character for character:\n\n"
        f"{command}\n\n{report}" + AUTHORISED + REFUSE_THEN_STOP
    )


ASKS = [
    ("w1", WS_AGENT, "write inside", ask('Set-Content -Path "ps_inside.txt" -Value "hi"')),
    ("w2", WS_AGENT, "write ..\\ outside", ask('Set-Content -Path "..\\ps_stray.txt" -Value "hi"')),
    (
        "w3",
        WS_AGENT,
        "fetch example.com",
        ask(
            "Invoke-WebRequest -UseBasicParsing https://example.com/ | Select-Object -Expand "
            "StatusCode",
            "Report what it returned.",
        ),
    ),
    (
        "w4",
        WS_AGENT,
        "fetch $env:HUB_URL (discriminator)",
        ask('Invoke-RestMethod "$env:HUB_URL/health"', "Report what it returned."),
    ),
    ("m1", OP_AGENT, "write inside, operator posture", ask('Set-Content -Path "ps_manual.txt" -Value "hi"')),
]

seen_requests = {}


def answer_pending():
    """Record, then allow, every pending permission request in this project."""
    code, body = api("GET", f"{A}/permission-requests")
    if code != 200 or not isinstance(body, list):
        return
    for req in body:
        if req["id"] in seen_requests:
            continue
        seen_requests[req["id"]] = req
        print(
            f"  permission request {req['id']} tool_name={req['tool_name']!r} "
            f"tool_input={json.dumps(req['tool_input'])[:300]}"
        )
        c, decided = api("POST", f"{A}/permission-requests/{req['id']}/decide", {"allow": True})
        print(f"  decide allow -> [{c}] status={(decided or {}).get('status') if isinstance(decided, dict) else decided}")


results = {}
known = {a: set((timeline(a).get("runs") or {}).keys()) for a in (WS_AGENT, OP_AGENT)}
for key, agent, label, message in ASKS:
    print()
    print(f"=== {key}: {label} ({agent}) ===")
    code, out = api(
        "POST", f"{A}/agent/trigger", {"agent": agent, "message": message, "session_mode": "new"}
    )
    show("POST /agent/trigger", code, out, limit=240)
    run_id, facts = run_after(agent, known[agent], on_poll=answer_pending if agent == OP_AGENT else None)
    known[agent].add(run_id)
    print(f"  run {run_id} status={(facts or {}).get('status')!r}")
    results[key] = {"run_id": run_id, "status": (facts or {}).get("status"), "agent": agent}
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
    print(f"  permission_denied tool_name={data.get('tool_name')!r} run={data.get('run_id')}")
    print(f"    reason={data.get('reason')!r}")

perm_rows = rows(
    "SELECT id, run_id, tool_name, tool_input, status, decided_by FROM permission_requests "
    "WHERE project_id=? ORDER BY created_at",
    P,
)
print(f"  permission_requests: {json.dumps(perm_rows, default=str)[:1500]}")

transcripts = {}
for key, r in results.items():
    outs = rows(
        "SELECT sequence, kind, content, payload FROM agent_outputs WHERE run_id=? ORDER BY sequence",
        r["run_id"],
    )
    transcripts[key] = outs
    r["denied"] = by_run.get(r["run_id"], [])
    names = []
    for o in outs:
        blob = str(o.get("payload") or "")
        for tool in ("PowerShell", "Bash", "Write", "Edit", "WebFetch"):
            if f'"{tool}"' in blob and tool not in names:
                names.append(tool)
    r["tool_names_in_transcript"] = names
    print(f"  {key} run={r['run_id']} tool names seen in transcript payloads: {names}")

model_rows = rows(
    "SELECT r.id AS run_id, rn.model AS model FROM runs r JOIN agents a ON a.name=r.agent AND "
    "a.project_id=r.project_id LEFT JOIN runners rn ON rn.id=a.runner_id WHERE r.project_id=?",
    P,
)

out_dir = BASE / "transcripts"
out_dir.mkdir(exist_ok=True)
for key, outs in transcripts.items():
    (out_dir / f"{key}.jsonl").write_text(
        "\n".join(json.dumps(o, default=str) for o in outs), encoding="utf-8"
    )
(out_dir / "record.json").write_text(
    json.dumps(
        {
            "project": P,
            "results": results,
            "denied": denied,
            "permission_requests": perm_rows,
            "seen_requests_via_api": seen_requests,
            "models": model_rows,
        },
        indent=1,
        default=str,
    ),
    encoding="utf-8",
)
con.close()


def reasons(key):
    return [str(d.get("reason") or "") for d in results[key]["denied"]]


def names(key):
    return [str(d.get("tool_name") or "") for d in results[key]["denied"]]


print()
print("=== assertions ===")
for key in results:
    check(f"{key} run ended completed", results[key]["status"] == "completed", results[key]["status"])
check(
    "every run in this project joined to Haiku",
    bool(model_rows) and all(m["model"] == HAIKU for m in model_rows),
    str({m["model"] for m in model_rows}),
)
check("w1 not refused", not results["w1"]["denied"], str(reasons("w1")))
check("w1 wrote ps_inside.txt in the workspace", bool(workspace_files("ps_inside.txt")), str(workspace_files("ps_inside.txt")))
check("w2 refused, approver named the tool 'PowerShell'", names("w2") == ["PowerShell"] * len(names("w2")) and names("w2"), str(names("w2")))
check("w2 refused as outside", any("is outside your workspace" in r for r in reasons("w2")), str(reasons("w2")))
check("w2 wrote no ps_stray.txt", not (BASE / "ps_stray.txt").exists() and not workspace_files("ps_stray.txt"))
check("w3 refused, approver named the tool 'PowerShell'", names("w3") == ["PowerShell"] * len(names("w3")) and names("w3"), str(names("w3")))
check(
    "w3 refused with D5's network text verbatim",
    any(r.endswith(NETWORK_TEXT) and "example.com" in r for r in reasons("w3")),
    str(reasons("w3")),
)
check(
    "w4 ($env:HUB_URL) not refused -- only a 'PowerShell'-only reading allows it",
    not results["w4"]["denied"],
    str(list(zip(names("w4"), reasons("w4")))),
)
m1_req = [r for r in perm_rows if r["run_id"] == results["m1"]["run_id"]]
check("m1 opened a permission request", bool(m1_req), str(m1_req))
for r in m1_req:
    tool_input = json.loads(r["tool_input"]) if isinstance(r["tool_input"], str) else r["tool_input"]
    check(f"m1 request {r['id']} tool_name == 'PowerShell'", r["tool_name"] == "PowerShell", repr(r["tool_name"]))
    check(
        f"m1 request {r['id']} carries the script in tool_input['command']",
        isinstance(tool_input, dict) and "ps_manual.txt" in str(tool_input.get("command", "")),
        json.dumps(tool_input)[:200],
    )
check("m1 wrote ps_manual.txt once allowed", bool(workspace_files("ps_manual.txt")), str(workspace_files("ps_manual.txt")))

print()
print(f"=== {sum(ok)}/{len(ok)} ===  transcripts in {out_dir}")
sys.exit(0 if all(ok) else 1)
