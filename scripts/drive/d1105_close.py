"""Acceptance drive for AWOAW-3's close (spec agentweave-is-its-own-app-on-windows): FR-8, FR-9, FR-11.

The idle close (FR-7) and the two-Hub close (FR-10) are d1105_own_app.py's `close` and `own-hub`
steps. This drive adds, each on its own scratch Hub launched as the desktop shortcut launches it:

  busy      (FR-8 close-busy) -- a real Haiku turn in progress; the window is closed and each choice
            taken in turn through the page (UI Automation, by the button's name), reopening between:
            the prompt names one agent turn; Cancel leaves the window open; Keep running closes the
            window, the Hub process is the same and the turn completes; with a second turn in
            progress, Stop it all leaves no Hub process and no process of the turn.
  firings   (FR-9 work-between-firings) -- a build that has not ended and no turn: the prompt
            appears and names the build. Then the build ended and an enabled recurring job that is
            not a build: no prompt, and the Hub stops. The build row is written into the scratch
            profile's own database (a build needs an approved document and a flow to start through
            the API); the job is created through the API.
  setting   (FR-11 setting-restores-old-close) -- the setting turned on in App settings (UI
            Automation: the rail's App settings, Hub connection, the switch), the window closed, the
            app launched again: the setting still reads on; a close with nothing running asks
            nothing, and the Hub is still running and answering 60 seconds later.

Scratch ports 8177-8179 and d1105own* profiles; never :8000 or :8010.

  py -3.11 scripts/drive/d1105_close.py
  py -3.11 scripts/drive/d1105_close.py --only busy      # or firings, setting
"""

from __future__ import annotations

import argparse
import pathlib
import sqlite3
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "drive"))
import d1105_own_app as d  # noqa: E402

user32 = d.user32
SETTING = "Closing the window leaves AgentWeave running"


def uia(hwnd: int, label: str, action: str = "find", timeout: float = 20) -> str:
    """UI Automation on the window's page, retried until something answers or `timeout` passes:
    WebView2 builds its page's accessibility tree only once something asks, so the first look sees
    an empty document (2026-11-05)."""
    return (
        d.wait_for(
            lambda: (lambda r: None if r == "missing" else r)(_uia(hwnd, label, action)),
            timeout,
            1.0,
        )
        or "missing"
    )


def _uia(hwnd: int, label: str, action: str) -> str:
    """The first element whose name contains `label`.

    `find` answers "found"; `invoke` clicks it (Invoke, else Toggle); `state` answers its toggle
    state ("On"/"Off"). Answers "missing" when nothing in the page is named so.
    """
    script = rf"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd})
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
  [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {{
  if ($e.Current.Name -like '*{label}*') {{
    $p = $null
    if ('{action}' -eq 'find') {{ 'found'; exit 0 }}
    if ('{action}' -eq 'state') {{
      if ($e.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$p)) {{
        $p.Current.ToggleState.ToString(); exit 0 }}
      continue }}
    if ($e.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$p)) {{
      $p.Invoke(); 'done'; exit 0 }}
    if ($e.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$p)) {{
      $p.Toggle(); 'done'; exit 0 }}
  }} }}
