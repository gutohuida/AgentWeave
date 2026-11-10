"""The long-values check: do the settings screens hold up when their values are long?

One command, from a plain checkout:

    py -3.11 scripts/checks/long_values_check.py

It starts its own Hub from this checkout's source on a temporary database, with a deeply nested
temporary project folder, seeds long values through the Hub's own API, serves this checkout's UI
(the Vite dev server, proxied to that Hub) and sweeps every App, Project and Agent settings section
at 960 and 1440px, dark and light, in a headless browser. It exits 1 and names the section and the
element for each of:

  * sideways scroll: the page, or a container, that scrolls horizontally;
  * an element outside the window: text or a control past the window's edge;
  * content spilling out of its own box (a non-wrapping value running past its row);
  * a text column under 240px beside its control (a row's label and description squeezed to
    one word per line);
  * a runner warning (.aw-control-warning) wider than its column, or none rendering on the
    Agent -> Execution page of the seeded agent the Hub reports as not runnable.

It needs nothing that is not in git: no mock fixtures, no testbed data. It uses two free ports
chosen at random and never touches :8000 (the operator's Hub) or :8010 (the trial Hub); the Hub it
starts gets a throwaway home directory too, so nothing under ~/.agentweave is read or written.

Needs: Python Playwright with a Chromium installed, Node/npm (`npm ci` runs in hub/ui when
node_modules is missing), and git.

    --width 960 --width 1440      limit the widths      --mode dark --mode light   limit the modes
    --section Agent:context       limit sections (substring of the label)
    --inject-fault                give the first row of every section a non-wrapping 600px value,
                                  to see the check fail (the check's own self-test)
    --shots DIR                   write a screenshot of every section/width/mode into DIR
    --keep                        leave the temporary folder in place and print its path
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
HUB_DIR = REPO / "hub"
UI_DIR = HUB_DIR / "ui"

FORBIDDEN_PORTS = {8000, 8010}
WIDTHS = (960, 1440)
MODES = ("dark", "light")
HEIGHT = 900
MIN_TEXT_COLUMN = 240

APP_SECTIONS = ("notifications", "appearance", "connection")
PROJECT_SECTIONS = (
    "quality",
    "instructions",
    "runners",
    "charters",
    "manager",
    "worktrees",
    "diagnostics",
    "budgets",
    "settings",
)
AGENT_SECTIONS = ("identity", "execution", "charter", "interaction", "context", "access", "workspace")
# Selector that must be on the page before a section is measured (its seeded data has loaded).
SECTION_READY = {"Agent:workspace": '[data-testid="agent-working-dir"]'}

API_KEY = "aw_live_" + "l0ngvalues" * 3 + "ab"  # throwaway key for the throwaway Hub


# --------------------------------------------------------------------------------------------
# Plumbing: ports, processes, HTTP
# --------------------------------------------------------------------------------------------


def free_port() -> int:
    while True:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in FORBIDDEN_PORTS:
            return port


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def wait_for(url: str, proc: subprocess.Popen, what: str, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{what} exited with code {proc.returncode} before it was ready")
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status < 500:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError(f"{what} did not answer {url} within {timeout:.0f}s")


class Api:
    def __init__(self, base: str) -> None:
        self.base = base

    def call(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}/api/v1{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:600]
            raise SeedError(f"{method} {path} -> {exc.code}: {detail}") from None
        return json.loads(raw) if raw else None


class SeedError(RuntimeError):
    pass


# --------------------------------------------------------------------------------------------
# The seed: long values, through the Hub's own API
# --------------------------------------------------------------------------------------------


def nested_project_dir(root: Path) -> Path:
    """A folder ~170 characters deep (Windows' 260 limit is the ceiling git and the Hub work under)."""
    segments = [f"a-long-folder-name-{i}-{'x' * 6}" for i in range(4)]
    path = root.joinpath(*segments, "the-project-whose-path-is-long")
    path.mkdir(parents=True)
    return path


def git(cwd: Path, *args: str) -> None:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="lv",
        GIT_AUTHOR_EMAIL="lv@example.invalid",
        GIT_COMMITTER_NAME="lv",
        GIT_COMMITTER_EMAIL="lv@example.invalid",
    )
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, stdout=subprocess.DEVNULL)


