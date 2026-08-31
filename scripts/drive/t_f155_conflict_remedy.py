"""F155 -- can a reader follow the conflict refusal to a merged outcome, using only what it said?

The finding, live 2026-08-30: approval was refused with *"Resolve the conflict on the branch, then
approve -- approving is what merges it."* The reviewer did exactly that, approved again, and got the
identical sentence back. On the evidence route that instruction is false: what integration merges is
the commit the accepted evidence names, so a resolution commit no evidence names changes nothing.
The next move was `git reset --hard` on a branch holding the only copy of an agent's work.

The unit tests prove the sentence composes. They cannot prove the thing that matters, which is
whether a person holding only the 409 can get to `merged`. So this file drives it:

  LANE 1  the refusal, on the evidence route. Read the sentence, and check it against the four
          things the requirement asks of it -- the commit, both branches distinctly, a remedy that
          is not "resolve it on the branch", and the acceptance clause.
  LANE 2  FOLLOW IT. Everything this lane does is derived from the refusal's own text: the branch
          it names is parsed out of the message, not out of the harness's own knowledge of the
          setup. If the sentence does not carry enough to act on, this lane cannot run.
  LANE 3  the old remedy, driven to prove it still does nothing -- the defect itself, so the fix
          cannot be mistaken for a behaviour change.
  LANE 4  the branch-tip route, whose sentence is deliberately the old one, because there it works.

Operator surface only, over HTTP, against a real repository. No agent turns, so no model is bound:
the whole population this refusal addresses is operator-facing. Creates its own project in a fresh
temporary directory and never touches an existing one.

    AW_HUB=http://127.0.0.1:8011 py -3.11 scripts/drive/t_f155_conflict_remedy.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time

from aw import api

VERDICTS = []
ROOT = ""
P = ""


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


def approve(task_id):
    """Drive a task to `approved` from wherever it currently is.

    A refused approval leaves the task at `under_review`, and re-driving from `assigned` is refused
    by the status machine instead -- a different refusal, with a plain-string detail. Getting this
    wrong reads as "the gate answered something odd" when the gate was never reached.
    """
    order = ["assigned", "in_progress", "completed", "under_review", "approved"]
    code, body = api("GET", f"/projects/{P}/tasks/{task_id}")
    current = (body or {}).get("status") if isinstance(body, dict) else None
    start = order.index(current) + 1 if current in order else 0
    code, body = 0, None
    for status_name in order[start:]:
        code, body = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": status_name})
        if code != 200:
            return code, body
    return code, body


def refusal_of(body):
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return detail
    return {"message": str(detail if detail is not None else body)}


def record_and_accept(identifier, summary, task_id=None):
    """The operator recording an observation of whatever the project checkout is standing on.

    No `locator`, deliberately: a locator naming a commit sends `read_footprint` through
    `_branch_at`, which answers `""` for a commit that is not exactly one branch's tip. The remedy
    the product states is about *where the recording is done from*, and this is what doing it from
    there looks like.
    """
    body = {"identifier": identifier, "summary": summary}
    if task_id:
        body["task_id"] = task_id
    code, recorded = api("POST", f"/projects/{P}/project/spec/evidence", body)
    if code != 201:
        raise SystemExit(f"could not record evidence: {code} {recorded}")
    return recorded


def make_project():
    global ROOT, P
    ROOT = tempfile.mkdtemp(prefix="aw-f155-")
    must("init", "-q")
    must("config", "user.email", "drive@example.com")
    must("config", "user.name", "Drive")
    must("checkout", "-q", "-b", "main")
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("base\n")
    must("add", "README.md")
    must("commit", "-q", "-m", "base")

    # `open`, not `create`: `create` refuses a directory that already exists, and this one has to
    # exist first because it is a repository with a main branch before the Hub ever sees it.
    code, created = api("POST", "/projects/open", {"path": ROOT, "name": "f155-drive"})
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
        "POST", f"/projects/{P}/project/documents", {"path": path, "title": "F155 drive"}
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
                "title": "F155 drive",
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


BRANCH_IN_REMEDY = re.compile(r"recorded from a checkout of ([^\s.,;]+)")
COMMIT_IN_MESSAGE = re.compile(r"The commit judged is ([0-9a-f]{7,40})")


def main():
    step("SETUP -- a fresh project, a fresh repository, one requirement, one task")
    make_project()
    make_document(
        "spec/changes/f155/spec.html",
        [{"key": "alpha", "statement": "It ledgers", "modal": "MUST"}],
    )
    task = make_task("Land the ledger", ["FR-1"])

    # The work, on a branch, and evidence recorded from a checkout of it.
    must("checkout", "-q", "-b", "work/ledger")
    with open(os.path.join(ROOT, "ledger.py"), "w", encoding="utf-8") as handle:
        handle.write("TOTAL = 1\n")
    must("add", "ledger.py")
    must("commit", "-q", "-m", "the ledger")
    judged = must("rev-parse", "HEAD")
    evidence = record_and_accept("FR-1", "ran the ledger tests", task_id=task)
    print(f"  evidence {evidence['id']} footprints {str(evidence.get('footprint'))[:160]}")

    # And the conflict: the same file, changed differently, landed on main first.
    must("checkout", "-q", "main")
    with open(os.path.join(ROOT, "ledger.py"), "w", encoding="utf-8") as handle:
        handle.write("TOTAL = 2\n")
    must("add", "ledger.py")
    must("commit", "-q", "-m", "someone else's ledger")
    main_head = must("rev-parse", "main")

    step("LANE 1 -- the refusal, read as a reader")
    code, body = approve(task)
    detail = refusal_of(body)
    message = str(detail.get("message") or "")
    print(f"\n  {message}\n")
    check("approval is REFUSED rather than attempted", code == 409, str(code))
    check(
        "it is the gate's refusal",
        detail.get("code") == "gate_unsatisfied",
        repr(detail.get("code")),
    )
    entry = (detail.get("unmergeable") or [{}])[0]
    check(
        "the entry says the commit came from evidence",
        entry.get("named_by_evidence") is True,
        str(entry)[:200],
    )
    check("the conflicting path is named", "ledger.py" in message, message[:120])
    check("the commit judged is IN THE SENTENCE", judged[:12] in message, judged[:12])
    check(
        "the branch the work would merge INTO is named",
        "main" in message,
        message[:120],
    )
    check(
        "the branch the commit was recorded ON is named, distinctly",
        "work/ledger" in message,
        message[:200],
    )
    check(
        "it does NOT tell the reader to resolve the conflict on the branch and approve",
        "Resolve the conflict on the branch" not in message,
        message[:200],
    )
    check(
        "it says who accepting belongs to",
        "grant an agent the capability to accept it" in message,
        message[-160:],
    )
    check(
        "the repository was NOT touched by the refused approval",
        must("rev-parse", "main") == main_head,
        main_head[:12],
    )

    step("LANE 2 -- follow the sentence, and nothing else")
    found = BRANCH_IN_REMEDY.search(message)
    check(
        "the sentence carries the branch to act on in a form a reader can extract",
        bool(found),
        repr(message[:200]) if not found else found.group(1),
    )
    if not found:
        print("  cannot follow a remedy that does not name where to act -- lane 2 stops here")
    else:
        branch = found.group(1)
        # Everything below is derived from the message. The harness does not consult its own
        # knowledge of which branch the work was on.
        must("checkout", "-q", branch)
        merged, out, err = git("merge", "main", "-m", "take main's ledger")
        if merged != 0:
            with open(os.path.join(ROOT, "ledger.py"), "w", encoding="utf-8") as handle:
                handle.write("TOTAL = 2\n")
            must("add", "ledger.py")
            must("commit", "-q", "-m", "resolve the ledger against main")
        resolved = must("rev-parse", "HEAD")
        check("the resolution is a new commit on that branch", resolved != judged, resolved[:12])

        # "record evidence naming the resolved commit ... recorded from a checkout of that branch"
        fresh = record_and_accept("FR-1", "re-ran after resolving the conflict")
        print_footprint = fresh.get("footprint") or {}
        check(
            "the fresh evidence footprints the resolved commit on that branch",
            print_footprint.get("commit_sha") == resolved
            and print_footprint.get("branch") == branch,
            json.dumps(print_footprint, default=str)[:200],
        )

        must("checkout", "-q", "main")
        code, body = approve(task)
        check(
            "THE POINT: following the sentence gets to approved",
            code == 200,
            str(code) + " " + str(body)[:200],
        )
        code, rows = api("GET", f"/projects/{P}/tasks/{task}/integrations")
        outcomes = [row.get("outcome") for row in (rows or {}).get("integrations", [])]
        check("integration recorded a merge", outcomes == ["merged"], str(outcomes))
        code, on_main, _ = git("merge-base", "--is-ancestor", resolved, "main")
        check("and the resolved commit is on the main branch", code == 0, resolved[:12])

    step("LANE 3 -- the OLD remedy, driven to prove it still does nothing")
    other = make_task("A second ledger", ["FR-1"])
    must("checkout", "-q", "-b", "work/second")
    with open(os.path.join(ROOT, "audit.py"), "w", encoding="utf-8") as handle:
        handle.write("AUDIT = 1\n")
    must("add", "audit.py")
    must("commit", "-q", "-m", "the audit")
    second_judged = must("rev-parse", "HEAD")
    record_and_accept("FR-1", "ran the audit tests", task_id=other)

    must("checkout", "-q", "main")
    with open(os.path.join(ROOT, "audit.py"), "w", encoding="utf-8") as handle:
        handle.write("AUDIT = 2\n")
    must("add", "audit.py")
    must("commit", "-q", "-m", "someone else's audit")

    code, body = approve(other)
    first_message = str(refusal_of(body).get("message") or "")
    check("the second task is refused too", code == 409, str(code))

    # Do what the old sentence said: resolve on the branch, approve again. Nothing else.
    must("checkout", "-q", "work/second")
    merged, _, _ = git("merge", "main", "-m", "take main's audit")
    if merged != 0:
        with open(os.path.join(ROOT, "audit.py"), "w", encoding="utf-8") as handle:
            handle.write("AUDIT = 2\n")
        must("add", "audit.py")
        must("commit", "-q", "-m", "resolve the audit against main")
    must("checkout", "-q", "main")

    code, body = approve(other)
    second_message = str(refusal_of(body).get("message") or "")
    check("it is refused again", code == 409, str(code))
    check(
        "F155 ITSELF: the old remedy returns the identical sentence",
        second_message == first_message and second_judged[:12] in second_message,
        f"identical={second_message == first_message}",
    )
    check(
        "so the product no longer gives that instruction on this route",
        "Resolve the conflict on the branch" not in second_message,
        second_message[:160],
    )

    step("LANE 4 -- the branch-tip route keeps the old sentence, because there it works")
    code, created = api(
        "POST",
        f"/projects/{P}/jobs",
        {
            "name": "f155-loop",
            "agent": "builder",
            "message": "work the queue",
            "cron": "0 2 * * *",
            "stop_when_queue_empties": True,
            # Both of these are creation-time and only creation-time, and the product says so
            # rather than letting a later PATCH look like it worked: "a loop declares at creation
            # whether its work needs evidence, and it cannot be changed afterwards", and "a task's
            # loop assignment is set at creation and cannot be changed afterwards". Two good
            # refusals that this harness earned by trying the wrong way round first.
            "work_needs_evidence": False,
        },
    )
    if code != 201 or not (created or {}).get("loop"):
        check(
            "a loop could be created for the branch-tip lane", False, f"{code} {str(created)[:200]}"
        )
    else:
        loop_id = created["loop"]["id"]
        check(
            "the loop declares at creation that its work needs no evidence",
            created["loop"].get("work_needs_evidence") is False,
            str(created["loop"])[:200],
        )

        code, attached = api(
            "POST", f"/projects/{P}/tasks", {"title": "Loop work", "loop_id": loop_id}
        )
        check("the task is on that loop", code == 201, f"{code} {str(attached)[:160]}")
        if code != 201:
            raise SystemExit("cannot drive the branch-tip lane without a loop task")
        tip_task = attached["id"]

        branch = f"agentweave/task/{tip_task}"
        must("checkout", "-q", "-b", branch)
        with open(os.path.join(ROOT, "ledger.py"), "w", encoding="utf-8") as handle:
            handle.write("TOTAL = 99\n")
        must("add", "ledger.py")
        must("commit", "-q", "-m", "the loop's work")
        must("checkout", "-q", "main")
        with open(os.path.join(ROOT, "ledger.py"), "w", encoding="utf-8") as handle:
            handle.write("TOTAL = 100\n")
        must("add", "ledger.py")
        must("commit", "-q", "-m", "and someone else again")

        code, body = approve(tip_task)
        tip_message = str(refusal_of(body).get("message") or "")
        print(f"\n  {tip_message}\n")
        if code == 409:
            check(
                "the branch-tip refusal keeps the sentence F155 was reported against",
                "Resolve the conflict on the branch" in tip_message,
                tip_message[:160],
            )
        else:
            check(
                "the branch-tip lane reached a conflict refusal at all",
                False,
                f"{code} {tip_message[:200]}",
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