'missing'
"""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=90,
        creationflags=0x08000000,
    )
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else "missing"


def open_app(app: d.App) -> int | None:
    proc = app.launch()
    hwnd = app.wait_window(proc, 60)
    if hwnd is None or not app.wait_healthy():
        return None
    time.sleep(6.0)  # past the splash, into the app, the project registered
    return hwnd


def asks(hwnd: int, wording: str) -> bool:
    """Close the window and see the prompt: the window stays, and the page shows `wording`."""
    d.close_window(hwnd)
    time.sleep(3.0)
    if not user32.IsWindow(hwnd):
        d.note("the window closed instead of asking")
        return False
    if uia(hwnd, wording) == "found":
        return True
    # Say what is there instead: a native message box (the page could not show the prompt), or
    # what the page's accessibility tree holds.
    owner = d.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, d.ctypes.byref(owner))
    boxes = [w for w in d.top_windows() if w["pid"] == owner.value and w["cls"] == "#32770"]
    d.note(f"no '{wording}' in the page; native boxes of the launcher: {boxes}")
    d.note(f"page has 'still working': {uia(hwnd, 'still working', timeout=5)}")
    return False


def gone(app: d.App, hwnd: int, limit: float = d.CLOSE_LIMIT) -> bool:
    return bool(
        d.wait_for(
            lambda: not user32.IsWindow(hwnd)
            and not d.hub_pids(app.port)
            and d.port_free(app.port),
            limit,
            0.5,
        )
    )


def project_id(app: d.App) -> str | None:
    """The scratch project's id, opened as the app's picker would when the launch registered none
    (as `d1105_own_app.start_turn` does)."""
    _, rows = app.api("GET", "/projects")
    rows = rows if isinstance(rows, list) else (rows or {}).get("projects", [])
    for p in rows:
        path = p.get("path") or p.get("working_directory") or ""
        if path and pathlib.Path(path).resolve() == app.cwd.resolve():
            return p["id"]
    code, project = app.api("POST", "/projects/open", {"path": str(app.cwd), "name": app.cwd.name})
    d.note(f"the launch registered no project for {app.cwd}; opened it: {code}")
    return project.get("id") if isinstance(project, dict) else None


def step_busy(app: d.App) -> None:
    hwnd = open_app(app)
    if not d.check("busy: the app opens", hwnd is not None):
        return
    run_id, why = d.start_turn(app)
    if not d.check("busy: an agent turn is in progress", run_id is not None, why or run_id):
        return
    d.wait_for(lambda: d.run_status(app, run_id) == "running", 60, 1.0)
    hub = d.hub_pids(app.port)

    d.check("busy: the close asks, naming one agent turn", asks(hwnd, "1 agent turn is running"))
    d.check("busy: Cancel can be chosen", uia(hwnd, "Cancel", "invoke") == "done")
    time.sleep(3.0)
    d.check("busy: after Cancel the window is still open", bool(user32.IsWindow(hwnd)))

    d.check("busy: the close asks again", asks(hwnd, "1 agent turn is running"))
    d.check(
        "busy: Keep running can be chosen",
        uia(hwnd, "Keep running in the background", "invoke") == "done",
    )
    closed = d.wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.5)
    time.sleep(3.0)
    d.check("busy: Keep running closes the window", bool(closed))
    d.check(
        "busy: after Keep running the Hub process is the same",
        d.hub_pids(app.port) == hub and bool(hub),
        f"{hub} -> {d.hub_pids(app.port)}",
    )
    d.wait_for(lambda: d.run_status(app, run_id) != "running", 300, 3.0)
    d.check(
        "busy: after Keep running the turn completes",
        d.run_status(app, run_id) == "completed",
        d.run_status(app, run_id),
    )

    hwnd = open_app(app)
    if not d.check(
        "busy: reopened on the same Hub", hwnd is not None and d.hub_pids(app.port) == hub
    ):
        return
    run_id, why = d.start_turn(app)
    if not d.check("busy: a second turn is in progress", run_id is not None, why or run_id):
        return
    d.wait_for(lambda: d.run_status(app, run_id) == "running", 60, 1.0)
    rows = d.processes()
    tree = d.descendants(rows, set(hub)) - app.pids
    d.check("busy: the close asks a third time", asks(hwnd, "1 agent turn is running"))
    d.check("busy: Stop it all can be chosen", uia(hwnd, "Stop it all", "invoke") == "done")
    d.check(
        f"busy: after Stop it all, within {d.CLOSE_LIMIT:.0f} s no Hub process remains",
        gone(app, hwnd),
        f"{d.hub_pids(app.port)}, port free {d.port_free(app.port)}",
    )

    def left() -> list:
        return [r for r in d.processes() if r["ProcessId"] in tree]

    d.wait_for(lambda: not left(), d.CLOSE_LIMIT, 1.0)
    alive = [(r["ProcessId"], r["Name"], (r.get("CommandLine") or "")[:120]) for r in left()]
    d.check(
        f"busy: and within {d.CLOSE_LIMIT:.0f} s no process of the Hub's turn remains",
        not alive,
        f"{alive}",
    )


def step_firings(app: d.App) -> None:
    hwnd = open_app(app)
    if not d.check("firings: the app opens", hwnd is not None):
        return
    pid = project_id(app)
    if not d.check("firings: the project is registered", pid is not None):
        return
    db = d.HUB_HOME / "profiles" / app.profile / "agentweave.db"
    connection = sqlite3.connect(str(db), timeout=30)
    try:
        connection.execute(
            "insert into builds (id, project_id, document_id, state, driver, level, builders,"
            " reviewers, landing, created_at) values ('build-between-firings', ?, 'spdoc-drive',"
            " 'running', 'flow', 'reviewed', '[]', '[]', 'main', datetime('now'))",
            (pid,),
        )
        connection.commit()
    finally:
        connection.close()
    d.check(
        "firings: with a build between firings the close asks, naming the build",
        asks(hwnd, "build-between-firings"),
    )
    uia(hwnd, "Cancel", "invoke")
    time.sleep(2.0)

    connection = sqlite3.connect(str(db), timeout=30)
    try:
        connection.execute("update builds set state='stopped' where id='build-between-firings'")
        connection.commit()
    finally:
        connection.close()
    code, job = app.api(
        "POST",
        f"/projects/{pid}/jobs",
        {
            "name": "recurring",
            "agent": "worker",
            "message": "hello",
            "cron": "0 3 * * *",
            "session_mode": "new",
            "enabled": True,
        },
    )
    if code >= 300:  # the job needs its agent first
        _, runner = app.api(
            "POST", f"/projects/{pid}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU}
        )
        app.api("POST", f"/projects/{pid}/agents", {"name": "worker", "runner_id": runner["id"]})
        code, job = app.api(
            "POST",
            f"/projects/{pid}/jobs",
            {
                "name": "recurring",
                "agent": "worker",
                "message": "hello",
                "cron": "0 3 * * *",
                "session_mode": "new",
                "enabled": True,
            },
        )
    if not d.check(
        "firings: an enabled recurring job exists", code < 300, f"{code} {str(job)[:200]}"
    ):
        return
    d.close_window(hwnd)
    d.check(
        f"firings: with only the recurring job, no prompt and the Hub stops within {d.CLOSE_LIMIT:.0f} s",
        gone(app, hwnd),
        f"window {bool(user32.IsWindow(hwnd))}, Hub {d.hub_pids(app.port)}",
    )


def step_setting(app: d.App) -> None:
    setting_file = d.HUB_HOME / "app-window" / f"close-{app.port}.json"
    setting_file.unlink(missing_ok=True)
    hwnd = open_app(app)
    if not d.check("setting: the app opens", hwnd is not None):
        return
    d.check("setting: App settings opens", uia(hwnd, "App settings", "invoke") == "done")
    time.sleep(2.0)
    d.check(
        "setting: its Hub connection section opens", uia(hwnd, "Hub connection", "invoke") == "done"
    )
    time.sleep(2.0)
    d.check("setting: the setting reads off at first", uia(hwnd, SETTING, "state") == "Off")
    d.check("setting: it can be turned on", uia(hwnd, SETTING, "invoke") == "done")
    time.sleep(1.0)
    d.check("setting: it reads on", uia(hwnd, SETTING, "state") == "On")
    hub = d.hub_pids(app.port)
    d.close_window(hwnd)
    d.wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.5)

    hwnd = open_app(app)  # the app restarted
    if not d.check("setting: the app opens again", hwnd is not None):
        return
    uia(hwnd, "App settings", "invoke")
    time.sleep(2.0)
    uia(hwnd, "Hub connection", "invoke")
    time.sleep(2.0)
    d.check("setting: after the restart it still reads on", uia(hwnd, SETTING, "state") == "On")
    d.close_window(hwnd)
    closed = d.wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.5)
    d.check("setting: the close asks nothing and closes the window", bool(closed))
    time.sleep(60)
    d.check(
        "setting: 60 seconds later the Hub process is still running and answering",
        d.hub_pids(app.port) == hub and bool(hub) and d.healthy(app.port),
        f"{hub} -> {d.hub_pids(app.port)}, healthy {d.healthy(app.port)}",
    )
    setting_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8177, help="first of three scratch ports")
    parser.add_argument("--only", choices=["busy", "firings", "setting"])
    opts = parser.parse_args()
    ports = [opts.port, opts.port + 1, opts.port + 2]
    if d.FORBIDDEN_PORTS & set(ports):
        raise SystemExit(f"refusing ports {ports}: :8000 and :8010 are never driven")
    steps = [
        ("busy", step_busy, ports[0]),
        ("firings", step_firings, ports[1]),
        ("setting", step_setting, ports[2]),
    ]
    for name, step, port in steps:
        if opts.only and opts.only != name:
            continue
        if not d.port_free(port):
            raise SystemExit(f"scratch port {port} already in use; pick another --port")
        app = d.App(port, f"{d.PROFILE}{name[0]}c", d.project_dir(f"close-{name}"))
        try:
            step(app)
        finally:
            app.cleanup()
            (d.HUB_HOME / "app-window" / f"close-{port}.json").unlink(missing_ok=True)
            (d.HUB_HOME / "app-window" / f"window-{port}.json").unlink(missing_ok=True)
    d.clear_scratch()
    print(f"\n{len(d.failures)} FAIL" if d.failures else "\nALL PASS")
    for name in d.failures:
        print(f"  - {name}")
    return 1 if d.failures else 0


if __name__ == "__main__":
    sys.exit(main())