def long_name(prefix: str, length: int) -> str:
    return (prefix + "-" + "n" * length)[:length]


def seed(api: Api, project_dir: Path, scratch: Path) -> Dict[str, Any]:
    git(project_dir, "init", "-q", "-b", "master")
    (project_dir / "README.md").write_text("long values\n", encoding="utf-8")
    git(project_dir, "add", "README.md")
    git(project_dir, "commit", "-q", "-m", "first")

    project = api.call(
        "POST", "/projects/open", {"path": str(project_dir), "name": long_name("The project with a very long name", 80)}
    )
    pid = project["id"]
    base = f"/projects/{pid}"

    charters = []
    for i in range(3):
        charters.append(
            api.call(
                "POST",
                f"{base}/charters",
                {
                    "name": long_name(f"Charter {i} with a name that is very long indeed", 64),
                    "content": ("You work carefully and say what you did. " * 30),
                },
            )["id"]
        )

    runners = []
    for i, flags in enumerate(([], ["--append-system-prompt", "x" * 120], ["--verbose"])):
        runners.append(
            api.call(
                "POST",
                f"{base}/runners",
                {
                    "name": long_name(f"Runner {i} named at its stored maximum length", 64),
                    "cli": "claude",
                    "model": "claude-sonnet-5-5",
                    "flags": flags,
                },
            )["id"]
        )

    agents = []
    for i in range(5):
        name = long_name(f"agent{i}-with-a-maximal-name", 32)
        api.call(
            "POST",
            f"{base}/agents",
            {"name": name, "runner_id": runners[i % len(runners)], "charter_id": charters[i % len(charters)]},
        )
        agents.append(name)

    long_roots = [
        {"path": str(scratch.joinpath(*[f"granted-folder-{j}-{'y' * 20}" for j in range(8)], f"leaf-{i}")), "access": "read" if i % 2 else "readwrite"}
        for i in range(5)
    ]
    hosts = [f"{'a-very-long-subdomain-' * 3}{i}.example-registry-host.test:*" for i in range(5)]
    grants = {"roots": long_roots, "hosts": hosts}

    for name in agents:
        api.call(
            "PATCH",
            f"{base}/agents/{name}",
            {
                "description": ("An agent that does a great deal of careful work on long paths. " * 6)[:250],
                "reach_grants": grants,
            },
        )

    # An agent the Hub reports as not runnable, so Agent -> Execution shows a real runner warning
    # ("This agent cannot run: <reason>") with a long reason: the agent's own config pins a runner
    # CLI that is not a file. The Hub puts that path in the reason verbatim.
    broken = agents[-1]
    missing_cli = str(scratch.joinpath(*[f"no-such-folder-{j}-{'z' * 16}" for j in range(6)], "missing-runner-cli"))
    api.call("PATCH", f"{base}/agents/{broken}", {"config": {"cli": missing_cli}})
    verdict = api.call("GET", f"{base}/agents/launchability")["agents"][broken]
    if verdict.get("runnable") is not False:
        raise SeedError(f"the seeded agent {broken} should be reported not runnable, got {verdict}")

    checks = [
        {
            "name": long_name(f"check-{i}-with-a-name-at-the-stored-limit", 64),
            "command": f"py -3.11 -m pytest tests/ -k '{'a_very_long_selector_' * 8}' --maxfail=1 -q",
            "paths": [f"src/{'deeply/' * 6}nested/folder-{i}/**/*.py" for i in range(4)],
            "change_command": "py -3.11 -m pytest {changed_files} -q " + "--option-with-a-long-name " * 8,
            "rerun_command": "py -3.11 -m pytest {tests} -q " + "--option-with-a-long-name " * 8,
            "report_path": "reports/" + "a-long-report-folder/" * 5 + "report.xml",
        }
        for i in range(5)
    ]
    api.call(
        "PUT",
        f"{base}/settings",
        {
            "main_branch": "master",
            "checks": checks,
            "generated_files": {
                "paths": [f"src/generated/{'deeply/' * 5}file-{i}-with-a-long-name.generated.ts" for i in range(5)],
                "command": "py -3.11 scripts/regenerate_everything.py " + "--with-a-very-long-flag-name " * 14,
            },
            "pr_ci_check_names": [f"Continuous integration / {'a-matrix-job-' * 6}{i} (windows-latest, py3.11)" for i in range(5)],
            "reach_grants": grants,
        },
    )
    return {"project_id": pid, "agents": agents, "broken_agent": broken}


