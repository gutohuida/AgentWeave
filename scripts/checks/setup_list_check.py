"""The set-up list check: does a project say what it still needs, in the three places?

One command, from a plain checkout:

    py -3.11 scripts/checks/setup_list_check.py

Spec `a-project-says-what-it-still-needs`. It starts its own Hub from this checkout's source on a
temporary database (the harness `long_values_check.py` uses), serves this checkout's UI (the Vite dev
server, proxied to that Hub), opens a scratch folder with no git as a project and, in a headless
browser, checks:

  * ac-fresh-folder  Overview lists the repository and agent items and nothing else;
  * ac-three-places  the list is at the top of Overview and of Project settings sections, the rail
                     row shows "2" beside the name, naming both on hover, and no hover action
                     overlaps it; after both are resolved none of the three shows anything;
  * ac-links         each item, clicked, opens the screen it names with the field or action in view;
  * ac-dismiss       (the screen half) "Not for this project" removes the repository item from all
                     three places, and "Show it again" in Project settings brings it back;
  * ac-live          adding an agent without reloading removes the item and the rail count;
  * ac-cannot-run    an agent whose coding agent is not on the Hub's PATH is named, with "not installed".

It exits 1 and prints each failure, 2 when it cannot set up. It is a drive, not one of the project's
checks. It never touches :8000 or :8010, and the Hub it starts gets a throwaway home directory.

Needs: Python Playwright with a Chromium installed, Node/npm, git, and one coding agent on this
machine that is installed and logged in (ac-live adds an agent that can run).

    --shots DIR     write a screenshot after each step into DIR
    --keep          leave the temporary folder in place and print its path
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import long_values_check as lv  # noqa: E402  (the shared harness)

REPO, HUB_DIR, UI_DIR = lv.REPO, lv.HUB_DIR, lv.UI_DIR
SHORT = 8000  # ms to wait for something that should be on the screen
CLIS = ("codex", "copilot", "claude")  # the Hub's runner CLIs, in the order tried for the missing one


class Checks:
    def __init__(self, shots: Optional[Path]) -> None:
        self.failures: List[str] = []
        self.passed: List[str] = []
        self.shots = shots

    def ok(self, ac: str, what: str, cond: bool, detail: str = "") -> bool:
        if cond:
            self.passed.append(f"{ac}: {what}")
        else:
            self.failures.append(f"{ac}: {what}" + (f"\n      {detail}" if detail else ""))
        return cond

    def shot(self, page: Any, name: str) -> None:
        if self.shots:
            page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)


# --------------------------------------------------------------------------------------------
# What the page shows
# --------------------------------------------------------------------------------------------

READ_ITEMS_JS = r"""
() => {
  const list = document.querySelector('[data-testid="setup-list"][data-place]')
  const lists = Array.from(document.querySelectorAll('[data-testid="setup-list"]'))
  return {
    lists: lists.length,
    items: lists.length
      ? Array.from(lists[0].querySelectorAll('[data-testid^="setup-item-"]')).map((li) => ({
          key: li.getAttribute('data-key'),
          text: li.innerText.replace(/\s+/g, ' ').trim(),
        }))
      : [],
    place: list ? list.getAttribute('data-place') : null,
    dismissedText: lists.length ? lists[0].querySelector('.aw-setup-dismissed')?.innerText ?? '' : '',
  }
}
"""

# Is the list the first thing in the screen's content: nothing visible and wider than a line of
# text sits above it, inside the scrolling content?
TOP_JS = r"""
() => {
  const list = document.querySelector('[data-testid="setup-list"]')
  if (!list) return null
  const r = list.getBoundingClientRect()
  const seen = []
  for (const el of document.querySelectorAll('main h1, main h2, main [data-testid], .aw-settings-row, .settings-row')) {
    if (list.contains(el) || el.contains(list)) continue
    const b = el.getBoundingClientRect()
    if (b.width > 0 && b.height > 0 && b.bottom <= r.top + 1 && b.top >= 0) seen.push(el.getAttribute('data-testid') || el.className)
  }
  const firstRow = document.querySelector('.aw-settings-row, .settings-row')
  return { top: r.top, bottom: r.bottom, above: seen.slice(0, 5), rowTop: firstRow ? firstRow.getBoundingClientRect().top : null }
}
"""

COUNT_JS = r"""
(pid) => {
  const row = document.querySelector(`[data-testid="rail-project-${pid}"] .aw-rail-project-row`)
  if (!row) return { row: false }
  const count = row.querySelector('[data-testid="setup-count"]')
  if (!count) return { row: true, count: null }
  const c = count.getBoundingClientRect()
  const overlaps = []
  for (const b of row.querySelectorAll('.aw-rail-actions button, .aw-rail-row-end button')) {
    const r = b.getBoundingClientRect()
    if (r.width <= 0 || r.height <= 0) continue
    const cs = getComputedStyle(b.closest('.aw-reveal') || b)
    if (cs.visibility === 'hidden' || cs.opacity === '0') continue
    const w = Math.min(c.right, r.right) - Math.max(c.left, r.left)
    const h = Math.min(c.bottom, r.bottom) - Math.max(c.top, r.top)
    if (w > 0 && h > 0) overlaps.push(b.getAttribute('aria-label') || b.title)
  }
  const name = row.querySelector('.truncate')
  return {
    row: true,
    count: count.innerText.trim(),
    title: count.getAttribute('title') || count.getAttribute('aria-label') || '',
    overlaps,
    besideName: name ? Math.abs(c.left - name.getBoundingClientRect().right) < 400 : null,
  }
}
"""


def read_items(page: Any) -> Dict[str, Any]:
    return page.evaluate(READ_ITEMS_JS)


def settle(page: Any) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(600)


def open_url(page: Any, url: str) -> None:
    for attempt in range(3):
        page.goto("about:blank")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            page.wait_for_timeout(1500)
    try:
        page.wait_for_selector("main, .aw-settings-page, [data-testid]", timeout=60000)
    except Exception:  # noqa: BLE001
        pass
    settle(page)


def wait_for_list(page: Any) -> bool:
    try:
        page.locator('[data-testid="setup-list"]').first.wait_for(state="visible", timeout=SHORT)
        return True
    except Exception:  # noqa: BLE001
        return False


def wait_no_list(page: Any) -> bool:
    try:
        page.locator('[data-testid="setup-list"]').first.wait_for(state="detached", timeout=SHORT)
        return True
    except Exception:  # noqa: BLE001
        return False


def keys(state: Dict[str, Any]) -> List[str]:
    return sorted(i["key"] for i in state["items"])


def in_view(page: Any, selector: str) -> bool:
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="visible", timeout=SHORT)
        return bool(
            loc.evaluate(
                "el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth }"
            )
        )
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------------------------
# The drive
# --------------------------------------------------------------------------------------------


def drive(
    c: Checks, ui: str, api: lv.Api, pid: str, runnable_cli: str, missing_cli: str, browser: Any, lose_cli: Any
) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(
        "try{sessionStorage.setItem('agentweave-session',JSON.stringify({apiKey:%s,hubUrl:location.origin}));"
        "localStorage.setItem('agentweave-selected-project',%s)}catch(e){}"
        % (lv.json.dumps(lv.API_KEY), lv.json.dumps(pid))
    )
    page = context.new_page()
    page.set_default_timeout(SHORT)
    overview = f"{ui}/?project={pid}"
    settings = lambda s: f"{ui}/?project={pid}&tab=environment&section={s}"  # noqa: E731

    # ---- ac-fresh-folder -------------------------------------------------------------------
    open_url(page, overview)
    has_list = wait_for_list(page)
    state = read_items(page) if has_list else {"items": [], "lists": 0}
    c.shot(page, "1-overview-fresh")
    c.ok("ac-fresh-folder", "Overview shows a set-up list", has_list, "no [data-testid=setup-list] on Overview")
    c.ok(
        "ac-fresh-folder",
        "the list holds the repository and agent items and nothing else",
        keys(state) == ["agent", "repository"],
        f"items: {keys(state)}",
    )

    # ---- ac-three-places: Overview, two Project settings sections, the rail ----------------
    top = page.evaluate(TOP_JS) if has_list else None
    c.ok(
        "ac-three-places",
        "the list is at the top of Overview",
        bool(top) and not top["above"],
        f"{top}",
    )
    for section in ("general", "checks"):
        open_url(page, settings(section))
        shown = wait_for_list(page)
        c.shot(page, f"2-settings-{section}")
        t = page.evaluate(TOP_JS) if shown else None
        c.ok(
            "ac-three-places",
            f"the list is at the top of Project settings -> {section}",
            bool(t) and (t["rowTop"] is None or t["bottom"] <= t["rowTop"] + 1),
            f"{'no list on the section' if not shown else t}",
        )
    open_url(page, overview)
    wait_for_list(page)
    row_main = page.locator(f'[data-testid="project-name-{pid}"]')
    try:
        row_main.hover()
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(400)
    rail = page.evaluate(COUNT_JS, pid)
    c.shot(page, "3-rail-hover")
    c.ok("ac-three-places", "the rail row shows 2 beside the name", rail.get("count") == "2", f"{rail}")
    title = rail.get("title") or ""
    c.ok(
        "ac-three-places",
        "hovering the count names both items",
        "repository" in title.lower() and "agent" in title.lower(),
        f"title: {title!r}",
    )
    c.ok("ac-three-places", "no hover action overlaps the count", rail.get("count") is not None and not rail.get("overlaps"), f"{rail}")

    # ---- ac-links: no agent opens adding an agent; no repository opens the action ----------
    open_url(page, overview)
    if wait_for_list(page):
        page.locator('[data-testid="setup-list"] [data-key="agent"] button').last.click()
        try:
            page.get_by_role("heading", name="Create agent").wait_for(state="visible", timeout=SHORT)
            opened = True
        except Exception:  # noqa: BLE001
            opened = False
        c.shot(page, "4-link-agent")
        c.ok("ac-links", "the agent item opens adding an agent", opened, "no 'Create agent' dialog")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.locator('[data-testid="setup-list"] [data-key="repository"] button').last.click()
        settle(page)
        c.shot(page, "5-link-repository")
        c.ok(
            "ac-links",
            "the repository item opens 'Make this a git repository' in view",
            "section=general" in page.url and in_view(page, "#make-repository"),
            f"url {page.url}",
        )
    else:
        c.ok("ac-links", "the agent and repository items can be clicked", False, "no list to click")

    # ---- ac-dismiss (screen half): all three places, and back ------------------------------
    open_url(page, overview)
    if wait_for_list(page):
        page.get_by_role("button", name="Not for this project").click()
        gone = True
        left = read_items(page)
        c.ok("ac-dismiss", "Overview no longer lists the repository item", "repository" not in keys(left), f"{keys(left)}")
        open_url(page, settings("general"))
        wait_for_list(page)
        st = read_items(page)
        c.ok("ac-dismiss", "Project settings no longer lists it as an item", "repository" not in keys(st), f"{keys(st)}")
        c.ok("ac-dismiss", "Project settings offers 'Show it again'", page.get_by_role("button", name="Show it again").count() > 0)
        rail = page.evaluate(COUNT_JS, pid)
        c.ok("ac-dismiss", "the rail count drops to 1", rail.get("count") == "1", f"{rail}")
        c.shot(page, "6-dismissed")
        if page.get_by_role("button", name="Show it again").count():
            page.get_by_role("button", name="Show it again").first.click()
            page.wait_for_timeout(500)
            back = read_items(page)
            c.ok("ac-dismiss", "'Show it again' brings the repository item back", "repository" in keys(back), f"{keys(back)}")
        del gone
        # Leave it dismissed for ac-live: the agent item is then the only thing left.
        open_url(page, overview)
        wait_for_list(page)
        page.get_by_role("button", name="Not for this project").click()
    else:
        c.ok("ac-dismiss", "the repository item can be dismissed", False, "no list")

    # ---- ac-live: add an agent without reloading -------------------------------------------
    open_url(page, overview)
    before = wait_for_list(page) and keys(read_items(page)) == ["agent"]
    c.ok("ac-live", "Overview shows only the agent item before the agent is added", before, f"{keys(read_items(page))}")
    runner = api.call(
        "POST", f"/projects/{pid}/runners", {"name": "Runs", "cli": runnable_cli}
    )["id"]
    api.call("POST", f"/projects/{pid}/agents", {"name": "builder", "runner_id": runner})
    # Only a list that was there can disappear: without `before` these would pass on an empty page.
    c.ok("ac-live", "the item disappears without a reload", before and wait_no_list(page), "the list is still on Overview, or was never shown")
    page.wait_for_timeout(500)
    rail = page.evaluate(COUNT_JS, pid)
    c.ok("ac-live", "the rail count disappears without a reload", before and rail.get("row") and rail.get("count") is None, f"{rail}")
    c.shot(page, "7-live")

    # ---- ac-cannot-run ---------------------------------------------------------------------
    # The Hub refuses to create an agent on a CLI it cannot find, so the agent is made first and the
    # CLI then leaves the Hub's PATH (the Hub restarts without it, on the same database and port).
    broken = api.call("POST", f"/projects/{pid}/runners", {"name": "Cannot", "cli": missing_cli})["id"]
    api.call("POST", f"/projects/{pid}/agents", {"name": "ghost", "runner_id": broken})
    lose_cli()
    open_url(page, overview)
    shown = wait_for_list(page)
    st = read_items(page) if shown else {"items": []}
    can_run = [i for i in st["items"] if i["key"] == "can-run"]
    c.shot(page, "8-cannot-run")
    c.ok("ac-cannot-run", "the can-run item is shown", bool(can_run), f"items: {keys(st)}")
    text = can_run[0]["text"] if can_run else ""
    c.ok(
        "ac-cannot-run",
        "it names the agent and says its coding agent is not installed",
        "ghost" in text and "not installed" in text.lower(),
        f"text: {text!r}",
    )
    c.ok("ac-cannot-run", "it is the only item (the runnable agent is not listed)", keys(st) == ["can-run"], f"{keys(st)}")
    if can_run:
        page.locator('[data-testid="setup-list"] [data-key="can-run"] button').last.click()
        settle(page)
        c.shot(page, "9-link-can-run")
        c.ok(
            "ac-links",
            "the can-run item opens that agent's Running -> Model",
            "ghost" in page.url and "settings=running" in page.url and in_view(page, "text=Model"),
            f"url {page.url}",
        )
    context.close()


# --------------------------------------------------------------------------------------------


def hub_path_without(cli: str) -> str:
    """The process PATH minus every folder `cli` is found in, so the Hub cannot find it."""
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    while True:  # a CLI can be installed in several folders (an installer's and npm's)
        found = shutil.which(cli, path=os.pathsep.join(parts))
        if not found:
            return os.pathsep.join(parts)
        here = os.path.normcase(os.path.normpath(os.path.dirname(found)))
        parts = [p for p in parts if os.path.normcase(os.path.normpath(p)) != here]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shots")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    if not (UI_DIR / "node_modules").exists():
        print("hub/ui/node_modules is missing; running npm ci ...")
        subprocess.run("npm ci --no-audit --no-fund --prefer-offline", cwd=UI_DIR, shell=True, check=True)

    scratch = Path(tempfile.mkdtemp(prefix="aw-sl-"))
    procs: List[subprocess.Popen] = []
    logs: List[Any] = []
    try:
        hub_port, ui_port = lv.free_port(), lv.free_port()
        while ui_port == hub_port:
            ui_port = lv.free_port()
        folder = scratch / "projects" / "scratch-folder"  # no git
        folder.mkdir(parents=True)
        (folder / "notes.txt").write_text("a folder with no git\n", encoding="utf-8")
        db = scratch / "db" / "agentweave.db"
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("HUB_URL", "AW_PORT") and not k.startswith(("AW_RUN_", "AW_AGENT_"))
        }
        env.update(
            DATABASE_URL="sqlite+aiosqlite:///" + db.as_posix(),
            AW_BOOTSTRAP_API_KEY=lv.API_KEY,
            PYTHONUNBUFFERED="1",
        )
        env.pop("PYTHONPATH", None)
        hub_url = f"http://127.0.0.1:{hub_port}"
        hub_log = (scratch / "hub.log").open("a")
        logs.append(hub_log)
        hubs: List[subprocess.Popen] = []

        def start_hub(path: str) -> None:
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1", "--port", str(hub_port)],
                cwd=HUB_DIR,
                env=dict(env, PATH=path),
                stdout=hub_log,
                stderr=subprocess.STDOUT,
            )
            hubs.append(proc)
            procs.append(proc)
            lv.wait_for(f"{hub_url}/health", proc, "the Hub")

        full_path = os.environ.get("PATH", "")
        start_hub(full_path)
        print(f"Hub from this checkout on {hub_url} (database {db})")
        api = lv.Api(hub_url)

        project = api.call("POST", "/projects/open", {"path": str(folder), "name": "Scratch"})
        pid = project["id"]
        probe = api.call("GET", f"/projects/{pid}/runners/launchability-by-provider")["providers"]
        runnable_clis = [cli for cli, v in probe.items() if v.get("runnable")]
        if len(runnable_clis) < 2:
            raise lv.SeedError(
                "this needs two coding agents installed and logged in on this machine (one that keeps "
                f"running, one that leaves the Hub's PATH): {probe}"
            )
        # A pair where taking one off the PATH leaves the other on it (npm installs share a folder).
        pair = next(
            (
                (r, m)
                for m in runnable_clis
                for r in runnable_clis
                if r != m and shutil.which(r, path=hub_path_without(m))
            ),
            None,
        )
        if pair is None:
            raise lv.SeedError(f"no two of {runnable_clis} can be told apart by PATH: they share their folders")
        runnable, missing_cli = pair
        stripped = hub_path_without(missing_cli)

        def lose_cli() -> None:
            kill_hub = hubs[-1]
            lv.kill_tree(kill_hub)
            start_hub(stripped)
            after = api.call("GET", f"/projects/{pid}/runners/launchability-by-provider")["providers"]
            if after.get(missing_cli, {}).get("present") or not after.get(runnable, {}).get("runnable"):
                raise lv.SeedError(f"after taking '{missing_cli}' off the Hub's PATH: {after}")

        print(f"project {pid} on a folder with no git; '{runnable}' can run, '{missing_cli}' will leave the Hub's PATH")

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
        lv.wait_for(ui_url + "/", vite, "the Vite dev server", timeout=120)

        shots = Path(args.shots) if args.shots else None
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
        checks = Checks(shots)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                drive(checks, ui_url, api, pid, runnable, missing_cli, browser, lose_cli)
            except Exception as exc:  # noqa: BLE001
                checks.failures.append(f"the drive stopped: {type(exc).__name__}: {str(exc).splitlines()[0][:300]}")
            finally:
                browser.close()
        for line in checks.passed:
            print(f"  ok    {line}")
        for line in checks.failures:
            print(f"  FAIL  {line}")
        if checks.failures:
            print(f"\nset-up list check: FAIL - {len(checks.failures)} failed, {len(checks.passed)} passed")
            return 1
        print(f"\nset-up list check: PASS - {len(checks.passed)} checks")
        return 0
    except lv.SeedError as exc:
        print(f"set-up list check: could not set up: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"set-up list check: {exc}", file=sys.stderr)
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
