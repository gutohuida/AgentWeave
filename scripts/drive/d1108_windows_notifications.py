"""Acceptance drive for "Windows notifications for what calls the operator"
(spec/changes/windows-notifications-for-what-calls-the-operator). Written failing first (WNWCO-1).

Runs this checkout's CLI and Hub (src/ and hub/ on PYTHONPATH) on ONE scratch port (8180 by
default) with a scratch profile -- never :8000 (the operator's) or :8010 (the trial Hub). Reuses
d1105_own_app.py's launcher, window, process and Hub-API helpers.

What it reads, and how:
  * the shell's notification history: Windows' own store, %LOCALAPPDATA%\\Microsoft\\Windows\\
    Notifications\\wpndatabase.db (copied with its WAL, read read-only). Each row's handler is the
    AppUserModelID it was shown under; its payload is the toast XML (text, image, launch link).
    A "notification" in this drive is a new row under AgentWeave.Hub; nothing is read from the
    product's own bookkeeping.
  * the operator stream: GET /api/v1/events with the instance credential, kept by a reader thread.
  * the page's route: the window runs with WebView2's remote-debugging port (SCRATCH_CDP_PORT);
    /json lists its pages with their URLs.
  * the activation link: taken from the toast XML's `launch` attribute and opened through the
    shell (`explorer.exe <link>`, as a click does) -- never by calling the launcher.

Assumptions about the CONTRACT's open details (named once so the build can move them):
  NOTIFY_SETTINGS_PATH -- the Hub route for the Windows kinds, {ask, fail, done, reply} booleans.
  AW_TOAST_COMMAND     -- set to a command that exits non-zero for the c-quiet step.

Steps, each named after its criterion: c-event, c-notice, c-behind, c-identity, c-in-front,
c-closed, c-click, c-quiet, c-kinds. Real Haiku turns: the ask_user turn (c-behind, c-event) and
the run made to fail (a runner with a model that does not exist).

  py -3.11 scripts/drive/d1108_windows_notifications.py [--port 8180]
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "drive"))
import d1105_own_app as d  # noqa: E402

user32 = d.user32
check, note, wait_for = d.check, d.note, d.wait_for

PROFILE_PREFIX = "d1108wn"
RUN = time.strftime("%H%M%S")
SCRATCH_CDP_PORT = 9338
NOTIFY_SETTINGS_PATH = "/notify-settings"
WPN_DIR = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Notifications"
AUMID = "AgentWeave.Hub"
SW_RESTORE, SW_MINIMIZE = 9, 6
LIMIT = 5.0  # the spec's "within 5 seconds"
failures = d.failures


# --- the shell's notification history ----------------------------------------------------------


def history() -> list[dict]:
    """Every toast the shell holds: {id, aumid, xml}. Read from a copy so the store's lock is moot."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="d1108wpn"))
    try:
        for suffix in ("", "-wal", "-shm"):
            src = WPN_DIR / f"wpndatabase.db{suffix}"
            if src.exists():
                shutil.copy2(src, tmp / src.name)
        con = sqlite3.connect(f"file:{(tmp / 'wpndatabase.db').as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "select n.Id, h.PrimaryId, n.Payload from Notification n "
                "join NotificationHandler h on h.RecordId = n.HandlerId where n.Type = 'toast'"
            ).fetchall()
        finally:
            con.close()
        out = []
        for nid, aumid, payload in rows:
            xml = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(payload)
            out.append({"id": nid, "aumid": aumid or "", "xml": xml})
        return out
    except Exception as exc:  # a store that cannot be read is a failed step, said once
        note(f"history unreadable: {exc}")
        return []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Shell:
    """Counts toasts that appear after a mark, by the text they carry."""

    def __init__(self):
        self.seen = {h["id"] for h in history()}

    def mark(self):
        self.seen = {h["id"] for h in history()}

    def new(self, needle: str = "", aumid: str | None = AUMID) -> list[dict]:
        return [
            h
            for h in history()
            if h["id"] not in self.seen
            and (aumid is None or h["aumid"] == aumid)
            and needle in h["xml"]
        ]

    def wait_new(self, needle: str, timeout: float) -> list[dict]:
        return wait_for(lambda: self.new(needle), timeout, 0.25) or []


# --- the operator stream -----------------------------------------------------------------------


