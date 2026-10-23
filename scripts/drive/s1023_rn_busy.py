"""2026-10-23 Runs drive: refusal probes on stop/trigger, then a busy agent.

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_rn_busy.py <agent> <idle-agent> <old-conversation>

1. Free probes: stop an idle agent, an unknown agent; trigger with a bad model / effort /
   permission override, an unknown agent, an unknown conversation, another agent's conversation.
   For each refused trigger: did it leave a conversation or a queue entry behind?
2. A turn in a fresh conversation runs a 200 s sleep. While it runs: the roster's
   `running_conversation_id`; the old conversation in Chromium (F844: "busy in ...", no Stop);
   a message sent into the old conversation (queued?). Then stop, stop again at once, and again
   after it settled. Then survivors of the tree (F987 general) are listed and killed.
"""

import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_rn_lib import B, P, descendants, e2e, procs, q, req, trigger, wait_run  # noqa: E402

agent, idle, old_conv = sys.argv[1], sys.argv[2], sys.argv[3]


def counts():
    return (
        q("select count(*) n from conversations where project_id=?", P)[0]["n"],
        q("select count(*) n from inbound_queue_entries where project_id=?", P)[0]["n"],
    )


def probe(label, method, path, body=None):
    before = counts()
    status, res = req(method, path, body)
    after = counts()
    left = "" if before == after else f"  LEFT BEHIND conversations/entries {before} -> {after}"
    print(f"[{label}] {method} {path} -> {status}: {json.dumps(res, ensure_ascii=False)[:500]}{left}")
    return status, res


print("== 1. refusal probes")
probe("stop idle", "POST", f"{B}/agent/{idle}/stop")
probe("stop unknown", "POST", f"{B}/agent/ghost/stop")
base = {"agent": agent, "message": "reply OK"}
probe("bad model", "POST", f"{B}/agent/trigger", {**base, "overrides": {"model": "claude-nope-9"}})
probe("bad effort", "POST", f"{B}/agent/trigger", {**base, "overrides": {"effort": "ludicrous"}})
probe("bad perm", "POST", f"{B}/agent/trigger", {**base, "overrides": {"permission_mode": "yolo"}})
probe("bad key", "POST", f"{B}/agent/trigger", {**base, "overrides": {"colour": "red"}})
probe("unknown agent", "POST", f"{B}/agent/trigger", {**base, "agent": "ghost"})
probe("unknown conv", "POST", f"{B}/agent/trigger", {**base, "conversation_id": "conv-000000000000"})
probe("other agent's conv", "POST", f"{B}/agent/trigger", {**base, "agent": idle, "conversation_id": old_conv})

print("\n== 2. busy agent")
CMD = 'py -3.11 -c "import time; [time.sleep(1) for i in range(200)]"'
status, res = trigger(
    agent,
    "Run exactly this shell command once, with a 600000 ms timeout, and wait for it to finish "
    f"before replying. Do not run it in the background. Command: {CMD}",
    fresh=True,
)
print("busy trigger ->", status, json.dumps(res)[:300])
run_id, busy_conv = res.get("run_id"), res.get("conversation_id")
sleeper = None
for _ in range(80):
    row = q("select status, pid from runs where id=?", run_id)
    table = procs()
    hits = [p for p, r in table.items() if "range(200)" in r["cmd"] and r["name"].lower() == "python.exe"]
    if hits and row and row[0]["status"] == "running":
        sleeper = hits[0]
        break
    if row and row[0]["status"] not in ("running", "queued", "starting", "pending"):
        break
    time.sleep(3)
print("sleeper:", sleeper)
pid = q("select pid from runs where id=?", run_id)[0]["pid"]
table = procs()
tree = [pid] + descendants(table, pid) if pid in table else []

status, roster = req("GET", f"{B}/agents")
for a in roster if isinstance(roster, list) else []:
    if a.get("name") == agent:
        print("roster:", {k: a.get(k) for k in ("status", "running_conversation_id", "current_run_id")})
print("busy conversation:", busy_conv)

try:
    from uiharness import Judge

    with Judge("s1023-rn-busy", hub=e2e.hub(), key=e2e.key()) as j:
        page = j.page(P, mode="light", query=f"agent={agent}&conversation={old_conv}")
        page.wait_for_timeout(6000)
        head = page.locator("main").first
        text = " ".join((head.text_content() or "").split())
        print("OLD CONV text head:", text[:400])
        for needle in ("busy in", "waiting on your answer", "is responding", "Stop turn", "will queue"):
            print(f"   contains {needle!r}:", needle in text or page.get_by_text(needle).count() > 0)
        ph = page.locator("textarea").first
        print("   composer placeholder:", ph.get_attribute("placeholder") if ph.count() else None)
        stops = page.get_by_role("button", name="Stop turn")
        print("   Stop turn buttons:", stops.count())
        j.shot(page, "old_conv_while_busy")
        page2 = j.page(P, mode="light", query=f"agent={agent}&conversation={busy_conv}")
        page2.wait_for_timeout(5000)
        print("   BUSY CONV Stop turn buttons:", page2.get_by_role("button", name="Stop turn").count())
        j.shot(page2, "busy_conv")
except Exception as exc:  # noqa: BLE001
    print("UI step failed:", type(exc).__name__, exc)

status, res = trigger(agent, "When you are free, reply with the single word OK.", conversation=old_conv)
print("message into old conversation while busy ->", status, json.dumps(res)[:400])
queued_run = res.get("run_id")

t0 = time.time()
s1 = req("POST", f"{B}/agent/{agent}/stop")
s2 = req("POST", f"{B}/agent/{agent}/stop")
print("stop #1 ->", s1[0], json.dumps(s1[1])[:300])
print("stop #2 (at once) ->", s2[0], json.dumps(s2[1])[:300])
print("busy run settled:", wait_run(run_id, 2), f"+{time.time() - t0:.1f}s")
s3 = req("POST", f"{B}/agent/{agent}/stop")
print("stop #3 (after settle) ->", s3[0], json.dumps(s3[1])[:300])
time.sleep(6)
after = procs()
alive = [p for p in tree if p in after and after[p]["name"] == table[p]["name"]]
print("survivors:", [(p, after[p]["name"]) for p in alive])
for p in alive:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p)], capture_output=True)
time.sleep(2)
print("after kill, alive:", [p for p in alive if p in procs()])
runs = q("select id, conversation_id, status, started_at from runs where agent=? order by started_at", agent)
for r in runs:
    print("  run", r)
entries = q(
    "select id, conversation_id, state, delivered_in_run_id, waiting_reason, substr(content,1,60) c from inbound_queue_entries "
    "where project_id=? order by sequence",
    P,
)
for e in entries[-4:]:
    print("  entry", e)
print("queued run id from trigger:", queued_run)
