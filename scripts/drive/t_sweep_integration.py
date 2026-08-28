"""Full-surface sweep, part 6: what approving a task actually does.

Row 17 of the coverage matrix, and the one the findings file calls the most consequential thing the
product does — approval is what merges work to the main branch (F9). It was marked *not reached* in
the first pass because it looked like it needed an agent turn. It does not: an operator can walk a
task the whole way, and the interesting question is what the Hub does at the last step when there is
no committed work behind the task at all.

That is the case worth driving. A task approved with nothing to merge is not a contrived input — it
is what an operator produces by moving a card while the agent's work is still in its worktree, or
after a run failed. What the Hub does then is either a clean refusal or a silent no-op, and only one
of those is safe.

**It does neither, and the answer is better than both.** The approval succeeds and records an
integration whose outcome is `skipped`, with its reason in words — *"no accepted evidence names a
commit, so there is nothing to merge"* — and the same sentence is available from
`integration-preview` **before** approving, with `will_merge: false`. Nothing is claimed to have
merged, and nothing is refused for a state the operator may have reached deliberately.

So this file is kept as a regression guard for behaviour that held, not because it found a defect.
A sweep that records only defects describes a different product from the one being driven.

Route names matter here and cost a wrong reading first time: it is `…/tasks/{id}/integrations` and
`…/integrations/retry`, both plural, and the *task* row carries no integration field at all — the
record lives in its own table, which is why reading `task.integration_state` shows `None` for a task
whose integration was correctly skipped.

Run: AW_PROJECT=<proj> AW_KEY=<key> py -3.11 scripts/drive/t_sweep_integration.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import P, api  # noqa: E402

RESULTS = []


def step(label, method, path, body=None, expect=None):
    code, out = api(method, path, body)
    ok = expect is None or code in (expect if isinstance(expect, tuple) else (expect,))
    detail = out.get("detail") if isinstance(out, dict) else None
    if isinstance(detail, dict):
        detail = detail.get("message")
    RESULTS.append((label, code, ok, detail if isinstance(detail, str) else None))
    print(f"  {label}: {code}{'' if ok else '   <-- UNEXPECTED'}")
    if isinstance(detail, str):
        print(f"      refusal: {detail[:240]}")
    elif not ok:
        print(f"      {json.dumps(out, default=str)[:300]}")
    return code, out


AGENT = f"integ-{int(time.time()) % 100000}"
api("POST", f"/projects/{P}/agents/register", {"name": AGENT, "contact_mode": "poll"})

print("=" * 78)
print("ROW 17 — approval, and what it does with nothing to merge")
print("=" * 78)

code, task = step("create a task", "POST", f"/projects/{P}/tasks",
                  {"title": "Integration probe"}, expect=(200, 201))
tid = task["id"]
print(f"      task {tid}")

step("assign it", "PATCH", f"/projects/{P}/tasks/{tid}", {"assignee": AGENT}, expect=200)
for status in ("in_progress", "completed", "under_review"):
    step(f"-> {status}", "PATCH", f"/projects/{P}/tasks/{tid}", {"status": status}, expect=200)

print()
print("--- could the operator have seen it coming, before approving?")
code, preview = step("integration preview", "GET",
                     f"/projects/{P}/tasks/{tid}/integration-preview", expect=200)
if isinstance(preview, dict):
    print(f"      will_merge={preview.get('will_merge')!r} "
          f"main_branch={preview.get('main_branch')!r} targets={preview.get('targets')}")
    print(f"      reason: {preview.get('reason')}")
    assert preview.get("will_merge") is False, "a task with no evidence must not claim it will merge"
    assert preview.get("reason"), "and it must say why"

print()
print("--- the operator approves work that has no commit behind it")
step("-> approved", "PATCH", f"/projects/{P}/tasks/{tid}", {"status": "approved"}, expect=200)

print()
print("--- what the approval recorded about the merge")
code, integrations = step("its integration record", "GET",
                          f"/projects/{P}/tasks/{tid}/integrations", expect=200)
rows = (integrations or {}).get("integrations", [])
for row in rows:
    print(f"      outcome={row.get('outcome')!r} target={row.get('target_branch')!r} "
          f"commit={row.get('commit_sha')!r} mechanism={row.get('mechanism')!r}")
    print(f"      reason: {row.get('reason')}")
assert rows, "approval recorded no integration attempt at all"
assert rows[0]["outcome"] == "skipped", f"expected a skipped integration, got {rows[0]['outcome']!r}"
assert rows[0]["commit_sha"] is None, "nothing should have been merged"
assert rows[0]["reason"], "a skipped integration has to say why"

step("retry it", "POST", f"/projects/{P}/tasks/{tid}/integrations/retry", expect=200)

print()
print("=" * 78)
bad = [r for r in RESULTS if not r[2]]
for label, code, ok, detail in bad:
    print(f"  UNEXPECTED  {label} -> {code}  {(detail or '')[:120]}")
print("row 17 held" if not bad else "row 17 has something to look at")
sys.exit(1 if bad else 0)
