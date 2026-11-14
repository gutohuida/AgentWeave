"""Acceptance drive for `the-side-panel-s-files-tab-browses-the-agent-s-worktree-or-the-project-root`
(SPSFT-1), 2026-11-14: every criterion of the document, written failing first, before the routes
(SPSFT-2, worktree-routes) and the wiring (SPSFT-3, wire-files). SPSFT-4 runs it green.

Starts its own Hub from THIS checkout's `hub/` on a scratch port and a fresh database (default
:8014 and a temp file; AW_DRIVE_PORT / AW_DRIVE_DB move them), and refuses a port something already
answers on, so the UI and routes under test are always this checkout's. Never :8000 or :8010.
Built on the Changes slice's drive (`d1113_changes_tab.py`) and its helpers in
`d1029_build_plan_in_spec.py`.

The scenario. Project A, a scratch git repository on branch `main`:

  README.md ("Root README"), keep.txt, old.txt, src/app.py, docs/guide/deep_nested_widget.py,
  .gitignore (`*.log`, `.agentweave/`); untracked in the root only: big.txt (2 MB), blob.bin.

Haiku agents (real turns; every one but two is a one-word "OK" turn):

  Maker   writing agent. A quiet turn provisions its worktree; the drive then seeds it with git:
          committed on agentweave/Maker: added.txt (A), keep.txt (M), old.txt deleted (D);
          uncommitted: new_untracked.txt, debug.log (ignored), README.md ("Worktree README"),
          notes.md, src/tool.py, big.txt (2 MB), blob.bin, and a link out of the worktree.
          Its second turn, with the tab open, creates live.txt                       -> ac-live
  Tasker  bound to a task (`task_id` on the trigger), so its turn runs in the task checkout
          .agentweave/tasks/<task>/ and creates task_note.txt                    -> ac-task-checkout
  Reader  read-only (`config.read_only`): no checkout of its own                  -> ac-no-checkout
  Fresh   writing agent whose worktree the drive removes after its quiet turn     -> ac-no-checkout
  Project B holds an agent also named Maker, with a worktree, for the cross-project guard.

The page contract the drive reads (the mock's FilesTab and LocationSwitch already render it,
hub/ui/src/components/panel/FilesTab.tsx, LocationSwitch.tsx):
  the tab        a panel tab "Files" (`panel-tab-files` / `panel-launch-files`, or the "Add a tab"
                 menu), whose content is `[data-testid=files-tab]` (today's FilesIndexTab is
                 `files-index-tab`, which has no location at all)
  location       `[role=radiogroup][aria-label=Where]` with radios "<agent>'s worktree" and
                 "Project root"; the checked radio is the location the header names
  rows           `[data-slot=files-row]`, its `title` the path (optionally " — added by X"), its
                 mark `[data-status=A|M|D]`, a deleted name `[data-deleted=true]`;
                 folders `[data-slot=files-dir]` with `aria-expanded`
  find           the input labelled "Find a file"
  changed only   the switch labelled "Only files the agent changed"
  no checkout    no radiogroup, the root listed, and a note naming the case (read-only / works in
                 the project directory, or no checkout yet)
  a file tab     clicking a row opens a panel tab; the selected tab (or its title) names the path
                 and the location ("worktree" / "project root"); content `file-tab-content`,
                 `file-preview-markdown`, `file-tab-binary`, `file-tab-error`; `file-tab-insert`

The route contract the drive probes (the builder of worktree-routes may change the names; the
drive is then fixed in SPSFT-4, the behaviour is not):
  GET /projects/{pid}/workspace/paths?conversation_id=C&location=worktree|root
      -> with conversation_id: {location, state, message, branch, paths: [...], changed: {p: A|M|D}}
         (a bare list is still read as `paths`); without it, today's list, unchanged
  GET /projects/{pid}/workspace/file?path=P&conversation_id=C&location=worktree
      -> today's WorkspaceFileResponse, 404 for a path not listed there or through a link out,
         413 over 1 MB, `binary: true` for a NUL-sniffed file

Hub-test outline (what SPSFT-2 writes under hub/tests, each failing before its fix; the drive's
route probes below are the end-to-end half of the same criteria):
  ac-task-checkout  seed a task worktree and a run bound to it; the Files route's checkout and
                    branch equal the Changes route's `_resolve_target` answer for that conversation
  ac-no-checkout    a read-only agent, and a writing agent with no worktree: state names the
                    case, paths are the root's, no 4xx/5xx; no worktree is created by the read
  ac-uncommitted    temp repo: untracked file listed, ignored file not, nested tracked file listed
  ac-guards         unlisted path, link out of the worktree, another agent's checkout, another
                    project's conversation: each refused, no content
  ac-large-binary   2 MB text -> 413, NUL file -> binary, the same as the root route answers
  ac-changed-only   added/modified/deleted since main: `changed` equals the Changes route's
                    `since_base` paths and statuses

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. Screenshots and the tab's text go to testbed/files-drive/<HHMMSS>/.
ac-preview-themes is the operator's to judge: the drive attaches files-light-*.png and
files-dark-*.png and checks only what a machine can (highlight spans, rendered headings and lists,
text/background contrast).

    py -3.11 scripts/drive/files_tab_drive.py            # own Hub on :8014, fresh db
    py -3.11 scripts/drive/files_tab_drive.py --keep     # leave the Hub up afterwards
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse

STAMP = time.strftime("%H%M%S")
os.environ.setdefault("AW_DRIVE_PORT", "8014")
os.environ.setdefault(
    "AW_DRIVE_DB",
    str(pathlib.Path(tempfile.gettempdir()) / "drive-files-tab" / STAMP / "hub.db"),
)
if os.environ["AW_DRIVE_PORT"] in ("8000", "8010"):
    sys.exit("REFUSING: this drive starts its own Hub and never runs on :8000 or :8010")

import d1029_build_plan_in_spec as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = d.REPO / "testbed" / "files-drive" / STAMP
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "drive-files-tab" / STAMP
ROOT = SCRATCH / "proj"
OTHER = SCRATCH / "other"
OUTSIDE = SCRATCH / "outside"
TURN_WAIT = 8 * 60
LIVE_LIMIT = 5.0  # FR-8: within 5 seconds of the turn's end
LIVE_WATCH = 30.0  # how long the drive keeps looking, so a late arrival is reported with its delay
NO_GIT = "Do not run git or commit anything; the Hub commits your work. Change nothing else."
QUIET = "Reply with the single word OK. Do not create, edit or delete any file, and do not run git."
TASK_TURN = "Create task_note.txt in your working directory holding the single line `task`. " + NO_GIT
LIVE_TURN = "Create live.txt in your working directory holding the single line `live`. " + NO_GIT
ERROR_CODE = re.compile(r"\b[45]\d\d\b|Internal Server Error|Traceback|\bundefined\b|\bnull\b")
NESTED = "docs/guide/deep_nested_widget.py"
TOOL_PY = (
    "import json\n\n\nclass Tool:\n    \"\"\"A tool.\"\"\"\n\n    def run(self, value: int) -> str:\n"
    "        return json.dumps({'value': value * 2})\n"
)
NOTES_MD = "# Notes from Maker\n\n## Plan\n\n- first item\n- second item\n\nSome *emphasis* here.\n"

checks = {}  # key -> (reached, failed, detail)


def record(key, reached, ok, detail):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


class Setup(Exception):
    """The scenario could not be built; not a verdict on the product."""


# --------------------------------------------------------------------------- scenario (REST + git)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def big_text():
    return ("x" * 99 + "\n") * (2 * 1024 * 1024 // 100 + 1)  # just over 2 MB


def turn(base, agent, message, conversation=None, task_id=None):
    body = {"agent": agent, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    if task_id:
        body["task_id"] = task_id
    code, out = d.api("POST", f"{base}/agent/trigger", body, timeout=90)
    if code != 200:
        raise Setup(f"trigger {agent}: {code} {str(out)[:300]}")
    return out


def last_run(pid, agent):
    rows = d.ro("select id, status, ended_at, snapshot_commit_sha, workspace_dir from runs "
                "where project_id=? and agent=? order by started_at desc limit 1", (pid, agent))
    return rows[0] if rows else None


def run_count(pid, agent):
    return d.ro("select count(*) from runs where project_id=? and agent=?", (pid, agent))[0][0]


def finished(row):
    return row and row[1] not in ("running", "queued", "starting")


def wait_turn(pid, agent, since_count):
    if not d.poll(lambda: run_count(pid, agent) > since_count and finished(last_run(pid, agent)),
                  TURN_WAIT, every=0.25):
        raise Setup(f"{agent}'s turn did not end within {TURN_WAIT}s")
    return last_run(pid, agent)


def ended_epoch(text):
    stamp = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.timestamp()


def new_project(root, name):
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": name})
    if code not in (200, 201):
        raise Setup(f"project open {name}: {code} {project}")
    base = f"/projects/{project['id']}"
    d.api("PATCH", base, {"main_branch": "main"})
    code, runner = d.api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": d.HAIKU})
    if code not in (200, 201):
        raise Setup(f"runner {name}: {code} {runner}")
    return project["id"], base, runner["id"]


def add_agent(base, runner_id, name, read_only=False):
    code, out = d.api("POST", f"{base}/agents", {"name": name, "runner_id": runner_id})
    if code not in (200, 201):
        raise Setup(f"agent {name}: {code} {out}")
    if read_only:
        code, out = d.api("PATCH", f"{base}/agents/{name}", {"config": {"read_only": True}})
        if code != 200:
            raise Setup(f"{name} read-only: {code} {out}")


def seed_repo(root, readme):
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    write(root / "README.md", readme)
    write(root / "keep.txt", "keep\n")
    write(root / "old.txt", "old\n")
    write(root / "src" / "app.py", "print('hello')\n")
    write(root / NESTED, "WIDGET = 1\n")
    write(root / ".gitignore", "*.log\n.agentweave/\n")
    d.git(root, "add", ".")
    d.git(root, "commit", "-q", "-m", "seed")


def make_link(worktree):
    """A link from inside the worktree to a file outside it. A file symlink where Windows allows
    one, else a directory junction (no privilege needed). Returns the in-worktree path or None."""
    write(OUTSIDE / "secret.txt", "outside the worktree\n")
    try:
        os.symlink(OUTSIDE / "secret.txt", worktree / "escape_link.txt")
        return "escape_link.txt"
    except OSError:
        pass
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(worktree / "escape_dir"), str(OUTSIDE)],
                          capture_output=True, text=True)
    return "escape_dir/secret.txt" if done.returncode == 0 else None


def build_scenario():
    seed_repo(ROOT, "Root README\n")
    write(ROOT / "big.txt", big_text())
    (ROOT / "blob.bin").write_bytes(b"\x00\x01\x02binary\x00" * 64)
    pid, base, runner = new_project(ROOT, f"files-{STAMP}")
    for name in ("Maker", "Tasker", "Fresh"):
        add_agent(base, runner, name)
    add_agent(base, runner, "Reader", read_only=True)
    state = {"pid": pid, "base": base, "conv": {}}

    for agent in ("Maker", "Reader", "Fresh"):
        before = run_count(pid, agent)
        state["conv"][agent] = turn(base, agent, QUIET)["conversation_id"]
        row = wait_turn(pid, agent, before)
        print(f"  {agent}'s quiet turn: {row[1]} workspace={row[4]}", flush=True)
        if row[3]:
            raise Setup(f"{agent}'s quiet turn committed {row[3]}; it was to change nothing")

    worktree = ROOT / ".agentweave" / "worktrees" / "Maker"
    if not (worktree / ".git").is_file():
        raise Setup(f"Maker's turn left no worktree at {worktree}")
    if (ROOT / ".agentweave" / "worktrees" / "Reader").exists():
        raise Setup("Reader has a worktree; it was to have no checkout of its own")
    fresh = ROOT / ".agentweave" / "worktrees" / "Fresh"
    if fresh.exists():
        d.git(ROOT, "worktree", "remove", "--force", str(fresh))
    subprocess.run(["git", "branch", "-D", "agentweave/Fresh"], cwd=ROOT, capture_output=True)
    if fresh.exists():
        raise Setup("Fresh's worktree could not be removed")

    # Maker's branch: one added, one modified, one deleted since main.
    write(worktree / "added.txt", "added on Maker's branch\n")
    write(worktree / "keep.txt", "keep\nchanged by Maker\n")
    (worktree / "old.txt").unlink()
    d.git(worktree, "add", "-A")
    d.git(worktree, "commit", "-q", "-m", "Maker: add, modify, delete")
    # Uncommitted in the worktree.
    write(worktree / "new_untracked.txt", "not committed yet\n")
    write(worktree / "debug.log", "ignored\n")
    write(worktree / "README.md", "Worktree README\n")
    write(worktree / "notes.md", NOTES_MD)
    write(worktree / "src" / "tool.py", TOOL_PY)
    write(worktree / "big.txt", big_text())
    (worktree / "blob.bin").write_bytes(b"\x00\x01\x02binary\x00" * 64)
    state["link"] = make_link(worktree)
    state["worktree"] = worktree

    # Tasker: a turn bound to a task runs in the task's own checkout.
    code, task = d.api("POST", f"{base}/tasks", {"title": "Leave a note", "description": TASK_TURN,
                                                "assignee": "Tasker"})
    if code not in (200, 201):
        raise Setup(f"task: {code} {task}")
    state["task"] = task["id"]
    before = run_count(pid, "Tasker")
    state["conv"]["Tasker"] = turn(base, "Tasker", TASK_TURN, task_id=task["id"])["conversation_id"]
    row = wait_turn(pid, "Tasker", before)
    checkout = pathlib.Path(row[4] or "")
    if ".agentweave" not in checkout.parts or "tasks" not in checkout.parts:
        raise Setup(f"Tasker's turn did not run in a task checkout: workspace_dir={row[4]}")
    if not (checkout / "task_note.txt").exists():
        raise Setup(f"Tasker's turn did not create task_note.txt in {checkout}")
    state["task_checkout"] = checkout
    print(f"  Tasker's task turn: {row[1]} in {checkout}", flush=True)

    # Project B: another project's agent, also named Maker, with a worktree.
    seed_repo(OTHER, "Other project's README\n")
    pid_b, base_b, runner_b = new_project(OTHER, f"files-other-{STAMP}")
    add_agent(base_b, runner_b, "Maker")
    before = run_count(pid_b, "Maker")
    state["conv_b"] = turn(base_b, "Maker", QUIET)["conversation_id"]
    wait_turn(pid_b, "Maker", before)
    state["pid_b"], state["base_b"] = pid_b, base_b
    write(OTHER / ".agentweave" / "worktrees" / "Maker" / "other_secret.txt", "project B\n")
    return state


# --------------------------------------------------------------------------- the routes


def q(**params):
    return "?" + urllib.parse.urlencode(params)


def files_route(base, conv, location):
    code, out = d.api("GET", f"{base}/workspace/paths" + q(conversation_id=conv, location=location))
    if isinstance(out, list):
        return code, {"paths": out}
    return code, out if isinstance(out, dict) else {"raw": out}


def file_route(base, conv, path, location="worktree"):
    return d.api("GET", f"{base}/workspace/file" + q(path=path, conversation_id=conv, location=location))


def changes_route(base, conv):
    code, out = d.api("GET", f"{base}/conversations/{conv}/changes")
    return out if code == 200 and isinstance(out, dict) else {}


# --------------------------------------------------------------------------- the page


def open_conversation(page, state, agent, reload=False):
    url = f"{d.HUB}/?project={state['pid']}&agent={agent}&conversation={state['conv'][agent]}"
    if reload:
        page.reload(wait_until="domcontentloaded")
    else:
        page.goto(url, wait_until="domcontentloaded")
    page.get_by_test_id("conversation-pane").wait_for(timeout=20000)
    page.wait_for_timeout(1500)


def open_panel_tab(page, testid, name):
    """Opens the panel tab `name` the way the operator does; returns its content locator."""
    tab = page.get_by_test_id(testid)
    if not page.get_by_test_id("panel-shell").count():
        page.get_by_role("button", name="More conversation actions").click()
        page.get_by_test_id("conversation-toggle-panel").click()
        page.wait_for_timeout(800)
    key = name.lower()
    for opener in (page.get_by_test_id(f"panel-tab-{key}"), page.get_by_test_id(f"panel-launch-{key}")):
        if opener.count():
            opener.first.click()
            break
    else:
        add = page.get_by_test_id("panel-tab-add")
        if add.count():
            add.first.click()
            page.wait_for_timeout(300)
            item = page.get_by_role("menuitem", name=name)
            if item.count():
                item.first.click()
            else:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
    try:
        tab.wait_for(timeout=8000)
    except Exception:  # noqa: BLE001 -- absence is what the checks report
        pass
    page.wait_for_timeout(800)
    return tab


def wait_until(page, predicate, timeout=10000, step=150):
    """Polls `predicate` until it holds or `timeout` ms pass; returns whether it held."""
    waited = 0
    while True:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001 -- the page may be mid-render; poll again
            pass
        if waited >= timeout:
            return False
        page.wait_for_timeout(step)
        waited += step


def settled(page, timeout=10000):
    """Waits until the Files tab's row list has rows and stops changing between polls."""
    last = [None]

    def stable():
        now = sorted(tree(page))
        same = bool(now) and now == last[0]
        last[0] = now
        return same

    return wait_until(page, stable, timeout)