# --------------------------------------------------------------------------------------------
# The measurement, run inside the page
# --------------------------------------------------------------------------------------------

MEASURE_JS = r"""
({ minText, expectWarning }) => {
  const W = window.innerWidth
  const findings = []
  const seen = new Set()

  const describe = (el) => {
    const parts = []
    let node = el
    for (let depth = 0; node && node !== document.body && depth < 4; depth++, node = node.parentElement) {
      let s = node.tagName.toLowerCase()
      const tid = node.getAttribute('data-testid')
      if (tid) s += `[data-testid=${tid}]`
      else if (node.id) s += '#' + node.id
      else if (typeof node.className === 'string' && node.className.trim())
        s += '.' + node.className.trim().split(/\s+/).slice(0, 3).join('.')
      parts.unshift(s)
      if (tid) break
    }
    const text = (el.innerText || el.getAttribute('aria-label') || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 60)
    return parts.join(' > ') + (text ? `  "${text}"` : '')
  }
  const add = (kind, el, detail) => {
    const key = kind + '|' + describe(el)
    if (seen.has(key)) return
    seen.add(key)
    findings.push({ kind, element: describe(el), detail })
  }
  const visible = (el) => {
    const r = el.getBoundingClientRect()
    if (r.width <= 0 || r.height <= 0) return false
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') return false
    return !el.closest('[aria-hidden="true"], .sr-only, [hidden]')
  }
  // A box that clips or scrolls what is inside it: elements beyond its edge are its business.
  const clipsX = (el) => {
    const o = getComputedStyle(el).overflowX
    return o === 'hidden' || o === 'auto' || o === 'scroll' || o === 'clip'
  }

  // 1. Sideways scroll.
  const root = document.scrollingElement
  if (root.scrollWidth > root.clientWidth + 1)
    add('sideways-scroll', document.body, `the page scrolls sideways: ${root.scrollWidth}px of content in a ${root.clientWidth}px window`)
  const all = Array.from(document.body.querySelectorAll('*'))
  for (const el of all) {
    const cs = getComputedStyle(el)
    if ((cs.overflowX === 'auto' || cs.overflowX === 'scroll') && el.scrollWidth > el.clientWidth + 1 && visible(el)) {
      add('sideways-scroll', el, `scrolls sideways: ${el.scrollWidth}px of content in ${el.clientWidth}px`)
    }
  }

  // 2. Outside the window, and 3. content spilling out of its own box.
  for (const el of all) {
    if (!visible(el)) continue
    const r = el.getBoundingClientRect()
    if (r.right > W + 1 || r.left < -1) {
      let clipped = false
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        if (clipsX(p)) { clipped = true; break }
      }
      // A clipping ancestor excuses only what it can scroll to (right/bottom); overflow past the
      // start edge cannot be scrolled to, so it is reported even when clipped.
      if ((!clipped || r.left < -1) && !(el.closest('[data-radix-popper-content-wrapper], [role="dialog"]')))
        add('outside-window', el, `spans ${Math.round(r.left)}..${Math.round(r.right)}px in a ${W}px window`)
    }
    const cs = getComputedStyle(el)
    if (
      cs.overflowX === 'visible' &&
      (cs.display === 'block' || cs.display === 'flex' || cs.display === 'grid' || cs.display === 'flow-root') &&
      el.clientWidth > 0 &&
      el.scrollWidth > el.clientWidth + 1 &&
      el.closest('main, [data-testid], .aw-settings-page, .settings-row')
    ) {
      // text that merely reaches its box is fine; what spills past the box's right edge is not
      let spill = 0
      for (const child of el.children) {
        if (!visible(child)) continue
        const cr = child.getBoundingClientRect()
        spill = Math.max(spill, cr.right - r.right)
      }
      if (spill > 1) add('spills-out-of-its-box', el, `content runs ${Math.round(spill)}px past the right edge of its ${el.clientWidth}px box`)
    }
  }

  // 4. A text column squeezed beside its control.
  const rows = [
    ['.aw-settings-row', '.aw-settings-row-text', '.aw-settings-row-control'],
    ['.settings-row', ':scope > div:first-child', '.settings-row-control'],
  ]
  for (const [rowSel, textSel, ctlSel] of rows) {
    for (const row of document.querySelectorAll(rowSel)) {
      if (!visible(row)) continue
      const text = row.querySelector(textSel)
      const ctl = row.querySelector(ctlSel)
      if (!text || !ctl || !visible(text) || !visible(ctl)) continue
      const tr = text.getBoundingClientRect()
      const cr = ctl.getBoundingClientRect()
      const beside = cr.left >= tr.right - 1 && cr.top < tr.bottom && cr.bottom > tr.top
      if (beside && tr.width < minText)
        add('narrow-text-column', text, `text column is ${Math.round(tr.width)}px wide beside its ${Math.round(cr.width)}px control (needs ${minText}px)`)
    }
  }

  // 5. A warning under a control: it wraps inside the control's column and never widens the row.
  const warnings = Array.from(document.querySelectorAll('.aw-control-warning')).filter(visible)
  for (const w of warnings) {
    const wr = w.getBoundingClientRect()
    const holder = w.closest('.aw-settings-row-control, .settings-row-control, .aw-control-stack') || w.parentElement
    const hr = holder.getBoundingClientRect()
    if (w.scrollWidth > w.clientWidth + 1)
      add('warning-overflows', w, `warning text is ${w.scrollWidth}px wide in a ${w.clientWidth}px box`)
    else if (wr.right > hr.right + 1 || wr.left < hr.left - 1)
      add('warning-overflows', w, `warning spans ${Math.round(wr.left)}..${Math.round(wr.right)}px outside its column ${Math.round(hr.left)}..${Math.round(hr.right)}px`)
  }
  if (expectWarning && warnings.length === 0)
    add('no-runner-warning', document.body, 'this page should show a runner warning (.aw-control-warning) and shows none, so wrapping was not measured')
  return { findings, warnings: warnings.length }
}
"""

