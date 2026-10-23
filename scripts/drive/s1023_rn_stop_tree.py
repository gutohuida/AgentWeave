"""F987 generalised: does Stop on a run blocked in a plain long shell call leave its tree alive?

    AW_E2E_STATE=... AW_P=proj-... py -3.11 scripts/drive/s1023_rn_stop_tree.py <agent> [--keep]

Triggers the agent to run a 300 s python sleep loop, waits until the run is `running` and the
sleep process exists, snapshots the run's process tree, POSTs stop, then reports which of the
tree's processes survive, whether the run's workspace directory can be renamed (a held handle
refuses it), and kills survivors unless --keep.
"""

import json
import os
import subprocess
import sys
import time

from s1023_rn_lib import B, procs, descendants, q, req, trigger, wait_run

agent = sys.argv[1] if len(sys.argv) > 1 else "alpha"
keep = "--keep" in sys.argv
CMD = 'py -3.11 -c "import time; [time.sleep(1) for i in range(300)]"'
msg = (
    "Run exactly this shell command once, with a 600000 ms timeout, and wait for it to finish "
    f"before replying. Do not run it in the background. Command: {CMD}"
)
status, res = trigger(agent, msg, fresh=True)
print("trigger ->", status, json.dumps(res)[:400])
run_id = res.get("run_id")
if not run_id:
    sys.exit(1)

sleeper = None
deadline = time.time() + 240
while time.time() < deadline:
    row = q("select status, pid, workspace_dir, session_id from runs where id=?", run_id)
    if row and row[0]["status"] not in ("running", "queued", "starting", "pending"):
        print("run ended before the sleep was seen:", row[0])
        sys.exit(2)
    table = procs()
    hits = [p for p, r in table.items() if "range(300)" in r["cmd"] and r["name"].lower() == "python.exe"]
    if hits and row and row[0]["status"] == "running":
        sleeper = hits[0]
        break
    time.sleep(3)
if sleeper is None:
    print("never saw the sleep process")
    sys.exit(3)

run = q("select status, pid, workspace_dir, session_id, harness_mcp_status from runs where id=?", run_id)[0]
print("run before stop:", run)
tools = q(
    "select kind, substr(content,1,200) c from agent_outputs where run_id=? order by timestamp, sequence",
    run_id,
)
print("outputs before stop:", tools)
table = procs()
chain, cur = [], sleeper
while cur in table:
    chain.append((cur, table[cur]["name"], table[cur]["cmd"][:120]))
    cur = table[cur]["ppid"]
print("sleeper ancestor chain (sleeper first):")
for c in chain:
    print("   ", c)
root = run["pid"]
tree = [root] + descendants(table, root) if root in table else []
print(f"run pid {root} in table: {root in table}; tree size {len(tree)}")
for p in tree:
    print("    tree", p, table[p]["name"], table[p]["cmd"][:100])

t0 = time.time()
status, res = req("POST", f"{B}/agent/{agent}/stop")
print("stop ->", status, json.dumps(res))
final = wait_run(run_id, 2)
print("run status after stop:", final, f"(+{time.time() - t0:.1f}s)")
time.sleep(8)
after = procs()
alive = [p for p in tree if p in after and after[p]["name"] == table[p]["name"]]
print("tree members still alive 8 s after the run settled:")
for p in alive:
    print("    ALIVE", p, after[p]["name"], "ppid", after[p]["ppid"], after[p]["cmd"][:100])
print("sleeper alive:", sleeper in after)
ws = run["workspace_dir"]
if ws and os.path.isdir(ws):
    probe = ws.rstrip("/\\") + "_renametest"
    try:
        os.rename(ws, probe)
        os.rename(probe, ws)
        print("workspace rename: OK (no handle held)")
    except OSError as exc:
        print("workspace rename refused:", exc)
row = q("select status, error, exit_code, ended_at from runs where id=?", run_id)[0]
print("run row:", row)
if alive and not keep:
    for p in alive:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p)], capture_output=True)
    time.sleep(2)
    left = procs()
    print("after taskkill, still alive:", [p for p in alive if p in left])
print("RUN=" + run_id)
