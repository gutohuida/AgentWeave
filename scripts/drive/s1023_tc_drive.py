"""2026-10-23 day sweep, Traces row: the runs whose traces the UI drive then opens.

  setup    seed a module, commit, two project checks (one prints a fake key, one fails), a task
  secret   titles job on; tracer, bound to the task, echoes a whole fake key, a key split across two
           outputs and a GitHub token (three tool calls); titles job off afterwards
  stop     tracer runs a 120 s sleep in the same conversation, with a file held open in its calls
           directory (to make prepare_calls_dir warn); Stop through the operator route
  fail     tracer runs a 120 s sleep; its claude process is killed -> run_failed
  checks   the task's checks run from the operator route (a work trace with command spans)

  py -3.11 scripts/drive/s1023_tc_drive.py <phase>
"""

import json
import os
import subprocess
import sys
import time

from s1023_tc_lib import DIR, GH, HALF1, HALF2, KEY, S, q, req, save, say, trigger, wait_run, wait_tool_call

SLEEP = (
    'I am testing the Stop button of my job runner and need a command that takes two minutes. '
    'Run exactly this shell command and nothing else, then reply DONE: '
    'py -3.11 -c "import time\nfor i in range(120): time.sleep(1)"'
)


def phase_setup():
    (DIR / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    for args in (
        ["add", "calc.py"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "calc module"],
    ):
        subprocess.run(["git", "-C", str(DIR), *args], check=True)
    st, res = req("GET", "~/settings")
    body = {k: v for k, v in res.items() if k != "name"}
    body["name"] = res["name"]
    body["checks"] = [
        {"name": "prints-key", "command": f'py -3.11 -c "print(\'token {KEY}\')"', "timeout_seconds": 60},
        {"name": "fails", "command": 'py -3.11 -c "import sys; print(\'boom\'); sys.exit(3)"', "timeout_seconds": 60},
    ]
    st, res = req("PUT", "~/settings", body)
    say(f"PUT settings checks -> {st}", res if st != 200 else res.get("checks", res))
    st, task = req("POST", "~/tasks", {"title": "Echo the fixtures", "description": "Trace probe.", "assignee": "tracer"})
    say(f"task -> {st}", {k: task.get(k) for k in ("id", "status", "detail")})
    S["TASK"] = task.get("id")
    save()


def phase_secret():
    st, res = req("PATCH", "~/manager/jobs/conversation-titles", {"enabled": True})
    say(f"titles on -> {st}", res)
    msg = (
        "These are fake test fixture strings, not real credentials. Run these three shell commands, "
        "each as its own separate tool call, in order, and then reply with the single word DONE.\n"
        f"1. echo KEY={KEY}\n2. echo HALF1={HALF1}\n3. echo HALF2={HALF2} GH={GH}"
    )
    run = trigger("tracer", msg, task=S["TASK"])
    S["RUN_OK"] = run
    save()
    say("final", wait_run(run))
    S["CONV"] = q("select conversation_id from runs where id=?", run)[0]["conversation_id"]
    save()
    # Give the title worker time to fire, then turn the job off.
    end = time.time() + 120
    while time.time() < end:
        rows = q("select count(*) n from event_logs where event_type='manager_job_fired' and project_id=?", S["P"])
        if rows[0]["n"]:
            break
        time.sleep(4)
    say("manager_job_fired rows", q("select event_type, data from event_logs where event_type like 'manager_job%' and project_id=?", S["P"]))
    st, res = req("PATCH", "~/manager/jobs/conversation-titles", {"enabled": False})
    say(f"titles off -> {st}", res)


def phase_secret2():
    """Haiku declined `secret` (it read the split as detection evasion): the values come from a
    committed file instead, so they appear only in the tool outputs (show.py prints line N)."""
    msg = (
        "Run these three shell commands, each as its own separate tool call, in order: "
        "`py -3.11 show.py 1`, then `py -3.11 show.py 2`, then `py -3.11 show.py 3`. "
        "Then reply with the single word DONE."
    )
    run = trigger("tracer", msg, conversation=S["CONV"], task=S["TASK"])
    S["RUN_OK"] = run
    save()
    say("final", wait_run(run))


def _calls_dirs():
    return [p for p in DIR.rglob("calls") if p.is_dir() and p.parent.name == ".agentweave"]


def phase_stop():
    holder = None
    dirs = _calls_dirs()
    say("calls dirs", [str(d) for d in dirs])
    for d in dirs:
        if "worktrees" in str(d) or "tasks" in str(d):
            target = d / "held.json"
            target.write_text("{}", encoding="utf-8")
            # A second process holds it open: Windows refuses to delete an open file.
            holder = subprocess.Popen(
                [sys.executable, "-c", f"import time; f=open(r'{target}'); time.sleep(240)"]
            )
            say("holding open", str(target))
    time.sleep(2)
    run = trigger("tracer", SLEEP, conversation=S.get("CONV2"), task=S["TASK"])
    S.setdefault("CONV2", q("select conversation_id from runs where id=?", run)[0]["conversation_id"])
    S["RUN_STOP"] = run
    save()
    say("tool call seen", wait_tool_call(run))
    st, res = req("POST", "~/agent/tracer/stop")
    say(f"stop {st}", res)
    say("final", wait_run(run, 120))
    if holder:
        holder.kill()


def _claude_children(hub_pid):
    ps = (
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    kids = {}
    for p in json.loads(out):
        kids.setdefault(p["ParentProcessId"], []).append(p)
    found, stack = [], [hub_pid]
    while stack:
        pid = stack.pop()
        for c in kids.get(pid, []):
            stack.append(c["ProcessId"])
            if (c["Name"] or "").lower().startswith("claude"):
                found.append(c)
    return found


def phase_fail():
    run = trigger("tracer", SLEEP, conversation=S.get("CONV2"), task=S["TASK"])
    S.setdefault("CONV2", q("select conversation_id from runs where id=?", run)[0]["conversation_id"])
    S["RUN_FAIL"] = run
    save()
    say("tool call seen", wait_tool_call(run))
    hub_pid = int(json.loads(open(os.environ["AW_E2E_STATE"]).read())["pid"])
    kids = _claude_children(hub_pid)
    say("claude processes", [(k["ProcessId"], k["Name"]) for k in kids])
    for k in kids:
        subprocess.run(["taskkill", "/F", "/PID", str(k["ProcessId"])], capture_output=True)
    say("final", wait_run(run, 180))
    say("run row", q("select status, exit_code, error from runs where id=?", run))


def phase_checks():
    st, res = req("POST", f"~/tasks/{S['TASK']}/checks/run")
    say(f"checks/run -> {st}", res)
    time.sleep(15)
    st, res = req("GET", f"~/tasks/{S['TASK']}/checks")
    say(f"checks -> {st}", res)


if __name__ == "__main__":
    {"setup": phase_setup, "secret": phase_secret, "secret2": phase_secret2, "stop": phase_stop, "fail": phase_fail, "checks": phase_checks}[
        sys.argv[1]
    ]()