def open_files(page):
    tab = open_panel_tab(page, "files-tab", "Files")
    settled(page)
    return tab


def files_tab(page):
    return page.get_by_test_id("files-tab")


def what_is_there(page):
    """One phrase for a detail line: what the Files panel holds when the contract is not met."""
    if files_tab(page).count():
        return "files-tab present"
    if page.get_by_test_id("files-index-tab").count():
        return ("no Worktree location: the Files tab is still the root-only path search "
                "(files-index-tab), with no switch and no tree")
    return "no Files tab content at all"


def location_shown(page):
    """The checked location radio's text, or '' when there is no switch."""
    group = files_tab(page).locator('[role=radiogroup][aria-label="Where"]')
    if not group.count():
        return ""
    checked = group.locator('[role=radio][aria-checked="true"]')
    return checked.first.inner_text().strip() if checked.count() else ""


def switch_to(page, location):
    group = files_tab(page).locator('[role=radiogroup][aria-label="Where"]')
    if not group.count():
        return False
    name = re.compile(r"worktree", re.I) if location == "worktree" else re.compile(r"project root", re.I)
    radio = group.get_by_role("radio", name=name)
    if not radio.count():
        return False
    radio.first.click()
    wait_until(page, lambda: radio.first.get_attribute("aria-checked") == "true")
    settled(page)
    return True


