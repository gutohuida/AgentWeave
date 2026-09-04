"""Task 9.4 -- the live drive: a real Haiku turn writes outside its workspace, and the Hub says so.

F115 was found by a live drive and could not be found by the suite. Phases 9.1-9.3 have now proved
the suite green over this tree, which is exactly the thing that is not proof of behaviour. This
drives the product:

  Leg A -- a turn that writes only inside its own worktree leaves `Run.outside_workspace_writes`
           at `[]` (*observed, and nothing left*) and emits no notice. `[]` is unreachable unless
           `watch` really runs, so this is the leg that proves the NULL/`[]` distinction is a fact
           and not a docstring.
  Leg B -- a turn handed two absolute paths outside its worktree, one in the project root and one
           outside the project entirely, records BOTH destinations on the run row with their kinds,
           and emits one `agent_wrote_outside_workspace` per destination.
  Leg C -- the notice renders. N-21 found the UI had no `summaryForEvent` case at all and the row
           displayed as its own event name twice over; the case exists now, so the drive runs the
           real payloads the Hub just wrote through the real function.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=... AW_AGENT=... AW_ROOT=... AW_ELSEWHERE=... \
        py -3.11 scripts/drive/t_awrite_p9_recorded.py

Polls the HTTP API, never sqlite, and never in a tight loop -- N-19 measured a concurrent read
killing the very run it was watching (F279).
"""

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api, show  # noqa: E402

AGENT = os.environ["AW_AGENT"]
ROOT = pathlib.Path(os.environ["AW_ROOT"])
ELSEWHERE = pathlib.Path(os.environ["AW_ELSEWHERE"])
WORKTREE = ROOT / ".agentweave" / "worktrees" / AGENT
REPO = pathlib.Path(__file__).resolve().parents[2]

ok = []


def check(label, condition, detail=""):
    ok.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}{('  -- ' + detail) if detail else ''}")


def timeline():
    _, body = api("GET", f"/projects/{P}/agents/{AGENT}/timeline?limit=200")
    return body if isinstance(body, dict) else {}


def run_after(known, deadline=420):
    """Wait for a run this agent has that is not in *known*, and return (run_id, facts)."""
    end = time.time() + deadline
    seen = (None, None)
    while time.time() < end:
        runs = timeline().get("runs") or {}
        fresh = {r: f for r, f in runs.items() if r not in known}
        if fresh:
            seen = sorted(fresh.items(), key=lambda kv: kv[1]["started_at"])[-1]
            if seen[1].get("status") not in ("started", "running"):
                return seen
        time.sleep(4)
    return seen


def notices(run_id=None):
    """Every `agent_wrote_outside_workspace` row, optionally only this run's.

    Scoped by run rather than counted globally so re-running the drive against a project that
    already has notices in it cannot turn a correct product into a red harness.
    """
    _, body = api("GET", f"/projects/{P}/events/history?limit=400")
    rows = body.get("events", body) if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return []
    raised = [e for e in rows if e.get("type") == "agent_wrote_outside_workspace"]
    if run_id is None:
        return raised
    return [e for e in raised if payload_of(e).get("run_id") == run_id]


def payload_of(event):
    return event.get("payload") or event.get("data") or {}


def send(message):
    code, out = api(
        "POST",
        f"/projects/{P}/agent/trigger",
        {"agent": AGENT, "message": message, "session_mode": "new"},
    )
    show("POST /agent/trigger", code, out, limit=300)
    return code, out


