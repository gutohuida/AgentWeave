"""Sweep A (2026-10-18): operator-route probes for Conversations, Runs, Agents (no agent turn is
expected to start; a probe that does start one is reported).

    py -3.11 scripts/drive/s1018_A_misc.py
"""

import json
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1018_A_lib import P, q, req  # noqa: E402

base = f"/projects/{P}"


def s(method, path, body=None):
    status, res = req(method, path, body)
    print(f"\n## {method} {path} {json.dumps(body, ensure_ascii=False) if body is not None else ''}\n-> {status} {json.dumps(res, ensure_ascii=False)[:800]}")
    return status, res


runs_before = q("select count(*) n from runs where project_id=?", P)[0]["n"]
# work_dir doors (F669)
for wd in (".agentweave", ".agentweave/worktrees/alpha", ".AGENTWEAVE\\worktrees", "C:\\Windows", "no-such-dir"):
    s("POST", base + "/agent/trigger", {"agent": "alpha", "message": "noop", "work_dir": wd})
# conversations
_, convs = s("GET", base + "/agent/alpha/conversations")
convs = convs if isinstance(convs, list) else convs.get("conversations", [])
c0 = convs[-1]["id"] if convs else None
s("PATCH", base + f"/agent/alpha/conversations/{c0}", {"title": "Renamed by sweep A ✓"})
s("PATCH", base + f"/agent/alpha/conversations/{c0}", {"title": ""})
s("PATCH", base + f"/agent/alpha/conversations/{c0}", {"title": "x" * 1000})
s("POST", base + f"/agent/alpha/conversations/{c0}/archive")
s("POST", base + "/agent/trigger", {"agent": "alpha", "message": "noop", "conversation_id": c0})
s("POST", base + f"/agent/alpha/conversations/{c0}/archive")
s("POST", base + f"/agent/alpha/conversations/{c0}/unarchive")
s("PATCH", base + "/agent/alpha/conversations/conv-nope", {"title": "x"})
s("POST", base + "/agent/board/conversations/" + str(c0) + "/archive")
s("GET", base + f"/agent/alpha/chat/{c0}")
s("GET", base + f"/conversations")
# sessions, divergences
s("GET", base + "/agent/sessions/alpha")
s("GET", base + "/tasks/divergences/recent")
# tasks: assignee must be an open agent (F642)
s("POST", base + "/tasks", {"title": "t ghost", "assignee": "ghost"})
s("POST", base + "/agents/boards/archive")
s("POST", base + "/tasks", {"title": "t archived", "assignee": "boards"})
s("POST", base + "/agents/boards/unarchive")
s("POST", base + "/tasks", {"title": "t board", "id": "board"})
# messages: operator -> agent with no runner (F623), to operator, to ghost
s("PATCH", base + "/agents/arch1", {"runner_id": None})
s("POST", base + "/messages", {"to": "arch1", "content": "Please read README when you can."})
s("POST", base + "/messages", {"to": "ghost", "content": "hi"})
s("POST", base + "/messages", {"to": "operator", "content": "hi"})
s("POST", base + "/messages", {"from": "alpha", "to": "board", "content": "spoof"})
s("POST", base + "/agent/trigger", {"agent": "arch1", "message": "Are you there?"})
print("queue arch1:", q("select state, delivery_attempts, content from inbound_queue_entries where project_id=? and agent='arch1'", P))
# stop an idle agent; stop with unknown run
s("POST", base + "/agent/alpha/stop", {})
# agent-context and the first-turn text
st, ctx = req("GET", base + "/agents/agent-context?agent=alpha")
print("\nagent-context:", st, (json.dumps(ctx)[:300] if st >= 300 else ""))
if st < 300:
    text = ctx.get("context") if isinstance(ctx, dict) else str(ctx)
    for needle in ("no tools", "not have", "vault", "mcp__agentweave__", "aw-tool", "send_message"):
        i = (text or "").find(needle)
        print(f"  {needle!r}:", "no" if i < 0 else repr(text[max(0, i - 100):i + 140]))
runs_after = q("select count(*) n from runs where project_id=?", P)[0]["n"]
print("\nruns started by these probes:", runs_after - runs_before)
print(q("select id, agent, status from runs where project_id=? order by started_at desc limit 3", P))
