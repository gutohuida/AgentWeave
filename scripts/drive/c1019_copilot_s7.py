"""Scenario 7 (2026-10-19 Copilot stall drive): Stop a Copilot run mid-command, then continue the
same conversation (session/load) with a one-word turn. Does Stop end the shell's process tree,
what does the operator see, and what does the resumed turn cost to start?

    py -3.11 scripts/drive/c1019_copilot_s7.py
"""

import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, outputs, poll, report, req  # noqa: E402


def sleepers():
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*c1019stop*' -and "
         "$_.Name -ne 'powershell.exe' } | ForEach-Object { \"$($_.ProcessId) $($_.Name)\" }"],
        capture_output=True, text=True).stdout.strip().replace("\n", "; ")


rid = e2e.cmd_turn(
    P, "cop", "Run exactly this in the shell and wait for it: "
    "py -3.11 -c \"import time; time.sleep(150); print('c1019stop')\" then reply with its output. "
    "Do not ask me anything.", perm="workspace", fresh=True)
t0 = time.time()
while time.time() - t0 < 90:
    outs = outputs(rid)
    if any(o["kind"] == "tool_use" for o in outs):
        break
    time.sleep(2)
time.sleep(8)
print("before stop: sleepers=", sleepers())
s, body = req("POST", f"/projects/{P}/agent/cop/stop")
print("stop ->", s, body)
print(poll(rid, 60, every=1))
time.sleep(3)
print("after stop: sleepers=", sleepers())
report(rid)
conv = e2e.latest_conversation(P, "cop")
t1 = time.time()
rid2 = e2e.cmd_turn(P, "cop", "Reply with just the word OK2 and nothing else.")
print(poll(rid2, 300))
print(f"resumed turn wall: {time.time()-t1:.1f}s (conversation {conv})")
report(rid2)
