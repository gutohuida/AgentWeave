"""Acceptance drive for `the-side-panel-s-changes-tab-shows-what-the-agent-changed` (SPSCT-1),
2026-11-13: ac-two-files (FR-1), ac-diff (FR-2), ac-switch (FR-3), ac-live (FR-4), ac-empty (FR-5),
ac-open-file (FR-7). Written failing first, before the route (SPSCT-2) and the wiring (SPSCT-3).

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default
:8013 and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), and refuses a port something already
answers on, so the UI and routes under test are always this checkout's. Never :8000 or :8010.

The scenario, in a scratch git repository (branch `main`: README.md, src/app.py), three Haiku agents:

  Maker   turn 1: appends one line to README.md and adds notes.txt (two lines)       -> ac-two-files
          turn 2, with the tab open, never reloaded: adds plan.txt                  -> ac-live
          then Last turn lists only plan.txt, Since main lists all three           -> ac-switch
  Quiet   one turn that changes nothing                                             -> ac-empty (1)
  Reader  read-only (`config.read_only`), so it has no checkout of its own          -> ac-empty (2)

The expected marks and +/- counts are read from git (`git show --numstat` of each turn's
auto-snapshot commit, `runs.snapshot_commit_sha`), never assumed from the prompt. If a Haiku turn
did not do what it was asked, the drive says SETUP and stops rather than blaming the product.

What the drive reads in the page (the contract the wiring meets; the mock's ChangesTab already does):
  the tab        a panel tab "Changes" (`panel-tab-changes` / `panel-launch-changes`, or the
                 "Add a tab" menu), whose content is `[data-testid=changes-tab]`
  the list       `[aria-label="Changed files"] li` (else `[data-slot=changes-file]`): one row per
                 file, its text holding the file name, its mark (A/M/D/R or added/modified/...)
                 and `+N` and `-N` / `−N`
  selecting      clicking a row; the diff then shows inside the tab, the conversation pane
                 (`[data-testid=conversation-pane]`) still visible
  scope          controls named "Last turn" and "Since main"; the tab's text names
                 `agentweave/Maker` and `main`
  open the file  a control in the tab whose accessible name or title matches /open .*files?|open
                 file/i (e.g. "Open README.md in Files"); the panel then has a selected tab
                 named README.md

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots and the tab's text go to
testbed/changes-drive/<HHMMSS>/.

    py -3.11 scripts/drive/d1113_changes_tab.py            # own Hub on :8013, fresh db
    py -3.11 scripts/drive/d1113_changes_tab.py --keep     # leave the Hub up afterwards
"""

import argparse
import datetime
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

STAMP = time.strftime("%H%M%S")
os.environ.setdefault("AW_DRIVE_PORT", "8013")
os.environ.setdefault(
    "AW_DRIVE_DB",
    str(pathlib.Path(tempfile.gettempdir()) / "drive1113-changes" / STAMP / "hub.db"),
)
if os.environ["AW_DRIVE_PORT"] in ("8000", "8010"):
    sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")

import d1029_build_plan_in_spec as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = d.REPO / "testbed" / "changes-drive" / STAMP
ROOT = pathlib.Path(tempfile.gettempdir()) / "drive1113-changes" / STAMP / "proj"
TURN_WAIT = 8 * 60
LIVE_LIMIT = 5.0  # FR-4: within 5 seconds of the turn's end
LIVE_WATCH = 30.0  # how long the drive keeps looking, so a late arrival is reported with its delay
NO_GIT = "Do not run git or commit anything; the Hub commits your work. Change nothing else."
TURN1 = ("Edit two files in your working directory: append the single line `Second line from Maker.` "
         "to the end of README.md, and create notes.txt holding exactly two lines, `alpha` and "
         "`beta`. " + NO_GIT)
TURN2 = "Create plan.txt in your working directory holding the single line `gamma`. " + NO_GIT
QUIET = "Reply with the single word OK. Do not create, edit or delete any file, and do not run git."
ERROR_CODE = re.compile(r"\b[45]\d\d\b|Internal Server Error|Traceback|\bundefined\b|\bnull\b")

checks = {}  # key -> (reached, failed, detail)


def record(key, reached, ok, detail):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


class Setup(Exception):
    """The scenario could not be built; not a verdict on the product."""


# --------------------------------------------------------------------------- scenario (REST + git)


