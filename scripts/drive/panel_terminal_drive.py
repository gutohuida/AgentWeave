"""Acceptance drive for `a-terminal-in-the-side-panel` (TSP-1), 2026-11-14: every criterion of the
document, written failing first, before the shell service (TSP-2), the wired tab (TSP-3) and the
agent's read tool (TSP-4). TSP-5 runs it green and fixes only the drive.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default
:8016 and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them) and refuses a port something already
answers on. Never :8000 or :8010. The Hub listens on 0.0.0.0 (AW_DRIVE_HOST moves it) because
ac-remote-refused needs a non-loopback interface; Windows may show a firewall prompt for python.exe,
which can be dismissed -- the drive's own LAN requests come from this machine. Real agent turns
bind Haiku. Built on the Files tab's drive (`files_tab_drive.py`) and `d1029_build_plan_in_spec.py`.

The refusal criteria come first, each with a positive control: a refusal counts only when the same
request from loopback, signed in, from the app's own origin opens a shell (2xx and a new shell
process under the Hub), and only as 401/403 -- a 404 from a route that does not exist is not a
refusal. "Another address" is this machine's LAN address when it has one, and an X-Forwarded-For
address sent from loopback (uvicorn trusts forwarded headers from 127.0.0.1 by default, which is how
a Docker bridge address, 172.17.0.2, is simulated; it is also the hazard that check exists for).

The scenario. A scratch git repository on branch `main`, Haiku agents:
  Maker   writing agent; a quiet turn provisions its worktree. Its conversation holds the shells.
  Reader  read-only (`config.read_only`): no worktree, so the worktree choice must say why.
  Other   another conversation's agent, for ac-agent-reads' scope.
A second Hub (AW_RUNTIME=docker, port+1) serves ac-docker.

The route contract the drive probes (TSP-2's builder may rename these; TSP-5 then fixes the drive,
not the behaviour):
  GET    /api/v1/projects/{pid}/terminal/shells?conversation_id=C
           -> {shells: [{id, label, detail, wsl}], last_pick: {option_id|optionId, location}|null,
               unavailable: null|"remote"|"docker", worktree_unavailable: null|str}
  POST   /api/v1/projects/{pid}/conversations/{C}/terminals   {shell: <option id>, location}
           -> 201 {id, directory, ...}; 401/403 refused (FR-1, FR-2, FR-3), 409 over the cap (FR-7)
  GET    /api/v1/projects/{pid}/conversations/{C}/terminals   -> [{id, label, location, directory,
                                                                   running, exit_code}]
  DELETE /api/v1/projects/{pid}/conversations/{C}/terminals/{T}
  POST   /api/v1/projects/{pid}/conversations/{C}/terminals/{T}/restart
  WS     /api/v1/projects/{pid}/conversations/{C}/terminals/{T}/attach?token=<key>
           client -> {"type": "input", "data": s} | {"type": "resize", "cols", "rows"};
           server -> output as text/bytes, or JSON {"type": "output", "data"} / {"type": "exit",
           "code"}. The drive sends both the Authorization header and the `token` query.
  GET    /api/v1/agent-actions/terminals   (run credential) -> [{name, directory, running, lines}]

The page contract (the mock's TerminalTab, hub/ui/src/components/panel/TerminalTab.tsx): the tab
`[data-testid=terminal-tab]` (opened by `panel-tab-terminal` / `panel-launch-terminal` / the "Add a
tab" menu), `data-unavailable=remote|docker`, shell tabs `.aw-term-shelltab` (`data-ended`), + is
the button named "New shell", the menu's radios are LocationSwitch's, `.aw-term-menu-why`, "last
used" chip, `.aw-term-dir`, `.aw-term-surface` holds the emulator (its rows are read as text: the
DOM renderer, or `.xterm-accessibility`), `.aw-term-ended`, "Open it again", "Send to <agent>",
"Restart", `.aw-term-foot`, "Limit of 4 reached".

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots go to testbed/terminal-drive/<HHMMSS>/.

    py -3.11 scripts/drive/panel_terminal_drive.py            # own Hubs on :8016/:8017
    py -3.11 scripts/drive/panel_terminal_drive.py --no-wsl   # skip the WSL cases
"""

import argparse
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

STAMP = time.strftime("%H%M%S")
os.environ.setdefault("AW_DRIVE_PORT", "8016")
os.environ.setdefault(
    "AW_DRIVE_DB",
    str(pathlib.Path(tempfile.gettempdir()) / "drive-terminal" / STAMP / "hub.db"),
)
if os.environ["AW_DRIVE_PORT"] in ("8000", "8010"):
    sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")

import d1029_build_plan_in_spec as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from websockets.sync.client import connect as ws_connect  # noqa: E402

sys.path.insert(0, str(d.REPO / "src"))
from agentweave.cli import _hub_kill_pid  # noqa: E402 -- the operator's own stop path

HOST = os.environ.get("AW_DRIVE_HOST", "0.0.0.0")
DOCKER_PORT = d.PORT + 1
APP_ORIGIN = d.HUB
FOREIGN_ORIGIN = "http://evil.example"
OUT = d.REPO / "testbed" / "terminal-drive" / STAMP
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-terminal" / STAMP
ROOT = SCRATCH / "proj"
TURN_WAIT = 8 * 60
QUIET = "Reply with the single word OK. Do not create, edit or delete any file, and do not run git."
READ_TURN = ("Use your tool that reads this conversation's terminals (shells). Reply with every "
             "line of their output that contains AWREAD, verbatim, and for each shell say whether "
             "it is still running. Do not run any command yourself. If you have no such tool or it "
             "returns no shells, reply NONE.")
PLANTED_RUN_TOKEN = "aw_run_drive_planted_" + STAMP
PLANTED_RUN_ID = "run-drive-planted-" + STAMP
SHELL_NAMES = {"pwsh.exe", "powershell.exe", "cmd.exe", "bash.exe", "sh.exe", "wsl.exe",
               "wslhost.exe", "openconsole.exe", "conhost.exe"}
LIMIT = 4

checks = {}  # key -> (reached, failed, detail)
ends_parts = []  # (name, ok, detail) for ac-ends, recorded once the Hub has been stopped


def record(key, reached, ok, detail):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


class Setup(Exception):
    """The scenario could not be built; not a verdict on the product."""


# --------------------------------------------------------------------------- Hubs and processes


def start_hub(port, db, extra_env=None):
    """A Hub from this checkout's hub/, listening on HOST, in its own process group with a hidden
    console so the operator's stop path (CTRL_BREAK) can reach it."""
    db.parent.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/")
    )
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = d.KEY
    # ac-env: an agent run credential the Hub holds; no shell may inherit it.
    env["AW_RUN_TOKEN"] = PLANTED_RUN_TOKEN
    env["AW_RUN_ID"] = PLANTED_RUN_ID
    env.update(extra_env or {})
    log = open(db.parent / f"hub-{port}.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", HOST],
        cwd=str(d.REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000,  # CREATE_NO_WINDOW
    )
    url = f"http://127.0.0.1:{port}"
    if not d.poll(lambda: call("GET", "/projects", hub=url)[0] == 200, 120):
        proc.kill()
        raise Setup(f"the Hub on :{port} did not come up; see {db.parent / f'hub-{port}.log'}")
    print(f"started a Hub on {HOST}:{port} from {d.REPO / 'hub'} on {db}", flush=True)
    return proc