FAULT_JS = r"""
() => {
  // Break the warnings' wrapping the way a regression would: no wrapping, no break opportunities.
  for (const w of document.querySelectorAll('.aw-control-warning'))
    w.style.cssText += ';white-space:nowrap;overflow-wrap:normal;word-break:keep-all'

  const row = document.querySelector('.aw-settings-row-text, .settings-row > div')
  if (!row) return false
  const span = document.createElement('span')
  span.setAttribute('data-fault', 'long-value')
  span.textContent = 'x'.repeat(80)
  span.style.cssText = 'display:block;white-space:nowrap;width:600px;overflow:visible'
  row.appendChild(span)
  return true
}
"""


# --------------------------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------------------------


def targets(project_id: str, agent: str, broken_agent: str) -> List[Dict[str, str]]:
    out = []
    for s in APP_SECTIONS:
        out.append({"label": f"App:{s}", "query": f"appSettings={s}&project={project_id}"})
    for s in PROJECT_SECTIONS:
        out.append({"label": f"Project:{s}", "query": f"project={project_id}&tab=environment&section={s}"})
    for s in AGENT_SECTIONS:
        out.append({"label": f"Agent:{s}", "query": f"project={project_id}&agent={agent}&settings={s}"})
    # The agent the Hub reports as not runnable: its runner picker carries a long warning.
    out.append(
        {
            "label": "Agent:execution (runner warning)",
            "query": f"project={project_id}&agent={broken_agent}&settings=execution",
            "expect_warning": "1",
        }
    )
    return out