def row_path(el):
    title = el.get_attribute("title") or el.inner_text()
    return title.split(" — ")[0].strip()


def tree(page):
    """{path: {mark, deleted}} of the file rows shown now."""
    out = {}
    found = files_tab(page).locator("[data-slot=files-row]")
    for i in range(found.count()):
        el = found.nth(i)
        mark = el.locator("[data-status]")
        out[row_path(el)] = {
            "mark": mark.first.get_attribute("data-status") if mark.count() else None,
            "deleted": el.locator('[data-deleted="true"]').count() > 0,
        }
    return out


def find(page, text):
    box = files_tab(page).get_by_label("Find a file")
    if not wait_until(page, lambda: box.count() > 0):
        return False
    box.first.fill(text)
    wait_until(page, lambda: box.first.input_value() == text)
    # the filtered list is read next; wait for it to stop changing (an empty one is a result too)
    last = [None]

    def stable():
        now = sorted(tree(page))
        same = now == last[0]
        last[0] = now
        return same

    wait_until(page, stable)
    return True


def open_row(page, path):
    """Opens `path` from the tree through find; True when a row was clicked."""
    if not find(page, path.rsplit("/", 1)[-1]):
        return False
    rows = files_tab(page).locator("[data-slot=files-row]")
    for i in range(rows.count()):
        if row_path(rows.nth(i)) == path:
            rows.nth(i).click()
            page.wait_for_timeout(1500)
            return True
    find(page, "")
    return False