def stop_hub(proc):
    """The operator's stop: CTRL_BREAK first, forced only if that fails (cli._hub_kill_pid)."""
    if proc is None or proc.poll() is not None:
        return "already stopped"
    _hub_kill_pid(proc.pid)
    try:
        proc.wait(30)
        return "stopped"
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        return "did not stop within 30s; killed its tree"


def processes():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine "
         "| ConvertTo-Json -Compress"],
        capture_output=True, text=True, timeout=90).stdout
    return {p["ProcessId"]: p for p in json.loads(out or "[]")}


def descendants(root_pid, procs):
    children = {}
    for p in procs.values():
        children.setdefault(p["ParentProcessId"], []).append(p["ProcessId"])
    seen, stack = set(), [root_pid]
    while stack:
        for kid in children.get(stack.pop(), []):
            if kid not in seen:
                seen.add(kid)
                stack.append(kid)
    return seen


def shell_processes(hub_pid):
    """Shell-like processes under the Hub, as {pid: name}."""
    procs = processes()
    return {pid: procs[pid]["Name"] for pid in descendants(hub_pid, procs)
            if (procs[pid]["Name"] or "").lower() in SHELL_NAMES and not is_detection(procs[pid])}


def is_detection(proc):
    """The Hub's own `wsl.exe -l -q` style refresh (hub/hub/terminal/shells.py): not a terminal shell."""
    if (proc["Name"] or "").lower() != "wsl.exe":
        return False
    args = (proc.get("CommandLine") or "").lower().split()[1:]
    return bool(args) and all(a.startswith("-") for a in args) and not {"-e", "--exec", "-d", "--distribution"} & set(args)


def settled_shells(hub_pid, quiet=3.0, limit=30):
    """The shell processes once the tree has stopped changing (late children of earlier shells,
    agent runs' tool calls), so a baseline is not taken mid-spawn."""
    current, since, deadline = set(shell_processes(hub_pid)), time.time(), time.time() + limit
    while time.time() < deadline and time.time() - since < quiet:
        time.sleep(0.5)
        nxt = set(shell_processes(hub_pid))
        if nxt != current:
            current, since = nxt, time.time()
    return current


def with_cmdline(marker):
    return [p["ProcessId"] for p in processes().values() if marker in (p.get("CommandLine") or "")]


