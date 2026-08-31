"""F156 -- the drawer beside the approve control promises a merge the gate refuses one call later.

The finding, live 2026-08-30: `GET .../integration-preview` answered `will_merge: true, reason: ""`
for a task whose approval the gate refused twice in the same minute, over that exact commit. The
handler is candid about why -- it deliberately runs no conflict probe, "a sentence, not a second
gate" -- and that reasoning is sound. The **word** is not: `will_merge` is
`bool(main_branch and targets)` (`hub/hub/api/v1/tasks.py:1102-1107`), which answers *is there
something to merge*, and the operator reads it as *will it merge*.

Recorded as prose, F156 reads like something you need a particular repository to reach. This file
shows it is four HTTP calls and one conflicting commit, with no agent turn and no model bound:

  LANE 1  the drawer, at `under_review`, exactly where an operator consults it. What does it say?
  LANE 2  the gate, at the same instant, over the same commit. What does it say?
  LANE 3  the drawer AGAIN, after the refusal. Has it learned anything? (It has not -- and F141
          already recorded that the gate's refusal leaves no trace behind it.)
  LANE 4  the CONTRAST that makes this a defect rather than a rough edge: a task with no conflict
          gets the byte-identical `will_merge: true`, and its approval succeeds. One word carries
          both outcomes, so it distinguishes nothing an operator wants to know.
  LANE 5  the honest half. Where nothing will merge, the route says so with a stated reason -- so
          the `false` side is right and only the `true` side over-promises.

The prose the operator actually reads is the drawer's, not the JSON's:
`TaskDetailDrawer.tsx:66-79` renders **"Approving writes to your repository: it cherry-picks <sha>
from <branch> into <main>"** -- a claim in the indicative about what approval will do, with no
clause anywhere saying the clean-merge question is asked later. LANE 1 asserts against the fields
that sentence is built from, since a headless drive cannot read the browser.

Operator surface only, over HTTP, against a real repository. Creates its own project in a fresh
temporary directory and never touches an existing one.

    AW_HUB=http://127.0.0.1:8011 py -3.11 scripts/drive/t_f156_preview_promises_the_merge.py
"""

import os
import subprocess
import sys
import tempfile
import time

from aw import api

VERDICTS = []
ROOT = ""
P = ""

ORDER = ["assigned", "in_progress", "completed", "under_review", "approved"]


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 78)
    print(label)
    print("=" * 78)


def git(*args, root=None):
    done = subprocess.run(
        ["git", *args], cwd=root or ROOT, capture_output=True, text=True, check=False
    )
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def must(*args, root=None):
    code, out, err = git(*args, root=root)
    if code != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {err or out}")
    return out


def walk_to(task_id, target):
    """Drive a task by hand to `target`, from wherever it currently is.

    The operator's only route through the lifecycle. Stops at the named status rather than running
    to `approved`, because the whole point of LANE 1 is to read the drawer at the moment the
    approve control is reachable and before it is pressed.
    """
    code, body = api("GET", f"/projects/{P}/tasks/{task_id}")
    current = (body or {}).get("status") if isinstance(body, dict) else None
    start = ORDER.index(current) + 1 if current in ORDER else 0
    code, body = 0, None
    for status_name in ORDER[start : ORDER.index(target) + 1]:
        code, body = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": status_name})
        if code != 200:
            return code, body
    return code, body


def preview(task_id):
    code, body = api("GET", f"/projects/{P}/tasks/{task_id}/integration-preview")
    if code != 200:
        raise SystemExit(f"the preview route did not answer: {code} {body}")
    return body


def refusal_of(body):
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return detail
    return {"message": str(detail if detail is not None else body)}


def record_evidence(identifier, summary, task_id):
    """The operator recording an observation of whatever the checkout is standing on.

    No `locator`, deliberately -- same reason as the F155 harness: a locator naming a commit sends
    `read_footprint` through `_branch_at`, which answers `""` for a commit that is not exactly one
    branch's tip.
    """
    code, recorded = api(
        "POST",
        f"/projects/{P}/project/spec/evidence",
        {"identifier": identifier, "summary": summary, "task_id": task_id},
    )
    if code != 201:
        raise SystemExit(f"could not record evidence: {code} {recorded}")
    return recorded