def selected_tab_label(page):
    sel = page.locator("[data-testid=panel-tab-strip] [role=tab][aria-selected=true]")
    if not sel.count():
        return ""
    el = sel.first
    return " ".join(filter(None, [el.inner_text(), el.get_attribute("title"), el.get_attribute("aria-label")]))


def file_tabs(page):
    tabs = page.locator("[data-testid=panel-tab-strip] [role=tab]")
    return [tabs.nth(i) for i in range(tabs.count())]


def panel_text(page):
    content = page.get_by_test_id("panel-tab-content")
    return content.inner_text() if content.count() else ""


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f"{name}.png"))
    (OUT / f"{name}.txt").write_text(panel_text(page), encoding="utf-8")


def says_worktree(label):
    return re.search(r"worktree|checkout", label, re.I) is not None


def says_root(label):
    return re.search(r"project root|root", label, re.I) is not None


CONTRAST_JS = """
(el) => {
  const rgb = (s) => (s.match(/[\\d.]+/g) || []).slice(0, 4).map(Number);
  const lum = ([r, g, b]) => {
    const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const fg = rgb(getComputedStyle(el).color);
  let node = el, bg = null;
  while (node) {
    const c = rgb(getComputedStyle(node).backgroundColor);
    if (c.length >= 3 && (c.length < 4 || c[3] > 0.5)) { bg = c; break; }
    node = node.parentElement;
  }
  bg = bg || [255, 255, 255];
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}
"""


