"""D-1 2026-09-09: the three night changes on ONE Hub, in the order they interact.

Legs, each runnable on its own so a firing that runs out of room leaves the fixture usable:

    notice   two turns on the same agent -- the first has no grounds to claim MCP, the second
             does, because the first run's adapter announced itself. The cross-run behaviour of
             `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, which is the half no
             single-turn drive can see.
    stop     a long turn stopped mid-flight (F295's cancelled-run path), then a burst of ordinary
             requests to say whether the pool handed back a dead connection, then F274's run facts
             for the same conversation.
    ghost    the pre-spawn failure (F291): three deliveries against a pinned text-file CLI.

    AW_HUB=http://127.0.0.1:8011 AW_PROJECT=proj-... AW_AGENT_OK=... AW_AGENT_GHOST=... \
        py -3.11 scripts/drive/t_d1_0909_together.py <leg>
"""

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

LEG = sys.argv[1] if len(sys.argv) > 1 else "notice"
OK = os.environ["AW_AGENT_OK"]
GHOST = os.environ.get("AW_AGENT_GHOST", "")
ROOT = pathlib.Path(os.environ["AW_FIXTURE_ROOT"])
# A writing agent runs in its own worktree, so the canonical context it actually read is under
# the worktree, not the project root. Reading the root's copy reports ABSENT forever.
WORKTREES = ROOT / ".agentweave" / "worktrees"

# Names the marker rather than saying "the first lines of this prompt": asked the vaguer way, a
# real Haiku turn quoted the harness's own system prompt ("You are Claude Code...") and said
# nothing about AgentWeave at all.
ECHO = (
    "Immediately before this sentence your turn text carries one or more lines beginning with "
    "the marker [AgentWeave]. Reply with those lines copied exactly and nothing else. "
    "If there are none, reply exactly NO-AGENTWEAVE-NOTICE. Use no tools."
)
LONG = (
    "Write a 3000 word essay about the history of the bicycle, in full prose, "
    "one paragraph at a time. Use no tools and read no files."
)


def trigger(agent, message, conversation_id=None):
    body = {"agent": agent, "message": message}
    if conversation_id:
        # `session_mode` is the deprecated legacy field and only accepts new/resume; a turn that
        # continues an existing conversation names the conversation.
        body["conversation_id"] = conversation_id
    code, out = api("POST", f"/projects/{P}/agent/trigger", body)
    if not isinstance(out, dict):
        print(f"  trigger {agent} -> [{code}] {str(out)[:400]}")
        return None, None
    print(f"  trigger {agent} -> [{code}] conv={out.get('conversation_id')} run={out.get('run_id')}")
    return out.get("conversation_id"), out.get("run_id")


def wait_idle(agent, seconds=240):
    # The roster says `running`, not `working` -- a first draft of this script waited on the
    # wrong token and reported every turn idle in 0.0s.
    t0 = time.time()
    last = None
    while time.time() - t0 < seconds:
        code, roster = api("GET", f"/projects/{P}/agents")
        rows = roster if isinstance(roster, list) else (roster or {}).get("agents", [])
        row = next((r for r in rows if r.get("name") == agent), None)
        last = row.get("status") if row else None
        if row and last not in ("working", "running"):
            print(f"  idle after {time.time() - t0:.1f}s status={last}")
            return row
        time.sleep(3)
    print(f"  STILL working after {seconds}s (status={last})")
    return None


def chat(agent, limit=40):
    code, out = api("GET", f"/projects/{P}/agent/{agent}/chat?limit={limit}")
    return code, out


def dump_runs(agent, label):
    code, out = chat(agent)
    runs = (out or {}).get("runs", {}) if isinstance(out, dict) else {}
    entries = (out or {}).get("entries", []) if isinstance(out, dict) else []
    print(f"  --- {label}: GET chat/history [{code}] entries={len(entries)} runs={len(runs)}")
    for rid, f in runs.items():
        print(f"      {rid} status={f.get('status'):<12} exit={f.get('exit_code')} "
              f"started={f.get('started_at')} ended={f.get('ended_at')}")
    return out


def context_file(agent):
    for p in (WORKTREES / agent / ".agentweave" / "context" / f"{agent}.md",
              ROOT / ".agentweave" / "context" / f"{agent}.md"):
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def notice_shape(text):
    """Which access path a piece of delivered text describes, read the way an agent would."""
    if text is None:
        return "ABSENT"
    http = "HUB_URL" in text or "AW_RUN_TOKEN" in text
    mcp = "mcp__agentweave__" in text or "MCP tool" in text
    nothing = "no AgentWeave tool surface is available" in text
    injected = "No AgentWeave tools are injected this turn" in text
    return (f"http-form={http} mcp-form={mcp} says-you-have-nothing={nothing} "
            f"says-not-injected={injected}")


def last_reply(agent):
    code, out = chat(agent)
    entries = (out or {}).get("entries", []) if isinstance(out, dict) else []
    for e in reversed(entries):
        if (e.get("role") or e.get("author")) not in ("operator", "user"):
            body = e.get("content") or e.get("text") or ""
            if body:
                return body[:900]
    return ""


if LEG == "notice":
    conv = None
    for turn in (1, 2):
        print(f"=== notice turn {turn}")
        conv, run = trigger(OK, ECHO, conversation_id=conv)
        wait_idle(OK)
        ctx = context_file(OK)
        print(f"  context file: {notice_shape(ctx)}")
        print(f"  agent's echo of what preceded the message:\n      {last_reply(OK)[:600]!r}")
        dump_runs(OK, f"after turn {turn}")

elif LEG == "stop":
    print("=== stop: a long turn, cancelled mid-flight")
    conv, run = trigger(OK, LONG)
    time.sleep(12)
    code, out = api("POST", f"/projects/{P}/agent/{OK}/stop", {})
    print(f"  POST stop -> [{code}] {str(out)[:200]}")
    # F295: whatever the cancelled run's background task did to its connection, ordinary
    # requests must keep being answered and must not hang. Short timeout on purpose.
    t0 = time.time()
    slow = []
    for i in range(30):
        c0 = time.time()
        code, _ = api("GET", f"/projects/{P}/agents", timeout=10)
        dt = time.time() - c0
        if code != 200 or dt > 3:
            slow.append((i, code, round(dt, 2)))
        time.sleep(0.4)
    print(f"  30 ordinary requests in {time.time() - t0:.1f}s; slow-or-failed: {slow}")
    wait_idle(OK, 60)
    dump_runs(OK, "after stop")

elif LEG == "ghost":
    print("=== ghost: the pre-spawn failure")
    for i in range(3):
        trigger(GHOST, f"say hello ({i})")
        time.sleep(6)
    out = dump_runs(GHOST, "after three deliveries")
    entries = (out or {}).get("entries", []) if isinstance(out, dict) else []
    for e in entries:
        print(f"      entry {e.get('id')} state={e.get('delivery_state')} "
              f"run_id={e.get('run_id')} attempts={e.get('delivery_attempts')}")
    code, evs = api("GET", f"/projects/{P}/agent/{GHOST}/timeline")
    kinds = [(x.get("type") or x.get("kind")) for x in (evs or {}).get("events", [])]
    print(f"  timeline event kinds: {json.dumps(kinds[-14:])}")

else:
    sys.exit(f"unknown leg {LEG!r}")
