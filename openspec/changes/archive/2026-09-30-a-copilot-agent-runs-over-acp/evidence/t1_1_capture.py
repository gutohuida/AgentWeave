"""Task 1.1 capture: one ACP prompt exercising a custom agent marker, a file write, three shell
commands, a web fetch, and an MCP call, under the Hub's real mcp_server.py against a dead port.
Every session/request_permission is answered allow_once, with params recorded."""
import json, os, queue, subprocess, sys, threading, time

EXE = r"C:\Users\huida\AppData\Roaming\npm\node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe"
TEMP = os.environ["TEMP"]
HOME = os.path.join(TEMP, "ghcp-t1-home")
WS = os.path.join(TEMP, "ghcp-t1-ws")
MCPCFG = os.path.join(TEMP, "ghcp-t1-mcp.json")
PY = sys.executable
SERVER = r"C:\Users\huida\Documents\projects\AgentWeave\hub\hub\mcp_server.py"
DEAD_PORT = 9
AGENT_NAME = "probe-writer"
MARKER = "AW-MARKER-5521"

os.makedirs(os.path.join(WS, ".github", "agents"), exist_ok=True)
os.makedirs(HOME, exist_ok=True)

with open(os.path.join(WS, ".github", "agents", f"{AGENT_NAME}.agent.md"), "w", encoding="utf-8") as f:
    f.write(
        "---\n"
        f"name: {AGENT_NAME}\n"
        'description: "Probe agent for task 1.1 capture"\n'
        'tools: ["*"]\n'
        "---\n\n"
        f"Remember this marker: {MARKER}\n"
    )

with open(MCPCFG, "w", encoding="utf-8") as f:
    json.dump(
        {
            "mcpServers": {
                "agentweave": {
                    "type": "stdio",
                    "command": PY,
                    "args": [SERVER],
                    "env": {
                        "HUB_URL": f"http://127.0.0.1:{DEAD_PORT}",
                        "AW_RUN_TOKEN": "aw_run_probe",
                        "AW_AGENT_IDENTITY": AGENT_NAME,
                    },
                    "tools": ["*"],
                }
            }
        },
        f,
    )

env = dict(os.environ)
env["COPILOT_HOME"] = HOME
for k in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN"):
    env.pop(k, None)

COPILOT_RAW_EVENTS = [
    "session.error", "session.warning", "session.info",
    "session.mcp_servers_loaded", "session.mcp_server_status_changed",
    "session.model_change", "session.auto_mode_resolved", "session.tools_updated",
    "permission.requested",
    "tool.execution_start", "tool.execution_complete",
    "session.mode_changed", "exit_plan_mode.requested",
]

argv = [
    EXE, "--acp", "--stdio", "--no-auto-update", "--disable-builtin-mcps",
    "--additional-mcp-config", "@" + MCPCFG,
]
print("ARGV", argv)
p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WS, env=env)

wire = []  # every JSON-RPC message in wire order: {"dir": "send"|"recv", "msg": obj}
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l.decode("utf-8", "replace")) for l in p.stdout], daemon=True).start()
threading.Thread(target=lambda: [sys.stderr.write("STDERR " + l.decode("utf-8", "replace")) for l in p.stderr], daemon=True).start()
nid = [0]
permission_requests = []


def send(method, params, timeout=90, is_request=True):
    msg = {"jsonrpc": "2.0", "method": method, "params": params}
    if is_request:
        nid[0] += 1
        msg["id"] = nid[0]
    wire.append({"dir": "send", "msg": msg})
    p.stdin.write((json.dumps(msg) + "\n").encode())
    p.stdin.flush()
    print(">>>", json.dumps(msg)[:500])
    if not is_request:
        return None
    end = time.time() + timeout
    while time.time() < end:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            continue
        try:
            o = json.loads(line)
        except Exception:
            print("RAW", line[:300])
            continue
        wire.append({"dir": "recv", "msg": o})
        if o.get("id") == msg.get("id") and ("result" in o or "error" in o):
            print("<<<", json.dumps(o)[:2000])
            return o
        if "method" in o and "id" in o:
            print("<<REQ", json.dumps(o)[:3000])
            if o["method"] == "session/request_permission":
                permission_requests.append(o["params"])
                opts = o["params"].get("options", [])
                chosen = next((op for op in opts if op.get("kind") == "allow_once"), None)
                if chosen is None:
                    chosen = opts[0] if opts else None
                print("PERMISSION OPTIONS", json.dumps(opts))
                if chosen is not None:
                    resp = {"jsonrpc": "2.0", "id": o["id"], "result": {"outcome": {"outcome": "selected", "optionId": chosen["optionId"]}}}
                else:
                    resp = {"jsonrpc": "2.0", "id": o["id"], "result": {"outcome": {"outcome": "cancelled"}}}
            else:
                resp = {"jsonrpc": "2.0", "id": o["id"], "result": {}}
            wire.append({"dir": "send", "msg": resp})
            p.stdin.write((json.dumps(resp) + "\n").encode())
            p.stdin.flush()
        else:
            print("<<N", o.get("params", {}).get("update", {}).get("sessionUpdate") or o.get("params", {}).get("type") or o.get("method"))
    print("TIMEOUT", method)
    return None


init = send("initialize", {
    "protocolVersion": 1,
    "clientCapabilities": {"_meta": {"github.com/copilot": {"events": COPILOT_RAW_EVENTS}}},
})
new = send("session/new", {"cwd": WS, "mcpServers": []})
sid = new["result"]["sessionId"]
opts = new["result"].get("configOptions") or []
agent_opt = next((o for o in opts if o.get("id") == "agent"), None)
print("AGENT OPTION BEFORE SELECT", json.dumps(agent_opt))

sel = send("session/set_config_option", {"sessionId": sid, "configId": "agent", "value": AGENT_NAME})
sel_opts = (sel or {}).get("result", {}).get("configOptions") or []
agent_opt_after = next((o for o in sel_opts if o.get("id") == "agent"), None)
print("AGENT OPTION AFTER SELECT", json.dumps(agent_opt_after))

prompt_text = (
    "Quote the marker in your agent instructions. "
    "Then create file probe.txt containing hi. "
    "Then run each of these shell commands separately: "
    "`Set-Content probe2.txt hi`, then `Get-ChildItem`, then "
    f"`curl.exe -s http://127.0.0.1:{DEAD_PORT}/`. "
    f"Then fetch `http://127.0.0.1:{DEAD_PORT}/` with your web fetch tool. "
    "Then call agentweave-list_tasks."
)
result = send("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt_text}]}, timeout=180)
print("PROMPT RESULT", json.dumps(result)[:1000] if result else None)

# drain trailing notifications
t = time.time() + 4
while time.time() < t:
    try:
        line = q.get(timeout=0.5)
        o = json.loads(line)
        wire.append({"dir": "recv", "msg": o})
        print("<<N(tail)", o.get("params", {}).get("update", {}).get("sessionUpdate") or o.get("params", {}).get("type") or o.get("method"))
    except queue.Empty:
        pass
    except Exception:
        pass

p.stdin.close()
try:
    p.wait(10)
except Exception:
    p.kill()

print("PERMISSION REQUEST COUNT", len(permission_requests))
for i, pr in enumerate(permission_requests):
    print(f"PERMISSION {i}", json.dumps(pr)[:1500])

out_path = os.path.join(TEMP, "ghcp-t1-wire.jsonl")
with open(out_path, "w", encoding="utf-8") as f:
    for entry in wire:
        f.write(json.dumps(entry) + "\n")
print("WIRE SAVED", out_path, len(wire), "messages")
