"""Row 17 INTEGRATION, driven on top of Row 16's two genuinely conflicting task branches.

alpha and beta each completed a task whose branch edits calc.py. Approving one should
reach main. Approving the other should hit a real conflict -- and the question is whether
the operator is told what to do about it.
"""

import json
import os
import time

from aw import api, show

P = os.environ.get("AW_PROJECT") or "proj-dc4d43543bea"
A = os.environ.get("AW_TASK_A")
B = os.environ.get("AW_TASK_B")


def step(label):
    print("\n" + "=" * 70)
    print(label)
    print("=" * 70)


def patch(task_id, body):
    return api("PATCH", f"/projects/{P}/tasks/{task_id}", body)


def main():
    step("0. Settings: which branch does integration target?")
    show("settings", *api("GET", f"/projects/{P}/settings"), limit=2000)

    step("1. Integration preview for BOTH tasks, before either is approved")
    for name, tid in (("alpha", A), ("beta", B)):
        show(f"preview {name}", *api("GET", f"/projects/{P}/tasks/{tid}/integration-preview"), limit=2500)

    step("2. under_review -> approved for alpha (the first one in)")
    show("alpha under_review", *patch(A, {"status": "under_review"}), limit=900)
    show("alpha approved", *patch(A, {"status": "approved"}), limit=2500)
    time.sleep(4)
    show("alpha integrations", *api("GET", f"/projects/{P}/tasks/{A}/integrations"), limit=2500)

    step("3. Now beta -- its branch touches the same lines alpha just merged")
    show("beta preview (after alpha merged)", *api("GET", f"/projects/{P}/tasks/{B}/integration-preview"), limit=2500)
    show("beta under_review", *patch(B, {"status": "under_review"}), limit=900)
    show("beta approved", *patch(B, {"status": "approved"}), limit=2500)
    time.sleep(4)
    show("beta integrations", *api("GET", f"/projects/{P}/tasks/{B}/integrations"), limit=3000)

    step("4. What does the task itself say now?")
    for name, tid in (("alpha", A), ("beta", B)):
        c, b = api("GET", f"/projects/{P}/tasks/{tid}")
        print(f"--- {name} [{c}] status={b.get('status')} latest_integration=")
        print(json.dumps(b.get("latest_integration"), indent=1))

    step("5. Retry beta's integration")
    show("beta retry", *api("POST", f"/projects/{P}/tasks/{B}/integrations/retry", {}), limit=2500)
    time.sleep(3)
    show("beta integrations after retry", *api("GET", f"/projects/{P}/tasks/{B}/integrations"), limit=3000)

    step("6. Conflicts endpoint after the merge")
    show("conflicts", *api("GET", f"/projects/{P}/worktrees/conflicts"), limit=2500)


if __name__ == "__main__":
    main()
