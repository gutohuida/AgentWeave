"""Row 17 INTEGRATION -- approving work and watching it reach (or fail to reach) the main branch.

Never driven before 2026-08-30. The previous version of this file assumed row 16's two conflicting
task branches were enough, and they are not: integration cherry-picks *the commit named by each
accepted piece of evidence* (`api/v1/tasks.py:1041-1064`), so a task with no evidence previews
`will_merge: false, "no accepted evidence names a commit"` and approving it merges nothing. It
would have driven two no-ops and reported a clean run.

So this file establishes the precondition it needs rather than assuming it, and drives both halves:

  A. the CONTRAST -- a task with a real branch and no accepted evidence. The preview must say so,
     in a sentence, before the operator approves.
  B. the REAL PATH -- two tasks whose evidence carries a git footprint naming their branch head,
     accepted by the operator, whose branches edit THE SAME FILE. The first should reach main. The
     second cannot, and the whole question of row 17 is whether the operator is told why, in terms
     they can act on, or whether the approval silently does nothing.

AW_TASK_A and AW_TASK_B are the conflicting pair; AW_TASK_C is the contrast, and is optional.
Real surface only. No row inserts. Nothing is approved that this file has not first shown a preview
for.
"""

import json
import os
import subprocess
import sys
import time

from aw import api

P = os.environ.get("AW_PROJECT") or ""
A = os.environ.get("AW_TASK_A") or ""
B = os.environ.get("AW_TASK_B") or ""
C = os.environ.get("AW_TASK_C") or ""

VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok), detail))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def step(label):
    print("\n" + "=" * 74)
    print(label)
    print("=" * 74)


def blob(x, limit=1400):
    return json.dumps(x, indent=1, default=str)[:limit]


def task(task_id):
    c, b = api("GET", f"/projects/{P}/tasks/{task_id}")
    return b if c == 200 else {}


def preview(task_id):
    c, b = api("GET", f"/projects/{P}/tasks/{task_id}/integration-preview")
    return c, b


def integrations(task_id):
    c, b = api("GET", f"/projects/{P}/tasks/{task_id}/integrations")
    return c, (b.get("integrations", []) if isinstance(b, dict) else [])


def repo_root():
    c, rows = api("GET", "/projects")
    row = next((x for x in (rows or []) if x.get("id") == P), None) if isinstance(rows, list) else None
    return (row or {}).get("working_directory")


