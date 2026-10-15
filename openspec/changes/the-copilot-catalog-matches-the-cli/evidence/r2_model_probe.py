"""R2 probe (R1's, plus the raw key order), no model call: what the Copilot CLI the Hub spawns reports for a `--model` at session start.

Sends `initialize` and `session/new` only (no `session/prompt`, so no premium request), with the
same session-event opt-in the Hub sends (`copilot_acp.py:103-104`), then listens for a few seconds.
Usage: python r1_model_probe.py <model-or-'none'>
"""
import json, os, queue, shutil, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = sys.argv[1]
WS = os.path.join(HERE, "_probe_ws")
os.makedirs(WS, exist_ok=True)
# The binary the Hub spawns (copilot_probe.resolve_copilot_executable unwraps the npm shim),
# with the flag the Hub passes (copilot_acp.py:1944).
EXE = os.path.join(os.environ["APPDATA"], "npm", "node_modules", "@github", "copilot",
                   "node_modules", "@github", "copilot-win32-x64", "copilot.exe")
argv = [EXE, "--acp", "--stdio", "--no-auto-update", "--disable-builtin-mcps"]
if MODEL != "none":
    argv += ["--model", MODEL]
argv += sys.argv[2:]
print("ARGV", argv[1:])
p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=WS)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(l.decode("utf-8", "replace")) for l in p.stdout], daemon=True).start()
threading.Thread(target=lambda: [q.put("STDERR " + l.decode("utf-8", "replace")) for l in p.stderr], daemon=True).start()
nid = [0]


def show(line):
    line = line.strip()
    if line.startswith("STDERR"):
        print(line[:600]); return
    try:
        o = json.loads(line)
    except Exception:
        print("RAW", line[:300]); return
    if isinstance(o.get("result"), dict) and "configOptions" in o["result"]:
        opts = o["result"]["configOptions"]
        print("<<< configOptions ids:", [(c.get("id"), c.get("currentValue"), len(c.get("options") or [])) for c in opts])
        for c in opts:
            if c.get("id") not in ("mode", "allow_all", "agent"):
                print("    OPTION", c.get("id"), "current=", c.get("currentValue"))
                for v in c.get("options") or []:
                    print("       ", v.get("value"), json.dumps(v.get("_meta")))
        print("    result keys (as sent):", list(o["result"].keys()))
        print("    models:", json.dumps(o["result"].get("models"))[:6000])
        return
    params = o.get("params") or {}
    if o.get("method") == "github.com/copilot/sessionEvent":
        print("<<EVENT", params.get("type"), json.dumps(params.get("data"))[:1500]); return
    upd = params.get("update") or {}
    if upd.get("sessionUpdate") == "available_commands_update":
        print("<<N available_commands_update (elided)"); return
    if upd.get("sessionUpdate") == "config_option_update":
        print("<<N config_option_update ids:", [c.get("id") for c in upd.get("configOptions") or []]); return
    print("<<", json.dumps(o)[:1500])


def send(method, params, timeout=60):
    nid[0] += 1
    i = nid[0]
    p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n").encode())
    p.stdin.flush()
    print(">>>", method)
    end = time.time() + timeout
    while time.time() < end:
        try:
            line = q.get(timeout=1)
        except queue.Empty:
            continue
        show(line)
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("id") == i and ("result" in o or "error" in o):
            return o
    print("TIMEOUT", method)


send("initialize", {"protocolVersion": 1, "clientCapabilities": {"_meta": {"github.com/copilot": {"events": [
    "session.tools_updated", "session.warning", "session.error", "session.info",
    "session.model_change", "session.auto_mode_resolved"]}}}})
send("session/new", {"cwd": WS, "mcpServers": []})
t = time.time() + 8
while time.time() < t:
    try:
        show(q.get(timeout=0.5))
    except queue.Empty:
        pass
p.stdin.close()
try:
    p.wait(10)
except Exception:
    p.kill()