def port_open(port, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent; picks the outbound interface
            ip = s.getsockname()[0]
        except OSError:
            return None
    return None if ip.startswith("127.") else ip


def wsl_distributions():
    try:
        out = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    text = out.decode("utf-16-le", errors="ignore") if b"\x00" in out else out.decode(errors="ignore")
    return [line.strip() for line in text.splitlines() if line.strip()]


def wsl_pgrep(distro, pattern):
    done = subprocess.run(["wsl.exe", "-d", distro, "--", "pgrep", "-f", pattern],
                          capture_output=True, text=True, timeout=60)
    return [x for x in done.stdout.split() if x.isdigit()]


# --------------------------------------------------------------------------- HTTP and WebSocket


def call(method, path, body=None, hub=None, key=None, headers=None, timeout=60):
    """One request with exactly the headers given: `key=""` sends no Authorization at all."""
    data = json.dumps(body).encode() if body is not None else None
    sent = {"Content-Type": "application/json"}
    token = d.KEY if key is None else key
    if token:
        sent["Authorization"] = "Bearer " + token
    sent.update(headers or {})
    request = urllib.request.Request((hub or d.HUB) + "/api/v1" + path, data, sent, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")[:2000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def refused(code):
    return code in (401, 403)


def terminals_path(state, conv=None):
    return f"/projects/{state['pid']}/conversations/{conv or state['conv']['Maker']}/terminals"


def shell_options(state, conv=None, hub=None, pid=None):
    path = f"/projects/{pid or state['pid']}/terminal/shells?" + urllib.parse.urlencode(
        {"conversation_id": conv or state["conv"]["Maker"]})
    code, out = call("GET", path, hub=hub)
    return code, out if isinstance(out, dict) else {"shells": out if isinstance(out, list) else []}


def option_id(state, pattern, default):
    for o in state.get("options") or []:
        if re.search(pattern, str(o.get("label", "")), re.I):
            return o.get("id")
    return default


def open_shell(state, shell, location="root", conv=None, origin=APP_ORIGIN, **kw):
    headers = dict(kw.pop("headers", {}) or {})
    if origin:
        headers["Origin"] = origin
    code, out = call("POST", terminals_path(state, conv), {"shell": shell, "location": location},
                     headers=headers, **kw)
    return code, out


def shell_id(out):
    return out.get("id") if isinstance(out, dict) else None


def list_shells(state, conv=None):
    code, out = call("GET", terminals_path(state, conv))
    if isinstance(out, dict):
        out = out.get("shells") or out.get("terminals") or []
    return code, out if isinstance(out, list) else []


def close_shell(state, tid, conv=None):
    return call("DELETE", f"{terminals_path(state, conv)}/{tid}", headers={"Origin": APP_ORIGIN})


class Attached:
    """A live attachment to one shell; output is collected on a thread."""

    def __init__(self, state, tid, conv=None, origin=APP_ORIGIN, host="127.0.0.1", key=None,
                 headers=None):
        token = d.KEY if key is None else key
        path = (f"/api/v1/projects/{state['pid']}/conversations/{conv or state['conv']['Maker']}"
                f"/terminals/{tid}/attach")
        url = f"ws://{host}:{d.PORT}{path}" + (f"?token={urllib.parse.quote(token)}" if token else "")
        sent = dict(headers or {})
        if token:
            sent["Authorization"] = "Bearer " + token
        self.text, self.exit_code, self.closed = "", None, False
        self.ws = ws_connect(url, origin=origin, additional_headers=sent, proxy=None,
                             open_timeout=10, compression=None)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for frame in self.ws:
                if isinstance(frame, bytes):
                    self.text += frame.decode(errors="replace")
                    continue
                try:
                    msg = json.loads(frame)
                except ValueError:
                    self.text += frame
                    continue
                if isinstance(msg, dict) and msg.get("type") == "exit":
                    self.exit_code = msg.get("code")
                elif isinstance(msg, dict):
                    self.text += str(msg.get("data") or "")
                else:
                    self.text += frame
        except Exception:  # noqa: BLE001 -- the connection ended; `closed` says so
            pass
        self.closed = True

    def send(self, line):
        self.ws.send(json.dumps({"type": "input", "data": line + "\r"}))

    def wait_for(self, pattern, secs=20):
        return d.poll(lambda: re.search(pattern, self.text) is not None, secs, every=0.2)

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001
            pass


def try_attach(state, tid, **kw):
    """(attached or None, how it went) -- a refused handshake or an immediate close is refused."""
    try:
        att = Attached(state, tid, **kw)
    except Exception as exc:  # noqa: BLE001 -- InvalidStatus carries the refusal's status
        return None, f"handshake refused: {str(exc)[:120]}"
    time.sleep(1.5)
    if att.closed:
        return None, f"closed at once ({att.text[:60]!r})"
    return att, "attached"


# --------------------------------------------------------------------------- scenario


def turn(base, agent, message, conversation=None, hub=None):
    body = {"agent": agent, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    code, out = call("POST", f"{base}/agent/trigger", body, hub=hub, timeout=90)
    if code != 200:
        raise Setup(f"trigger {agent}: {code} {str(out)[:300]}")
    return out


def run_count(db, pid, agent):
    return ro(db, "select count(*) from runs where project_id=? and agent=?", (pid, agent))[0][0]


def last_run(db, pid, agent):
    rows = ro(db, "select id, status from runs where project_id=? and agent=? "
                  "order by started_at desc limit 1", (pid, agent))
    return rows[0] if rows else None


def ro(db, sql, args=()):
    import sqlite3
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def run_turn(db, pid, base, agent, message, conversation=None, hub=None):
    before = run_count(db, pid, agent)
    out = turn(base, agent, message, conversation, hub)
    if not d.poll(lambda: run_count(db, pid, agent) > before
                  and last_run(db, pid, agent)[1] not in ("running", "queued", "starting"),
                  TURN_WAIT, every=0.5):
        raise Setup(f"{agent}'s turn did not end within {TURN_WAIT}s")
    run_id = last_run(db, pid, agent)[0]
    reply = "".join(c for (c,) in ro(db, "select content from agent_outputs where run_id=? "
                                         "order by sequence", (run_id,)))
    return out["conversation_id"], reply


def new_project(root, name, hub=None):
    code, project = call("POST", "/projects/open", {"path": str(root), "name": name}, hub=hub)
    if code not in (200, 201):
        raise Setup(f"project open {name}: {code} {project}")
    base = f"/projects/{project['id']}"
    call("PATCH", base, {"main_branch": "main"}, hub=hub)
    code, runner = call("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude",
                                                    "model": d.HAIKU}, hub=hub)
    if code not in (200, 201):
        raise Setup(f"runner {name}: {code} {runner}")
    return project["id"], base, runner["id"]


def add_agent(base, runner_id, name, read_only=False, hub=None):
    code, out = call("POST", f"{base}/agents", {"name": name, "runner_id": runner_id}, hub=hub)
    if code not in (200, 201):
        raise Setup(f"agent {name}: {code} {out}")
    if read_only:
        code, out = call("PATCH", f"{base}/agents/{name}", {"config": {"read_only": True}}, hub=hub)
        if code != 200:
            raise Setup(f"{name} read-only: {code} {out}")


def seed_repo(root):
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("Terminal drive\n", encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")


def build_scenario(hub_proc, wsl):
    seed_repo(ROOT)
    pid, base, runner = new_project(ROOT, f"terminal-{STAMP}")
    add_agent(base, runner, "Maker")
    add_agent(base, runner, "Other")
    add_agent(base, runner, "Reader", read_only=True)
    state = {"pid": pid, "base": base, "conv": {}, "hub_pid": hub_proc.pid, "wsl": wsl}
    for agent in ("Maker", "Reader", "Other"):
        state["conv"][agent], _ = run_turn(d.DB, pid, base, agent, QUIET)
    state["worktree"] = ROOT / ".agentweave" / "worktrees" / "Maker"
    if not (state["worktree"] / ".git").is_file():
        raise Setup(f"Maker's turn left no worktree at {state['worktree']}")
    code, out = shell_options(state)
    state["options_code"], state["options"] = code, out.get("shells") or []
    state["pwsh"] = option_id(state, r"PowerShell", "powershell")
    state["bash"] = option_id(state, r"Git Bash", "git-bash")
    state["wsl_id"] = option_id(state, re.escape(wsl), f"wsl:{wsl}") if wsl else None
    print(f"  shells route {code}: {[o.get('label') for o in state['options']]}", flush=True)
    return state


# --------------------------------------------------------------------------- the page


def open_conversation(page, state, agent, hub=None, reload=False):
    url = f"{hub or d.HUB}/?project={state['pid']}&agent={agent}&conversation={state['conv'][agent]}"
    if reload:
        page.reload(wait_until="domcontentloaded")
    else:
        page.goto(url, wait_until="domcontentloaded")
    page.get_by_test_id("conversation-pane").wait_for(timeout=20000)
    page.wait_for_timeout(1500)


def open_terminal(page):
    if not page.get_by_test_id("panel-shell").count():
        more = page.get_by_role("button", name="More conversation actions")
        if more.count():
            more.first.click()
            page.get_by_test_id("conversation-toggle-panel").click()
            page.wait_for_timeout(800)
    for opener in (page.get_by_test_id("panel-tab-terminal"), page.get_by_test_id("panel-launch-terminal")):
        if opener.count():
            opener.first.click()
            break
    else:
        add = page.get_by_test_id("panel-tab-add")
        if add.count():
            add.first.click()
            page.wait_for_timeout(300)
            item = page.get_by_role("menuitem", name="Terminal")
            if item.count():
                item.first.click()
            else:
                page.keyboard.press("Escape")
    tab = page.get_by_test_id("terminal-tab")
    try:
        tab.wait_for(timeout=8000)
    except Exception:  # noqa: BLE001 -- absence is what the checks report
        pass
    page.wait_for_timeout(800)
    return tab


def tab_text(page):
    tab = page.get_by_test_id("terminal-tab")
    return tab.first.inner_text() if tab.count() else ""


def what_is_there(page):
    if page.get_by_test_id("terminal-tab").count():
        return f"terminal tab: {tab_text(page)[:160]!r}"
    if page.get_by_test_id("panel-shell").count():
        return "no Terminal tab in the panel (the app has no terminal)"
    return "no side panel"


def shell_tabs(page):
    return page.locator(".aw-term-shelltab")


def surface_text(page):
    surface = page.locator(".aw-term-surface")
    if not surface.count():
        return ""
    rows = surface.locator(".xterm-rows")
    target = rows if rows.count() else surface
    return target.first.inner_text()


def ui_type(page, text, enter=True):
    surface = page.locator(".aw-term-surface")
    if not surface.count():
        return False
    surface.first.click()
    page.keyboard.type(text, delay=5)
    if enter:
        page.keyboard.press("Enter")
    return True


def ui_open(page, label_pattern, location):
    """+ -> where -> which shell. Returns whether a new shell tab appeared."""
    before = shell_tabs(page).count()
    plus = page.get_by_role("button", name="New shell")
    if not plus.count():
        return False
    plus.first.click()
    page.wait_for_timeout(400)
    radio = page.get_by_role("radio", name=re.compile("worktree" if location == "worktree" else "Project root", re.I))
    if radio.count():
        radio.first.click()
    item = page.get_by_role("menuitem", name=re.compile(label_pattern, re.I))
    if not item.count():
        page.keyboard.press("Escape")
        return False
    item.first.click()
    return d.poll(lambda: shell_tabs(page).count() > before, 15, every=0.3)


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"))


def new_page(browser, state, hub=None, pid=None):
    page = browser.new_page(viewport={"width": 1440, "height": 940})
    page.add_init_script(
        f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, hubUrl: {(hub or d.HUB)!r}}}));"
        f"localStorage.setItem('agentweave-selected-project', {(pid or state['pid'])!r});")
    return page


