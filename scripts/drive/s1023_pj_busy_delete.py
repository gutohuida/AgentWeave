"""Projects sweep 2026-10-23 -- delete a project while one of its runs is active (one Haiku turn).

The run holds itself open with a plain shell sleep; the drive then tries DELETE through the API and
through the Delete-project dialog, reads what each says, stops the agent and waits for the run.

    py -3.11 scripts/drive/s1023_pj_busy_delete.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s1023_pj_lib import PB, hub_and_key, q, req  # noqa: E402
from uiharness import Judge  # noqa: E402

HUB, KEY = hub_and_key()
MSG = (
    "Run exactly this one shell command and nothing else, then reply 'done': "
    "py -3.11 -c \"import time; [time.sleep(1) for i in range(100)]\""
)


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def main():
    status, res = req("POST", f"/projects/{PB}/agent/trigger",
                      {"agent": "beta", "message": MSG, "overrides": {"permission_mode": "workspace"}})
    print("trigger:", status, json.dumps(res)[:300])
    run_id = res.get("run_id")
    for _ in range(60):
        time.sleep(2)
        row = q("select status from runs where id = ?", run_id)
        procs = os.popen('powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \'*range(100)*\' -and $_.Name -eq \'python.exe\' } | Measure-Object | Select-Object -ExpandProperty Count"').read().strip()
        if row and row[0]["status"] == "running" and procs not in ("", "0"):
            break
    print("run:", run_id, row, "sleepers:", procs)
    status, body = req("DELETE", f"/projects/{PB}?remove_private=true")
    print("API DELETE during run ->", status, json.dumps(body, ensure_ascii=False))
    name = req("GET", f"/projects/{PB}")[1]["name"]
    with Judge("s1023-pj", hub=HUB, key=KEY) as j:
        page = j.page(PB, mode="dark", query="tab=environment&section=settings")
        page.wait_for_timeout(3500)
        page.get_by_role("button", name="Delete project…").click()
        page.wait_for_timeout(600)
        dlg = page.get_by_role("dialog").filter(has_text="to confirm")
        dlg.get_by_label("Project name to confirm").fill(name)
        dlg.get_by_role("button", name="Delete project").click()
        page.wait_for_timeout(2000)
        print("dialog alert:", repr(txt(dlg.get_by_role("alert"))))
        j.shot(page, "55_delete_during_run")
        page.context.close()
    print("stop:", req("POST", f"/projects/{PB}/agent/beta/stop"))
    for _ in range(30):
        time.sleep(2)
        row = q("select status from runs where id = ?", run_id)
        if row and row[0]["status"] != "running":
            break
    print("run after stop:", row)


if __name__ == "__main__":
    main()