class Stream:
    def __init__(self, app: d.App):
        self.app, self.events, self.log, self.stop = app, [], [], False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while not self.stop:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.app.port}/api/v1/events",
                    headers={"Authorization": "Bearer " + self.app.key()},
                )
                with urllib.request.urlopen(req, timeout=300) as r:
                    name = None
                    for raw in r:
                        if self.stop:
                            return
                        line = raw.decode("utf-8", "replace").rstrip("\r\n")
                        if line.startswith("event:"):
                            name = line[6:].strip()
                        elif line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                            except ValueError:
                                continue
                            if isinstance(data, dict):
                                data["_seen"] = time.monotonic()  # arrival time, for the 5 s limits
                            self.events.append((name, data))
                            self.log.append((name, data))  # never cleared: the final c-notice count
            except Exception:
                time.sleep(1.0)

    def of(self, name: str) -> list[dict]:
        return [dat for n, dat in list(self.events) if n == name]

    def logged(self, name: str) -> list[dict]:
        return [dat for n, dat in list(self.log) if n == name]


# --- the app, the page and the shell link ------------------------------------------------------


class WinApp(d.App):
    """d.App with the remote-debugging port on and an optional AW_TOAST_COMMAND."""

    toast_command: str | None = None

    def launch(self):
        saved = d.app_env

        def env():
            e = saved()
            # An explicit address for the agents' tool calls: a run's own HUB_URL otherwise comes from
            # the first connection the Hub sees (2026-11-08: a scratch Hub's run was refused 401).
            e["HUB_URL"] = f"http://127.0.0.1:{self.port}"
            e["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
                f"--remote-debugging-port={SCRATCH_CDP_PORT}"
            )
            if self.toast_command:
                e["AW_TOAST_COMMAND"] = self.toast_command
            return e

        d.app_env = env
        try:
            return super().launch()
        finally:
            d.app_env = saved


def page_url() -> str:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{SCRATCH_CDP_PORT}/json", timeout=2) as r:
            pages = [p for p in json.loads(r.read()) if p.get("type") == "page"]
        return pages[0]["url"] if pages else ""
    except Exception:
        return ""


def foreground(hwnd: int) -> bool:
    return user32.GetForegroundWindow() == hwnd


def bring_front(hwnd: int) -> bool:
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.AllowSetForegroundWindow(d.ASFW_ANY)
    user32.keybd_event(0x12, 0, 0, 0)  # a tap of Alt lets this process take the foreground
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return bool(wait_for(lambda: foreground(hwnd), 5, 0.1))


def page_text(hwnd: int) -> str:
    """Every accessible name in the window's page, by UI Automation (what the in-app toast draws)."""
    script = rf"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd})
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,
  [System.Windows.Automation.Condition]::TrueCondition)
foreach ($e in $all) {{ $e.Current.Name }}
"""
    try:
        return subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=0x08000000,
        ).stdout
    except Exception:
        return ""


def open_link(link: str) -> None:
    """As a click does: hand the registered agentweave: link to the shell."""
    subprocess.Popen(["explorer.exe", link], creationflags=0x08000000)


def link_of(xml: str) -> str:
    m = re.search(r'launch="([^"]+)"', xml)
    return (m.group(1) if m else "").replace("&amp;", "&")


def text_of(xml: str) -> str:
    return " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", xml))


# --- scratch project ---------------------------------------------------------------------------


def project_of(app: WinApp) -> str:
    _, rows = app.api("GET", "/projects")
    rows = rows if isinstance(rows, list) else (rows or {}).get("projects", [])
    for p in rows:
        if (
            pathlib.Path(p.get("path") or p.get("working_directory") or "").resolve()
            == app.cwd.resolve()
        ):
            return p["id"]
    _, p = app.api("POST", "/projects/open", {"path": str(app.cwd), "name": app.cwd.name})
    return p["id"]


def make_agent(app: WinApp, project: str, name: str, model: str) -> None:
    a = f"/projects/{project}"
    app.api("PATCH", a, {"main_branch": "main"})
    _, runner = app.api(
        "POST", f"{a}/runners", {"name": f"r-{name}", "cli": "claude", "model": model}
    )
    if not isinstance(runner, dict) or "id" not in runner:
        raise SystemExit(f"runner for {name}: {runner}")
    app.api("POST", f"{a}/agents", {"name": name, "runner_id": runner["id"]})


def ask(app: WinApp, project: str, agent: str, blocking: bool = False) -> str | None:
    """A question as the operator's API takes it (non-blocking: no run to wait on)."""
    code, q = app.api(
        "POST",
        f"/projects/{project}/questions",
        {
            "from_agent": agent,
            "question": f"{agent}: does the call come through?",
            "header": "Drive",
            "options": [
                {"label": "Yes", "description": "ok"},
                {"label": "No", "description": "no"},
            ],
            "multi_select": False,
        },
    )
    return q.get("id") if isinstance(q, dict) else None