def set_mode(page, state, agent, mode):
    page.evaluate(f"localStorage.setItem('agentweave-prefs', JSON.stringify({{mode: {mode!r}}}))")
    open_conversation(page, state, agent, reload=True)


# --------------------------------------------------------------------------- the checks


def check_switch(page, state):
    open_conversation(page, state, "Maker")
    open_files(page)
    state["maker_first_location"] = location_shown(page)
    worktree_tree, worktree_label = tree(page), location_shown(page)
    shot(page, "switch-worktree")
    switched = switch_to(page, "root")
    root_tree, root_label = tree(page), location_shown(page)
    shot(page, "switch-root")
    switch_to(page, "worktree")
    ok = ("added.txt" in worktree_tree and switched and "added.txt" not in root_tree and root_tree
          and says_worktree(worktree_label) and "maker" in worktree_label.lower()
          and says_root(root_label) and not says_worktree(root_label))
    record("ac-switch", True, ok,
           f"{what_is_there(page)}; Worktree header={worktree_label!r} lists added.txt="
           f"{'added.txt' in worktree_tree}; switch={switched}; Project root header={root_label!r} "
           f"lists added.txt={'added.txt' in root_tree} ({len(root_tree)} rows)")


def check_uncommitted(page, state):
    switch_to(page, "worktree")
    find(page, "")
    now = tree(page)
    listed = {"new_untracked.txt": "new_untracked.txt" in now, NESTED: NESTED in now,
              "debug.log (ignored)": "debug.log" in now}
    found = find(page, "nested_wid")
    wait_until(page, lambda: NESTED in tree(page))
    narrowed = set(tree(page))
    text = files_tab(page).inner_text() if files_tab(page).count() else ""
    folder = files_tab(page).locator('[data-slot=files-dir][aria-expanded="true"]')
    expanded = "docs/guide" in text or any("guide" in folder.nth(i).inner_text() for i in range(folder.count()))
    shot(page, "uncommitted-find")
    find(page, "")
    ok = (listed["new_untracked.txt"] and listed[NESTED] and not listed["debug.log (ignored)"]
          and found and narrowed == {NESTED} and expanded)
    record("ac-uncommitted", True, ok,
           f"{what_is_there(page)}; in the worktree tree: {listed}; find 'nested_wid' -> "
           f"{sorted(narrowed)} folder shown={expanded}")


def check_changed_only(page, state):
    switch_to(page, "worktree")
    toggle = files_tab(page).get_by_label("Only files the agent changed")
    turned = False
    if wait_until(page, lambda: toggle.count() > 0):
        toggle.first.click()
        # narrowed: every row left carries a mark, and the list has stopped changing
        wait_until(page, lambda: bool(tree(page)) and all(v["mark"] for v in tree(page).values()))
        settled(page)
        turned = True
    now = tree(page)
    shot(page, "changed-only")
    if turned:
        toggle.first.click()
        wait_until(page, lambda: any(not v["mark"] for v in tree(page).values()))
    marks = {p: v["mark"] for p, v in now.items()}
    since = {f["path"]: f["status"][0] for f in changes_route(state["base"], state["conv"]["Maker"])
             .get("since_base", [])}
    want = {"added.txt": "A", "keep.txt": "M", "old.txt": "D"}
    ok = (turned and marks == want and now.get("old.txt", {}).get("deleted") and since == want
          and set(marks) == set(since))
    record("ac-changed-only", True, ok,
           f"{what_is_there(page)}; Changed only control={turned} -> {marks}; old.txt struck="
           f"{now.get('old.txt', {}).get('deleted')}; Changes route Since main={since}")


