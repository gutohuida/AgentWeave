"""Scenario 6 (2026-10-19 Copilot stall drive): restart the scratch Hub while a Copilot run is in
flight. Does the run strand; does Stop answer 409; does a new turn queue behind it?

    py -3.11 scripts/drive/c1019_copilot_s6.py
"""

import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, outputs, q, report, req  # noqa: E402

E2E = str(e2e.__file__)


def copilots():
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'copilot.exe' -or "
         "$_.CommandLine -like '*c1019restart*' } | Where-Object { $_.Name -ne 'powershell.exe' } "
         "| ForEach-Object { \"$($_.ProcessId)/$($_.ParentProcessId) $($_.Name)\" }"],
        capture_output=True, text=True).stdout.strip().replace("\n", "; ")


rid = e2e.cmd_turn(
    P, "cop", "Run exactly this in the shell and wait for it: "
    "py -3.11 -c \"import time; time.sleep(120); print('c1019restart')\" then reply with its "
    "output. Do not ask me anything.", perm="workspace", fresh=True)
t0 = time.time()
while time.time() - t0 < 90 and not any(o["kind"] == "tool_use" for o in outputs(rid)):
    time.sleep(2)
time.sleep(5)
print("before restart:", copilots())
print(subprocess.run([sys.executable, E2E, "hub-down"], capture_output=True, text=True).stdout)
time.sleep(3)
print("hub down:", copilots())
up = subprocess.run([sys.executable, E2E, "hub-up", "c1019cop", "8110"], capture_output=True,
                    text=True)
print(up.stdout[-600:], up.stderr[-600:])
e2e._KEY = None
time.sleep(5)
print("after restart:", copilots())
print("run row:", q("select status, error, ended_at from runs where id=?", rid))
print("stop ->", req("POST", f"/projects/{P}/agent/cop/stop"))
rid2 = e2e.cmd_turn(P, "cop", "Reply with just the word OK3 and nothing else.", fresh=True)
time.sleep(20)
print("new turn:", rid2, q("select status, error from runs where id=?", rid2) if rid2 else None)
print("cop entries:", q("select id, state, waiting_reason, delivery_attempts, substr(content,1,60) c "
                        "from inbound_queue_entries where agent='cop' and state in ('queued',"
                        "'delivered') order by sequence desc limit 3"))
print("status route:", req("GET", f"/projects/{P}/agents/cop/status") if True else None)
t1 = time.time()
while time.time() - t1 < 240:
    st = q("select status from runs where id=?", rid)[0]["status"]
    if st != "running":
        break
    time.sleep(10)
print(f"stranded run after {time.time()-t1:.0f}s more:", q("select status, error, ended_at from runs where id=?", rid))
report(rid)
if rid2:
    report(rid2)