def trigger(app: WinApp, project: str, agent: str, message: str) -> str | None:
    code, run = app.api(
        "POST",
        f"/projects/{project}/agent/trigger",
        {"agent": agent, "session_mode": "new", "message": message},
    )
    return run.get("run_id") if isinstance(run, dict) else None


def settings_get(app: WinApp):
    return app.api("GET", NOTIFY_SETTINGS_PATH)


# --- the steps ---------------------------------------------------------------------------------


def step_event(app, stream, project):
    """c-event: a question asked from a conversation carries conversation_id."""
    run = trigger(
        app,
        project,
        "haikubot",
        "Call the ask_user tool once with the question 'Does the call come through?' and two "
        "options, Yes and No. Do nothing else until it is answered.",
    )
    check("c-event: a Haiku turn started", bool(run))
    got = wait_for(
        lambda: [e for e in stream.of("question_asked") if e.get("from_agent") == "haikubot"],
        90,
        1.0,
    )
    check("c-event: the Haiku agent's question reached the operator stream", bool(got))
    if got:
        ev = got[0]
        check("c-event: question_asked has conversation_id", "conversation_id" in ev, f"{ev}")
        rows = app.db("select conversation_id from questions where id=?", (ev.get("id"),))
        check(
            "c-event: it names the conversation the question belongs to",
            bool(rows) and rows[0][0] is not None and ev.get("conversation_id") == rows[0][0],
            f"{ev} vs {rows}",
        )
        check(
            "c-event: an old-style consumer still parses it (id, from_agent, blocking intact)",
            {"id", "from_agent", "blocking"} <= set(ev),
            f"{sorted(ev)}",
        )
    return run


# The recorded sequence of every kind of event (blocking and non-blocking question, permission
# request, failed run, finished loop, agent reply, and the silent ones) is replayed through the Hub
# by hub/tests/test_operator_notices.py -- that is where c-notice's exact-sequence check lives.
# This drive checks the same contract on what it can cause live.
NON_SILENT = {
    "question_asked",
    "permission_requested",
    "run_failed",
    "loop_stopped",
    "run_completed",
}
CONTRACT = {"id", "kind", "project_id", "agent", "conversation_id", "title", "text", "source_event"}


def step_notice(app, stream, project):
    """c-notice (early): the Haiku question made exactly one ask notice, with the whole contract."""
    notices = stream.of("operator_notice")
    check(
        "c-notice: the operator stream carries operator_notice events",
        bool(notices),
        f"{len(notices)} notices; events seen: {sorted({n for n, _ in stream.events})}",
    )
    asks = [n for n in notices if n.get("kind") == "ask" and n.get("agent") == "haikubot"]
    check(
        "c-notice: the Haiku question made exactly one ask notice with a stable id",
        len(asks) == 1 and bool(asks[0].get("id")),
        f"{asks}",
    )
    for n in notices:
        check(
            f"c-notice: notice {n.get('id')} has the whole contract",
            CONTRACT <= set(n),
            f"{sorted(n)}",
        )


def step_notice_final(stream):
    """c-notice (late): over every event the drive caused so far, one notice per non-silent one."""
    events = [(n, d_) for n, d_ in list(stream.log) if n != "operator_notice"]
    notices = stream.logged("operator_notice")
    silent = [n for n in notices if n.get("source_event") not in NON_SILENT]
    check("c-notice: no notice for run_started or any other silent event", not silent, f"{silent}")
    check(
        "c-notice: notice ids are unique (one notice per event)",
        bool(notices) and len({n.get("id") for n in notices}) == len(notices),
        f"{len(notices)} notices",
    )
    for source, want in (
        ("question_asked", [d_ for n, d_ in events if n == "question_asked"]),
        ("run_failed", [d_ for n, d_ in events if n == "run_failed"]),
        (
            "run_completed",
            [
                d_
                for n, d_ in events
                if n == "run_completed" and d_.get("initiator") != "autonomous"
            ],
        ),
    ):
        if not want:
            note(f"c-notice: no {source} event was caused by this drive; nothing to count")
            continue
        got = [n for n in notices if n.get("source_event") == source]
        check(
            f"c-notice: one notice per non-silent {source} event",
            len(got) == len(want),
            f"{len(got)} notices for {len(want)} events",
        )


