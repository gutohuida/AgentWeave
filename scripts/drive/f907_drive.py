"""F907 drive (scratch Hub hub-up f907 8125): give the Activity digest a stopped and a failed turn.

  py -3.11 scripts/drive/f907_drive.py <stop|fail> <project-id>
"""

import json
import os
import pathlib
import subprocess
import sys

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f907.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import s1022_tr_drive as d  # noqa: E402

PHASE, PROJECT = sys.argv[1], sys.argv[2]
d.S["P"] = PROJECT


def main():
    run = d.trigger("alpha", d.SLEEP, project=PROJECT)
    d.say("tool call seen", d.wait_tool_call(run))
    if PHASE == "stop":
        st, res = d.api("POST", "~/agent/alpha/stop", project=PROJECT)
        d.say(f"stop {st}", res)
    else:
        hub_pid = int(json.loads(pathlib.Path(os.environ["AW_E2E_STATE"]).read_text())["pid"])
        for k in d._claude_children(hub_pid):
            subprocess.run(["taskkill", "/F", "/PID", str(k["ProcessId"])], capture_output=True)
    d.say("final", d.wait_run(run, 180))
    d.say("run row", d.ro("select status, exit_code from runs where id=?", (run,)))


main()