def git(*args):
    """Read the operator's repository directly. The API's word for what reached main is a claim;
    the repository is the fact, and row 17 is the one row where the difference is the subject."""
    root = repo_root()
    if not root:
        return ""
    out = subprocess.run(
        ["git", "-C", root, *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return (out.stdout or "").strip()


def evidence_for(task_id):
    c, b = api("GET", f"/projects/{P}/project/spec/evidence")
    rows = b.get("evidence", []) if isinstance(b, dict) else []
    return [e for e in rows if e.get("task_id") == task_id]


def wait_for_integration(task_id, limit=60):
    """Approval writes the repository; the record may land a beat later. Polling for it is not the
    same as sleeping for it -- a fixed sleep reports 'nothing happened' for something that had not
    happened *yet*, which is a wrong verdict rather than a slow one."""
    t0 = time.time()
    while time.time() - t0 < limit:
        c, rows = integrations(task_id)
        if rows:
            return rows
        time.sleep(2)
    return []


def preflight():
    step("PRE. Preconditions this file's assertions depend on")
    if not P or not A or not B:
        sys.exit("set AW_PROJECT, AW_TASK_A and AW_TASK_B")
    if A == B:
        sys.exit("AW_TASK_A and AW_TASK_B must differ -- the second is the one that conflicts")
    c, st = api("GET", f"/projects/{P}/settings")
    if c != 200:
        sys.exit(f"cannot read settings: {c}")
    main = st.get("main_branch")
    if not main:
        sys.exit("the project has no main branch configured; nothing can be integrated into it")
    root = repo_root()
    if not root or not os.path.isdir(root):
        sys.exit(f"project working directory {root!r} is not on this machine")
    for tid in (A, B):
        t = task(tid)
        if not t:
            sys.exit(f"task {tid} does not exist on {P}")
        if t.get("status") not in ("completed", "under_review"):
            sys.exit(
                f"task {tid} is {t.get('status')!r}; this file starts from finished work "
                "(`completed`), which is what an operator approves"
            )
        ev = evidence_for(tid)
        shas = {(e.get("footprint") or {}).get("commit_sha") for e in ev}
        shas.discard(None)
        if not shas:
            sys.exit(
                f"task {tid} has {len(ev)} evidence rows and none carries a git footprint naming a "
                "commit -- approving it would merge nothing and this file would drive a no-op"
            )
        print(f"  [OK ] {tid}: {t.get('status')}, evidence naming {sorted(shas)}")
    print(f"  [OK ] main branch {main!r} at {git('rev-parse', '--short', main)} in {root}")


def accept_evidence(task_id):
    """The operator's own decision, through the operator's route. `record_evidence` from an agent
    lands undecided; nothing merges until somebody accepts it, which is the gate working."""
    accepted = []
    for e in evidence_for(task_id):
        c, b = api(
            "POST",
            f"/projects/{P}/project/spec/evidence/{e['id']}/decision",
            {"decision": "accepted", "reason": "row 17 drive"},
        )
        print(f"    decide {e['id']}: {c}")
        if c >= 300:
            print("      " + blob(b, 400))
        else:
            accepted.append(e["id"])
    return accepted


def approve(task_id, label):
    """`completed -> under_review -> approved`. The middle step is not skippable: the transition
    table refuses `completed -> approved` directly, which this asserts rather than assumes."""
    t = task(task_id)
    if t.get("status") == "completed":
        c1, b1 = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": "approved"})
        check(
            f"{label}: completed -> approved is refused, and the refusal names the way through",
            c1 == 409 and "under_review" in str(b1),
            f"{c1} {str(b1)[:160]}",
        )
        c2, b2 = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": "under_review"})
        check(f"{label}: completed -> under_review accepted", c2 == 200, f"{c2} {str(b2)[:200]}")
        if c2 >= 300:
            return None
    c3, b3 = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": "approved"})
    print(f"    approve {label}: {c3}")
    if c3 >= 300:
        print("      " + blob(b3, 700))
    return c3, b3


def main():
    preflight()
    main_branch = api("GET", f"/projects/{P}/settings")[1].get("main_branch")
    before = git("rev-parse", main_branch)

    if C:
        step("A. The CONTRAST -- a finished task whose evidence names no commit")
        c, pv = preview(C)
        print("  " + blob(pv, 600))
        check("the preview answers 200", c == 200, str(c))
        check(
            "it says it will not merge, rather than saying nothing",
            pv.get("will_merge") is False,
            repr(pv.get("will_merge")),
        )
        check(
            "and the reason names the missing thing, not just 'no'",
            "evidence" in str(pv.get("reason", "")).lower(),
            repr(pv.get("reason")),
        )

    step("B1. Accept the evidence on both tasks, as the operator")
    for label, tid in (("A", A), ("B", B)):
        print(f"  {label} = {tid}")
        got = accept_evidence(tid)
        check(f"{label}: at least one piece of evidence accepted", bool(got), str(got))

    step("B2. Preview both, now that the evidence is accepted")
    previews = {}
    for label, tid in (("A", A), ("B", B)):
        c, pv = preview(tid)
        previews[label] = pv
        print(f"  {label} " + blob(pv, 700))
        check(f"{label}: the preview now says it WILL merge", pv.get("will_merge") is True, blob(pv, 200))
        check(
            f"{label}: and names the commit it is about to write",
            bool(pv.get("targets")),
            str(pv.get("targets"))[:200],
        )

    step("B3. Approve A -- the first one in. It should reach main.")
    approve(A, "A")
    rows_a = wait_for_integration(A)
    print("  " + blob(rows_a, 1600))
    check("A: an integration was recorded", bool(rows_a), str(len(rows_a)))
    # The row's key is `outcome`, not `status` (`api/v1/tasks.py:1094-1110`). Reading `status`
    # returned `[None]` for a row that plainly said `"outcome": "merged"` -- the drive's recurring
    # harness defect, guessing a shape with the real one printed two lines above it.
    a_ok = any(r.get("outcome") == "merged" for r in rows_a)
    check("A: it reports a merge", a_ok, str([r.get("outcome") for r in rows_a]))
    after_a = git("rev-parse", main_branch)
    check("A: the main branch actually moved", after_a != before, f"{before[:8]} -> {after_a[:8]}")
    # The API's word for "merged" and the repository agreeing is the whole point of the row.
    sha_a = next(
        ((e.get("footprint") or {}).get("commit_sha") for e in evidence_for(A) if e.get("footprint")),
        None,
    )
    check(
        "A: the commit its evidence named is now an ancestor of main",
        bool(sha_a)
        and subprocess.run(
            ["git", "-C", repo_root(), "merge-base", "--is-ancestor", sha_a, main_branch],
            capture_output=True,
        ).returncode
        == 0,
        f"{sha_a} vs {main_branch}",
    )
    loc_a = next((e.get("locator") for e in evidence_for(A) if e.get("locator")), "")
    if loc_a:
        check(
            f"A: {loc_a} is readable on {main_branch}",
            bool(git("show", f"{main_branch}:{loc_a}")),
            git("show", f"{main_branch}:{loc_a}")[:120].replace(chr(10), " | "),
        )

    step("B4. Approve B -- its branch touches the same file A just merged")
    # The first version of this section expected an integration ATTEMPT and a failure record. The
    # product is better than that: `requirement_gate._check_mergeable` runs a real `would_conflict`
    # probe before the transition, so the approval is refused and the repository is never touched.
    # Asserting the attempt made a correct refusal read as "a silent nothing".
    res_b = approve(B, "B")
    code_b, body_b = res_b if res_b else (0, {})
    detail_b = body_b.get("detail") if isinstance(body_b, dict) else {}
    detail_b = detail_b if isinstance(detail_b, dict) else {"message": str(detail_b)}
    check("B: approval is REFUSED rather than attempted", code_b == 409, str(code_b))
    check(
        "B: the refusal is the gate's, with its own code",
        detail_b.get("code") == "gate_unsatisfied",
        repr(detail_b.get("code")),
    )
    unmergeable = detail_b.get("unmergeable") or []
    check(
        "B: it names the branch and the commit that will not merge",
        bool(unmergeable) and bool(unmergeable[0].get("commit_sha")),
        str(unmergeable)[:300],
    )
    check(
        "B: it names the conflicting PATH, not just the fact of a conflict",
        any(u.get("paths") for u in unmergeable),
        str([u.get("paths") for u in unmergeable]),
    )
    # F155: this used to assert the message contained both "resolve" and "approve", lowercased.
    # That was an assertion about *one* remedy, and the product now has two — the evidence route's
    # sentence deliberately does not say "approve", because approving again is precisely what does
    # not clear it there. So ask what the requirement now asks: does the message name the commit it
    # judged, and does it state a remedy the reader can actually take?
    message_b = str(detail_b.get("message", ""))
    judged_b = str((unmergeable[0] or {}).get("commit_sha") or "")[:12] if unmergeable else ""
    check(
        "B: the sentence names the commit it judged, not only the structured half",
        bool(judged_b) and judged_b in message_b,
        f"{judged_b} vs {message_b[:200]!r}",
    )
    named_by_evidence = bool((unmergeable[0] or {}).get("named_by_evidence")) if unmergeable else 0
    if named_by_evidence:
        remedy_b = (
            "accepted evidence" in message_b.lower()
            and "recorded from a checkout of" in message_b.lower()
        )
    else:
        remedy_b = (
            "resolve" in message_b.lower() and "approve" in message_b.lower()  # the tip route
        )
    check(
        "B: and states a remedy that clears it on the route it was refused on",
        remedy_b,
        f"named_by_evidence={named_by_evidence}: {message_b[:260]!r}",
    )
    after_b = git("rev-parse", main_branch)
    check(
        "B: the repository was NOT touched by the refused approval",
        after_b == after_a,
        f"{after_a[:8]} -> {after_b[:8]}",
    )
    c_rows_b, rows_b = integrations(B)
    check(
        "B: and no integration row was written for an integration that never ran",
        rows_b == [],
        str(rows_b)[:200],
    )
    # F141. The gate has just probed git and knows this branch does not merge. Nothing persists
    # that: the task carries no record, `/integrations` is empty, and the preview beside the
    # approve control goes back to saying it will merge. Asserted in the direction the product
    # actually behaves, so the day it is fixed this line goes red and says so.
    c_pv, pv_b = preview(B)
    check(
        "F141: the preview still reads will_merge=true for the branch just refused as unmergeable",
        pv_b.get("will_merge") is True,
        blob(pv_b, 200),
    )
    print(f"  main: {before[:8]} -> {after_a[:8]} -> {after_b[:8]}")

    step("B5. What the tasks say afterwards")
    ta, tb = task(A), task(B)
    print(f"  A {A} status={ta.get('status')}")
    print("    latest_integration=" + blob(ta.get("latest_integration"), 700))
    check("A: it is approved", ta.get("status") == "approved", repr(ta.get("status")))
    check(
        "A: the task carries its integration outcome where the drawer reads it",
        (ta.get("latest_integration") or {}).get("outcome") == "merged",
        repr(ta.get("latest_integration")),
    )
    print(f"  B {B} status={tb.get('status')}")
    check(
        "B: it stays where it was, recoverable -- the refusal did not strand it",
        tb.get("status") == "under_review",
        repr(tb.get("status")),
    )

    step("B6. Retry B's integration")
    c, b = api("POST", f"/projects/{P}/tasks/{B}/integrations/retry", {})
    print(f"  retry: {c}")
    print("  " + blob(b, 1200))
    check("B: retry is refused for a task that was never approved", c == 409, str(c))
    check(
        "B: and the refusal says which status it needs, rather than 'cannot retry'",
        "approved" in str(b).lower() and "under_review" in str(b),
        str(b)[:220],
    )

    step("B7. The conflicts endpoint after the merge")
    c, conf = api("GET", f"/projects/{P}/worktrees/conflicts")
    print(f"  {c}: " + blob(conf, 1200))

    step("VERDICTS")
    bad = [v for v in VERDICTS if not v[1]]
    for label, ok, detail in VERDICTS:
        print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    print(f"\n  {len(VERDICTS) - len(bad)}/{len(VERDICTS)} held")


if __name__ == "__main__":
    main()