def step_behind(app, stream, shell, hwnd, project):
    """c-behind: window open and minimized, Haiku calls ask_user -> one notification within 5 s."""
    user32.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(1.0)
    check("c-behind: the window is minimized", bool(user32.IsIconic(hwnd)))
    shell.mark()
    stream.events.clear()
    trigger(
        app,
        project,
        "behindbot",
        "Call the ask_user tool once with the question 'Behind: does it come through?' and two "
        "options, Yes and No. Do nothing else until it is answered.",
    )
    asked = wait_for(
        lambda: [e for e in stream.of("question_asked") if e.get("from_agent") == "behindbot"],
        90,
        1.0,
    )
    check("c-behind: the agent called ask_user", bool(asked))
    t0 = time.monotonic()
    got = shell.wait_new("behindbot", LIMIT)
    took = time.monotonic() - t0
    check(
        f"c-behind: one Windows notification within {LIMIT:.0f} s of the question",
        len(got) == 1,
        f"{len(got)} under {AUMID}, {took:.1f} s after the question",
    )
    return got[0] if got else None


def step_identity(toast, xml_extra=""):
    """c-identity: source AgentWeave, the packaged icon, text names the agent."""
    check("c-identity: a notification was shown to read", toast is not None)
    if toast is None:
        return
    check("c-identity: its source is AgentWeave.Hub", toast["aumid"] == AUMID, toast["aumid"])
    check(
        "c-identity: its text names the agent",
        "behindbot" in text_of(toast["xml"]),
        text_of(toast["xml"]),
    )
    ps = (
        "$lnk = Get-ChildItem -Recurse -Filter 'AgentWeave*.lnk' "
        "([Environment]::GetFolderPath('Programs')) | Select-Object -First 1; "
        "if ($lnk) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk.FullName); "
        "$lnk.BaseName; $s.IconLocation; "
        "(Get-StartApps | Where-Object { $_.Name -eq $lnk.BaseName } | "
        "ForEach-Object { $_.AppID }) -join ';' }"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=60,
        creationflags=0x08000000,
    ).stdout.splitlines()  # by line: an icon path may hold spaces (Program Files)
    out = [line.strip() for line in out if line.strip()]
    icon = (out[1] if len(out) > 1 else "").rsplit(",", 1)[0]
    ids = (out[2] if len(out) > 2 else "").split(";")
    packaged = ROOT / "src" / "agentweave" / "assets" / "icon.ico"
    check(
        "c-identity: the Start-menu shortcut's AppUserModelID is AgentWeave.Hub",
        AUMID in ids,
        f"{out}",
    )
    check(
        "c-identity: that shortcut shows the packaged icon",
        bool(icon) and pathlib.Path(icon).name == packaged.name,
        f"{out}",
    )


def step_in_front(app, stream, shell, proc, hwnd, project):
    """c-in-front: in front -> none; closed while a second asked -> one; reopened while a third -> one."""
    check(
        "c-in-front: the window is in front",
        bring_front(hwnd),
        f"foreground {user32.GetForegroundWindow()}",
    )
    shell.mark()
    ask(app, project, "frontone")
    time.sleep(LIMIT + 1)
    first = shell.new("frontone")
    check("c-in-front: no notification for the first question", not first, f"{len(first)}")

    d.close_window(hwnd)
    ask(app, project, "fronttwo")  # asked at the same moment the window closes
    wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.1)
    second = shell.wait_new("fronttwo", 10)
    time.sleep(LIMIT)
    second = shell.new("fronttwo")
    check("c-in-front: exactly one for the second question", len(second) == 1, f"{len(second)}")

    p2 = app.launch()
    ask(app, project, "frontthree")  # asked while the window comes back
    h2 = app.wait_window(p2, 60)
    check("c-in-front: the window reopened", h2 is not None)
    time.sleep(LIMIT + 3)
    third = shell.new("frontthree")
    check("c-in-front: exactly one for the third question", len(third) == 1, f"{len(third)}")
    return h2