def git_out(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def turn(base, pid, agent, message, conversation=None):
    body = {"agent": agent, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    code, out = d.api("POST", f"{base}/agent/trigger", body, timeout=90)
    if code != 200:
        raise Setup(f"trigger {agent}: {code} {str(out)[:300]}")
    return out


def last_run(pid, agent):
    rows = d.ro("select id, status, ended_at, snapshot_commit_sha from runs where project_id=? "
                "and agent=? order by started_at desc limit 1", (pid, agent))
    return rows[0] if rows else None


def wait_turn(pid, agent, since_count):
    """Waits for `agent`'s newest run (the one after `since_count` runs) to end; returns its row."""
    def ended():
        n = d.ro("select count(*) from runs where project_id=? and agent=?", (pid, agent))[0][0]
        row = last_run(pid, agent)
        return n > since_count and row and row[1] not in ("running", "queued", "starting")
    if not d.poll(ended, TURN_WAIT, every=0.25):
        raise Setup(f"{agent}'s turn did not end within {TURN_WAIT}s")
    return last_run(pid, agent)


def run_count(pid, agent):
    return d.ro("select count(*) from runs where project_id=? and agent=?", (pid, agent))[0][0]


def numstat(sha):
    """{path: (status letter, added, removed)} of one commit, from git."""
    status = {}
    for line in git_out("show", "--name-status", "--format=", sha).splitlines():
        if line.strip():
            parts = line.split("\t")
            status[parts[-1]] = parts[0][0]
    counts = {}
    for line in git_out("show", "--numstat", "--format=", sha).splitlines():
        if line.strip():
            a, r, path = line.split("\t")
            counts[path] = (status.get(path, "?"), int(a), int(r))
    return counts


def ended_epoch(text):
    stamp = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.timestamp()


def build_scenario():
    ROOT.mkdir(parents=True)
    d.git(ROOT, "init", "-q", "-b", "main")
    (ROOT / "README.md").write_text("Scratch project for the Changes tab drive.\n", encoding="utf-8")
    (ROOT / "src").mkdir()
    (ROOT / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    d.git(ROOT, "add", ".")
    d.git(ROOT, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(ROOT), "name": f"changes-{STAMP}"})
    if code not in (200, 201):
        raise Setup(f"project open: {code} {project}")
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    code, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    if code not in (200, 201):
        raise Setup(f"runner: {code} {runner}")
    for name in ("Maker", "Quiet", "Reader"):
        code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner["id"]})
        if code not in (200, 201):
            raise Setup(f"agent {name}: {code} {out}")
    code, out = d.api("PATCH", f"{base}/agents/Reader", {"config": {"read_only": True}})
    if code != 200:
        raise Setup(f"Reader read-only: {code} {out}")

    state = {"pid": pid, "base": base, "conv": {}}
    for agent, message in (("Maker", TURN1), ("Quiet", QUIET), ("Reader", QUIET)):
        before = run_count(pid, agent)
        out = turn(base, pid, agent, message)
        state["conv"][agent] = out["conversation_id"]
        row = wait_turn(pid, agent, before)
        print(f"  {agent}'s turn: {row[1]} snapshot={row[3]}", flush=True)
        state[f"{agent}-run"] = row
    sha = state["Maker-run"][3]
    if not sha:
        raise Setup("Maker's first turn left no auto-snapshot commit")
    first = numstat(sha)
    if first.get("README.md", ("",))[0] != "M" or first.get("notes.txt", ("",))[0] != "A" or len(first) != 2:
        raise Setup(f"Maker's first turn did not modify README.md and add notes.txt only: {first}")
    if state["Quiet-run"][3]:
        raise Setup(f"Quiet's turn committed {state['Quiet-run'][3]}; it was to change nothing")
    if (ROOT / ".agentweave" / "worktrees" / "Reader").exists():
        raise Setup("Reader has a worktree; it was to have no checkout of its own")
    state["first"] = first
    print(f"  Maker's first turn, from git: {first}", flush=True)
    return state


# --------------------------------------------------------------------------- the page


def open_conversation(page, state, agent):
    pid = state["pid"]
    page.goto(f"{d.HUB}/?project={pid}&agent={agent}&conversation={state['conv'][agent]}",
              wait_until="domcontentloaded")
    page.get_by_test_id("conversation-pane").wait_for(timeout=20000)
    page.wait_for_timeout(1500)


def open_changes(page):
    """Opens the Changes tab the way the operator does; returns its locator (may be absent)."""
    tab = page.get_by_test_id("changes-tab")
    if tab.count():
        return tab
    if not page.get_by_test_id("panel-shell").count():
        page.get_by_role("button", name="More conversation actions").click()
        page.get_by_test_id("conversation-toggle-panel").click()
        page.wait_for_timeout(800)
    for opener in (page.get_by_test_id("panel-tab-changes"), page.get_by_test_id("panel-launch-changes")):
        if opener.count():
            opener.first.click()
            break
    else:
        add = page.get_by_test_id("panel-tab-add")
        if add.count():
            add.first.click()
            page.wait_for_timeout(300)
            item = page.get_by_role("menuitem", name="Changes")
            if item.count():
                item.first.click()
            else:
                page.keyboard.press("Escape")  # no Changes on offer: leave the menu closed
                page.wait_for_timeout(300)
    try:
        tab.wait_for(timeout=8000)
    except Exception:  # noqa: BLE001 -- absence is what the checks report
        pass
    return tab


