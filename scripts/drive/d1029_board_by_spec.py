"""Acceptance drive for `the-board-shows-one-spec-no-spec-or-all`, FR-7 `ac-drive`.

Written before the build. It drives the trial Hub on :8010 in Chromium, reusing one that already
answers there and otherwise starting one from this checkout's `hub/` (never :8000); a Hub already
up serves its own checkout's bundle, so stop it before judging a branch. It costs no agent turn: the
project has no agents and nothing is fired.

It opens a scratch project holding, through the operator's routes:

  Alpha board spec  approved, three pending tasks
  Beta board spec   archived, one approved task and one rejected task (the Hub refuses to archive
                    a change with any other, and these are what All hides)
  no spec           two hand-made tasks

Then, against the served bundle:

  1. the board opens on All, which shows what it always did: archived Beta's tasks stay hidden;
  2. the picker offers All, No spec, and each spec with its count, and typing narrows it;
  3. each scope shows exactly its tasks and names itself, and All names nothing;
  4. the action on the name returns to All;
  5. a reload keeps the last scope, No spec;
  6. Alpha's page's "Show these on the board" opens the board on Alpha's scope, naming it, and a
     reload keeps it.

Step 6 runs whether or not the picker exists: on master the link already narrows, so its failure
shows the board cannot name or keep that scope.

The names the build must give the board, which nothing else fixes:

  board-scope                  the control that opens the picker
  board-scope-filter           the picker's type-to-narrow input
  board-scope-option-all       the All choice
  board-scope-option-none      the No spec choice
  board-scope-option-<id>      one spec's choice, by its document id, reading its title and count
  board-scope-name             present only when the scope is not All: the title or No spec, and
                               "N tasks"
  board-scope-clear            the one action returning to All

    py -3.11 scripts/drive/d1029_board_by_spec.py

AW_DRIVE_DB names the database of an already-running :8010 when it is not the trial profile's.
"""

import re
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

import d1029_build_plan_in_spec as d

d.TMP = d.TMP.parent.parent / "drive1029-board-by-spec" / d.STAMP
ALPHA, BETA = "Alpha board spec", "Beta board spec"
SETTLE_MS = 10000


def payload(title, keys):
    word = title.split()[0].lower()
    return {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"{title}, a scratch document.", "problem": "The board needs tasks in specs.",
        "scope": {"in_scope": [f"{word}.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": word, "modal": "MUST", "statement": f"{word}.txt MUST exist."}],
        "acceptance_criteria": [{
            "key": f"has-{word}", "requirement": word, "given": "the repository",
            "when": "it is listed", "then": f"{word}.txt is there",
            "how_to_check": f"ls {word}.txt", "checked_by": "agent"}],
        "tasks": [{"key": key, "title": f"{title} {key}", "description": f"Work {key} of {title}.",
                   "requirements": [word], "files": [f"{word}-{key}.txt"]} for key in keys],
    }