def step_closed(app, stream, shell, hwnd, project, watch):
    """c-closed: window closed, 'closing leaves AgentWeave running' on, a failing run -> a notification."""
    if hwnd and user32.IsWindow(hwnd):
        d.close_window(hwnd)
        wait_for(lambda: not user32.IsWindow(hwnd), 15, 0.1)
    time.sleep(2.0)
    check("c-closed: the Hub still runs with the window closed", d.healthy(app.port))
    before = set(watch.ours)
    shell.mark()
    stream.events.clear()

    def claude_children() -> set[int]:
        rows = d.processes()
        hub = set(d.hub_pids(app.port, rows))
        return {
            r["ProcessId"]
            for r in rows
            if r["ParentProcessId"] in hub and "claude" in (r.get("CommandLine") or "").lower()
        }

    existing = claude_children()  # haikubot's and behindbot's blocked turns: not to be touched
    run = trigger(
        app,
        project,
        "failbot",
        "Run this shell command and wait for it: powershell -NoProfile -Command Start-Sleep -Seconds 120",
    )
    check("c-closed: failbot's turn started", bool(run))
    # Made to fail: only this run's CLI process (the one that appears after the trigger) is killed
    # under it, which the Hub records as run_failed.
    if run and wait_for(lambda: d.run_status(app, run) == "running", 90, 1.0):
        mine = wait_for(lambda: claude_children() - existing, 60, 1.0) or set()
        time.sleep(8.0)  # let the turn get into its tool call
        for pid in mine | (claude_children() - existing):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    failed = wait_for(
        lambda: [
            e
            for e in stream.of("run_failed")
            if e.get("run_id") == run or e.get("agent") == "failbot"
        ],
        120,
        0.25,
    )
    check("c-closed: the run made to fail failed", bool(failed))
    seen = failed[0]["_seen"] if failed else time.monotonic()
    got = shell.wait_new("failbot", max(0.5, LIMIT - (time.monotonic() - seen)))
    took = time.monotonic() - seen
    check(
        f"c-closed: a notification within {LIMIT:.0f} s of the failure",
        len(got) >= 1 and took <= LIMIT + 0.5,
        f"{len(got)} under {AUMID}, {took:.1f} s after run_failed",
    )
    check(
        "c-closed: no conhost or powershell window was shown",
        set(watch.ours) == before and not watch.others,
        f"{[v for k, v in watch.ours.items() if k not in before]} {watch.others}",
    )


def step_click(app, stream, shell, project):
    """c-click: the activation link, opened through the shell, opens the conversation."""
    shell.mark()
    stream.events.clear()
    run = trigger(
        app,
        project,
        "clickbot",
        "Call the ask_user tool once with the question 'Click: does it come through?' and two "
        "options, Yes and No. Do nothing else until it is answered.",
    )
    wait_for(
        lambda: [e for e in stream.of("question_asked") if e.get("from_agent") == "clickbot"],
        90,
        1.0,
    )
    got = shell.wait_new("clickbot", 10)
    check("c-click: the question's notification was shown", bool(got))
    link = link_of(got[0]["xml"]) if got else ""
    check("c-click: it carries an agentweave: link", link.startswith("agentweave:"), link)
    hub = d.hub_pids(app.port)
    conv = None
    ev = [e for e in stream.of("question_asked") if e.get("from_agent") == "clickbot"]
    if ev:
        conv = ev[0].get("conversation_id")
    check("c-click: the window is closed and the Hub runs the turn", not app.windows())
    if link:
        open_link(link)
    h = wait_for(lambda: (app.windows() or [{}])[0].get("hwnd"), 60, 0.2)
    check("c-click: a window opens", bool(h))
    time.sleep(4.0)
    url = page_url()
    check(
        "c-click: it opens on that agent's conversation",
        bool(conv) and conv in url,
        f"{url} vs {conv}",
    )
    check(
        "c-click: the Hub's process id is unchanged",
        d.hub_pids(app.port) == hub,
        f"{hub} -> {d.hub_pids(app.port)}",
    )
    check(
        "c-click: the running turn is unchanged (same run, still running)",
        bool(run) and d.run_status(app, run) == "running",
        d.run_status(app, run) if run else "no run",
    )
    if h:
        user32.ShowWindow(h, SW_MINIMIZE)
        time.sleep(1.0)
        shell.mark()
        ask(app, project, "clicktwo")
        got2 = shell.wait_new("clicktwo", 10)
        link2 = link_of(got2[0]["xml"]) if got2 else ""
        if link2:
            open_link(link2)
        wait_for(lambda: not user32.IsIconic(h), 15, 0.2)
        time.sleep(2.0)
        check("c-click: with a window open and minimized, it is restored", not user32.IsIconic(h))
        check(
            "c-click: and it navigates there (no second window)",
            len(app.windows()) == 1,
            page_url(),
        )
        check(
            "c-click: and the running turn is still the same one",
            d.run_status(app, run) == "running",
            d.run_status(app, run),
        )
    return h