def preview_facts(page):
    code = page.locator("[data-testid=file-tab-content].hljs span[class^=hljs-]")
    md = page.get_by_test_id("file-preview-markdown")
    target = page.get_by_test_id("file-tab-content")
    if not target.count():
        target = md
    contrast = target.first.evaluate(CONTRAST_JS) if target.count() else 0.0
    return {"spans": code.count(), "headings": md.locator("h1, h2").count() if md.count() else 0,
            "items": md.locator("li").count() if md.count() else 0, "contrast": round(contrast, 2)}


def check_preview_themes(page, state):
    results = {}
    for mode in ("dark", "light"):
        set_mode(page, state, "Maker", mode)
        open_files(page)
        switch_to(page, "worktree")
        for path in ("src/tool.py", "notes.md"):
            opened = open_row(page, path)
            label = selected_tab_label(page)
            facts = preview_facts(page) if opened else {}
            shot(page, f"files-{mode}-{path.replace('/', '_')}")
            results[(mode, path)] = (opened, label, facts)
            open_files(page)
    set_mode(page, state, "Maker", "dark")
    bad = []
    for (mode, path), (opened, label, facts) in results.items():
        if not opened:
            bad.append(f"{mode} {path}: no row to open")
            continue
        if path not in label and path.rsplit("/", 1)[-1] not in label or not says_worktree(label):
            bad.append(f"{mode} {path}: tab label {label!r} does not name path and worktree")
        if path.endswith(".py") and not facts.get("spans"):
            bad.append(f"{mode} {path}: not highlighted")
        if path.endswith(".md") and not (facts.get("headings") and facts.get("items") >= 2):
            bad.append(f"{mode} {path}: not rendered {facts}")
        if facts.get("contrast", 0) < 4.5:
            bad.append(f"{mode} {path}: contrast {facts.get('contrast')}")
    record("ac-preview-themes", True, not bad,
           f"{what_is_there(page)}; " + ("; ".join(bad) if bad else
                                          f"{ {f'{m} {p}': r[2] for (m, p), r in results.items()} }")
           + f"; screenshots for the operator in {OUT}")


def check_two_tabs(page, state):
    open_conversation(page, state, "Maker")
    open_files(page)
    seen = {}
    for location in ("worktree", "root"):
        switched = switch_to(page, location)
        opened = switched and open_row(page, "README.md")
        seen[location] = (opened, selected_tab_label(page), panel_text(page))
        open_files(page)
    readme_tabs = [t for t in file_tabs(page) if "README" in (t.inner_text() + (t.get_attribute("title") or ""))]
    wt, rt = seen["worktree"], seen["root"]
    ok = (wt[0] and rt[0] and len(readme_tabs) == 2 and says_worktree(wt[1]) and says_root(rt[1])
          and not says_worktree(rt[1]) and "Worktree README" in wt[2] and "Root README" in rt[2])
    shot(page, "two-tabs")
    record("ac-two-tabs", True, ok,
           f"{what_is_there(page)}; worktree opened={wt[0]} label={wt[1]!r} own content="
           f"{'Worktree README' in wt[2]}; root opened={rt[0]} label={rt[1]!r} own content="
           f"{'Root README' in rt[2]}; README tabs={len(readme_tabs)}")


def composer_value(page):
    box = page.get_by_test_id("conversation-pane").locator("textarea")
    return box.first.input_value() if box.count() else ""


def check_insert(page, state):
    open_files(page)
    switch_to(page, "worktree")
    opened = open_row(page, "src/tool.py")
    insert = page.get_by_test_id("file-tab-insert")
    if opened and insert.count():
        insert.first.click()
        page.wait_for_timeout(600)
    value = composer_value(page)
    ok = opened and "src/tool.py" in value and ".agentweave" not in value and "task-" not in value
    shot(page, "insert")
    record("ac-insert", True, ok,
           f"{what_is_there(page)}; opened src/tool.py from the worktree={opened}; composer={value!r}")