def make_project():
    global ROOT, P
    ROOT = tempfile.mkdtemp(prefix="aw-f156-")
    must("init", "-q")
    must("config", "user.email", "drive@example.com")
    must("config", "user.name", "Drive")
    must("checkout", "-q", "-b", "main")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    must("add", "README.md")
    must("commit", "-q", "-m", "base")

    code, created = api("POST", "/projects/open", {"path": ROOT, "name": "f156-drive"})
    if code not in (200, 201):
        raise SystemExit(f"could not open the project: {code} {created}")
    P = created["id"]
    globals()["P"] = P
    code, saved = api("PUT", f"/projects/{P}/settings", {"main_branch": "main"})
    if code != 200:
        raise SystemExit(f"could not set the main branch: {code} {saved}")
    print(f"  project {P} at {ROOT}")
    return P


def make_document(path, requirements):
    code, created = api(
        "POST", f"/projects/{P}/project/documents", {"path": path, "title": "F156 drive"}
    )
    if code != 201:
        raise SystemExit(f"could not create the document: {code} {created}")
    code, saved = api(
        "PUT",
        f"/projects/{P}/project/documents/{path}/content",
        {
            "document": {
                "schema_version": 1,
                "kind": "change-spec",
                "title": "F156 drive",
                "requirements": requirements,
            }
        },
    )
    if code != 200:
        raise SystemExit(f"could not save the document: {code} {saved}")
    return created["id"]


def make_task(title, requirement_ids=None):
    body = {"title": title}
    if requirement_ids:
        body["requirement_ids"] = requirement_ids
    code, created = api("POST", f"/projects/{P}/tasks", body)
    if code != 201:
        raise SystemExit(f"could not create the task: {code} {created}")
    return created["id"]


def commit_on(branch, path, content, message, base="main"):
    """One commit on its own branch, cut from `base`. Leaves the checkout on `branch`."""
    must("checkout", "-q", base)
    must("checkout", "-q", "-b", branch)
    with open(os.path.join(ROOT, path), "w", encoding="utf-8") as handle:
        handle.write(content)
    must("add", path)
    must("commit", "-q", "-m", message)
    return must("rev-parse", "HEAD")