def step_quiet(app, stream, shell, project, hwnd_getter):
    """c-quiet: AW_TOAST_COMMAND failing -> in-app toast/sound/flash still happen, no error, run goes on."""
    d.close_window(hwnd_getter()) if hwnd_getter() else None
    time.sleep(2.0)
    app.cleanup()
    app.toast_command = f'"{sys.executable}" -c "import sys; sys.exit(7)"'
    p = app.launch()
    h = app.wait_window(p, 90)
    app.wait_healthy()
    time.sleep(6.0)
    check("c-quiet: the window opens with a failing toast command", h is not None)
    project = project_of(app)
    run = trigger(
        app,
        project,
        "quietbot",
        "Run: powershell -NoProfile -Command Start-Sleep -Seconds 60 . Then say done.",
    )
    user32.ShowWindow(h, SW_MINIMIZE)
    time.sleep(1.0)
    shell.mark()
    ask(app, project, "quietone")
    time.sleep(LIMIT)
    notices = [n for n in stream.of("operator_notice") if n.get("agent") == "quietone"]
    check(
        "c-quiet: the notice was published (the in-app toast is drawn from it)",
        len(notices) == 1,
        f"{len(notices)}",
    )
    seen_in_page = wait_for(lambda: "quietone" in page_text(h), LIMIT, 1.0)
    check(
        "c-quiet: the in-app toast still shows in the page (read through UI Automation)",
        bool(seen_in_page),
    )
    note(
        "c-quiet: the sound and the taskbar flash are NOT observed -- Windows exposes no read of "
        "either; they are covered by the page's own tests, and the toast above is the proof the "
        "page's notifier still ran"
    )
    check(
        "c-quiet: no Windows notification, no error window",
        not shell.new("quietone") and len(app.windows()) == 1,
    )
    check(
        "c-quiet: the run continues",
        d.run_status(app, run) in ("running", "queued", "starting", "completed"),
        d.run_status(app, run) if run else "no run",
    )
    d.close_window(h)
    time.sleep(3.0)
    ask(app, project, "quiettwo")
    time.sleep(LIMIT)
    check("c-quiet: with the window closed, the Hub carries on", d.healthy(app.port))
    check("c-quiet: and still no error window", not app.windows())