def tab_text(page):
    tab = page.get_by_test_id("changes-tab")
    return tab.inner_text() if tab.count() else ""


def rows(page):
    tab = page.get_by_test_id("changes-tab")
    found = tab.locator('[aria-label="Changed files"] li')
    if not found.count():
        found = tab.locator("[data-slot=changes-file]")
    return [found.nth(i) for i in range(found.count())]


def listed(page):
    """{file name: row text} of the changed-files list as it is now."""
    out = {}
    for row in rows(page):
        text = row.inner_text().replace("−", "-").replace("\n", " ")
        for name in ("README.md", "notes.txt", "plan.txt", "app.py"):
            if name in text:
                out[name] = text
    return out


MARK = {"A": ("A", "added"), "M": ("M", "modified"), "D": ("D", "deleted"), "R": ("R", "renamed")}


def row_matches(text, status, added, removed):
    """The row carries the file's mark and its counts. Read as text, since a row's spans may
    render with no space between them ("MREADME.md+1-0")."""
    letter, word = MARK[status]
    mark = text.lstrip().startswith(letter) or re.search(r"\b%s\b" % letter, text) or word in text.lower()
    counts = re.search(rf"\+{added}(?!\d)", text) and re.search(rf"-{removed}(?!\d)", text)
    return bool(mark and counts)


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"))
    (OUT / f"{name}.txt").write_text(tab_text(page), encoding="utf-8")


def click_scope(page, name):
    tab = page.get_by_test_id("changes-tab")
    for loc in (tab.get_by_role("radio", name=name), tab.get_by_role("tab", name=name),
                tab.get_by_role("button", name=name), tab.get_by_text(name, exact=True)):
        if loc.count():
            loc.first.click()
            page.wait_for_timeout(600)
            return True
    return False


# --------------------------------------------------------------------------- the checks


def check_two_files(page, state):
    open_changes(page)
    page.wait_for_timeout(1500)
    shot(page, "two-files")
    now = listed(page)
    bad = []
    for path, (status, a, r) in state["first"].items():
        text = now.get(path)
        if text is None or not row_matches(text, status, a, r):
            bad.append(f"{path} expected {status} +{a} -{r}, row {text!r}")
    record("ac-two-files", True, not bad and len(now) == 2,
           "; ".join(bad) or f"both listed with marks and counts: {now}")


def check_diff(page, state):
    target = next((r for r in rows(page) if "README.md" in r.inner_text()), None)
    if target is not None:
        target.click()
        page.wait_for_timeout(1000)
    shot(page, "diff")
    text = tab_text(page)
    shown = "Second line from Maker." in text
    conversation = page.get_by_test_id("conversation-pane")
    stays = conversation.count() > 0 and conversation.first.is_visible()
    record("ac-diff", True, target is not None and shown and stays,
           f"row present={target is not None}, added line in the tab={shown}, conversation visible={stays}")


def check_open_file(page, state):
    tab = page.get_by_test_id("changes-tab")
    opener = None
    if tab.count():
        pattern = re.compile(r"open\b.*\bfiles?\b|open file", re.I)
        for candidate in (tab.get_by_role("button", name=pattern), tab.get_by_role("link", name=pattern),
                          tab.locator("[title]")):
            for i in range(candidate.count()):
                el = candidate.nth(i)
                label = " ".join(filter(None, [el.get_attribute("aria-label"), el.get_attribute("title"),
                                               el.inner_text()]))
                if pattern.search(label) and ("README.md" in label or "file" in label.lower()):
                    opener = el
                    break
            if opener is not None:
                break
    if opener is not None:
        opener.click()
        page.wait_for_timeout(1500)
    shot(page, "open-file")
    selected = page.locator('[data-testid=panel-tab-strip] [role=tab][aria-selected=true]')
    name = selected.first.inner_text().strip() if selected.count() else ""
    record("ac-open-file", True, opener is not None and name == "README.md",
           f"open control found={opener is not None}, selected panel tab={name!r}")