# --------------------------------------------------------------------------- FR-1, FR-2, FR-3


def control_shell(state):
    """The positive control: loopback, signed in, the app's origin. (id, detail)."""
    before = set(shell_processes(state["hub_pid"]))
    code, out = open_shell(state, state["pwsh"])
    tid = shell_id(out)
    appeared = d.poll(lambda: set(shell_processes(state["hub_pid"])) - before, 15) if tid else False
    detail = f"control (loopback, signed in, app origin) {code} {str(out)[:100]!r}, new shell process={appeared}"
    return (tid if code in (200, 201) and appeared else None), detail


def check_remote_refused(browser, state):
    hub_pid, lan = state["hub_pid"], lan_address()
    tid, control = control_shell(state)
    baseline = settled_shells(hub_pid)
    attempts = []
    if lan:
        lan_hub = f"http://{lan}:{d.PORT}"
        code, _ = open_shell(state, state["pwsh"], hub=lan_hub, origin=lan_hub)
        attempts.append((f"open from {lan}", code))
        code, _ = open_shell(state, state["pwsh"], hub=lan_hub, origin=lan_hub,
                             headers={"X-Forwarded-For": "127.0.0.1"})
        attempts.append((f"open from {lan} claiming X-Forwarded-For 127.0.0.1", code))
    for label, xff in (("another address (forwarded 192.168.77.5)", "192.168.77.5"),
                       ("Docker bridge (forwarded 172.17.0.2)", "172.17.0.2")):
        code, _ = open_shell(state, state["pwsh"], headers={"X-Forwarded-For": xff})
        attempts.append((f"open from {label}", code))
    code, _ = open_shell(state, state["pwsh"], key="")
    attempts.append(("open from loopback without sign-in", code))
    run_id, token = d.hold(state["pid"], "Maker")
    try:
        code, _ = open_shell(state, state["pwsh"], key=token)
    finally:
        d.release(run_id)
    attempts.append(("open from loopback with an agent's run credential", code))
    attaches = []
    if tid:
        if lan:
            att, how = try_attach(state, tid, host=lan, origin=f"http://{lan}:{d.PORT}")
            attaches.append((f"attach from {lan}", att is None, how))
            if att:
                att.close()
        for label, kw in (("attach from Docker bridge (forwarded)", {"headers": {"X-Forwarded-For": "172.17.0.2"}}),
                          ("attach without sign-in", {"key": ""})):
            att, how = try_attach(state, tid, **kw)
            attaches.append((label, att is None, how))
            if att:
                att.close()
    time.sleep(2)
    extra = set(shell_processes(hub_pid)) - baseline
    if tid:
        close_shell(state, tid)
    # The tab used from the other address.
    message, there = "", "no LAN address on this machine"
    if lan:
        lan_hub = f"http://{lan}:{d.PORT}"
        page = new_page(browser, state, hub=lan_hub)
        try:
            open_conversation(page, state, "Maker", hub=lan_hub)
            open_terminal(page)
            message, there = tab_text(page), what_is_there(page)
            shot(page, "remote-tab")
        finally:
            page.close()
    says = "only on the computer AgentWeave runs on" in message
    ok = (tid is not None and all(refused(c) for _, c in attempts)
          and all(r for _, r, _ in attaches) and len(attaches) >= 2 and not extra and says and lan)
    record("ac-remote-refused", True, ok,
           f"{control}; " + "; ".join(f"{n}: {c}" for n, c in attempts)
           + "; " + ("; ".join(f"{n}: {h}" for n, _, h in attaches) or "no attach tried: no control shell")
           + f"; new shell processes during refusals={sorted(extra)}; tab from {lan or 'n/a'} says "
           f"the message={says} ({there})")


FOREIGN_PAGE = """<!doctype html><html><body><pre id=out>running</pre><script>
const hub = %(hub)r, key = %(key)r, path = %(path)r, tid = %(tid)r;
const out = [];
fetch(hub + '/api/v1' + path, {method: 'POST', headers: {'Authorization': 'Bearer ' + key,
  'Content-Type': 'application/json'}, body: JSON.stringify({shell: %(shell)r, location: 'root'})})
 .then(r => out.push('open:' + r.status)).catch(e => out.push('open:blocked'))
 .finally(() => {
   const ws = new WebSocket(hub.replace('http', 'ws') + '/api/v1' + path + '/' + tid + '/attach?token=' + key);
   let opened = false;
   ws.onopen = () => { opened = true; ws.send(JSON.stringify({type: 'input', data: 'echo FOREIGN-%(stamp)s\\r'})); };
   ws.onclose = (e) => { out.push('attach:' + (opened ? 'opened-then-closed-' + e.code : 'refused-' + e.code));
     document.getElementById('out').textContent = out.join(' '); };
   setTimeout(() => { if (ws.readyState === 1) { out.push('attach:open'); ws.close(); } }, 4000);
 });
</script></body></html>"""