def approved_document(base, title, keys):
    """Approve a document with *keys* tasks; returns its path, id and materialised task ids."""
    path = f"spec/changes/{title.split()[0].lower()}-board/spec.json"
    quoted = urllib.parse.quote(path)
    code, out = d.api("POST", f"{base}/project/documents",
                      {"title": title, "kind": "change-spec", "path": path})
    d.check(f"setup: {title} is created", code == 201, f"{code} {out}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{path}/content",
                      {"document": payload(title, keys)})
    d.check(f"setup: {title} saves", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True,
                       "content_version": read.get("content_version")})
    d.check(f"setup: {title} is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    _, page = d.api("GET", f"{base}/tasks?limit=1000")
    tasks = [t for t in page["tasks"] if t["title"].startswith(title)]
    d.check(f"setup: {title} holds {len(keys)} tasks", len(tasks) == len(keys), f"{len(tasks)}", fatal=True)
    return path, tasks[0]["spec_document_id"], [t["id"] for t in tasks]


def seed(base):
    alpha_path, alpha_id, alpha = approved_document(base, ALPHA, ("a1", "a2", "a3"))
    beta_path, beta_id, beta = approved_document(base, BETA, ("b1", "b2"))
    for task, verdict in zip(beta, ("approved", "rejected")):
        for status in ("assigned", "in_progress", "completed", "under_review", verdict):
            code, out = d.api("PATCH", f"{base}/tasks/{task}", {"status": status, "notes": "The drive."})
            d.check(f"setup: {task} moves to {status}", code == 200,
                    f"{code} {str(out)[:400]}", fatal=True)
    quoted = urllib.parse.quote(beta_path)
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=archived",
                      {"reason": "drive", "no_capability_change": True})
    d.check(f"setup: {BETA} is archived", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    free = []
    for number in (1, 2):
        code, out = d.api("POST", f"{base}/tasks", {
            "title": f"Hand-made task {number}", "description": "Belongs to no spec.",
            "requirements": [], "acceptance_criteria": []})
        d.check(f"setup: hand-made task {number}", code in (200, 201) and not out.get("spec_document_id"),
                f"{code} {str(out)[:400]}", fatal=True)
        free.append(out["id"])
    return {
        "alpha_path": alpha_path, "alpha_id": alpha_id, "beta_id": beta_id,
        "alpha": set(alpha), "beta": set(beta), "free": set(free),
        "all": set(alpha) | set(free),
    }


def cards(page):
    return set(page.locator("[data-task-id]").evaluate_all(
        "nodes => nodes.map(node => node.getAttribute('data-task-id'))"))


def shows(page, name, expected):
    """The board settles on exactly *expected*. Waits, because the first paint can be a stale page."""
    try:
        page.wait_for_function(
            "ids => { const shown = [...document.querySelectorAll('[data-task-id]')]"
            ".map(n => n.getAttribute('data-task-id'));"
            " return shown.length === ids.length && ids.every(id => shown.includes(id)); }",
            arg=sorted(expected), timeout=SETTLE_MS)
    except Exception:  # noqa: BLE001 -- the check below reports what was on screen instead
        pass
    shown = cards(page)
    return d.check(name, shown == expected,
                   f"missing {sorted(expected - shown)} extra {sorted(shown - expected)}")


def names(page, name, words, count):
    """The board names its scope and how many tasks it holds."""
    label = page.get_by_test_id("board-scope-name")
    try:
        label.wait_for(timeout=SETTLE_MS)
    except Exception:  # noqa: BLE001 -- absent is the failure being reported
        return d.check(name, False, "no board-scope-name on the board")
    text = label.inner_text()
    return d.check(name, words in text and re.search(rf"\b{count} tasks?\b", text) is not None, text)


def open_picker(page):
    control = page.get_by_test_id("board-scope")
    try:
        control.wait_for(timeout=SETTLE_MS)
    except Exception:  # noqa: BLE001 -- absent is the failure being reported
        return False
    control.click()
    return True


def choose(page, option):
    open_picker(page)
    page.get_by_test_id(f"board-scope-option-{option}").click()


def picker_steps(page, facts, shot):
    if not d.check("2a the board offers a scope picker", open_picker(page), "no board-scope control"):
        shot("no_picker")
        return False
    offered = page.locator("[data-testid^='board-scope-option-']")
    texts = {node.get_attribute("data-testid").removeprefix("board-scope-option-"): node.inner_text()
             for node in offered.all()}
    d.check("2b it offers All, No spec and exactly the two specs",
            set(texts) == {"all", "none", facts["alpha_id"], facts["beta_id"]}, f"{texts}")
    alpha_text = texts.get(facts["alpha_id"], "")
    beta_text = texts.get(facts["beta_id"], "")
    d.check("2c each spec reads its title and number of tasks",
            ALPHA in alpha_text and "3" in alpha_text and BETA in beta_text and "2" in beta_text,
            f"{alpha_text!r} {beta_text!r}")
    page.get_by_test_id("board-scope-filter").fill("Alph")
    page.wait_for_timeout(300)
    left = [node.get_attribute("data-testid") for node in offered.all()]
    d.check("2d typing part of a title narrows the specs to it",
            f"board-scope-option-{facts['alpha_id']}" in left
            and f"board-scope-option-{facts['beta_id']}" not in left, f"{left}")
    page.keyboard.press("Escape")

    choose(page, facts["alpha_id"])
    shows(page, "3a Alpha shows exactly its tasks", facts["alpha"])
    names(page, "3b Alpha names itself and its three tasks", ALPHA, 3)
    shot("scope_alpha")

    choose(page, facts["beta_id"])
    shows(page, "3c archived Beta shows exactly its finished tasks, which All hides", facts["beta"])
    names(page, "3d Beta names itself and its two tasks", BETA, 2)
    shot("scope_beta")

    choose(page, "none")
    shows(page, "3e No spec shows exactly the hand-made tasks", facts["free"])
    names(page, "3f No spec names itself and its two tasks", "No spec", 2)
    shot("scope_none")

    choose(page, "all")
    shows(page, "3g All shows what the board showed before", facts["all"])
    d.check("3h All names no scope", page.get_by_test_id("board-scope-name").count() == 0)

    choose(page, facts["alpha_id"])
    names(page, "4a Alpha is named again before its action", ALPHA, 3)
    page.get_by_test_id("board-scope-clear").click()
    shows(page, "4b the action on the name returns to All", facts["all"])

    choose(page, "none")
    shows(page, "5a No spec is chosen last", facts["free"])
    page.reload(wait_until="domcontentloaded")
    shows(page, "5b a reload keeps No spec", facts["free"])
    names(page, "5c after the reload the board still names No spec", "No spec", 2)
    return True


def link_steps(page, facts, pid, shot):
    quoted = urllib.parse.quote(facts["alpha_path"], safe="")
    page.goto(f"{d.HUB}/?project={pid}&tab=spec&document={quoted}", wait_until="domcontentloaded")
    fact = page.get_by_test_id("spec-health-tasks")
    try:
        fact.wait_for(timeout=30000)
    except Exception:  # noqa: BLE001 -- recorded, with a picture of what was there instead
        shot("no_tasks_fact")
        d.check("6a Alpha's page offers its tasks", False, "no spec-health-tasks", fatal=True)
    fact.click()
    page.get_by_role("menuitem", name="Show these on the board").click()
    shows(page, "6b the link shows exactly Alpha's tasks", facts["alpha"])
    names(page, "6c the board opens on Alpha's scope and names it", ALPHA, 3)
    shot("link_alpha")
    page.reload(wait_until="domcontentloaded")
    shows(page, "6d a reload keeps Alpha's scope", facts["alpha"])
    names(page, "6e after the reload the board still names Alpha", ALPHA, 3)


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the board scope drive.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open",
                          {"path": str(root), "name": f"boardscope-{d.STAMP}"})
    d.check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    d.api("PATCH", base, {"main_branch": "main"})
    facts = seed(base)
    print(f"project {pid} facts {facts}", flush=True)

    init = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            " localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.add_init_script(init)
        page.on("pageerror", lambda e: errors.append(str(e)))

        def shot(name):
            page.screenshot(path=str(d.TMP / f"{name}.png"), full_page=True)

        page.goto(f"{d.HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        shows(page, "1 the board opens on All, hiding archived Beta's finished tasks", facts["all"])
        shot("board_all")
        picker_steps(page, facts, shot)
        link_steps(page, facts, pid, shot)
        browser.close()
    d.check("7 no page error while driving", not errors, f"{errors[:3]}")


def main():
    d.TMP.mkdir(parents=True, exist_ok=True)
    proc = d.start_hub()
    try:
        drive()
    except d.Stop:
        pass
    finally:
        d.stop_hub(proc)
    bad = [name for name, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed  (artefacts: {d.TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed at 0c0c42a (master), 2026-10-31 (artefacts drive1029-board-by-spec/145343): 25 passed,
# 4 failed. Step 1 passes, then 2a fails at the picker ("no board-scope control"), so steps 2b-5c do
# not run. The link narrows (6b passes) but cannot name its scope (6c), and a reload loses it (6d:
# the two hand-made tasks come back; 6e). Steps 2b-5c have therefore not yet run against a picker.