def sweep(
    args: argparse.Namespace, ui_url: str, hub_url: str, project_id: str, agent: str, broken_agent: str
) -> List[Dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    chosen = [
        t
        for t in targets(project_id, agent, broken_agent)
        if not args.section or any(f in t["label"] for f in args.section)
    ]
    if not chosen:
        raise SystemExit("no section matches --section")
    failures: List[Dict[str, Any]] = []
    measured = 0
    warnings_measured = 0
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for mode in args.mode or MODES:
                for width in args.width or WIDTHS:
                    context = browser.new_context(viewport={"width": width, "height": HEIGHT}, color_scheme=mode)
                    context.add_init_script(
                        "try{sessionStorage.setItem('agentweave-session',JSON.stringify({apiKey:%s,hubUrl:location.origin}));"
                        "localStorage.setItem('agentweave-prefs',JSON.stringify({mode:%s}));"
                        "localStorage.setItem('agentweave-selected-project',%s)}catch(e){}"
                        % (json.dumps(API_KEY), json.dumps(mode), json.dumps(project_id))
                    )
                    page = context.new_page()
                    for t in chosen:
                        for attempt in range(3):
                            # A page still settling (the app rewrites its own address) can abort the next goto.
                            page.goto("about:blank")
                            try:
                                page.goto(f"{ui_url}/?{t['query']}", wait_until="domcontentloaded", timeout=180000)
                                break
                            except Exception:  # noqa: BLE001
                                if attempt == 2:
                                    raise
                                page.wait_for_timeout(1500)
                        try:
                            page.wait_for_selector("main, .aw-settings-page, [data-testid]", timeout=60000)
                        except Exception:  # noqa: BLE001
                            pass
                        # Never measure before the section's seeded content is on the page: a render
                        # taken while the data still loads has nothing long in it and passes vacuously.
                        try:
                            page.wait_for_load_state("networkidle", timeout=30000)
                        except Exception:  # noqa: BLE001
                            pass
                        expect = SECTION_READY.get(t["label"])
                        if expect:
                            try:
                                page.locator(expect).first.wait_for(state="attached", timeout=60000)
                            except Exception:  # noqa: BLE001
                                raise SystemExit(
                                    f"{t['label']} at {width}/{mode}: {expect!r} never appeared, "
                                    "so the render cannot be measured"
                                )
                        page.wait_for_timeout(1500)
                        if args.inject_fault:
                            page.evaluate(FAULT_JS)
                            page.wait_for_timeout(100)
                        result = page.evaluate(
                            MEASURE_JS, {"minText": MIN_TEXT_COLUMN, "expectWarning": bool(t.get("expect_warning"))}
                        )
                        found = result["findings"]
                        warnings_measured += result["warnings"]
                        measured += 1
                        if shots:
                            safe = t["label"].replace(":", "-")
                            page.screenshot(path=str(shots / f"{safe}-{width}-{mode}.png"), full_page=True)
                        for f in found:
                            failures.append({"section": t["label"], "width": width, "mode": mode, **f})
                    context.close()
        finally:
            browser.close()
    print(f"measured {measured} section renders ({len(chosen)} sections), {warnings_measured} runner warning render(s)")
    return failures


def report(failures: List[Dict[str, Any]]) -> int:
    if not failures:
        print("long-values check: PASS - no sideways scroll, nothing outside the window, no squeezed text column")
        return 0
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for f in failures:
        grouped.setdefault(f["section"], []).append(f)
    print(f"long-values check: FAIL - {len(failures)} finding(s) in {len(grouped)} section(s)\n")
    for section, items in grouped.items():
        print(f"{section}")
        merged: Dict[tuple, List[str]] = {}
        for f in items:
            merged.setdefault((f["kind"], f["element"], f["detail"]), []).append(f"{f['width']}/{f['mode']}")
        for (kind, element, detail), where in merged.items():
            print(f"  [{kind}] {element}\n      {detail}   (at {', '.join(where)})")
    return 1


# --------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, action="append")
    ap.add_argument("--mode", choices=MODES, action="append")
    ap.add_argument("--section", action="append")
    ap.add_argument("--inject-fault", action="store_true")
    ap.add_argument("--shots")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if not (UI_DIR / "node_modules").exists():
        print("hub/ui/node_modules is missing; running npm ci ...")
        subprocess.run("npm ci --no-audit --no-fund --prefer-offline", cwd=UI_DIR, shell=True, check=True)

    scratch = Path(tempfile.mkdtemp(prefix="aw-lv-"))
    procs: List[subprocess.Popen] = []
    logs: List[Any] = []
    try:
        hub_port, ui_port = free_port(), free_port()
        while ui_port == hub_port:
            ui_port = free_port()
        project_dir = nested_project_dir(scratch / "projects")
        home = scratch / "home"
        home.mkdir()
        db = scratch / "db" / "agentweave.db"
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("HUB_URL", "AW_PORT") and not k.startswith(("AW_RUN_", "AW_AGENT_"))
        }
        env.update(
            DATABASE_URL="sqlite+aiosqlite:///" + db.as_posix(),
            AW_BOOTSTRAP_API_KEY=API_KEY,
            USERPROFILE=str(home),
            HOME=str(home),
            GIT_AUTHOR_NAME="lv",
            GIT_AUTHOR_EMAIL="lv@example.invalid",
            GIT_COMMITTER_NAME="lv",
            GIT_COMMITTER_EMAIL="lv@example.invalid",
            PYTHONUNBUFFERED="1",
        )
        env.pop("PYTHONPATH", None)
        py = [sys.executable]
        hub_log = (scratch / "hub.log").open("w")
        logs.append(hub_log)
        hub = subprocess.Popen(
            [*py, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", str(hub_port)],
            cwd=HUB_DIR,
            env=env,
            stdout=hub_log,
            stderr=subprocess.STDOUT,
        )
        procs.append(hub)
        hub_url = f"http://127.0.0.1:{hub_port}"
        print(f"Hub from this checkout on {hub_url} (database {db})")
        wait_for(f"{hub_url}/health", hub, "the Hub")

        api = Api(hub_url)
        data = seed(api, project_dir, scratch)
        print(f"seeded project {data['project_id']} at a {len(str(project_dir))}-character path, {len(data['agents'])} agents")

        vite_env = dict(os.environ, AW_DEV_HUB=hub_url)
        vite_log = (scratch / "vite.log").open("w")
        logs.append(vite_log)
        vite = subprocess.Popen(
            f"npx vite --host 127.0.0.1 --port {ui_port} --strictPort",
            cwd=UI_DIR,
            env=vite_env,
            shell=True,
            stdout=vite_log,
            stderr=subprocess.STDOUT,
        )
        procs.append(vite)
        ui_url = f"http://127.0.0.1:{ui_port}"
        print(f"UI from this checkout on {ui_url}")
        wait_for(ui_url + "/", vite, "the Vite dev server", timeout=120)

        failures = sweep(args, ui_url, hub_url, data["project_id"], data["agents"][0], data["broken_agent"])
        return report(failures)
    except SeedError as exc:
        print(f"long-values check: could not seed the Hub: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"long-values check: {exc}", file=sys.stderr)
        for log in ("hub.log", "vite.log"):
            path = scratch / log
            if path.exists():
                print(f"--- {log} (tail) ---\n" + "\n".join(path.read_text(errors="replace").splitlines()[-25:]), file=sys.stderr)
        return 2
    finally:
        for proc in reversed(procs):
            kill_tree(proc)
        for log_file in logs:
            log_file.close()
        if args.keep:
            print(f"kept {scratch}")
        else:
            shutil.rmtree(scratch, onerror=_clear_readonly_and_retry)


def _clear_readonly_and_retry(func: Any, path: str, _exc: Any) -> None:
    """git writes object files read-only, which makes rmtree fail on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError as exc:
        print(f"long-values check: could not remove {path}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