def check_other_site_refused(browser, state):
    hub_pid = state["hub_pid"]
    tid, control = control_shell(state)
    watch = None
    if tid:
        watch, _ = try_attach(state, tid)
    baseline = settled_shells(hub_pid)
    code_open, _ = open_shell(state, state["pwsh"], origin=FOREIGN_ORIGIN)
    code_null, _ = open_shell(state, state["pwsh"], origin="null")
    att, how = (try_attach(state, tid, origin=FOREIGN_ORIGIN) if tid else (None, "no control shell"))
    ws_refused = tid is not None and att is None
    if att:
        att.close()
    # A real page from another origin, given the operator's key (the worst case: the origin is
    # the only thing standing between it and a shell).
    site = SCRATCH / "foreign"
    site.mkdir(parents=True, exist_ok=True)
    (site / "index.html").write_text(FOREIGN_PAGE % {
        "hub": d.HUB, "key": d.KEY, "path": terminals_path(state), "tid": tid or "none",
        "shell": state["pwsh"], "stamp": STAMP}, encoding="utf-8")
    port = free_port()
    server = subprocess.Popen(["py", "-3.11", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=str(site), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    page_result = ""
    try:
        d.poll(lambda: port_open(port), 15)
        page = browser.new_page()
        page.goto(f"http://127.0.0.1:{port}/index.html")
        d.poll(lambda: page.locator("#out").inner_text() != "running", 20)
        page_result = page.locator("#out").inner_text()
        page.close()
    finally:
        server.kill()
    time.sleep(2)
    extra = set(shell_processes(hub_pid)) - baseline
    echoed = watch is not None and f"FOREIGN-{STAMP}" in watch.text
    if watch:
        watch.close()
    if tid:
        close_shell(state, tid)
    page_ok = "attach:refused" in page_result and "attach:open" not in page_result and not re.search(r"open:20\d", page_result)
    ok = (tid is not None and refused(code_open) and refused(code_null) and ws_refused and page_ok
          and not extra and not echoed)
    record("ac-other-site-refused", True, ok,
           f"{control}; open with Origin {FOREIGN_ORIGIN}: {code_open}; Origin null: {code_null}; "
           f"attach with Origin {FOREIGN_ORIGIN}: {how}; foreign page said {page_result!r}; its "
           f"input reached the shell={echoed}; new shell processes={sorted(extra)}")


def check_docker(browser, state):
    db = pathlib.Path(os.environ["AW_DRIVE_DB"]).parent / "docker" / "hub.db"
    url = f"http://127.0.0.1:{DOCKER_PORT}"
    proc = start_hub(DOCKER_PORT, db, {"AW_RUNTIME": "docker"})
    try:
        root = SCRATCH / "docker-proj"
        seed_repo(root)
        pid, base, runner = new_project(root, f"terminal-docker-{STAMP}", hub=url)
        add_agent(base, runner, "Maker", hub=url)
        conv, _ = run_turn(db, pid, base, "Maker", QUIET, hub=url)
        dstate = {"pid": pid, "conv": {"Maker": conv}, "hub_pid": proc.pid}
        before = set(shell_processes(proc.pid))
        code_opts, opts = shell_options(dstate, hub=url, pid=pid)
        code, out = call("POST", f"/projects/{pid}/conversations/{conv}/terminals",
                         {"shell": state["pwsh"], "location": "root"}, hub=url,
                         headers={"Origin": url})
        extra = set(shell_processes(proc.pid)) - before
        page = new_page(browser, dstate, hub=url, pid=pid)
        try:
            open_conversation(page, dstate, "Maker", hub=url)
            open_terminal(page)
            text, there = tab_text(page), what_is_there(page)
            shot(page, "docker-tab")
        finally:
            page.close()
    finally:
        stop_hub(proc)
    says = "not available in Docker mode" in text
    names_docker = "docker" in json.dumps(out).lower()
    ok = (code in (403, 409) and names_docker and opts.get("unavailable") == "docker" and says
          and not extra)
    record("ac-docker", True, ok,
           f"Docker-mode Hub: shells route {code_opts} unavailable={opts.get('unavailable')!r}; open "
           f"{code} {str(out)[:120]!r}; new shell processes={sorted(extra)}; tab says not available "
           f"in Docker mode={says} ({there})")


# --------------------------------------------------------------------------- FR-4 .. FR-8, FR-10

def installed_shells(wsl_all):
    import shutil
    found = []
    if shutil.which("pwsh"):
        found.append("PowerShell 7")
    if shutil.which("powershell"):
        found.append("Windows PowerShell")
    if shutil.which("cmd"):
        found.append("Command Prompt")
    git = shutil.which("git")
    # git.exe sits in <Git>/cmd or <Git>/mingw64/bin; Git Bash is <Git>/bin/bash.exe.
    roots = pathlib.Path(git).resolve().parents if git else []
    if any((root / "bin" / "bash.exe").exists() and (root / "git-bash.exe").exists() for root in roots):
        found.append("Git Bash")
    return found + wsl_all


def check_detected(page, state, wsl_all):
    expected = installed_shells(wsl_all)
    labels = [str(o.get("label", "")) for o in state["options"]]
    missing = [e for e in expected if not any(e.lower() in lab.lower() for lab in labels)]
    # docker-desktop is Docker's own distribution: neither required nor counted against the menu.
    unexpected = [lab for lab in labels if not any(e.lower() in lab.lower() for e in expected)
                  and "docker-desktop" not in lab.lower()]
    code, out = open_shell(state, state["bash"])
    if shell_id(out):
        close_shell(state, shell_id(out))
    _, again = shell_options(state)
    pick = again.get("last_pick") or {}
    picked = pick.get("option_id") or pick.get("optionId")
    open_conversation(page, state, "Maker")
    open_terminal(page)
    first, marked = "", False
    plus = page.get_by_role("button", name="New shell")
    if plus.count():
        plus.first.click()
        page.wait_for_timeout(400)
        items = page.get_by_role("menuitem")
        if items.count():
            first = items.first.inner_text()
            marked = "last used" in first
        shot(page, "detected-menu")
        page.keyboard.press("Escape")
    ok = (state["options_code"] == 200 and not missing and not unexpected and code in (200, 201)
          and picked == state["bash"] and "Git Bash" in first and marked)
    record("ac-detected", True, ok,
           f"{what_is_there(page)}; shells route {state['options_code']} lists {labels}; installed "
           f"{expected}; missing={missing} unexpected={unexpected}; opened Git Bash {code}; last "
           f"pick after={picked!r}; menu's first item={first!r} marked={marked}")


def check_where(page, state):
    wsl = state["wsl"]
    open_conversation(page, state, "Maker")
    open_terminal(page)
    cases = [("worktree", r"Windows PowerShell|PowerShell", "worktree"),
             ("root", r"Windows PowerShell|PowerShell", "root")]
    if wsl:
        cases.append(("wsl-worktree", re.escape(wsl), "worktree"))
    seen = []
    for name, pattern, location in cases:
        opened = ui_open(page, pattern, location)
        page.wait_for_timeout(2500)
        shown = page.locator(".aw-term-dir").first.inner_text() if page.locator(".aw-term-dir").count() else ""
        ui_type(page, "pwd")
        page.wait_for_timeout(2000)
        screen = surface_text(page)
        prints = bool(shown) and shown.rstrip("/\\") in screen
        expect_ok = True
        if name == "wsl-worktree":
            expect_ok = shown.startswith("/mnt/") and shown.endswith("/.agentweave/worktrees/Maker")
        elif name == "worktree":
            expect_ok = shown.replace("/", "\\").lower().endswith("\\.agentweave\\worktrees\\maker")
        else:
            expect_ok = shown.replace("/", "\\").rstrip("\\").lower() == str(ROOT).lower()
        seen.append((name, opened, shown, prints and expect_ok))
        shot(page, f"where-{name}")
    open_conversation(page, state, "Reader")
    open_terminal(page)
    why, disabled = "", False
    plus = page.get_by_role("button", name="New shell")
    if plus.count():
        plus.first.click()
        page.wait_for_timeout(400)
        why = page.locator(".aw-term-menu-why").first.inner_text() if page.locator(".aw-term-menu-why").count() else ""
        radio = page.get_by_role("radio", name=re.compile("worktree", re.I))
        disabled = bool(radio.count()) and (radio.first.is_disabled() or radio.first.get_attribute("aria-disabled") == "true"
                                            or bool(why))
        shot(page, "where-no-worktree")
        page.keyboard.press("Escape")
    ok = all(o and good for _, o, _, good in seen) and (len(seen) == 3 or not wsl) and bool(why) and disabled
    record("ac-where", True, ok,
           f"{what_is_there(page)}; " + "; ".join(f"{n}: opened={o} tab shows {s!r} pwd matches={g}"
                                                  for n, o, s, g in seen)
           + f"; Reader's worktree choice disabled={disabled} reason={why!r}"
           + ("" if wsl else "; no WSL distribution installed: WSL case not run"))


def check_cap(page, state):
    open_conversation(page, state, "Maker")
    open_terminal(page)
    code, shells = list_shells(state)
    while len(shells) < LIMIT and code == 200:
        c, out = open_shell(state, state["pwsh"])
        if not shell_id(out):
            break
        code, shells = list_shells(state)
    page.wait_for_timeout(1500)
    before = shell_processes(state["hub_pid"])
    code5, out5 = open_shell(state, state["pwsh"])
    time.sleep(2)
    after = shell_processes(state["hub_pid"])
    open_conversation(page, state, "Maker", reload=False)
    open_terminal(page)
    limit_shown = "Limit of 4 reached" in tab_text(page)
    shot(page, "cap")
    names_limit = re.search(r"\b4\b|four", json.dumps(out5), re.I) is not None
    ok = len(shells) == LIMIT and code5 in (409, 429, 400, 403) and names_limit and set(after) == set(before) and limit_shown
    record("ac-cap", True, ok,
           f"{what_is_there(page)}; open shells {len(shells)} (list {code}); fifth: {code5} "
           f"{str(out5)[:120]!r}; shell processes {len(before)} -> {len(after)}; tab shows the limit={limit_shown}")
    for s in shells:
        close_shell(state, s.get("id"))


def check_interactive(page, state):
    open_conversation(page, state, "Maker")
    open_terminal(page)
    opened = ui_open(page, r"Git Bash", "root")
    page.wait_for_timeout(2500)
    ui_type(page, "printf '\\033[31mAWRED\\033[0m\\n'")
    page.wait_for_timeout(1500)
    coloured = page.evaluate("""() => {
      const spans = [...document.querySelectorAll('.aw-term-surface span')].filter(s => s.textContent.includes('AWRED'));
      return spans.some(s => /xterm-fg-(1|9)\\b/.test(s.className) || getComputedStyle(s).color.match(/rgb\\((\\d+)/)?.[1] > 150);
    }""") if opened else False
    ui_type(page, "seq 1 400 | less")
    page.wait_for_timeout(2000)
    pager = surface_text(page)
    rows = [r for r in pager.splitlines() if r.strip()]
    fills = len(rows) >= 10 and rows[0].strip() == "1"
    page.keyboard.press("q")
    page.wait_for_timeout(1000)
    after_quit = [r for r in surface_text(page).splitlines() if r.strip()]
    joined = " | ".join(after_quit)
    quit_clean = (opened and "seq 1 400 | less" in joined and "(END)" not in joined
                  and not (after_quit and after_quit[-1].strip().startswith(":")))
    ui_type(page, "tput cols")
    page.wait_for_timeout(1000)
    cols_before = re.findall(r"^\s*(\d{2,3})\s*$", surface_text(page), re.M)
    widened = "viewport"
    handle = page.locator("[data-testid=panel-resize], [role=separator]")
    if handle.count():
        box = handle.first.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] - 250, box["y"] + box["height"] / 2, steps=10)
            page.mouse.up()
            widened = "dragged the panel's edge"
    else:
        page.set_viewport_size({"width": 1900, "height": 940})
    page.wait_for_timeout(1500)
    ui_type(page, "tput cols")
    page.wait_for_timeout(1000)
    cols_after = re.findall(r"^\s*(\d{2,3})\s*$", surface_text(page), re.M)
    shot(page, "interactive")
    page.set_viewport_size({"width": 1440, "height": 940})
    wider = bool(cols_before and cols_after) and int(cols_after[-1]) > int(cols_before[-1])
    record("ac-interactive", True, opened and coloured and fills and quit_clean and wider,
           f"{what_is_there(page)}; Git Bash opened={opened}; red text drawn={coloured}; pager "
           f"filled ({len(rows)} rows, first {rows[0] if rows else ''!r})={fills}; quit cleanly={quit_clean}; "
           f"cols {cols_before[-1:]} -> {cols_after[-1:]} after {widened}")