def same_path(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


before = set((timeline().get("runs") or {}).keys())

# ---------------------------------------------------------------- leg A: watched, and clean
print("=== leg A -- a turn that stays inside its own worktree ===")
send(
    "Create a file named inside-note.md in your current working directory, containing the single "
    "line 'stayed put'. Use a relative path. Do not write any file anywhere else, and do not use "
    "an absolute path. Then stop."
)
run_a, facts_a = run_after(before)
print(f"  run {run_a} -> {json.dumps(facts_a, default=str)}")
check(
    "leg A run finished",
    bool(facts_a) and facts_a.get("status") == "completed",
    f"status={(facts_a or {}).get('status')!r}",
)
writes_a = (facts_a or {}).get("outside_workspace_writes")
check(
    "the run was WATCHED, not skipped -- the column is not NULL",
    writes_a is not None,
    f"outside_workspace_writes={writes_a!r}",
)
check(
    "nothing left the workspace -- the column is []",
    writes_a == [],
    f"outside_workspace_writes={writes_a!r}",
)
check(
    "the agent really did write inside its worktree",
    (WORKTREE / "inside-note.md").exists(),
    str(WORKTREE / "inside-note.md"),
)
clean_notices = notices(run_a)
check("no notice was raised for a clean run", len(clean_notices) == 0, f"{len(clean_notices)}")

# ---------------------------------------------------------------- leg B: two strays, two notices
print()
print("=== leg B -- two absolute paths outside the worktree ===")
stray_project = ROOT / "stray-in-project.md"
stray_outside = ELSEWHERE / "stray-outside.md"
before = set((timeline().get("runs") or {}).keys())
send(
    "Write two files, each containing the single line 'landed here', using the Write tool and "
    f"these exact absolute paths:\n1. {stray_project}\n2. {stray_outside}\n"
    "Write them exactly where I said, do not create them anywhere else, and then stop."
)
run_b, facts_b = run_after(before)
print(f"  run {run_b} -> status={(facts_b or {}).get('status')!r}")
check(
    "leg B run finished",
    bool(facts_b) and facts_b.get("status") == "completed",
    f"status={(facts_b or {}).get('status')!r}",
)
writes_b = (facts_b or {}).get("outside_workspace_writes") or []
print("  Run.outside_workspace_writes:")
print(json.dumps(writes_b, indent=2))

check(
    "the agent really did write into the project root", stray_project.exists(), str(stray_project)
)
check("the agent really did write outside the project", stray_outside.exists(), str(stray_outside))

kinds = {e.get("kind"): e for e in writes_b}
check("the project-root write is recorded, as kind 'project'", "project" in kinds, str(list(kinds)))
check(
    "the wholly-outside write is recorded, as kind 'outside'", "outside" in kinds, str(list(kinds))
)
check(
    "neither destination reads as 'inside' or 'unknown'",
    not {"inside", "unknown"} & set(kinds),
    str(list(kinds)),
)
for kind, expect in (("project", stray_project), ("outside", stray_outside)):
    entry = kinds.get(kind) or {}
    check(
        f"  the {kind} entry names the tool that wrote it",
        entry.get("tool") == "Write",
        f"tool={entry.get('tool')!r}",
    )
    check(
        f"  the {kind} entry carries the path the tool declared",
        same_path(entry.get("path") or "", expect),
        f"path={entry.get('path')!r}",
    )
    check(
        f"  the {kind} entry counts at least one call",
        (entry.get("calls") or 0) >= 1,
        f"calls={entry.get('calls')!r}",
    )
check(
    "no overflow sentinel for two destinations",
    not any(e.get("kind") == "overflow" for e in writes_b),
)

print()
print("=== the operator's notice ===")
raised = notices(run_b)
for e in raised:
    print(f"  {e.get('type')}  severity={e.get('severity')!r}  agent={e.get('agent')!r}")
    print(f"    {json.dumps(payload_of(e), default=str)}")
check("one notice per destination, and no more", len(raised) == 2, f"{len(raised)} raised")
check(
    "each notice is a warning, not an error and not a refusal",
    all(e.get("severity") == "warn" for e in raised),
    str(sorted({e.get("severity") for e in raised})),
)
payloads = [payload_of(e) for e in raised]
check("every notice names this run", all(p.get("run_id") == run_b for p in payloads))
check("every notice names the agent", all(p.get("agent") == AGENT for p in payloads))
check(
    "the notices name the same two destinations the row does",
    {p.get("destination_kind") for p in payloads} == {"project", "outside"},
    str(sorted(str(p.get("destination_kind")) for p in payloads)),
)
# Scans only the names the *product* chose, never the run's own data -- N-19 measured the wider
# scan hitting `refus` inside a pytest temp directory called `test_..._refus0`.
chosen = json.dumps(
    [
        {
            "type": e.get("type"),
            "severity": e.get("severity"),
            "keys": sorted(payload_of(e).keys()),
            "kind": payload_of(e).get("destination_kind"),
        }
        for e in raised
    ]
).lower()
check("no notice reads as a refusal", "refus" not in chosen and "deni" not in chosen)

# ---------------------------------------------------------------- leg C: it renders
print()
print("=== leg C -- the notice renders, on the payloads the Hub just wrote ===")
ui = REPO / "hub" / "ui"
bundle = ui / "node_modules" / ".cache" / "awrite-p9-eventSummary.cjs"
bundle.parent.mkdir(parents=True, exist_ok=True)
build = subprocess.run(
    [
        str(ui / "node_modules" / ".bin" / "esbuild.cmd"),
        "src/lib/eventSummary.ts",
        "--bundle",
        "--format=cjs",
        "--platform=node",
        f"--outfile={bundle}",
    ],
    cwd=ui,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
rendered = []
if build.returncode != 0:
    print(build.stderr[-1500:])
else:
    script = (
        "const m = require(process.argv[1]);"
        "const rows = JSON.parse(process.argv[2]);"
        "for (const r of rows) console.log(m.summaryForEvent(r.type, r.payload));"
    )
    run = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(bundle),
            json.dumps([{"type": e.get("type"), "payload": payload_of(e)} for e in raised]),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if run.returncode == 0:
        rendered = [line for line in run.stdout.strip().splitlines() if line.strip()]
    else:
        print(run.stderr[-1500:])
for line in rendered:
    print(f"  {line}")
check("the real summariser renders both notices", len(rendered) == 2, f"{len(rendered)} lines")
check(
    "neither renders as its own event name",
    bool(rendered) and all("agent_wrote_outside_workspace" not in line for line in rendered),
)
check(
    "the project-root notice says where it landed",
    any("the project directory" in line for line in rendered),
)
check(
    "the wholly-outside notice says it left the workspace",
    any(line.rstrip().split(":")[0].endswith("wrote outside its workspace") for line in rendered),
)
check(
    "both notices name the tool and the path",
    bool(rendered) and all("Write → " in line for line in rendered),
)

print()
print(f"=== {sum(ok)}/{len(ok)} ===")
sys.exit(0 if all(ok) else 1)
