"""The settings-style check: are settings where their names say, saved on change, in the app's own controls?

One command, from a plain checkout:

    py -3.11 scripts/checks/settings_style_check.py

It starts its own Hub from this checkout's source on a temporary database (the harness
long_values_check.py uses: same plumbing, same throwaway home, two free ports, never :8000 or
:8010), serves this checkout's UI through the Vite dev server and drives it in a headless browser.
It exits 1 and names the section for each failure of the change `settings-in-the-app-s-style-where-
you-expect-them`:

  * ac-sections-listed  Project settings' side list: four group headings, fifteen sections, in
                        order, no General, Quality or Runners.
  * ac-every-setting    each project section holds the labelled rows the requirement places on it,
                        and no such setting sits on a second section.
  * ac-old-links        the old General, Quality, Runners and old agent section URLs open their
                        successor section, not an empty page.
  * ac-no-save-buttons  no Save / Save steps / Save export settings button outside Instructions;
                        changing a hop budget, a spec step's sizes, the trace retention and an
                        agent's question wait each issues exactly one write with no further click.
  * ac-no-native        no input[type=checkbox], input[type=date] or select on any section.
  * ac-agent-sections   an agent's settings list exactly Agent, Running, Permissions, Checkpoints
                        and Workspace, each holding the rows the requirement names.

It is not one of the project's checks. Needs Python Playwright with a Chromium, Node/npm, git.

    --keep    leave the temporary folder in place and print its path
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import long_values_check as lv  # noqa: E402  (the harness: Hub, Vite, ports, the API client)

UI_DIR = lv.UI_DIR
HUB_DIR = lv.HUB_DIR
API_KEY = lv.API_KEY

WIDTH, HEIGHT = 1440, 900

PROJECT_GROUPS: List[Tuple[str, List[str]]] = [
    ("Project", ["Project", "Collaboration", "Permissions", "Budgets"]),
    ("Agents", ["Instructions", "Charters", "Checkpoints", "Manager"]),
    ("Landing work", ["Checks", "Landing", "Worktrees"]),
    ("Specs and records", ["Spec steps", "Traces", "Diagnostics"]),
]
PROJECT_SECTIONS = [s for _, sections in PROJECT_GROUPS for s in sections]
AGENT_SECTION_LIST = ["Agent", "Running", "Permissions", "Checkpoints", "Workspace"]
FORBIDDEN_PROJECT = ("General", "Quality", "Runners")

# What the requirements place on each section: (name, regex on a row label). A setting whose rows
# are not labelled rows (delete, archive, provider sessions) matches anywhere in the section text,
# marked with a leading "~". Matched case-insensitively.
PROJECT_ROWS: Dict[str, List[Tuple[str, str]]] = {
    "Project": [("name", r"^name$"), ("folder", r"^folder$"), ("delete", "~delete")],
    "Collaboration": [
        ("jobs allowed", r"jobs"),
        ("hop budget", r"^hop budget"),
        ("deliveries per turn", r"^deliveries per turn"),
    ],
    "Permissions": [("default permissions", r"^default permissions$"), ("granted reach", r"^granted reach$")],
    "Budgets": [("agent budget", r"^agent budget"), ("token limit", r"token limit|pause agents working")],
    "Checkpoints": [
        ("checkpoint mode", r"^checkpoints$"),
        ("checkpoint at", r"^checkpoint at$"),
        ("ask for notes at", r"^ask for notes at$"),
        ("continue automatically", r"^continue automatically$"),
        ("checkpoint runner", r"^checkpoint runner$"),
        ("checkpoint model", r"^checkpoint model$"),
    ],
    "Checks": [
        ("checks", r"^checks$"),
        ("checks give way", r"^checks give way"),
        ("generated files", r"^generated files"),
    ],
    "Landing": [
        ("main branch", r"^main branch"),
        ("pull-request landing", r"pull request"),
        ("one commit per build", r"^one commit per build"),
        ("PR CI as the full check", r"full check"),
        ("CI check names", r"^ci check names"),
        ("CI interval", r"^ci asked every"),
        ("CI cutoff", r"^ci asking stops"),
    ],
}
AGENT_ROWS: Dict[str, List[Tuple[str, str]]] = {
    "Agent": [
        ("name", r"^name$"),
        ("description", r"^description$"),
        ("last active", r"^last active$"),
        ("charter", r"^charter$"),
        ("archive", "~archive"),
    ],
    "Running": [
        ("model", r"^model$"),
        ("permission-decision wait", r"permission decision"),
        ("question wait", r"question"),
    ],
    "Permissions": [
        ("default permissions", r"^default permissions$"),
        ("own granted reach", r"reach"),
        ("reading other agents' checkpoints", r"checkpoints"),
        ("recall", r"recall"),
        ("deciding evidence", r"evidence"),
        ("keeping the specs true", r"spec"),
    ],
    "Checkpoints": [
        ("checkpoint mode", r"^checkpoints$"),
        ("its checkpoint point", r"^checkpoint at$"),
        ("its checkpoints taken", r"^its checkpoints$"),
    ],
    "Workspace": [
        ("working directory", r"^working directory$"),
        ("its own checkout", r"^its own checkout$"),
        ("provider sessions", "~provider sessions"),
    ],
}

OLD_PROJECT_LINKS = [("settings", "Project"), ("quality", "Project"), ("runners", "Project")]
OLD_AGENT_LINKS = [
    ("identity", "Agent"),
    ("charter", "Agent"),
    ("execution", "Running"),
    ("interaction", "Running"),
    ("access", "Permissions"),
    ("context", "Checkpoints"),
]

# --------------------------------------------------------------------------------------------
# Seed
# --------------------------------------------------------------------------------------------


def seed(api: lv.Api, project_dir: Path) -> Dict[str, Any]:
    lv.git(project_dir, "init", "-q", "-b", "master")
    (project_dir / "README.md").write_text("settings style\n", encoding="utf-8")
    lv.git(project_dir, "add", "README.md")
    lv.git(project_dir, "commit", "-q", "-m", "first")
    pid = api.call("POST", "/projects/open", {"path": str(project_dir), "name": "Settings style"})["id"]
    base = f"/projects/{pid}"
    charter = api.call("POST", f"{base}/charters", {"name": "Careful", "content": "You work carefully.\n"})["id"]
    runner = api.call(
        "POST", f"{base}/runners", {"name": "Sonnet", "cli": "claude", "model": "claude-sonnet-5-5", "flags": []}
    )["id"]
    agent = "worker"
    api.call("POST", f"{base}/agents", {"name": agent, "runner_id": runner, "charter_id": charter})
    # One step of the operator's own, so a step's sizes have something to change.
    steps = api.call("GET", f"{base}/project/journey")["steps"]
    steps.append({"key": "review-notes", "title": "Review notes", "instructions": "Read the notes.\n", "sizes": ["large"]})
    api.call("PUT", f"{base}/project/journey", {"steps": steps})
    return {"project_id": pid, "agent": agent}


# --------------------------------------------------------------------------------------------
# Page helpers (run in the page)
# --------------------------------------------------------------------------------------------

NAV_JS = r"""
() => {
  const items = []
  for (const li of document.querySelectorAll('.aw-settings-nav-list > li')) {
    const g = li.querySelector('.aw-settings-nav-group')
    const b = li.querySelector('[data-slot="settings-nav-item"] span.flex-1')
    const btn = li.querySelector('[data-slot="settings-nav-item"]')
    items.push({
      group: g ? g.textContent.trim() : null,
      label: b ? b.textContent.trim() : '',
      active: btn ? btn.getAttribute('data-active') === 'true' : false,
    })
  }
  return items
}
"""

SECTION_JS = r"""
() => {
  const scroll = document.querySelector('.aw-settings-scroll')
  if (!scroll) return null
  const labels = []
  for (const el of scroll.querySelectorAll('.aw-settings-row-label')) labels.push(el.textContent.trim())
  for (const row of scroll.querySelectorAll('.settings-row')) {
    const first = row.firstElementChild && row.firstElementChild.firstElementChild
    if (first) labels.push(first.textContent.trim())
  }
  const inDialog = (el) => !!el.closest('[role="dialog"]')
  const saves = [...scroll.querySelectorAll('button')]
    .filter((b) => !inDialog(b))
    .map((b) => (b.textContent || '').trim() || b.getAttribute('aria-label') || '')
    .filter((t) => /^save\b/i.test(t))
  return {
    labels,
    text: scroll.innerText.toLowerCase(),
    saves,
    checkboxes: scroll.querySelectorAll('input[type="checkbox"]').length,
    dates: scroll.querySelectorAll('input[type="date"]').length,
    selects: scroll.querySelectorAll('select').length,
  }
}
"""


class Driver:
    def __init__(self, page: Any, ui_url: str, project_id: str, agent: str) -> None:
        self.page, self.ui, self.pid, self.agent = page, ui_url, project_id, agent
        self.writes: List[str] = []
        page.on("request", self._on_request)

    def _on_request(self, req: Any) -> None:
        if req.method in ("POST", "PUT", "PATCH", "DELETE") and "/api/v1/" in req.url:
            self.writes.append(f"{req.method} {req.url.split('/api/v1')[1].split('?')[0]}")

    def settle(self, ms: int = 1200) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:  # noqa: BLE001
            pass
        self.page.wait_for_timeout(ms)

    def open(self, query: str) -> None:
        for attempt in range(3):
            self.page.goto("about:blank")
            try:
                self.page.goto(f"{self.ui}/?{query}", wait_until="domcontentloaded", timeout=120000)
                break
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    raise
                self.page.wait_for_timeout(1500)
        try:
            self.page.wait_for_selector(".aw-settings-nav-list", timeout=60000)
        except Exception:  # noqa: BLE001
            pass
        self.settle()

    def project(self, section_id: str) -> None:
        self.open(f"project={self.pid}&tab=environment&section={section_id}")

    def agent_settings(self, section_id: str) -> None:
        self.open(f"project={self.pid}&agent={self.agent}&settings={section_id}")

    def nav(self) -> List[Dict[str, Any]]:
        return self.page.evaluate(NAV_JS)

    def active(self) -> Optional[str]:
        for item in self.nav():
            if item["active"]:
                return item["label"]
        return None

    def go(self, label: str) -> bool:
        """Click the side-list item named `label`; False when there is none."""
        item = self.page.locator('[data-slot="settings-nav-item"]').filter(has_text=re.compile(rf"^\s*{re.escape(label)}(\s*\d+|\s*\d* on|\s*Off)?\s*$"))
        if item.count() == 0:
            return False
        item.first.click()
        self.settle()
        return True

    def read(self) -> Optional[Dict[str, Any]]:
        return self.page.evaluate(SECTION_JS)

    def change(self, row: re.Pattern[str], action: str) -> Tuple[bool, List[str], str]:
        """Change the control in the first row whose label matches; return (found, writes, note)."""
        self.writes.clear()
        rows = self.page.locator(".aw-settings-row, .settings-row").filter(has_text=row)
        if rows.count() == 0:
            return False, [], "no such row"
        r = rows.first
        if action == "number":
            field = r.locator("input:not([type=hidden]):not([type=checkbox])").first
            if field.count() == 0:
                return False, [], "row has no text/number field"
            current = field.input_value()
            field.fill(str(int(current) + 1) if current.strip().isdigit() else "7")
            field.press("Tab")
        elif action == "size":
            toggle = r.locator('[role="switch"], [role="checkbox"], input[type="checkbox"], [role="radio"], [aria-pressed]').first
            if toggle.count() == 0:
                return False, [], "row has no size control"
            toggle.click()
        else:
            return False, [], f"unknown action {action}"
        self.page.wait_for_timeout(1800)
        return True, list(self.writes), ""


def expected_hits(rows: Dict[str, List[Tuple[str, str]]], section: str, data: Dict[str, Any]) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for name, pattern in rows[section]:
        if pattern.startswith("~"):
            out[name] = pattern[1:] in data["text"]
        else:
            out[name] = any(re.search(pattern, label, re.I) for label in data["labels"])
    return out


# --------------------------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------------------------


def run(d: Driver) -> List[str]:
    fails: List[str] = []

    def fail(ac: str, msg: str) -> None:
        fails.append(f"[{ac}] {msg}")

    # --- project side list -----------------------------------------------------------------
    d.project("instructions")
    nav = d.nav()
    got = [(i["group"], i["label"]) for i in nav]
    labels_only = [i["label"] for i in nav]
    headings = [i["group"] for i in nav if i["group"]]
    want_headings = [g for g, _ in PROJECT_GROUPS]
    want_labels = PROJECT_SECTIONS
    if headings != want_headings:
        fail("ac-sections-listed", f"group headings are {headings}, want {want_headings}")
    if labels_only != want_labels:
        fail("ac-sections-listed", f"sections are {labels_only}, want {want_labels}")
    for bad in FORBIDDEN_PROJECT:
        if bad in labels_only:
            fail("ac-sections-listed", f"the side list still has '{bad}'")
    del got

    # --- each project section --------------------------------------------------------------
    found_on: Dict[Tuple[str, str], List[str]] = {}
    sections_seen: List[str] = []
    for section in sorted(set(labels_only) | set(PROJECT_SECTIONS), key=lambda s: PROJECT_SECTIONS.index(s) if s in PROJECT_SECTIONS else 99):
        d.project("instructions")
        if not d.go(section):
            if section in PROJECT_SECTIONS:
                fail("ac-every-setting", f"project section '{section}' cannot be opened (not in the side list)")
            continue
        sections_seen.append(section)
        data = d.read()
        if data is None:
            fail("ac-every-setting", f"project section '{section}' rendered no settings area")
            continue
        if section != "Instructions" and data["saves"]:
            fail("ac-no-save-buttons", f"project '{section}' shows Save button(s): {data['saves']}")
        if section == "Instructions" and len(data["saves"]) > 1:
            fail("ac-no-save-buttons", f"project 'Instructions' shows {len(data['saves'])} Save buttons, want one")
        for what, n in (("checkbox", data["checkboxes"]), ("date input", data["dates"]), ("select", data["selects"])):
            if n:
                fail("ac-no-native", f"project '{section}' renders {n} native {what}(s)")
        if section in PROJECT_ROWS:
            hits = expected_hits(PROJECT_ROWS, section, data)
            for name, ok in hits.items():
                if not ok:
                    fail("ac-every-setting", f"project '{section}' has no '{name}' row (rows: {data['labels']})")
            for other_section, others in PROJECT_ROWS.items():
                if other_section == section:
                    continue
                for name, pattern in others:
                    if pattern.startswith("~"):
                        continue
                    if any(re.search(pattern, label, re.I) for label in data["labels"]):
                        found_on.setdefault((other_section, name), []).append(section)
    for (home, name), also in found_on.items():
        fail("ac-every-setting", f"'{name}' belongs on '{home}' but also appears on {also}")

    # --- changes issue one write, no click -------------------------------------------------
    probes = [
        ("Collaboration", re.compile(r"hop budget", re.I), "number", "a hop budget"),
        ("Spec steps", re.compile(r"review notes", re.I), "size", "a spec step's sizes"),
        ("Traces", re.compile(r"keep traces for", re.I), "number", "the trace retention"),
    ]
    for section, row, action, what in probes:
        d.project("instructions")
        if not d.go(section):
            fail("ac-no-save-buttons", f"cannot change {what}: no '{section}' section")
            continue
        ok, writes, note = d.change(row, action)
        if not ok:
            fail("ac-no-save-buttons", f"cannot change {what} on '{section}': {note}")
        elif len(writes) != 1:
            fail("ac-no-save-buttons", f"changing {what} issued {len(writes)} write(s) with no further click, want 1: {writes}")

    # --- old project links -----------------------------------------------------------------
    for old, successor in OLD_PROJECT_LINKS:
        d.project(old)
        active = d.active()
        data = d.read()
        if active != successor:
            fail("ac-old-links", f"project section '{old}' shows '{active}', want '{successor}'")
        elif not data or not data["labels"]:
            fail("ac-old-links", f"project section '{old}' opened '{successor}' with no rows (an empty page)")

    # --- agent settings --------------------------------------------------------------------
    d.agent_settings("workspace")
    agent_nav = [i["label"] for i in d.nav()]
    if agent_nav != AGENT_SECTION_LIST:
        fail("ac-agent-sections", f"the agent's sections are {agent_nav}, want {AGENT_SECTION_LIST}")
    for section in sorted(set(agent_nav) | set(AGENT_SECTION_LIST), key=lambda s: AGENT_SECTION_LIST.index(s) if s in AGENT_SECTION_LIST else 99):
        d.agent_settings("workspace")
        if not d.go(section):
            if section in AGENT_SECTION_LIST:
                fail("ac-agent-sections", f"agent section '{section}' cannot be opened (not in the side list)")
            continue
        if section == "Workspace":
            try:
                d.page.locator('[data-testid="agent-working-dir"]').first.wait_for(state="attached", timeout=30000)
            except Exception:  # noqa: BLE001
                pass
        data = d.read()
        if data is None:
            fail("ac-agent-sections", f"agent section '{section}' rendered no settings area")
            continue
        if data["saves"]:
            fail("ac-no-save-buttons", f"agent '{section}' shows Save button(s): {data['saves']}")
        for what, n in (("checkbox", data["checkboxes"]), ("date input", data["dates"]), ("select", data["selects"])):
            if n:
                fail("ac-no-native", f"agent '{section}' renders {n} native {what}(s)")
        if section in AGENT_ROWS:
            for name, ok in expected_hits(AGENT_ROWS, section, data).items():
                if not ok:
                    fail("ac-agent-sections", f"agent '{section}' has no '{name}' row (rows: {data['labels']})")

    d.agent_settings("workspace")
    if d.go("Running"):
        ok, writes, note = d.change(re.compile(r"question", re.I), "number")
        if not ok:
            fail("ac-no-save-buttons", f"cannot change an agent's question wait on 'Running': {note}")
        elif len(writes) != 1:
            fail("ac-no-save-buttons", f"changing an agent's question wait issued {len(writes)} write(s), want 1: {writes}")
    else:
        fail("ac-no-save-buttons", "cannot change an agent's question wait: no 'Running' section")

    # --- old agent links -------------------------------------------------------------------
    for old, successor in OLD_AGENT_LINKS:
        d.agent_settings(old)
        active = d.active()
        data = d.read()
        if active != successor:
            fail("ac-old-links", f"agent section '{old}' shows '{active}', want '{successor}'")
        elif not data or not data["labels"]:
            fail("ac-old-links", f"agent section '{old}' opened '{successor}' with no rows (an empty page)")

    return fails


# --------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if not (UI_DIR / "node_modules").exists():
        print("hub/ui/node_modules is missing; running npm ci ...")
        subprocess.run("npm ci --no-audit --no-fund --prefer-offline", cwd=UI_DIR, shell=True, check=True)

    scratch = Path(tempfile.mkdtemp(prefix="aw-ss-"))
    procs: List[subprocess.Popen] = []
    logs: List[Any] = []
    try:
        hub_port, ui_port = lv.free_port(), lv.free_port()
        while ui_port == hub_port:
            ui_port = lv.free_port()
        project_dir = lv.nested_project_dir(scratch / "projects")
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
            GIT_AUTHOR_NAME="ss",
            GIT_AUTHOR_EMAIL="ss@example.invalid",
            GIT_COMMITTER_NAME="ss",
            GIT_COMMITTER_EMAIL="ss@example.invalid",
            PYTHONUNBUFFERED="1",
        )
        env.pop("PYTHONPATH", None)
        hub_log = (scratch / "hub.log").open("w")
        logs.append(hub_log)
        hub = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", str(hub_port)],
            cwd=HUB_DIR,
            env=env,
            stdout=hub_log,
            stderr=subprocess.STDOUT,
        )
        procs.append(hub)
        hub_url = f"http://127.0.0.1:{hub_port}"
        print(f"Hub from this checkout on {hub_url} (database {db})")
        lv.wait_for(f"{hub_url}/health", hub, "the Hub")

        data = seed(lv.Api(hub_url), project_dir)
        print(f"seeded project {data['project_id']}, agent {data['agent']}")

        vite_log = (scratch / "vite.log").open("w")
        logs.append(vite_log)
        vite = subprocess.Popen(
            f"npx vite --host 127.0.0.1 --port {ui_port} --strictPort",
            cwd=UI_DIR,
            env=dict(os.environ, AW_DEV_HUB=hub_url),
            shell=True,
            stdout=vite_log,
            stderr=subprocess.STDOUT,
        )
        procs.append(vite)
        ui_url = f"http://127.0.0.1:{ui_port}"
        print(f"UI from this checkout on {ui_url}")
        lv.wait_for(ui_url + "/", vite, "the Vite dev server", timeout=120)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme="dark")
                context.add_init_script(
                    "try{sessionStorage.setItem('agentweave-session',JSON.stringify({apiKey:%s,hubUrl:location.origin}));"
                    "localStorage.setItem('agentweave-prefs',JSON.stringify({mode:'dark'}));"
                    "localStorage.setItem('agentweave-selected-project',%s)}catch(e){}"
                    % (json.dumps(API_KEY), json.dumps(data["project_id"]))
                )
                fails = run(Driver(context.new_page(), ui_url, data["project_id"], data["agent"]))
            finally:
                browser.close()

        if not fails:
            print("settings-style check: PASS")
            return 0
        print(f"settings-style check: FAIL - {len(fails)} finding(s)\n")
        for line in fails:
            print(f"  {line}")
        return 1
    except lv.SeedError as exc:
        print(f"settings-style check: could not seed the Hub: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"settings-style check: {exc}", file=sys.stderr)
        return 2
    finally:
        for proc in reversed(procs):
            lv.kill_tree(proc)
        for log_file in logs:
            log_file.close()
        if args.keep:
            print(f"kept {scratch}")
        else:
            shutil.rmtree(scratch, onerror=lv._clear_readonly_and_retry)


if __name__ == "__main__":
    sys.exit(main())