def check_keeps_running(page, state):
    open_conversation(page, state, "Maker")
    open_terminal(page)
    opened = ui_open(page, r"Windows PowerShell|PowerShell", "root")
    page.wait_for_timeout(2500)
    ui_type(page, "1..90 | % { \"tick $_\"; Start-Sleep 1 }")
    page.wait_for_timeout(4000)
    first = re.findall(r"tick (\d+)", surface_text(page))
    open_conversation(page, state, "Reader")
    time.sleep(20)
    open_conversation(page, state, "Maker")
    open_terminal(page)
    page.wait_for_timeout(1500)
    shown = [int(n) for n in re.findall(r"tick (\d+)", surface_text(page))]
    start = int(first[-1]) if first else 0
    meanwhile = set(range(start + 1, start + 18))
    _, shells = list_shells(state)
    running = any(s.get("running") for s in shells)
    shot(page, "keeps-running")
    ok = opened and bool(first) and meanwhile <= set(shown) and running
    record("ac-keeps-running", True, ok,
           f"{what_is_there(page)}; opened={opened}; last tick before leaving {start}; on return "
           f"shows ticks {min(shown) if shown else None}..{max(shown) if shown else None}, the 17 printed "
           f"meanwhile all shown={meanwhile <= set(shown)}; a shell still running={running}")


def composer_value(page):
    box = page.get_by_test_id("conversation-pane").locator("textarea")
    return box.first.input_value() if box.count() else ""


def message_count(state):
    return ro(d.DB, "select count(*) from messages where project_id=?", (state["pid"],))[0][0]


def check_send(page, state):
    open_conversation(page, state, "Maker")
    open_terminal(page)
    ui_type(page, "cls; 'AWSEND-ONE'; 'AWSEND-TWO'")
    page.wait_for_timeout(1500)
    sent_before = message_count(state)
    rows = page.locator(".aw-term-surface .xterm-rows > div")
    one = rows.filter(has_text=re.compile(r"^AWSEND-ONE"))
    two = rows.filter(has_text=re.compile(r"^AWSEND-TWO"))
    selected = False
    if one.count() and two.count():
        one.first.click(click_count=3)
        two.first.click(modifiers=["Shift"])
        selected = True
    button = page.get_by_role("button", name=re.compile(r"^Send to Maker"))
    first = second = ""
    directory = page.locator(".aw-term-dir").first.inner_text() if page.locator(".aw-term-dir").count() else "?"
    if button.count():
        button.first.click()
        page.wait_for_timeout(800)
        first = composer_value(page)
        page.locator(".aw-term-surface").first.click()  # clears the selection
        button.first.click()
        page.wait_for_timeout(800)
        second = composer_value(page)
    shot(page, "send")
    marked = directory != "?" and directory in first and re.search(r"PowerShell", first) is not None
    unsent = message_count(state) == sent_before
    ok = (selected and "AWSEND-ONE" in first and "AWSEND-TWO" in first and marked
          and len(second) > len(first) and directory in second[len(first):] and unsent)
    record("ac-send", True, ok,
           f"{what_is_there(page)}; selected two lines={selected}; composer after the first press "
           f"{first[:160]!r} (marked with shell and {directory!r}={marked}); after the second "
           f"{second[len(first):][:120]!r}; nothing sent={unsent}")


