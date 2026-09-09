"""D-1 2026-09-09: the F295 shutdown settle, on the Hub that carries all three night changes.

`f295_shutdown_drive.py` drives the same teardown, but it builds its own database and refuses to
run when 8011 is already listening -- which is right for a single-change drive and wrong for this
one, whose whole question is the three changes *together*. This one restarts the existing 8011
database in its own process group so `CTRL_BREAK_EVENT` can reach it, puts a real Haiku turn in
flight, and reads the teardown lines out of the log.

Ctrl-Break rather than `agentweave stop`: on Windows the CLI's stop is `taskkill /F`, which is
`TerminateProcess` -- no signal, no `lifespan` teardown, nothing for this change to do (F297).

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=... AW_AGENT_OK=... \
        py -3.11 scripts/drive/d1_0909_shutdown.py
"""

import os
import pathlib
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

REPO = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave")
TMP = pathlib.Path(r"C:\Users\huida\AppData\Local\Temp\aw0909")
DB = TMP / "aw0909.db"
LOG = TMP / "hub8011-restart.log"
AGENT = os.environ["AW_AGENT_OK"]
LONG = ("Write a 3000 word essay about the history of the bicycle, in full prose, "
        "one paragraph at a time. Use no tools and read no files.")

# Whatever is on 8011 now was started outside a process group of ours and cannot be signalled.
# The rows are all in the database, so a hard stop here loses nothing the drive needs.
subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -like '*8011*' } | "
     "ForEach-Object { taskkill /PID $_.ProcessId /T /F }"],
    capture_output=True,
)
time.sleep(2)

env = dict(os.environ)
env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
env["AW_LOG_LEVEL"] = "INFO"
# Not a context manager: the handle has to outlive this statement, because it is the child
# process's stdout for as long as the child runs, and the log is read back after `close()`.
log = open(LOG, "a", encoding="utf-8")  # noqa: SIM115
proc = subprocess.Popen(
    ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", "8011", "--host", "127.0.0.1"],
    cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
print(f"hub restarted in its own process group, pid {proc.pid}")

for _ in range(40):
    time.sleep(2)
    code, _ = api("GET", f"/projects/{P}/agents")
    if code == 200:
        break
else:
    sys.exit("hub did not come up")
print("hub answering")

code, out = api("POST", f"/projects/{P}/agent/trigger", {"agent": AGENT, "message": LONG})
print(f"trigger -> [{code}] run={out.get('run_id') if isinstance(out, dict) else out}")
time.sleep(12)
row = next((x for x in api("GET", f"/projects/{P}/agents")[1] if x["name"] == AGENT), None)
print(f"agent status at signal time: {row and row.get('status')}")

t0 = time.time()
os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
try:
    proc.wait(timeout=120)
except subprocess.TimeoutExpired:
    print("!! the process did not exit within 120s of Ctrl-Break")
print(f"exited rc={proc.returncode} after {time.time() - t0:.1f}s")
log.close()

text = LOG.read_text(encoding="utf-8", errors="replace")
print("--- teardown lines ---")
for line in text.splitlines():
    low = line.lower()
    if any(k in low for k in ("shutdown", "settle", "background run", "cancel", "event loop is closed",
                              "traceback", "error", "warning", "shutting down", "application")):
        print(f"    {line[:300]}")