def check_large_binary(page, state):
    base, conv = state["base"], state["conv"]["Maker"]
    route = {name: file_route(base, conv, name) for name in ("big.txt", "blob.bin")}
    root_route = {name: d.api("GET", f"{base}/workspace/file" + q(path=name)) for name in ("big.txt", "blob.bin")}
    shown = {}
    open_files(page)
    for location in ("worktree", "root"):
        switch_to(page, location)
        for name in ("big.txt", "blob.bin"):
            opened = open_row(page, name)
            state_el = ("binary" if page.get_by_test_id("file-tab-binary").count() else
                        "error" if page.get_by_test_id("file-tab-error").count() else "content")
            text = panel_text(page).replace("worktree", "").replace("project root", "")
            shown[(location, name)] = (opened, state_el, re.sub(r"\s+", " ", text)[:200])
            open_files(page)
    shot(page, "large-binary")
    route_ok = (route["big.txt"][0] == 413 and route["blob.bin"][0] == 200
                and isinstance(route["blob.bin"][1], dict) and route["blob.bin"][1].get("binary") is True
                and route["blob.bin"][1].get("content") is None
                and root_route["big.txt"][0] == 413 and isinstance(root_route["blob.bin"][1], dict)
                and root_route["blob.bin"][1].get("binary") is True)
    page_ok = all(shown[(loc, n)][0] for loc in ("worktree", "root") for n in ("big.txt", "blob.bin")) and \
        shown[("worktree", "blob.bin")][1] == shown[("root", "blob.bin")][1] == "binary" and \
        shown[("worktree", "big.txt")][1] == shown[("root", "big.txt")][1] == "error"
    record("ac-large-binary", True, route_ok and page_ok,
           f"{what_is_there(page)}; worktree route big={route['big.txt'][0]} blob={route['blob.bin'][0]} "
           f"binary={isinstance(route['blob.bin'][1], dict) and route['blob.bin'][1].get('binary')} "
           f"(root route big={root_route['big.txt'][0]}); page: "
           f"{ {f'{k[0]}:{k[1]}': v[:2] for k, v in shown.items()} }")


def check_guards(page, state):
    base, conv = state["base"], state["conv"]["Maker"]
    listed = file_route(base, conv, "added.txt")
    positive = listed[0] == 200 and isinstance(listed[1], dict) and "added on Maker's branch" in (
        listed[1].get("content") or "")
    task_rel = os.path.relpath(state["task_checkout"] / "task_note.txt", state["worktree"]).replace("\\", "/")
    asks = {
        "not listed (ignored debug.log)": file_route(base, conv, "debug.log"),
        "parent traversal": file_route(base, conv, "../../../README.md"),
        "another agent's checkout (relative)": file_route(base, conv, task_rel),
        "another agent's checkout (absolute)": file_route(base, conv, str(state["task_checkout"] / "task_note.txt")),
        "Tasker's conversation asking for Maker's file": file_route(base, state["conv"]["Tasker"], "added.txt"),
        "another project's conversation": file_route(base, state["conv_b"], "other_secret.txt"),
        "this project's conversation through project B": file_route(state["base_b"], conv, "added.txt"),
    }
    if state.get("link"):
        asks[f"link out ({state['link']})"] = file_route(base, conv, state["link"])
    leaked = {k: v[0] for k, v in asks.items()
              if v[0] == 200 or (isinstance(v[1], dict) and v[1].get("content"))}
    ok = positive and not leaked and state.get("link") is not None
    record("ac-guards", True, ok,
           f"listed worktree file reads from the worktree={positive} ({listed[0]}); refused: "
           f"{ {k: v[0] for k, v in asks.items()} }; leaked={leaked}"
           + ("" if state.get("link") else "; no link could be made on this machine"))


def check_no_checkout(page, state):
    found = {}
    for agent in ("Reader", "Fresh"):
        open_conversation(page, state, agent)
        open_files(page)
        shot(page, f"no-checkout-{agent}")
        text = files_tab(page).inner_text() if files_tab(page).count() else panel_text(page)
        switch = files_tab(page).locator('[role=radiogroup][aria-label="Where"]').count() > 0
        found[agent] = (files_tab(page).count() > 0, switch, "README.md" in tree(page), text)
    created = (ROOT / ".agentweave" / "worktrees" / "Fresh").exists()
    reader, fresh = found["Reader"], found["Fresh"]
    reader_note = re.search(r"read-only|project directory", reader[3], re.I)
    fresh_note = re.search(r"no checkout|not (been )?created|yet", fresh[3], re.I)
    ok = (reader[0] and fresh[0] and not reader[1] and not fresh[1] and reader[2] and fresh[2]
          and reader_note and fresh_note and not ERROR_CODE.search(reader[3])
          and not ERROR_CODE.search(fresh[3]) and not created)
    record("ac-no-checkout", True, bool(ok),
           f"{what_is_there(page)}; Reader: tab={reader[0]} switch={reader[1]} root listed={reader[2]} "
           f"note={bool(reader_note)}; Fresh: tab={fresh[0]} switch={fresh[1]} root listed={fresh[2]} "
           f"note={bool(fresh_note)}; Fresh worktree created by browsing={created}")