def env_listing(state, shell, command, location="root"):
    code, out = open_shell(state, shell, location)
    tid = shell_id(out)
    if not tid:
        return code, None, f"open {code} {str(out)[:100]!r}"
    try:
        att = Attached(state, tid)
    except Exception as exc:  # noqa: BLE001
        close_shell(state, tid)
        return code, None, f"attach failed: {str(exc)[:100]}"
    time.sleep(2)
    att.send(command)
    att.wait_for(r"ENV-END", 20)
    text = att.text
    att.close()
    close_shell(state, tid)
    return code, text, "listed"


def env_verdict(text):
    names = set(re.findall(r"ENV:([A-Za-z_][A-Za-z0-9_]*)", text or ""))
    leaked = [n for n in ("DATABASE_URL", "AW_BOOTSTRAP_API_KEY", "AW_RUN_TOKEN", "AW_RUN_ID") if n in names]
    values = [v for v in (d.KEY, PLANTED_RUN_TOKEN, PLANTED_RUN_ID, d.DB.as_posix()) if v in (text or "")]
    has_path = "PATH" in names or "Path" in names
    return has_path and not leaked and not values, f"PATH={has_path} leaked names={leaked} leaked values={len(values)}"


def check_env(state):
    code, text, how = env_listing(state, state["pwsh"],
                                  "Get-ChildItem env: | % { 'ENV:' + $_.Name + '=' + $_.Value }; 'ENV-END'")
    ok_pw, said_pw = env_verdict(text)
    parts = [f"PowerShell: {how}; {said_pw}"]
    ok = ok_pw and text is not None
    if state["wsl"]:
        code, text, how = env_listing(state, state["wsl_id"], "env | sed 's/^/ENV:/'; echo ENV-END")
        ok_wsl, said_wsl = env_verdict(text)
        ok = ok and ok_wsl and text is not None
        parts.append(f"WSL {state['wsl']}: {how}; {said_wsl}")
    else:
        parts.append("no WSL distribution: WSL case not run")
    record("ac-env", True, ok, "; ".join(parts))


def check_agent_reads(page, state):
    conv, other = state["conv"]["Maker"], state["conv"]["Other"]
    code1, out1 = open_shell(state, state["pwsh"])
    code2, out2 = open_shell(state, state["pwsh"])
    live, ended = shell_id(out1), shell_id(out2)
    if live:
        att = Attached(state, live)
        time.sleep(2)
        att.send("1..700 | % { \"AWREAD-$_\" }")
        att.wait_for(r"AWREAD-700", 30)
        att.close()
    if ended:
        att = Attached(state, ended)
        time.sleep(2)
        att.send("'AWREAD-ENDED'; exit 0")
        time.sleep(3)
        att.close()
    route_code, rows = d.as_agent(state["pid"], "Maker", "GET", "/terminals?" + urllib.parse.urlencode({"conversation_id": conv}))
    if isinstance(rows, dict):
        rows = rows.get("shells") or []
    if not isinstance(rows, list):
        rows = []
    lines = [r.get("lines") or [] for r in rows]
    bounded = bool(lines) and all(len(x) <= 500 for x in lines) and any("AWREAD-700" in "\n".join(x) for x in lines) \
        and not any(re.search(r"AWREAD-100\b", "\n".join(x)) for x in lines)
    other_code, other_rows = d.as_agent(state["pid"], "Other", "GET", "/terminals?" + urllib.parse.urlencode({"conversation_id": conv}))
    other_sees = "AWREAD" in json.dumps(other_rows)
    input_code, _ = d.as_agent(state["pid"], "Maker", "POST", f"/terminals/{live}/input", {"data": "echo AWTYPED\r"})
    _, reply = run_turn(d.DB, state["pid"], state["base"], "Maker", READ_TURN, conv)
    _, other_reply = run_turn(d.DB, state["pid"], state["base"], "Other", READ_TURN, other)
    _, shells = list_shells(state)
    typed = any("AWTYPED" in json.dumps(s) for s in shells)
    open_conversation(page, state, "Maker")
    open_terminal(page)
    foot = page.locator(".aw-term-foot").first.inner_text() if page.locator(".aw-term-foot").count() else ""
    shot(page, "agent-reads")
    ok = (code1 in (200, 201) and code2 in (200, 201) and route_code == 200 and bounded
          and not other_sees and input_code not in (200, 201, 202, 204) and not typed
          and "AWREAD-700" in reply and "AWREAD-ENDED" in reply and "AWREAD" not in other_reply
          and "Maker can read these" in foot)
    record("ac-agent-reads", True, ok,
           f"{what_is_there(page)}; shells opened {code1}/{code2}; agent route {route_code}: "
           f"{len(rows)} shells, at most 500 lines each and the last ones={bounded}; Other sees Maker's "
           f"shells={other_sees}; agent input {input_code}, reached the shell={typed}; Maker's reply "
           f"{reply[:120]!r}; Other's reply {other_reply[:80]!r}; footer {foot!r}")
    for tid in (live, ended):
        if tid:
            close_shell(state, tid)


# --------------------------------------------------------------------------- FR-9


def server_command(kind, port):
    if kind == "wsl":
        return f"python3 -m http.server {port} --bind 127.0.0.1"
    return f"py -3.11 -m http.server {port} --bind 127.0.0.1"


def child_alive(kind, port, distro):
    if kind == "wsl":
        return bool(wsl_pgrep(distro, f"http.server {port}"))
    return bool(with_cmdline(f"http.server {port}"))


def start_server_shell(state, kind):
    """A shell (via the routes) running a child that listens on a port. (tid, port, detail)."""
    shell = state["wsl_id"] if kind == "wsl" else state["pwsh"]
    port = free_port()
    code, out = open_shell(state, shell)
    tid = shell_id(out)
    if not tid:
        return None, port, f"open {code} {str(out)[:100]!r}"
    try:
        att = Attached(state, tid)
    except Exception as exc:  # noqa: BLE001
        return tid, port, f"attach failed: {str(exc)[:100]}"
    time.sleep(3 if kind != "wsl" else 6)
    att.send(server_command(kind, port))
    up = d.poll(lambda: child_alive(kind, port, state["wsl"]), 30)
    att.close()
    return tid, port, f"child listening on {port}={up}"


