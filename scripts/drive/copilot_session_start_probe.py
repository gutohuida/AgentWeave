"""No-prompt probe: initialize, session/new (model/effort from argv), set_config_option agent.

Prints each raw response (key order as sent). No session/prompt, so no premium request.
Usage: py -3.11 scripts/drive/copilot_session_start_probe.py <model|none> <effort|none> <agent-value> <out.jsonl>
"""
import json, os, queue, subprocess, sys, threading, time

MODEL, EFFORT, AGENT, OUT = sys.argv[1:5]
WS = os.path.join(os.environ.get("TEMP", "."), "copilot_probe_ws")
os.makedirs(WS, exist_ok=True)
EXE = os.path.join(os.environ["APPDATA"], "npm", "node_modules", "@github", "copilot",
                   "node_modules", "@github", "copilot-win32-x64", "copilot.exe")
argv = [EXE, "--acp", "--stdio", "--no-auto-update", "--disable-builtin-mcps"]
if MODEL != "none":
    argv += ["--model", MODEL]
if EFFORT != "none":
    argv += ["--reasoning-effort", EFFORT]
p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WS)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l.decode("utf-8", "replace")) for l in p.stdout], daemon=True).start()
threading.Thread(target=lambda: [q.put("STDERR " + l.decode("utf-8", "replace")) for l in p.stderr], daemon=True).start()
log = open(OUT, "w", encoding="utf-8")
log.write(json.dumps({"argv": argv[1:]}) + "\n")
nid = [0]


def call(method, params, wait=60):
    nid[0] += 1
    i = nid[0]
    p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n").encode())
    p.stdin.flush()
    end = time.time() + wait
    while time.time() < end:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            continue
        s = line.strip()
        try:
            o = json.loads(s)
        except Exception:
            log.write(json.dumps({"other": s[:500]}) + "\n")
            continue
        if o.get("id") == i and ("result" in o or "error" in o):
            log.write(json.dumps({"method": method, "answer": o}) + "\n")
            return o
        if o.get("method") == "session/update":
            continue
        log.write(json.dumps({"notification": o.get("method"), "type": (o.get("params") or {}).get("type"),
                              "data": (o.get("params") or {}).get("data")})[:2000] + "\n")
    raise SystemExit(f"{method}: no answer")


call("initialize", {"protocolVersion": 1, "clientCapabilities": {"_meta": {"github.com/copilot": {
    "events": ["session.model_change", "session.auto_mode_resolved", "session.tools_updated"]}}}})
new = call("session/new", {"cwd": WS, "mcpServers": []})
sid = new["result"]["sessionId"]
call("session/set_config_option", {"sessionId": sid, "configId": "agent", "value": AGENT})
time.sleep(3)
while not q.empty():
    log.write(json.dumps({"late": q.get()[:2000]}) + "\n")
p.kill()
log.close()
for line in open(OUT, encoding="utf-8"):
    o = json.loads(line)
    if "answer" in o:
        r = o["answer"].get("result") or {}
        print(o["method"], "keys:", list(r), "error:", o["answer"].get("error"))
        for c in r.get("configOptions") or []:
            print("   opt", c.get("id"), "=", c.get("currentValue"), [v.get("value") for v in c.get("options") or []][:8])
        if "models" in r:
            print("   currentModelId", r["models"].get("currentModelId"))
    else:
        print("  ", line.strip()[:300])
