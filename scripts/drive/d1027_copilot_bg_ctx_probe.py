"""Live Copilot-over-ACP probe for two questions (2026-10-27, FinOps Architect run-e7327f0e14e9).

bg   -- does `session/prompt` stay open while a background sub-agent the root launched is running,
        after the root has already written its final reply? (A Hub turn ends only when it returns.)
ctx  -- does `--context long_context` (or a session config option) give a 1M `usage_update.size`?

Usage: <python> scripts/drive/d1027_copilot_bg_ctx_probe.py bg  <model> <out.jsonl>
       <python> scripts/drive/d1027_copilot_bg_ctx_probe.py ctx <model> <default|long_context> <out.jsonl>
Each mode spends one premium request (bg: plus the sub-agent's). Workspace: %TEMP%/copilot_probe_ws.
"""
import json, os, queue, subprocess, sys, threading, time

MODE = sys.argv[1]
MODEL = sys.argv[2]
TIER = sys.argv[3] if MODE == "ctx" else None
OUT = sys.argv[-1]
WS = os.path.join(os.environ.get("TEMP", "."), "copilot_probe_ws")
os.makedirs(WS, exist_ok=True)
EXE = os.path.join(os.environ["APPDATA"], "npm", "node_modules", "@github", "copilot",
                   "node_modules", "@github", "copilot-win32-x64", "copilot.exe")
argv = [EXE, "--acp", "--stdio", "--no-auto-update", "--disable-builtin-mcps", "--allow-all-tools"]
if MODEL != "auto":
    argv += ["--model", MODEL]
if TIER and TIER != "default":
    argv += ["--context", TIER]
p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WS)
q: "queue.Queue[str]" = queue.Queue()
threading.Thread(target=lambda: [q.put(l.decode("utf-8", "replace")) for l in p.stdout], daemon=True).start()
threading.Thread(target=lambda: [q.put("STDERR " + l.decode("utf-8", "replace")) for l in p.stderr], daemon=True).start()
log = open(OUT, "w", encoding="utf-8")
T0 = time.time()
nid = [0]
sizes: list = []


def note(kind, **kw):
    rec = {"t": round(time.time() - T0, 1), "kind": kind, **kw}
    log.write(json.dumps(rec)[:3000] + "\n")
    log.flush()
    if kind not in ("chunk",):
        print(json.dumps(rec)[:400], flush=True)


def send(obj):
    p.stdin.write((json.dumps(obj) + "\n").encode())
    p.stdin.flush()


def handle(o):
    """One inbound message that is not the answer being waited for."""
    m = o.get("method")
    if m == "session/request_permission" and "id" in o:
        opts = (o.get("params") or {}).get("options") or []
        pick = next((x for x in opts if str(x.get("kind", "")).startswith("allow")), opts[0] if opts else None)
        send({"jsonrpc": "2.0", "id": o["id"],
              "result": {"outcome": {"outcome": "selected", "optionId": pick and pick.get("optionId")}}})
        note("permission_allowed", option=pick and pick.get("optionId"))
        return
    if m == "session/update":
        u = (o.get("params") or {}).get("update") or {}
        su = u.get("sessionUpdate")
        if su == "agent_message_chunk":
            note("chunk", text=(u.get("content") or {}).get("text", ""))
        elif su == "usage_update":
            sizes.append(u.get("size"))
            note("usage_update", used=u.get("used"), size=u.get("size"))
        elif su in ("tool_call", "tool_call_update"):
            note(su, title=u.get("title"), status=u.get("status"))
        else:
            note("update", su=su)
        return
    if m == "github.com/copilot/sessionEvent":
        prm = o.get("params") or {}
        ev = prm.get("event") or prm
        typ = ev.get("type") or prm.get("type")
        if typ and (typ.startswith("subagent") or typ.startswith("session.") or typ.startswith("assistant.")
                    or typ.startswith("system.")):
            note("raw", type=typ, agentId=prm.get("agentId") or ev.get("agentId"),
                 data={k: v for k, v in (ev.get("data") or {}).items()
                       if k in ("agentName", "model", "cancelled", "durationMs", "totalToolCalls",
                                "tokenLimit", "currentModel", "newModel", "chosenModel")})
        return
    if "id" in o and "method" in o:
        send({"jsonrpc": "2.0", "id": o["id"], "error": {"code": -32601, "message": "probe"}})
        note("server_request_refused", method=m)
        return
    note("other", body=str(o)[:300])


def call(method, params, wait=60.0):
    nid[0] += 1
    i = nid[0]
    send({"jsonrpc": "2.0", "id": i, "method": method, "params": params})
    end = time.time() + wait
    while time.time() < end:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            continue
        s = line.strip()
        if s.startswith("STDERR"):
            continue
        try:
            o = json.loads(s)
        except Exception:
            continue
        if o.get("id") == i and ("result" in o or "error" in o):
            note("answer", method=method, result_keys=list((o.get("result") or {}).keys()),
                 stop=(o.get("result") or {}).get("stopReason"), error=o.get("error"))
            return o
        handle(o)
    note("no_answer", method=method)
    return None


def drain(seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            s = q.get(timeout=1).strip()
        except queue.Empty:
            continue
        try:
            handle(json.loads(s))
        except Exception:
            pass


events = ["subagent.started", "subagent.completed", "subagent.failed", "session.model_change",
          "session.auto_mode_resolved", "session.compaction_start", "session.compaction_complete",
          # Turn-boundary signals the SDK surface exposes (d1027_copilot_sdk_probe.mjs): does ACP
          # forward them when subscribed?
          "assistant.turn_end", "session.idle", "session.background_tasks_changed",
          "session.usage_info", "system.notification"]
call("initialize", {"protocolVersion": 1,
                    "clientCapabilities": {"_meta": {"github.com/copilot": {"events": events}}}})
new = call("session/new", {"cwd": WS, "mcpServers": []})
sid = new["result"]["sessionId"]
opts = [(c.get("id"), c.get("currentValue"), [v.get("value") for v in c.get("options") or []][:12])
        for c in new["result"].get("configOptions") or []]
note("config_options", options=opts)
log.write(json.dumps({"session_new_result": new["result"]}) + "\n")

if MODE == "ctx":
    call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "Reply with just OK."}]},
         wait=180)
    drain(3)
    note("summary", mode="ctx", model=MODEL, tier=TIER, usage_sizes=sorted({s for s in sizes if s}))
else:
    prompt = (
        "Use your task tool to start ONE background agent (agent_type 'task', mode 'background') whose "
        "job is: run the PowerShell command `Start-Sleep -Seconds 60; 'bg-done'` and report its output. "
        "Do NOT wait for it, do not read it, do not poll it. As soon as it has started, reply with "
        "exactly the word LAUNCHED and end your turn."
    )
    t_send = time.time() - T0
    call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]}, wait=400)
    note("prompt_returned_after", seconds=round(time.time() - T0 - t_send, 1))
    note("draining_after_return")
    drain(90)
p.kill()
log.close()