def check_task_checkout(page, state):
    open_conversation(page, state, "Tasker")
    open_files(page)
    state["tasker_first_location"] = location_shown(page)
    now = tree(page)
    label = location_shown(page)
    there = what_is_there(page)
    shot(page, "task-checkout-files")
    open_panel_tab(page, "changes-tab", "Changes")
    changes_text = page.get_by_test_id("changes-tab").inner_text() if page.get_by_test_id("changes-tab").count() else ""
    shot(page, "task-checkout-changes")
    branch = f"agentweave/task/{state['task']}"
    route_changes = changes_route(state["base"], state["conv"]["Tasker"]).get("branch")
    code, route_files = files_route(state["base"], state["conv"]["Tasker"], "worktree")
    route_paths = route_files.get("paths") or []
    route_branch = route_files.get("branch")
    ok = ("task_note.txt" in now and says_worktree(label) and branch in changes_text
          and route_changes == branch and "task_note.txt" in route_paths
          and (route_branch is None or route_branch == route_changes))
    record("ac-task-checkout", True, ok,
           f"{there}; Files ({label!r}) lists task_note.txt={'task_note.txt' in now}; "
           f"Changes tab names {branch}={branch in changes_text}; routes: files {code} lists "
           f"task_note.txt={'task_note.txt' in route_paths} branch={route_branch!r}, changes branch="
           f"{route_changes!r}")


def check_default_and_remembered(page, state):
    first = state.get("maker_first_location", "")
    open_conversation(page, state, "Maker")
    open_files(page)
    switched = switch_to(page, "root")
    open_conversation(page, state, "Maker", reload=True)
    open_files(page)
    after = location_shown(page)
    open_conversation(page, state, "Tasker")
    open_files(page)
    second = location_shown(page)
    shot(page, "remembered")
    # Leave Maker on its worktree for ac-live.
    open_conversation(page, state, "Maker")
    open_files(page)
    switch_to(page, "worktree")
    ok = (says_worktree(first) and switched and says_root(after) and not says_worktree(after)
          and says_worktree(second) and says_worktree(state.get("tasker_first_location", "")))
    record("ac-default-and-remembered", True, ok,
           f"{what_is_there(page)}; Maker first opened on {first!r}, switched to root={switched}, "
           f"after reload {after!r}; Tasker opened on {state.get('tasker_first_location')!r}, "
           f"then {second!r}")


def check_live(page, state):
    pid, base = state["pid"], state["base"]
    open_files(page)
    switch_to(page, "worktree")
    find(page, "")
    label = location_shown(page)
    loads = page.evaluate("performance.getEntriesByType('navigation').length")
    before = run_count(pid, "Maker")
    turn(base, "Maker", LIVE_TURN, conversation=state["conv"]["Maker"])
    seen_at, ended = None, None
    deadline = time.time() + TURN_WAIT
    while time.time() < deadline:
        if seen_at is None and tree(page).get("live.txt", {}).get("mark") == "A":
            seen_at = time.time()
        if ended is None:
            row = last_run(pid, "Maker")
            if run_count(pid, "Maker") > before and finished(row):
                ended = row
        if ended is not None and (seen_at is not None or time.time() > ended_epoch(ended[2]) + LIVE_WATCH):
            break
        time.sleep(0.2)
    if ended is None:
        raise Setup("Maker's live turn did not end")
    if not (state["worktree"] / "live.txt").exists():
        raise Setup("Maker's live turn did not create live.txt")
    shot(page, "live")
    delay = None if seen_at is None else max(0.0, seen_at - ended_epoch(ended[2]))
    reloaded = page.evaluate("performance.getEntriesByType('navigation').length") != loads
    record("ac-live", True, delay is not None and delay <= LIVE_LIMIT and not reloaded and says_worktree(label),
           f"{what_is_there(page)}; tab on {label!r}; live.txt marked A "
           f"{'never within %ds' % LIVE_WATCH if delay is None else '%.1fs after the turn ended' % delay}"
           f", reloaded={reloaded}")


# --------------------------------------------------------------------------- main

STEPS = (
    ("ac-switch", check_switch),
    ("ac-uncommitted", check_uncommitted),
    ("ac-changed-only", check_changed_only),
    ("ac-preview-themes", check_preview_themes),
    ("ac-two-tabs", check_two_tabs),
    ("ac-insert", check_insert),
    ("ac-large-binary", check_large_binary),
    ("ac-guards", check_guards),
    ("ac-no-checkout", check_no_checkout),
    ("ac-task-checkout", check_task_checkout),
    ("ac-default-and-remembered", check_default_and_remembered),
    ("ac-live", check_live),
)


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
            for key, step in STEPS:
                try:
                    step(page, state)
                except Setup:
                    raise
                except Exception as exc:  # noqa: BLE001 -- a step that broke before its assertion
                    print(f"BROKE {step.__name__}: {exc}", flush=True)
                    checks.setdefault(key, (False, False, f"broke before its assertion: {str(exc)[:200]}"))
            if errors:
                print(f"page errors: {errors[:3]}")
            browser.close()
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    except Setup as exc:
        setup_error = str(exc)
        print(f"SETUP: {exc}", flush=True)
    finally:
        if not args.keep:
            d.stop_hub(hub)
    print("\n== drive_baseline")
    failed = False
    for key, _ in STEPS:
        reached, failed_here, detail = checks.get(key, (False, False, setup_error or "not run"))
        failed = failed or failed_here or not reached
        print(f"check {key}: reached={'yes' if reached else 'no'} "
              f"failed_at_assertion={'yes' if failed_here else 'no'} -- {detail}")
    print(f"output: {OUT}")
    sys.exit(1 if failed or setup_error else 0)


if __name__ == "__main__":
    main()
