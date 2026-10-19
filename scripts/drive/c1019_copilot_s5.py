"""Scenario 5 (2026-10-19 Copilot stall drive): silence. Agent `quiet` runs a project script that
waits on stdin (`Read-Host`). How long until anything notices; what the operator sees meanwhile.
Samples the run, its last output and the copilot process tree every 15 s.

    py -3.11 scripts/drive/c1019_copilot_s5.py
"""

import subprocess
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from c1019_copilot_lib import P, e2e, outputs, q, report  # noqa: E402

e2e.cmd_agent(P, "quiet", "-", "copilot", "claude-haiku-4.5")
t0 = time.time()
rid = e2e.cmd_turn(
    P, "quiet", "Run the project's setup script with `powershell -NoProfile -File tools/setup.ps1` "
    "and tell me in one line what it printed. Do not ask me anything.", fresh=True)
last = None
while time.time() - t0 < 720:
    st = e2e.ro().execute("select status from runs where id=?", (rid,)).fetchone()["status"]
    outs = outputs(rid)
    tail = (outs[-1]["timestamp"], outs[-1]["kind"], (outs[-1]["c"] or "")[:120]) if outs else None
    procs = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*setup.ps1*' } | "
         "ForEach-Object { \"$($_.ProcessId) $($_.Name)\" }"],
        capture_output=True, text=True).stdout.strip().replace("\n", "; ")
    if (st, tail, procs) != last:
        print(f"t+{time.time()-t0:5.0f}s run={st} last_output={tail} setup_procs=[{procs}]")
        last = (st, tail, procs)
    if st not in ("running", "queued", "starting"):
        break
    sys.stdout.flush()
    time.sleep(15)
report(rid)
print("heartbeat:", q("select last_heartbeat_at from runs where id=?", rid))
