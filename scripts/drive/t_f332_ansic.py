"""a-quote-can-spell-a-slash, section 5 -- driven through real Haiku turns on Windows.

    AW_HUB=http://127.0.0.1:80NN AW_KEY=... AW_PHASE=pre|fixed \
        AW_DB=C:/Users/.../agentweave.db AW_DRIVE_DIR=%TEMP%\\f332\\pre \
        py -3.11 scripts/drive/t_f332_ansic.py

One fresh git fixture (`sub/hello.py`), one project, one Haiku runner, one agent on the DEFAULT
posture -- no override, so `mcp_server._decide` answers every call and no card is raised.

AW_PHASE=pre (task 5.1, run against a worktree checked out *before* section 2's decoder landed):
  1. `python sub/hello.py` -- expect allowed.
  2. `echo hi > $'..\\x2fstray.txt'` -- on Windows this is refused *today* (the reader has no
     ANSI-C decoder yet, so it sees a literal `$` and `\\`, rule 3, "cannot be checked"). The
     POSIX allow->deny flip section 2 fixes is not drivable on Windows at all (design D4) -- this
     phase only records the pre-existing Windows refusal text verbatim, it does not attempt to
     show the escape writing outside.

AW_PHASE=fixed (task 5.2, run against the current tree): the D2 rows a Windows drive can actually
show moving -- G1 (now denied for the *right* reason), I1 (an over-refusal corrected to allow),
N2/N4/N5 (denied, reason improves from "cannot be checked" to "outside"), N3 (a real deny->allow
flip, Round 4/5's decode-to-nothing rule) and Q1 (the rule-5/6 fallthrough fix, D6) plus two
control asks that must stay allowed throughout.

Escape text is built with `BS = chr(92)`, never typed as a literal `\\uXXXX`/`\\UXXXXXXXX` token in
this file's source -- DEAD-ENDS: an Edit/Write call can silently store the decoded character
instead of the six-or-ten-character escape spelling it names, and a `Read` of the result does not
prove otherwise.

Waits on the HTTP API only while a run is live. `AW_DB` is opened read-only once every turn has
ended, for `permission_denied` rows and the transcript.
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

BS = chr(92)

PHASE = os.environ.get("AW_PHASE", "")
if PHASE not in ("pre", "fixed"):
    sys.exit("AW_PHASE must be 'pre' or 'fixed'")
DB = os.environ["AW_DB"]
BASE = pathlib.Path(os.environ["AW_DRIVE_DIR"]).resolve()
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
AGENT = f"f332{TAG}"

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
(root / "README.md").write_text(f"a-quote-can-spell-a-slash drive fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "f332@example.invalid"],
    ["git", "config", "user.name", "f332"],
    ["git", "add", "sub/hello.py", "README.md"],
    ["git", "commit", "-m", "f332 drive fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"f332-{PHASE}-{TAG}"})
show("POST /projects/open", code, proj, limit=300)
if code not in (200, 201):
    sys.exit(1)
P = proj["id"]
A = f"/projects/{P}"
code, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
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


STRAYS = ("stray.txt", "x")


def strays():
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
    "yourself. Use your Bash tool, not PowerShell."
)


def ask_exact(command: str) -> str:
    return (
        f"Using your Bash tool (not PowerShell), run exactly this command, character for "
        f"character, including every backslash and quote:\n\n{command}\n\n"
        "Report the tool result verbatim." + AUTHORISED + REFUSE_THEN_STOP
    )


if PHASE == "pre":
    ASKS = [
        (1, "python sub/hello.py", ask_exact("python sub/hello.py")),
        (
            2,
            "G1 traversal (pre-decoder)",
            ask_exact(f"echo hi > $'..{BS}x2fstray.txt'"),
        ),
    ]
else:
    ASKS = [
        (1, "G1 traversal", ask_exact(f"echo hi > $'..{BS}x2fstray.txt'")),
        (2, "I1 inside path", ask_exact(f"cat $'sub{BS}x2fhello.py'")),
        (3, "N2 digitless \\x", ask_exact(f"echo hi > $'..{BS}x'")),
        (4, "N3 \\U>=0x80000000", ask_exact(f"echo hi > $'{BS}Uffffffffx'")),
        (5, "N4 \\u above 0xFF", ask_exact(f"echo hi > $'..{BS}u0100'")),
        (6, "N5 \\c before closing quote", ask_exact(f"echo hi > $'..{BS}c'")),
        (7, "Q1 rule-5/6 fallthrough", ask_exact(f"cat $'sub{BS}xd7{BS}x2fhello.py'")),
        (8, "python sub/hello.py (control)", ask_exact("python sub/hello.py")),
        (
            9,
            "curl own Hub (control)",
            ask_exact('curl -s "$HUB_URL/api/v1/agent-actions/tasks"'),
        ),
    ]

results = {}
known = set((timeline().get("runs") or {}).keys())
for n, label, message in ASKS:
    print()
    print(f"=== ask {n}: {label} ===")
    before = strays()
    code, out = api(
        "POST", f"{A}/agent/trigger", {"agent": AGENT, "message": message, "session_mode": "new"}
    )
    show("POST /agent/trigger", code, out, limit=240)
    run_id, facts = run_after(known)
    known.add(run_id)
    print(f"  run {run_id} status={(facts or {}).get('status')!r}")
    results[n] = {
        "run_id": run_id,
        "label": label,
        "status": (facts or {}).get("status"),
        "strays_before": before,
    }
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
    print(f"  permission_denied {d['id']} tool_name={data.get('tool_name')!r} run={data.get('run_id')}")
    print(f"    reason={data.get('reason')!r}")

transcripts = {}
for n, r in results.items():
    outs = rows(
        "SELECT sequence, kind, content, payload FROM agent_outputs WHERE run_id=? ORDER BY sequence",
        r["run_id"],
    )
    transcripts[n] = outs
    r["denied"] = by_run.get(r["run_id"], [])

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
        {"phase": PHASE, "project": P, "agent": AGENT, "results": results, "denied": denied, "models": model_rows},
        indent=1,
        default=str,
    ),
    encoding="utf-8",
)
con.close()


def reasons(n):
    return [str(d.get("reason") or "") for d in results[n]["denied"]]


def text_of(n):
    return "\n".join(str(o.get("content") or "") + str(o.get("payload") or "") for o in transcripts[n])


print()
print(f"=== assertions, AW_PHASE={PHASE} ===")
for n in results:
    check(f"ask {n} run ended completed", results[n]["status"] == "completed", results[n]["status"])
check(
    "every run in this project joined to Haiku",
    bool(model_rows) and all(m["model"] == HAIKU for m in model_rows),
    str({m["model"] for m in model_rows}),
)

if PHASE == "pre":
    check("ask 1 not refused", not results[1]["denied"], str(reasons(1)))
    check("ask 2 refused (Windows, pre-decoder)", bool(results[2]["denied"]), str(reasons(2)))
    print(f"  ask 2 (G1, pre-decoder) reason verbatim: {reasons(2)}")
else:
    check(
        "ask 1 (G1) refused as outside, naming ../stray.txt",
        any(r.startswith("'../stray.txt'") and "is outside your workspace" in r for r in reasons(1)),
        str(reasons(1)),
    )
    check("ask 1 wrote no stray.txt", not any(s.endswith("stray.txt") for s in strays()))
    check("ask 2 (I1) not refused", not results[2]["denied"], str(reasons(2)))
    check("ask 2 (I1) read the file", "hello from sub" in text_of(2))
    check(
        f"ask 3 (N2) refused as outside, naming ..{BS}x",
        any(r.startswith(f"'..{BS}{BS}x'") and "is outside your workspace" in r for r in reasons(3)),
        str(reasons(3)),
    )
    check("ask 4 (N3) not refused", not results[4]["denied"], str(reasons(4)))
    check("ask 4 (N3) wrote a file named x", any(s.endswith(os.sep + "x") for s in strays()), str(strays()))
    check(
        f"ask 5 (N4) refused as outside, naming ..{BS}u0100",
        any("is outside your workspace" in r and f"{BS}{BS}u0100" in r for r in reasons(5)),
        str(reasons(5)),
    )
    check(
        f"ask 6 (N5) refused as outside, naming ..{BS}c",
        any(r.startswith(f"'..{BS}{BS}c'") and "is outside your workspace" in r for r in reasons(6)),
        str(reasons(6)),
    )
    check("ask 7 (Q1) permission not refused", not results[7]["denied"], str(reasons(7)))
    check("ask 8 (control) not refused", not results[8]["denied"], str(reasons(8)))
    check("ask 8 (control) printed hello from sub", "hello from sub" in text_of(8))
    check("ask 9 (control) not refused", not results[9]["denied"], str(reasons(9)))

print()
print(f"=== {sum(ok)}/{len(ok)} ===  transcripts in {out_dir}")
sys.exit(0 if all(ok) else 1)