def step_kinds(app, stream, shell):
    """c-kinds: defaults, a changed choice, a restart, and the choice applied with the window closed."""
    code, body = settings_get(app)
    want = {"ask": True, "fail": True, "done": False, "reply": False}
    check(
        "c-kinds: defaults read question and failure on, done and reply off",
        code == 200 and body == want,
        f"{code} {body}",
    )
    # Through the page, as the operator does: App settings, then the Windows switches.
    p0 = app.launch()
    h0 = app.wait_window(p0, 90)
    app.wait_healthy()
    time.sleep(4.0)
    check(
        "c-kinds: App settings opens in the page",
        h0 is not None and d.choose_in_page(h0, "App settings"),
    )
    check(
        "c-kinds: the page offers a Windows switch for 'reply'",
        h0 is not None and d.choose_in_page(h0, "Windows reply"),
    )
    check(
        "c-kinds: the page offers a Windows switch for 'question'",
        h0 is not None and d.choose_in_page(h0, "Windows question"),
    )
    time.sleep(1.0)
    code, body = settings_get(app)
    check(
        "c-kinds: the page's switches reached the Hub ('reply' on, 'question' off)",
        code == 200 and body == {"ask": False, "fail": True, "done": False, "reply": True},
        f"{code} {body}",
    )
    app.cleanup()
    p = app.launch()
    app.wait_window(p, 90)
    app.wait_healthy()
    code, body = settings_get(app)
    check(
        "c-kinds: after a restart the changed choices are still in force",
        code == 200 and body == {"ask": False, "fail": True, "done": False, "reply": True},
        f"{code} {body}",
    )
    h = (app.windows() or [{}])[0].get("hwnd")
    if h:
        d.close_window(h)
        wait_for(lambda: not user32.IsWindow(h), 15, 0.1)
    time.sleep(3.0)
    project = project_of(app)
    shell.mark()
    ask(app, project, "kindquestion")
    time.sleep(LIMIT + 1)
    check(
        "c-kinds: with the window closed a question gives no Windows notification",
        not shell.new("kindquestion"),
    )
    # A reply: a run the operator started in a conversation, finished while the window is closed.
    trigger(app, project, "haikubot", "Say hello in one word.")
    got = shell.wait_new("haikubot", 60)
    check("c-kinds: and a reply gives one", len(got) >= 1, f"{len(got)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8180)
    opts = parser.parse_args()
    if opts.port in d.FORBIDDEN_PORTS:
        raise SystemExit(f"refusing port {opts.port}: :8000 and :8010 are never driven")
    if not d.port_free(opts.port):
        raise SystemExit(f"scratch port {opts.port} already in use; pick another --port")
    if os.name != "nt" or not WPN_DIR.exists():
        raise SystemExit("this drive reads Windows' notification store; run it on Windows")

    profile = PROFILE_PREFIX + RUN
    app = WinApp(opts.port, profile, d.project_dir("wn"))
    close_file = d.HUB_HOME / "app-window" / f"close-{opts.port}.json"
    close_file.parent.mkdir(parents=True, exist_ok=True)
    close_file.write_text(json.dumps({"keep_running": True}), encoding="utf-8")
    shell = Shell()
    watch = d.ConsoleWatch(lambda: app.pids).start()
    stream = None
    try:
        p = app.launch()
        hwnd = app.wait_window(p, 90)
        if not check("the app window opens", hwnd is not None):
            return 1
        check("the Hub answers", app.wait_healthy())
        time.sleep(6.0)
        stream = Stream(app)
        project = project_of(app)
        for name, model in (
            ("haikubot", d.HAIKU),
            ("behindbot", d.HAIKU),
            ("clickbot", d.HAIKU),
            ("failbot", d.HAIKU),
            ("quietbot", d.HAIKU),
        ):
            make_agent(app, project, name, model)
        steps = [
            ("c-event", lambda: step_event(app, stream, project)),
            ("c-notice", lambda: step_notice(app, stream, project)),
            (
                "c-behind+c-identity",
                lambda: step_identity(step_behind(app, stream, shell, hwnd, project)),
            ),
            ("c-in-front", lambda: step_in_front(app, stream, shell, p, hwnd, project)),
        ]
        state = {"hwnd": hwnd}
        for label, fn in steps:
            try:
                r = fn()
                if label == "c-in-front":
                    state["hwnd"] = r or state["hwnd"]
            except Exception as exc:
                check(f"{label}: ran to the end", False, f"{type(exc).__name__}: {exc}")
        for label, fn in (
            ("c-closed", lambda: step_closed(app, stream, shell, state["hwnd"], project, watch)),
            ("c-click", lambda: step_click(app, stream, shell, project)),
            ("c-notice (all events)", lambda: step_notice_final(stream)),
            (
                "c-quiet",
                lambda: step_quiet(
                    app, stream, shell, project, lambda: (app.windows() or [{}])[0].get("hwnd")
                ),
            ),
            ("c-kinds", lambda: step_kinds(app, stream, shell)),
        ):
            try:
                fn()
            except Exception as exc:
                check(f"{label}: ran to the end", False, f"{type(exc).__name__}: {exc}")
    finally:
        if stream:
            stream.stop = True
        watch.stop()
        app.cleanup()
        close_file.unlink(missing_ok=True)
        for path in [*(d.HUB_HOME / "profiles").glob(PROFILE_PREFIX + "*"), d.SCRATCH]:
            shutil.rmtree(path, ignore_errors=True)
    print("\n%d FAIL" % len(failures) if failures else "\nALL PASS", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
