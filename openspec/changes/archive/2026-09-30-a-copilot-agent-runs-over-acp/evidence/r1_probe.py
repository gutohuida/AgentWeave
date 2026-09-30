"""Slice-2 R1 probe: no model call. Custom agent option, agentweave MCP (fastmcp) under Copilot, plan mode."""
import json, os, queue, subprocess, sys, threading, time

EXE = r"C:\Users\huida\AppData\Roaming\npm\node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe"
TEMP = os.environ["TEMP"]
HOME = os.path.join(TEMP, "ghcp-r1s2-home")
WS = os.path.join(TEMP, "ghcp-r1s2-ws")
MCPCFG = os.path.join(TEMP, "ghcp-r1s2-mcp.json")
PY = sys.executable
SERVER = r"C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py"
MODE = sys.argv[1] if len(sys.argv) > 1 else "agent"
EXTRA = sys.argv[2:]

with open(MCPCFG, "w", encoding="utf-8") as f:
    json.dump({"mcpServers": {"agentweave": {
        "type": "stdio", "command": PY, "args": [SERVER],
        # dead port: the adapter's online announcement must never reach :8000
        "env": {"HUB_URL": "http://127.0.0.1:9", "AW_RUN_TOKEN": "aw_run_probe", "AW_AGENT_IDENTITY": "probe-builder"},
        "tools": ["*"]},
        "envprobe": {"type": "stdio", "command": PY, "args": [os.path.join(os.path.dirname(os.path.abspath(__file__)), "r1_envsrv.py")],
        "env": {"AW_EXPANDED": "${AW_PROBE_SECRET}"}, "tools": ["*"]}}}, f)

env = dict(os.environ)
env["COPILOT_HOME"] = HOME
env["AW_PROBE_SECRET"] = "expanded-ok"
env["AW_INHERITED"] = "inherited-ok"
for k in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN"):
    env.pop(k, None)
argv = [EXE, "--acp", "--stdio", "--no-auto-update", "--disable-builtin-mcps",
        "--additional-mcp-config", "@" + MCPCFG] + EXTRA
print("ARGV", argv)
p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WS, env=env)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l.decode("utf-8", "replace")) for l in p.stdout], daemon=True).start()
threading.Thread(target=lambda: [sys.stderr.write("STDERR " + l.decode("utf-8", "replace")) for l in p.stderr], daemon=True).start()
nid = [0]

def send(method, params, timeout=60):
    nid[0] += 1
    i = nid[0]
    msg = {"jsonrpc": "2.0", "id": i, "method": method, "params": params}
    p.stdin.write((json.dumps(msg) + "\n").encode()); p.stdin.flush()
    print(">>>", json.dumps(msg)[:500])
    end = time.time() + timeout
    while time.time() < end:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            continue
        try:
            o = json.loads(line)
        except Exception:
            print("RAW", line[:300]); continue
        if o.get("id") == i and ("result" in o or "error" in o):
            print("<<<", json.dumps(o)[:8000]); return o
        if "method" in o and "id" in o:
            print("<<REQ", json.dumps(o)[:3000])
            p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": o["id"], "result": {"outcome": {"outcome": "cancelled"}}}) + "\n").encode()); p.stdin.flush()
        else:
            print("<<N", json.dumps(o)[:4000])
    print("TIMEOUT", method)

init = send("initialize", {"protocolVersion": 1, "clientCapabilities": {"_meta": {"github.com/copilot": {"events": [
    "session.mcp_servers_loaded", "session.mcp_server_status_changed", "session.tools_updated",
    "session.warning", "session.error", "session.info", "session.model_change", "session.auto_mode_resolved"]}}}})
new = send("session/new", {"cwd": WS, "mcpServers": []})
sid = new["result"]["sessionId"]
opts = new["result"].get("configOptions") or []
print("CONFIG OPTION IDS", [o.get("id") for o in opts])
for o in opts:
    if o.get("id") == "agent":
        print("AGENT OPTION", json.dumps(o))
if MODE == "agent":
    send("session/set_config_option", {"sessionId": sid, "configId": "agent", "value": "probe-builder"})
    send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "/env"}]}, timeout=60)
    send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "/mcp list"}]}, timeout=60)
    send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "/session info"}]}, timeout=30)
if MODE == "context":
    send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "/context"}]}, timeout=60)
    send("session/set_config_option", {"sessionId": sid, "configId": "agent", "value": "probe-builder"})
    send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "/context"}]}, timeout=60)
    print("SID_FOR_LOAD", sid)
if MODE == "load":
    old = os.environ["LOAD_SID"]
    send("session/load", {"sessionId": old, "cwd": WS, "mcpServers": []}, timeout=60)
    send("session/prompt", {"sessionId": old, "prompt": [{"type": "text", "text": "/context"}]}, timeout=60)
if MODE == "mcp":
    send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": "/mcp list"}]}, timeout=60)
if MODE == "plan":
    send("session/set_mode", {"sessionId": sid, "modeId": "https://agentclientprotocol.com/protocol/session-modes#plan"})
    send("session/set_config_option", {"sessionId": sid, "configId": "allow_all", "value": "on"})
t = time.time() + 3
while time.time() < t:
    try: print("<<N", q.get(timeout=0.5)[:4000].strip())
    except queue.Empty: pass
p.stdin.close()
try: p.wait(10)
except Exception: p.kill()
