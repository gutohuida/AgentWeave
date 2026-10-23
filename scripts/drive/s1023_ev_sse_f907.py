"""F907 re-drive, the Hub half: one Haiku turn stopped through the stop route, one whose claude.exe is
killed, both while a 120 s sleep tool call is in flight. Then read the events the Hub wrote.

    py -3.11 scripts/drive/s1023_ev_sse_f907.py stop|kill|events
"""

import json
import subprocess
import sys
import time

from s1023_ev_sse_lib import B, P, SLEEP_CMD, q, req, trigger, wait_status, wait_tool_call

WHAT = sys.argv[1]
MSG = f"Run this exact shell command and wait for it to finish, then reply DONE: {SLEEP_CMD}"


def tree(pid):
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq {pid} -or $_.ProcessId -eq {pid} }}"
         " | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json"],
        capture_output=True, text=True)
    return out.stdout.strip()


def run_one():
    run = trigger("alpha", MSG)
    print("RUN", run, wait_status(run, ("running",), 60))
    ok = wait_tool_call(run)
    print("sleep tool call recorded:", ok)
    time.sleep(6)
    row = q("select status, pid from runs where id=?", run)[0]
    print("run row before end:", row)
    return run, row


if WHAT == "stop":
    run, row = run_one()
    st, res = req("POST", f"{B}/agent/alpha/stop")
    print("stop ->", st, json.dumps(res))
    print("after:", wait_status(run, ("stopped", "failed", "completed"), 60))
elif WHAT == "kill":
    run, row = run_one()
    print("tree of pid", row["pid"], tree(row["pid"]))
    out = subprocess.run(["taskkill", "/F", "/PID", str(row["pid"])], capture_output=True, text=True)
    print("taskkill:", out.stdout.strip(), out.stderr.strip())
    print("after:", wait_status(run, ("stopped", "failed", "completed"), 90))
else:
    for r in q("select id, status, exit_code, error, started_at, ended_at from runs where project_id=? order by started_at", P):
        print("RUN", r)
    for e in q("select event_type, agent, severity, timestamp, substr(data,1,160) d from event_logs where project_id=?"
               " and event_type like 'run_%' order by timestamp", P):
        print("EV", e)