def main():
    step("SETUP -- a fresh project, a fresh repository, two requirements")
    make_project()
    make_document(
        "spec/changes/f156/spec.html",
        [
            {"key": "alpha", "statement": "It ledgers", "modal": "MUST"},
            {"key": "beta", "statement": "It reports", "modal": "MUST"},
        ],
    )

    conflicted = make_task("Land the ledger", ["FR-1"])
    judged = commit_on("work/ledger", "ledger.py", "TOTAL = 1\n", "the ledger")
    record_evidence("FR-1", "ran the ledger tests", conflicted)

    # The conflict: the same file, changed differently, landed on main first. Nothing about the
    # task changes -- the operator never touched it, and the drawer is about to be asked anyway.
    must("checkout", "-q", "main")
    with open(os.path.join(ROOT, "ledger.py"), "w", encoding="utf-8") as handle:
        handle.write("TOTAL = 2\n")
    must("add", "ledger.py")
    must("commit", "-q", "-m", "someone else's ledger")

    code, body = walk_to(conflicted, "under_review")
    if code != 200:
        raise SystemExit(f"could not reach under_review: {code} {body}")
    print(f"  task {conflicted} at under_review, commit {judged[:12]} conflicts with main")

    step("LANE 1 -- the drawer, read where the operator reads it: beside the approve control")
    before = preview(conflicted)
    print(f"\n  {before}\n")
    check("the route answers at all", isinstance(before, dict), str(before)[:120])
    check(
        "it names exactly the commit that is about to be refused",
        [t.get("commit_sha") for t in before.get("targets") or []] == [judged],
        str(before.get("targets"))[:200],
    )
    check(
        "it says the merge WILL happen",
        before.get("will_merge") is True,
        repr(before.get("will_merge")),
    )
    check(
        "and it offers no reason to doubt it",
        before.get("reason") == "",
        repr(before.get("reason")),
    )
    # The three fields the drawer's sentence is built from (TaskDetailDrawer.tsx:66-79). A headless
    # drive cannot read the browser, so assert the sentence is composable and unqualified.
    check(
        "the drawer therefore renders the amber 'it cherry-picks <sha> from <branch> into <main>'",
        bool(before.get("main_branch"))
        and bool((before.get("targets") or [{}])[0].get("source_branch")),
        f"main_branch={before.get('main_branch')!r} "
        f"source_branch={(before.get('targets') or [{}])[0].get('source_branch')!r}",
    )

    step("LANE 2 -- the gate, same instant, same commit")
    code, body = api("PATCH", f"/projects/{P}/tasks/{conflicted}", {"status": "approved"})
    detail = refusal_of(body)
    message = str(detail.get("message") or "")
    print(f"\n  {code} {message}\n")
    check("approval is REFUSED", code == 409, str(code))
    check(
        "it is the gate, not the status machine",
        detail.get("code") == "gate_unsatisfied",
        repr(detail.get("code")),
    )
    check("the refusal is about a conflict", "conflict" in message.lower(), message[:160])
    check(
        "over the very commit the preview promised",
        judged[:12] in message,
        judged[:12],
    )
    check(
        "so preview and gate disagree, about one commit, at one moment",
        before.get("will_merge") is True and code == 409,
        f"will_merge={before.get('will_merge')} approve={code}",
    )
    code, after_refusal = api("GET", f"/projects/{P}/tasks/{conflicted}")
    check(
        "and the task did not move",
        (after_refusal or {}).get("status") == "under_review",
        str((after_refusal or {}).get("status")),
    )

    step("LANE 3 -- the drawer again, now that the gate has answered")
    after = preview(conflicted)
    print(f"\n  {after}\n")
    check(
        "the drawer still promises the merge, having been contradicted",
        after.get("will_merge") is True and after.get("reason") == "",
        f"will_merge={after.get('will_merge')!r} reason={after.get('reason')!r}",
    )
    check(
        "nothing in it changed at all",
        after == before,
        "identical" if after == before else str(after)[:200],
    )

    step("LANE 5 -- the honest half: where nothing will merge, it says so")
    silent = make_task("Nothing to merge")
    code, body = walk_to(silent, "under_review")
    if code != 200:
        raise SystemExit(f"could not reach under_review on the empty task: {code} {body}")
    empty = preview(silent)
    print(f"\n  {empty}\n")
    check(
        "will_merge is false where there is no target",
        empty.get("will_merge") is False,
        repr(empty.get("will_merge")),
    )
    check(
        "and the false answer carries a stated reason",
        bool(empty.get("reason")),
        repr(empty.get("reason")),
    )

    step("LANE 4 -- the contrast: `true` also means the merge really will happen")
    clean = make_task("Land the report", ["FR-2"])
    report_sha = commit_on("work/report", "report.py", "ROWS = 1\n", "the report")
    record_evidence("FR-2", "ran the report tests", clean)
    must("checkout", "-q", "main")
    code, body = walk_to(clean, "under_review")
    if code != 200:
        raise SystemExit(f"could not reach under_review on the clean task: {code} {body}")

    clean_preview = preview(clean)
    print(f"\n  {clean_preview}\n")
    check(
        "the clean task's preview is byte-identical in the fields that matter",
        clean_preview.get("will_merge") is True and clean_preview.get("reason") == "",
        f"will_merge={clean_preview.get('will_merge')!r} reason={clean_preview.get('reason')!r}",
    )

    code, approved = api("PATCH", f"/projects/{P}/tasks/{clean}", {"status": "approved"})
    check("and THIS one approves", code == 200, f"{code} {str(approved)[:200]}")
    if code == 200:
        # `/integrations`, plural -- the singular is a 404 whose body has no rows in it either,
        # which a harness that only reads the body cannot tell from an honest empty history.
        code, history = api("GET", f"/projects/{P}/tasks/{clean}/integrations")
        rows = (history or {}).get("integrations") or []
        check(
            "the integration history route answers",
            code == 200,
            f"{code} {str(history)[:160]}",
        )
        check(
            "its work really did reach main",
            any(row.get("outcome") == "merged" for row in rows),
            str(rows)[:220],
        )
        merged_head = must("rev-parse", "main")
        check(
            "and main moved",
            merged_head != must("rev-parse", "main~1"),
            f"{merged_head[:12]} carries {report_sha[:12]}'s content",
        )
    check(
        "THE FINDING: one `will_merge: true` covered a refusal and a merge, and said "
        "nothing to tell them apart",
        before.get("will_merge") == clean_preview.get("will_merge")
        and before.get("reason") == clean_preview.get("reason"),
        f"conflicting={before.get('will_merge')!r}/{before.get('reason')!r} "
        f"clean={clean_preview.get('will_merge')!r}/{clean_preview.get('reason')!r}",
    )

    step("VERDICT")
    bad = [v for v in VERDICTS if not v[1]]
    for label, ok, _detail in VERDICTS:
        print(f"  [{'OK ' if ok else 'BAD'}] {label}")
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} checks passed")
    print(f"  project {P} at {ROOT} -- left in place for inspection")
    return 1 if bad else 0


if __name__ == "__main__":
    start = time.time()
    try:
        code = main()
    finally:
        print(f"\n  ({time.time() - start:.1f}s)")
    sys.exit(code)
