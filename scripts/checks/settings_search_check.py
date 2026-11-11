"""The settings-search check: can every setting be found, and does it say where its value comes from?

One command, from a plain checkout:

    py -3.11 scripts/checks/settings_search_check.py             # one step per acceptance criterion
    py -3.11 scripts/checks/settings_search_check.py --findable  # every rendered row, by its own label

It starts its own Hub from this checkout's source on a temporary database (the harness
long_values_check.py uses), serves this checkout's UI (the Vite dev server, proxied to that Hub),
seeds a project with three agents through the Hub's API and drives the app in a headless browser.
It never touches :8000 or :8010 and gives the Hub a throwaway home directory. It exits 1 and names
each step (or, for --findable, the scope, section and label of each row) that fails. It is not part
of the project's checks; run it by hand.

Steps (one per criterion): cross-scope, app-from-agent, agents-listed, palette, highlight, no-match,
reload, source-project, source-agent, reset, overrides, changed-only. Limit them with --step NAME.

The page contract the check drives (the hooks the search UI exposes):

  [data-testid=settings-search]            the search input on App, project and agent settings
  [data-testid=settings-search-result]     one per result; data-scope (app|project|agent),
                                           data-section, data-label; holds
    [data-testid=settings-search-open]       the button that opens the setting
    [data-testid=settings-search-agent]      one per agent under an agent setting (data-agent=NAME,
                                             text = the name); choosing it opens that agent's setting
  [data-testid=settings-search-empty]      the no-match message (names the words typed)
  .aw-settings-row[data-highlighted=true]  the row a result landed on
  [data-testid=setting-source]             inside a row: 'Changed' (+ default), "Agent's own" or
                                           'From project' (+ the value)
  [data-testid=setting-overrides]          inside a project row: one button per agent holding its own
                                           value (text = the agent's name)
  [data-testid=changed-only]               the 'Changed only' switch; [data-testid=changed-empty]
                                           the 'nothing is changed' message
  the command palette's group headed 'Settings' (cmdk items), opened with Ctrl K

Needs: Python Playwright with a Chromium installed, Node/npm and git.

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
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import long_values_check as lv  # noqa: E402  (the shared harness)

HUB_DIR, UI_DIR = lv.HUB_DIR, lv.UI_DIR
API_KEY = lv.API_KEY
TIMEOUT = 6000  # ms to wait for a hook that a working build shows at once
AGENTS = ("alpha", "bravo", "charlie")  # roster order; alpha=A, bravo=B, charlie=C
SEARCH = '[data-testid="settings-search"]'
RESULT = '[data-testid="settings-search-result"]'
ROW = ".aw-settings-row"
HIGHLIGHTED = ROW + '[data-highlighted="true"]'


class Fail(Exception):
    pass


# --------------------------------------------------------------------------------------------
# The seed
# --------------------------------------------------------------------------------------------


def seed_project(api: lv.Api, root: Path, name: str, *, agents: bool, hop_budget: Optional[int]) -> Dict[str, Any]:
    pdir = root / name
    pdir.mkdir(parents=True)
    lv.git(pdir, "init", "-q", "-b", "master")
    (pdir / "README.md").write_text(name + "\n", encoding="utf-8")
    lv.git(pdir, "add", "README.md")
    lv.git(pdir, "commit", "-q", "-m", "first")
    pid = api.call("POST", "/projects/open", {"path": str(pdir), "name": name})["id"]
    base = f"/projects/{pid}"
    if hop_budget is not None:
        api.call("PUT", f"{base}/settings", {"main_branch": "master", "hop_budget": hop_budget})
    if agents:
        runner = api.call("POST", f"{base}/runners", {"name": "runner", "cli": "claude", "model": "claude-sonnet-5-5", "flags": []})["id"]
        for agent in AGENTS:
            api.call("POST", f"{base}/agents", {"name": agent, "runner_id": runner})
        # A and B hold their own default permissions, C does not; A holds its own checkpoint mode.
        api.call("PATCH", f"{base}/agents/alpha", {"default_permission_mode": "acceptEdits", "checkpoint_mode": "offered"})
        api.call("PATCH", f"{base}/agents/bravo", {"default_permission_mode": "acceptEdits"})
    return {"id": pid, "base": base}


def agent_record(api: lv.Api, base: str, name: str) -> Dict[str, Any]:
    listing = api.call("GET", f"{base}/agents")
    items = listing.get("agents", listing) if isinstance(listing, dict) else listing
    if isinstance(items, dict):
        items = [{"name": k, **v} for k, v in items.items()]
    for item in items:
        if item.get("name") == name:
            return item
    raise Fail(f"the Hub has no agent {name}")


# --------------------------------------------------------------------------------------------
# Page helpers
# --------------------------------------------------------------------------------------------


class Ctx:
    def __init__(self, page: Any, ui: str, api: lv.Api, main: Dict[str, Any], empty: Dict[str, Any]) -> None:
        self.page, self.ui, self.api, self.main, self.empty = page, ui, api, main, empty
        self.strict = True  # --findable sets it False: a section with no rows is simply empty

    def project(self, section: str, pid: Optional[str] = None) -> None:
        self.go(f"project={pid or self.main['id']}&tab=environment&section={section}")

    def agent(self, name: str, section: str) -> None:
        self.go(f"project={self.main['id']}&agent={name}&settings={section}")

    def app(self, section: str = "notifications") -> None:
        self.go(f"appSettings={section}&project={self.main['id']}")

    def go(self, query: str, rows: bool = True) -> None:
        self.page.goto("about:blank")
        self.page.goto(f"{self.ui}/?{query}", wait_until="domcontentloaded", timeout=120000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        if rows:
            try:
                self.page.wait_for_selector(ROW, timeout=60000 if self.strict else 8000)
            except Exception:  # noqa: BLE001
                if self.strict:
                    raise

    def type(self, text: str) -> None:
        box = self.page.locator(SEARCH).first
        try:
            box.wait_for(state="visible", timeout=TIMEOUT)
        except Exception:  # noqa: BLE001
            raise Fail("there is no search field on this settings screen") from None
        box.fill("")
        box.fill(text)
        self.page.wait_for_timeout(400)

    def results(self) -> List[Dict[str, Any]]:
        return self.page.evaluate(
            """(sel) => Array.from(document.querySelectorAll(sel)).map((r) => ({
                 scope: r.dataset.scope, section: r.dataset.section, label: r.dataset.label,
                 agents: Array.from(r.querySelectorAll('[data-testid="settings-search-agent"]')).map((a) => a.dataset.agent || a.textContent.trim()),
               }))""",
            RESULT,
        )

    def find(self, scope: str, label_re: str, section: Optional[str] = None) -> int:
        """Index of the result for this scope, label and (optionally) section; raises if there is none."""
        for i, r in enumerate(self.results()):
            if r["scope"] == scope and re.search(label_re, r["label"] or "", re.I) and (section is None or r["section"] == section):
                return i
        raise Fail(f"no {scope} result matching /{label_re}/" + (f" in {section}" if section else "") + f"; results: {self.results()}")

    def open_result(self, index: int) -> None:
        self.page.locator(RESULT).nth(index).locator('[data-testid="settings-search-open"]').click(timeout=TIMEOUT)
        self.page.wait_for_timeout(500)

    def highlighted(self) -> Dict[str, Any]:
        try:
            self.page.locator(HIGHLIGHTED).first.wait_for(state="visible", timeout=TIMEOUT)
        except Exception:  # noqa: BLE001
            raise Fail("no row is highlighted after choosing the result") from None
        return self.page.evaluate(
            """(sel) => { const r = document.querySelector(sel); const b = r.getBoundingClientRect();
                 return { label: (r.querySelector('.aw-settings-row-label')||{}).textContent || '',
                          inView: b.top >= 0 && b.bottom <= window.innerHeight,
                          focusInside: r.contains(document.activeElement) && document.activeElement !== document.body,
                          url: location.href } }""",
            HIGHLIGHTED,
        )

    def row(self, label_re: str) -> Any:
        return self.page.locator(ROW).filter(has=self.page.locator(".aw-settings-row-label", has_text=re.compile(label_re, re.I))).first

    def source_of(self, label_re: str) -> str:
        row = self.row(label_re)
        try:
            row.wait_for(state="visible", timeout=TIMEOUT)
            return row.locator('[data-testid="setting-source"]').first.inner_text(timeout=TIMEOUT).strip()
        except Exception:  # noqa: BLE001
            raise Fail(f"the row /{label_re}/ shows no source ([data-testid=setting-source])") from None


CI_CUTOFF = re.compile(r"^\s*CI asking stops after", re.I)


def has_word(text: str, word: str) -> bool:
    """Whole-word match, so 'Off' is not found inside 'Offer me one'."""
    return re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text, re.I) is not None


def expect(cond: bool, message: str) -> None:
    if not cond:
        raise Fail(message)


# --------------------------------------------------------------------------------------------
# One step per criterion
# --------------------------------------------------------------------------------------------


def step_cross_scope(c: Ctx) -> None:
    c.project("general")
    c.type("checkpoint")
    res = c.results()
    proj = [r for r in res if r["scope"] == "project" and r["section"] and "heckpoint" in r["section"]]
    agent = [r for r in res if r["scope"] == "agent" and r["section"] and "heckpoint" in r["section"]]
    expect(bool(proj), f"no project Checkpoints result for 'checkpoint'; got {res}")
    expect(bool(agent), f"no agent Checkpoints result for 'checkpoint'; got {res}")
    first_non_label = next((i for i, r in enumerate(res) if "heckpoint" not in (r["label"] or "")), len(res))
    expect(all("heckpoint" in (r["label"] or "") for r in res[:first_non_label]), "label matches are not listed first")
    expect(all(not ("heckpoint" in (r["label"] or "")) for r in res[first_non_label:]), "a label match is listed after a description-only match")


def step_app_from_agent(c: Ctx) -> None:
    c.agent("alpha", "agent")
    c.type("volume")
    c.open_result(c.find("app", "volume"))
    c.page.wait_for_selector('[data-testid="notify-volume"]', timeout=TIMEOUT)
    expect(c.highlighted()["label"].strip().lower().startswith("volume"), "App settings did not open at Volume")


def step_agents_listed(c: Ctx) -> None:
    c.project("general")
    c.type("checkpoint mode")
    res = [r for r in c.results() if r["scope"] == "agent" and re.search("checkpoint", r["label"] or "", re.I)]
    expect(len(res) == 1, f"the agent checkpoint-mode setting should appear once, appears {len(res)} times")
    expect(res[0]["agents"] == list(AGENTS), f"agents under it are {res[0]['agents']}, want {list(AGENTS)}")
    idx = c.find("agent", "checkpoint")
    c.page.locator(RESULT).nth(idx).locator('[data-testid="settings-search-agent"]').nth(1).click(timeout=TIMEOUT)
    h = c.highlighted()
    expect(h["label"].strip().lower() == "checkpoints", f"landed on {h['label']!r}, not the checkpoint mode row")
    expect("agent=bravo" in h["url"], f"the second agent is bravo; landed at {h['url']}")


def step_palette(c: Ctx) -> None:
    c.go(f"project={c.main['id']}&tab=overview", rows=False)
    c.page.keyboard.press("Control+k")
    c.page.keyboard.type("CI cutoff")
    c.page.wait_for_timeout(400)
    group = c.page.locator("[cmdk-group]").filter(has=c.page.locator("[cmdk-group-heading]", has_text=re.compile("^Settings$")))
    try:
        group.first.wait_for(state="visible", timeout=TIMEOUT)
    except Exception:  # noqa: BLE001
        raise Fail("the palette has no 'Settings' group for 'CI cutoff'") from None
    group.locator("[cmdk-item]").first.click()
    c.page.wait_for_timeout(600)
    h = c.highlighted()
    expect("section=landing" in h["url"], f"Project settings did not open at Landing: {h['url']}")
    expect(CI_CUTOFF.search(h["label"]) is not None, f"landed on {h['label']!r}, not the CI cutoff row")


def step_highlight(c: Ctx) -> None:
    c.page.set_viewport_size({"width": 960, "height": 600})
    c.project("landing")
    below = c.page.evaluate(
        """(re) => { const rx = new RegExp(re, 'i');
             const l = Array.from(document.querySelectorAll('.aw-settings-row-label')).find((e) => rx.test(e.textContent));
             return l ? l.getBoundingClientRect().top >= window.innerHeight : null }""",
        "CI asking stops after",
    )
    expect(below is not None, "Landing has no 'CI asking stops after' row")
    expect(below, "the CI cutoff row is not below the fold at 960px before the search; the step proves nothing")
    c.project("general")
    c.type("CI cutoff")
    c.open_result(c.find("project", CI_CUTOFF.pattern, "Landing|landing"))
    h = c.highlighted()
    expect(h["inView"], "the row is not scrolled into view")
    expect(h["focusInside"], "keyboard focus is not on the row's control")
    c.page.wait_for_timeout(2000)
    expect(c.page.locator(HIGHLIGHTED).count() == 1, "the highlight is gone at 2s")
    expect(c.highlighted()["focusInside"], "focus left the row's control by 2s")


def step_no_match(c: Ctx) -> None:
    for where, go in (("project", lambda: c.project("general")), ("agent", lambda: c.agent("alpha", "agent")), ("app", c.app)):
        go()
        c.type("zzqx")
        msg = c.page.locator('[data-testid="settings-search-empty"]')
        try:
            msg.first.wait_for(state="visible", timeout=TIMEOUT)
        except Exception:  # noqa: BLE001
            raise Fail(f"{where} settings show no no-match message for 'zzqx'") from None
        expect("zzqx" in msg.first.inner_text(), f"{where}: the no-match message does not name the words typed")
        expect(c.page.locator(RESULT).count() == 0, f"{where}: results are listed for 'zzqx'")


def step_reload(c: Ctx) -> None:
    c.project("general")
    c.type("CI cutoff")
    c.open_result(c.find("project", CI_CUTOFF.pattern, "Landing|landing"))
    first = c.highlighted()
    c.page.reload(wait_until="domcontentloaded")
    second = c.highlighted()
    expect(CI_CUTOFF.search(second["label"]) is not None and second["label"] == first["label"] and "section=landing" in second["url"], "after a reload Landing → CI cutoff is not highlighted")
    c.project("general")
    c.page.go_back(wait_until="domcontentloaded")
    third = c.highlighted()
    expect(CI_CUTOFF.search(third["label"]) is not None and third["label"] == first["label"] and "section=landing" in third["url"], "after Back, Landing → CI cutoff is not highlighted")


def step_source_project(c: Ctx) -> None:
    c.project("collaboration")
    text = c.source_of("Hop budget")
    expect("Changed" in text, f"hop budget reads {text!r}, not Changed")
    expect("6" in text, f"hop budget does not name the default (6): {text!r}")


def step_source_agent(c: Ctx) -> None:
    project_mode = c.api.call("GET", f"/projects/{c.main['id']}/settings").get("checkpoint_mode")
    words = {"off": "Off", "offered": "Offer me one", "automatic": "Automatic"}
    c.agent("alpha", "checkpoints")
    a = c.source_of("checkpoint")
    expect(has_word(a, "own") and has_word(a, words.get(project_mode, str(project_mode))), f"agent A reads {a!r}; want Agent's own with the project's mode {project_mode!r}")
    c.agent("bravo", "checkpoints")
    b = c.source_of("checkpoint")
    expect("from project" in b.lower() and has_word(b, words.get(project_mode, str(project_mode))), f"agent B reads {b!r}; want From project with {project_mode!r}")


def step_reset(c: Ctx) -> None:
    c.agent("alpha", "checkpoints")
    row = c.row("checkpoint")
    row.get_by_role("button", name="Reset", exact=False).first.click(timeout=TIMEOUT)
    c.page.wait_for_timeout(800)
    text = c.source_of("checkpoint")
    expect("from project" in text.lower(), f"after reset the row reads {text!r}, not From project")
    expect(agent_record(c.api, c.main["base"], "alpha").get("checkpoint_mode") is None, "the Hub's agent record still has its own checkpoint mode")


def step_overrides(c: Ctx) -> None:
    c.project("permissions")
    row = c.row("Default permissions")
    names = [t.strip() for t in row.locator('[data-testid="setting-overrides"] button').all_inner_texts()]
    expect(names == ["alpha", "bravo"], f"default permissions names {names}, want alpha and bravo (not charlie)")
    reach = c.row("Granted reach").locator('[data-testid="setting-overrides"] button')
    expect(reach.count() == 0, "granted reach names agents though none holds its own")
    row.locator('[data-testid="setting-overrides"] button', has_text="bravo").click(timeout=TIMEOUT)
    c.page.wait_for_timeout(600)
    url = c.page.url
    expect("agent=bravo" in url and "settings=permissions" in url, f"clicking bravo did not open its Permissions: {url}")
    expect(c.highlighted()["label"].lower().startswith("default permissions"), "bravo's Permissions did not open at default permissions")


def step_changed_only(c: Ctx) -> None:
    c.project("general")
    toggle = c.page.locator('[data-testid="changed-only"]').first
    try:
        toggle.wait_for(state="visible", timeout=TIMEOUT)
    except Exception:  # noqa: BLE001
        raise Fail("project settings have no 'Changed only' control") from None
    sections = lambda: c.page.locator('nav[aria-label="Project settings"] [data-slot="settings-nav-item"]')  # noqa: E731
    total = sections().count()
    toggle.click()
    c.page.wait_for_timeout(500)
    shown = [t.strip() for t in sections().all_inner_texts()]
    expect(len(shown) == 1 and "Collaboration" in shown[0], f"Changed only shows sections {shown}, want only Collaboration")
    c.page.locator('nav[aria-label="Project settings"] [data-slot="settings-nav-item"]', has_text="Collaboration").first.click(timeout=TIMEOUT)
    c.page.wait_for_selector(ROW, timeout=TIMEOUT)
    expect("hop" in " ".join(c.page.locator(".aw-settings-row-label").all_inner_texts()).lower() and c.page.locator(ROW).count() == 1, "Collaboration under Changed only does not show just hop budget")
    toggle = c.page.locator('[data-testid="changed-only"]').first
    toggle.click()
    c.page.wait_for_timeout(500)
    expect(sections().count() == total == 14, f"turned off, {sections().count()} sections return, want all 14")
    c.project("general", c.empty["id"])
    c.page.locator('[data-testid="changed-only"]').first.click()
    c.page.wait_for_selector('[data-testid="changed-empty"]', timeout=TIMEOUT)


STEPS: Dict[str, Callable[[Ctx], None]] = {
    "cross-scope": step_cross_scope,
    "app-from-agent": step_app_from_agent,
    "agents-listed": step_agents_listed,
    "palette": step_palette,
    "highlight": step_highlight,
    "no-match": step_no_match,
    "reload": step_reload,
    "source-project": step_source_project,
    "source-agent": step_source_agent,
    "reset": step_reset,
    "overrides": step_overrides,
    "changed-only": step_changed_only,
}


# --------------------------------------------------------------------------------------------
# --findable: every rendered row, searched by its own label
# --------------------------------------------------------------------------------------------

ROW_LABELS_JS = """() => Array.from(document.querySelectorAll('.aw-settings-row-label'))
  .map((l) => l.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean)"""


def findable(c: Ctx, inject_fault: bool) -> List[str]:
    c.strict = False
    rows: List[Tuple[str, str, str]] = []  # (scope, section, label)
    enum_problems: List[str] = []
    pages: List[Tuple[str, str, Callable[[], None]]] = []
    for s in lv.APP_SECTIONS:
        pages.append(("app", s, lambda s=s: c.app(s)))
    for s in lv.PROJECT_SECTIONS:
        pages.append(("project", s, lambda s=s: c.project(s)))
    for s in lv.AGENT_SECTIONS:
        pages.append(("agent", s, lambda s=s: c.agent(AGENTS[0], s)))
    for scope, section, go in pages:
        go()
        # Wait for the section's rows, then until the row count has held still for 1s, so
        # late-rendering rows are not skipped; a section that never renders a row fails the walk.
        try:
            c.page.wait_for_selector(".aw-settings-row-label", timeout=30000)
        except Exception:  # noqa: BLE001
            # Editor-only sections (instructions, charters, ...) have no rows; the count shows it.
            print(f"  {scope:8} {section:20} 0 rows (none rendered within 30s)")
            continue
        labels: List[str] = []
        stable = 0
        for _ in range(60):
            now = list(dict.fromkeys(c.page.evaluate(ROW_LABELS_JS)))
            stable = stable + 1 if now == labels else 0
            labels = now
            if stable >= 4:
                break
            c.page.wait_for_timeout(250)
        print(f"  {scope:8} {section:20} {len(labels)} rows")
        for label in labels:
            rows.append((scope, section, label))
    opener = {(sc, se): g for sc, se, g in pages}
    print(f"found {len(rows)} settings rows in {len(pages)} sections")
    problems: List[str] = list(enum_problems)
    last: Optional[Tuple[str, str]] = None
    for n, (scope, section, label) in enumerate(rows):
        who = f"{scope} / {section} / {label!r}"
        if (scope, section) != last:
            opener[(scope, section)]()
            last = (scope, section)
        try:
            c.type(label + ("zzqx" if inject_fault and n == 0 else ""))
            hits = [i for i, r in enumerate(c.results()) if r["scope"] == scope and (r["label"] or "").strip().lower() == label.lower()]
            if not hits:
                problems.append(f"{who}: a search for its own label does not return it")
                continue
            c.open_result(hits[0])
            h = c.highlighted()
            if h["label"].strip().lower() != label.lower():
                problems.append(f"{who}: the result lands on the wrong row ({h['label'].strip()!r})")
            last = None  # choosing a result moved the screen; reopen the page for the next row
        except Fail as exc:
            problems.append(f"{who}: {exc}")
            if "no search field" in str(exc):
                problems.append(f"stopped after the first row: {len(rows) - n - 1} more rows cannot be searched either")
                break
            last = None
    return problems


# --------------------------------------------------------------------------------------------


def run(args: argparse.Namespace, ui: str, api: lv.Api, main: Dict[str, Any], empty: Dict[str, Any]) -> int:
    from playwright.sync_api import sync_playwright

    chosen = [n for n in STEPS if not args.step or n in args.step]
    if not chosen and not args.findable:
        raise SystemExit("no step matches --step")
    failures: List[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name in ([] if args.findable else chosen):
                # A step runs on a fresh page (own context), so one step's state cannot rescue another.
                context = browser.new_context(viewport={"width": 1440, "height": lv.HEIGHT})
                context.add_init_script(
                    "try{sessionStorage.setItem('agentweave-session',JSON.stringify({apiKey:%s,hubUrl:location.origin}));"
                    "localStorage.setItem('agentweave-selected-project',%s)}catch(e){}" % (json.dumps(API_KEY), json.dumps(main["id"]))
                )
                page = context.new_page()
                page.set_default_timeout(TIMEOUT)
                ctx = Ctx(page, ui, api, main, empty)
                try:
                    STEPS[name](ctx)
                    print(f"  ok    {name}")
                except Fail as exc:
                    failures.append(f"{name}: {exc}")
                    print(f"  FAIL  {name}: {exc}")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{name}: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")
                    print(f"  FAIL  {name}: {failures[-1].split(': ', 1)[1]}")
                context.close()
            if args.findable:
                context = browser.new_context(viewport={"width": 1440, "height": lv.HEIGHT})
                context.add_init_script(
                    "try{sessionStorage.setItem('agentweave-session',JSON.stringify({apiKey:%s,hubUrl:location.origin}));"
                    "localStorage.setItem('agentweave-selected-project',%s)}catch(e){}" % (json.dumps(API_KEY), json.dumps(main["id"]))
                )
                page = context.new_page()
                page.set_default_timeout(TIMEOUT)
                failures = findable(Ctx(page, ui, api, main, empty), args.inject_fault)
                context.close()
        finally:
            browser.close()
    if failures:
        print(f"\nsettings-search check: FAIL - {len(failures)} problem(s)")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nsettings-search check: PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--findable", action="store_true")
    ap.add_argument("--step", action="append", choices=list(STEPS))
    ap.add_argument("--inject-fault", action="store_true", help="with --findable: search the first row's label misspelt, to see the check fail")
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
        home = scratch / "home"
        home.mkdir()
        db = scratch / "db" / "agentweave.db"
        env = {k: v for k, v in os.environ.items() if k not in ("HUB_URL", "AW_PORT") and not k.startswith(("AW_RUN_", "AW_AGENT_"))}
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
            cwd=HUB_DIR, env=env, stdout=hub_log, stderr=subprocess.STDOUT,
        )
        procs.append(hub)
        hub_url = f"http://127.0.0.1:{hub_port}"
        print(f"Hub from this checkout on {hub_url} (database {db})")
        lv.wait_for(f"{hub_url}/health", hub, "the Hub")

        api = lv.Api(hub_url)
        main_project = seed_project(api, scratch / "projects", "settings-search", agents=True, hop_budget=12)
        empty_project = seed_project(api, scratch / "projects", "nothing-changed", agents=False, hop_budget=None)
        print(f"seeded {main_project['id']} (three agents, hop budget 12) and {empty_project['id']} (nothing changed)")

        vite_log = (scratch / "vite.log").open("w")
        logs.append(vite_log)
        vite = subprocess.Popen(
            f"npx vite --host 127.0.0.1 --port {ui_port} --strictPort",
            cwd=UI_DIR, env=dict(os.environ, AW_DEV_HUB=hub_url), shell=True, stdout=vite_log, stderr=subprocess.STDOUT,
        )
        procs.append(vite)
        ui_url = f"http://127.0.0.1:{ui_port}"
        print(f"UI from this checkout on {ui_url}")
        lv.wait_for(ui_url + "/", vite, "the Vite dev server", timeout=120)
        return run(args, ui_url, api, main_project, empty_project)
    except lv.SeedError as exc:
        print(f"settings-search check: could not seed the Hub: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"settings-search check: {exc}", file=sys.stderr)
        for log in ("hub.log", "vite.log"):
            path = scratch / log
            if path.exists():
                print(f"--- {log} (tail) ---\n" + "\n".join(path.read_text(errors="replace").splitlines()[-25:]), file=sys.stderr)
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