def check_live(page, state):
    pid, base = state["pid"], state["base"]
    # Back to the Changes tab (ac-open-file moved the panel to Files), on Last turn.
    open_changes(page)
    click_scope(page, "Last turn")
    loads = page.evaluate("performance.getEntriesByType('navigation').length")
    before = run_count(pid, "Maker")
    turn(base, pid, "Maker", TURN2, conversation=state["conv"]["Maker"])
    seen_at = None
    ended = None
    deadline = time.time() + TURN_WAIT
    while time.time() < deadline:
        if seen_at is None and "plan.txt" in listed(page):
            seen_at = time.time()
        if ended is None:
            row = last_run(pid, "Maker")
            if run_count(pid, "Maker") > before and row and row[1] not in ("running", "queued", "starting"):
                ended = row
        if ended is not None and (seen_at is not None or time.time() > ended_epoch(ended[2]) + LIVE_WATCH):
            break
        time.sleep(0.2)
    if ended is None:
        raise Setup("Maker's second turn did not end")
    sha = ended[3]
    second = numstat(sha) if sha else {}
    if list(second) != ["plan.txt"]:
        raise Setup(f"Maker's second turn did not add plan.txt only: {second} (snapshot {sha})")
    shot(page, "live")
    state["live_done"] = True
    end = ended_epoch(ended[2])
    delay = None if seen_at is None else max(0.0, seen_at - end)
    reloaded = page.evaluate("performance.getEntriesByType('navigation').length") != loads
    record("ac-live", True, delay is not None and delay <= LIVE_LIMIT and not reloaded,
           f"plan.txt listed {'never within %ds' % LIVE_WATCH if delay is None else '%.1fs after the turn ended' % delay}"
           f", reloaded={reloaded}")


def check_switch(page, state):
    if not state.get("live_done"):
        raise RuntimeError("Maker's second turn never ran, so there is no second snapshot to switch over")
    # ac-switch: Last turn = plan.txt only; Since main = all three; header names branch and main.
    click_scope(page, "Last turn")
    last = listed(page)
    shot(page, "switch-last-turn")
    switched = click_scope(page, "Since main")
    since = listed(page)
    shot(page, "switch-since-main")
    text = tab_text(page)
    names = "agentweave/Maker" in text and "main" in text.replace("agentweave/Maker", "")
    ok = (set(last) == {"plan.txt"} and switched and set(since) == {"README.md", "notes.txt", "plan.txt"}
          and names)
    record("ac-switch", True, ok,
           f"Last turn={sorted(last)}, Since main control={switched} -> {sorted(since)}, "
           f"header names agentweave/Maker and main={names}")


def check_empty(page, state):
    found = {}
    for agent in ("Quiet", "Reader"):
        open_conversation(page, state, agent)
        open_changes(page)
        page.wait_for_timeout(1500)
        shot(page, f"empty-{agent}")
        found[agent] = (tab_text(page), len(rows(page)))
    quiet, reader = found["Quiet"], found["Reader"]
    quiet_ok = (quiet[1] == 0 and re.search(r"nothing|no (files|changes)|changed no files", quiet[0], re.I)
                and not ERROR_CODE.search(quiet[0]))
    reader_ok = (reader[1] == 0 and re.search(r"checkout", reader[0], re.I)
                 and re.search(r"\bno\b|not|n't|without", reader[0], re.I)
                 and not ERROR_CODE.search(reader[0]))
    record("ac-empty", True, bool(quiet_ok and reader_ok),
           f"Quiet: {quiet[0][:160]!r} rows={quiet[1]}; Reader: {reader[0][:160]!r} rows={reader[1]}")


# --------------------------------------------------------------------------- main


ORDER = ("ac-two-files", "ac-diff", "ac-open-file", "ac-live", "ac-switch", "ac-empty")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="leave the Hub running")
    args = parser.parse_args()
    if d.api("GET", "/projects")[0] != 0:
        sys.exit(f"REFUSING: something already answers on :{d.PORT}; this drive starts its own Hub "
                 "from this checkout. Pick another AW_DRIVE_PORT.")
    pathlib.Path(os.environ["AW_DRIVE_DB"]).parent.mkdir(parents=True, exist_ok=True)
    hub = d.start_hub()
    print(f"Hub from {d.REPO / 'hub'} on :{d.PORT}, db {d.DB}; output {OUT}", flush=True)
    setup_error = None
    try:
        state = build_scenario()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 940})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.add_init_script(
                f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, hubUrl: {d.HUB!r}}}));"
                f"localStorage.setItem('agentweave-selected-project', {state['pid']!r});")
            open_conversation(page, state, "Maker")
            for step in (check_two_files, check_diff, check_open_file, check_live, check_switch, check_empty):
                try:
                    step(page, state)
                except Setup:
                    raise
                except Exception as exc:  # noqa: BLE001 -- a step that broke before its assertion
                    key = {check_two_files: "ac-two-files", check_diff: "ac-diff",
                           check_open_file: "ac-open-file", check_live: "ac-live",
                           check_switch: "ac-switch", check_empty: "ac-empty"}[step]
                    print(f"BROKE {step.__name__}: {exc}", flush=True)
                    checks.setdefault(key, (False, False, f"broke before its assertion: {str(exc)[:200]}"))
            if errors:
                print(f"page errors: {errors[:3]}")
            browser.close()
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        if not args.keep:
            d.stop_hub(hub)
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