def gone(state, kind, port, before_shells):
    """Polls until the child and the port are gone and no shell process of these remains."""
    def clear():
        return (not child_alive(kind, port, state["wsl"]) and not port_open(port)
                and not (set(shell_processes(state["hub_pid"])) & before_shells))
    return d.poll(clear, 20, every=1)


def ends_by(state, kind, how):
    """close / restart: start a server in a shell, end it `how`, see everything gone."""
    baseline = set(shell_processes(state["hub_pid"]))
    tid, port, detail = start_server_shell(state, kind)
    if not tid or "=True" not in detail:
        ends_parts.append((f"{how} ({kind})", False, detail))
        if tid:
            close_shell(state, tid)
        return
    mine = set(shell_processes(state["hub_pid"])) - baseline
    if how == "close":
        code, _ = close_shell(state, tid)
    else:
        code, _ = call("POST", f"{terminals_path(state)}/{tid}/restart", headers={"Origin": APP_ORIGIN})
    ok = code in (200, 202, 204) and gone(state, kind, port, mine)
    ends_parts.append((f"{how} ({kind})", ok, f"{detail}; {how} {code}; shell, child and port gone={ok}"))
    if how == "restart":
        _, shells = list_shells(state)
        for s in shells:
            close_shell(state, s.get("id"))


def ends_by_reload(page, state):
    open_conversation(page, state, "Maker")
    open_terminal(page)
    port = free_port()
    if not shell_tabs(page).count():
        ui_open(page, r"Windows PowerShell|PowerShell", "root")
    page.wait_for_timeout(2500)
    typed = ui_type(page, server_command("powershell", port))
    up = d.poll(lambda: child_alive("powershell", port, None), 30)
    _, before = list_shells(state)
    earlier = {s.get("id") for s in before}
    shells_before = set(shell_processes(state["hub_pid"]))
    open_conversation(page, state, "Maker", reload=True)
    cleared = up and gone(state, "powershell", port, shells_before)
    open_terminal(page)
    page.wait_for_timeout(3000)
    _, after = list_shells(state)
    fresh = len(after) == 1 and not ({s.get("id") for s in after} & earlier)
    tabs = shell_tabs(page).count()
    shot(page, "after-reload")
    ok = typed and up and cleared and fresh and tabs == 1
    ends_parts.append(("reload", ok, f"{what_is_there(page)}; child listening on {port}={up}; after "
                       f"reload shell, child and port gone={cleared}; shells listed {len(after)} "
                       f"(none earlier={fresh}), tabs {tabs}"))
    # typing exit shows it ended, with its exit code
    ui_type(page, "exit 3")
    shown = d.poll(lambda: "Ended with exit code 3" in tab_text(page).replace("\n", " "), 15)
    again = page.get_by_role("button", name="Open it again").count() > 0
    shot(page, "exit")
    ends_parts.append(("exit", shown and again, f"after `exit 3` the tab shows 'Ended with exit code 3'={shown}, "
                       f"'Open it again'={again}"))


def ends_by_hub_stop(state, hub_proc, kinds):
    started = []
    for kind in kinds:
        baseline = set(shell_processes(state["hub_pid"]))
        tid, port, detail = start_server_shell(state, kind)
        started.append((kind, tid, port, detail, set(shell_processes(state["hub_pid"])) - baseline))
    how = stop_hub(hub_proc)
    for kind, tid, port, detail, mine in started:
        if not tid or "=True" not in detail:
            ends_parts.append((f"Hub stop ({kind})", False, detail))
            continue
        procs = processes()
        alive = [p for p in mine if p in procs]

        def clear(kind=kind, port=port):
            return not child_alive(kind, port, state["wsl"]) and not port_open(port)
        ok = d.poll(clear, 20, every=1) and not alive
        ends_parts.append((f"Hub stop ({kind})", ok, f"{detail}; Hub {how}; shell processes left "
                           f"{alive}; child and port gone={ok}"))


# --------------------------------------------------------------------------- main

ORDER = ("ac-remote-refused", "ac-other-site-refused", "ac-docker", "ac-detected", "ac-where",
         "ac-cap", "ac-interactive", "ac-keeps-running", "ac-send", "ac-env", "ac-agent-reads",
         "ac-ends")


def guarded(key, fn, *args):
    try:
        fn(*args)
    except Setup as exc:  # this check's own scenario could not be built; the drive goes on
        print(f"SETUP {key}: {exc}", flush=True)
        checks.setdefault(key, (False, False, f"its scenario could not be built: {exc}"))
    except Exception as exc:  # noqa: BLE001 -- a step that broke before its assertion
        print(f"BROKE {key}: {exc}", flush=True)
        checks.setdefault(key, (False, False, f"broke before its assertion: {str(exc)[:200]}"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wsl", action="store_true", help="skip the WSL cases")
    args = parser.parse_args()
    for port in (d.PORT, DOCKER_PORT):
        if call("GET", "/projects", hub=f"http://127.0.0.1:{port}")[0] != 0:
            sys.exit(f"REFUSING: something already answers on :{port}; this drive starts its own "
                     "Hubs from this checkout. Pick another AW_DRIVE_PORT.")
    distros = [] if args.no_wsl else [x for x in wsl_distributions() if not x.startswith("docker-desktop")]
    wsl = distros[0] if distros else None
    hub = start_hub(d.PORT, d.DB)
    print(f"output {OUT}; WSL distribution {wsl or 'none'}", flush=True)
    setup_error = None
    try:
        state = build_scenario(hub, wsl)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = new_page(browser, state)
            guarded("ac-remote-refused", check_remote_refused, browser, state)
            guarded("ac-other-site-refused", check_other_site_refused, browser, state)
            guarded("ac-docker", check_docker, browser, state)
            guarded("ac-detected", check_detected, page, state, distros)
            guarded("ac-where", check_where, page, state)
            guarded("ac-cap", check_cap, page, state)
            guarded("ac-interactive", check_interactive, page, state)
            guarded("ac-keeps-running", check_keeps_running, page, state)
            guarded("ac-send", check_send, page, state)
            guarded("ac-env", check_env, state)
            guarded("ac-agent-reads", check_agent_reads, page, state)
            kinds = ["powershell"] + (["wsl"] if wsl else [])
            try:
                for kind in kinds:
                    ends_by(state, kind, "close")
                ends_by(state, "powershell", "restart")
                ends_by_reload(page, state)
                browser.close()
                ends_by_hub_stop(state, hub, kinds)
                ok = all(o for _, o, _ in ends_parts) and len(ends_parts) >= 4 + 2 * len(kinds) - 1
                record("ac-ends", True, ok, "; ".join(f"{n}: {'ok' if o else 'FAILED'} ({t})"
                                                      for n, o, t in ends_parts)
                       + ("" if wsl else "; no WSL distribution: WSL cases not run"))
            except Exception as exc:  # noqa: BLE001
                print(f"BROKE ac-ends: {exc}", flush=True)
                checks.setdefault("ac-ends", (False, False, f"broke before its assertion: {str(exc)[:200]}"))
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        stop_hub(hub)
    print("\n== drive_baseline")
    failed = False
    for key in ORDER:
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {OUT}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
