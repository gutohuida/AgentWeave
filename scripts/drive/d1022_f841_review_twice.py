"""Acceptance drive for F841/F842: "Look into it" pressed twice runs one review, and the answer lands.

Before: two concurrent POST .../vault/reports/<id>/review both answered 202 and spawned two paid
reviews; the second recorded a `failed` firing "the outcome could not be stored (Report ... is
answered, not pending.)". After: one 202, one 409 "already being looked into", one firing.

  py -3.11 scripts/drive/d1022_f841_review_twice.py <project-id>

On a scratch Hub that `e2e.py hub-up` started. One real Haiku review. The pending report is seeded
through the product's own `vault.add_report` (filing one over the API needs an agent run token).
"""

import importlib.util
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("e2e", ROOT / ".claude" / "skills" / "e2e-loop" / "e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)
sys.path.insert(0, str(ROOT / "hub"))
from hub import vault  # noqa: E402

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(project):
    base = f"/projects/{project}"
    root = pathlib.Path(
        e2e.ro().execute("select working_directory from projects where id=?", (project,)).fetchone()[0]
    )
    status, runner = e2e.request(
        "POST", f"{base}/runners",
        {"name": "reviewer", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
    )
    check("a Haiku runner was made", status == 201, str(status))
    status, _ = e2e.request(
        "PATCH", f"{base}/manager/jobs/vault-reports", {"enabled": True, "runner_id": runner["id"]}
    )
    check("the reports job is on", status == 200, str(status))
    status, source = e2e.request(
        "POST", f"{base}/vault/sources",
        {"name": "Refund policy", "type": "rules", "content": "Dana: the refund limit without approval is 300 euros.\n"},
    )
    check("a source was added", status == 201, str(status))
    private = pathlib.Path(e2e.request("GET", f"{base}/vault/settings")[1]["effective_private_location"])
    fact = vault.add_fact(
        root, private, claim="The refund limit without approval is 300 euros.",
        citations=[{"source": source["id"], "quote": "the refund limit without approval is 300 euros.",
                    "line_start": 1, "line_end": 1}],
        visibility=source["visibility"], made_by={"job": "vault-distillation", "model": "seed"},
    )
    report = vault.add_report(root, private, entry_id=fact["id"], message="Is the limit really 300?",
                              reporter={"agent": "helper"})["id"]
    url = f"{base}/vault/reports/{report}/review"
    codes = []
    first = threading.Thread(target=lambda: codes.append(e2e.request("POST", url, {})))
    first.start()
    time.sleep(2)  # the review is a ~10 s Haiku turn; the second press lands inside it
    second = e2e.request("POST", url, {})
    first.join()
    check("the first press is accepted", codes and codes[0][0] == 202, str(codes[:1]))
    check("the second press is refused 409 naming why", second[0] == 409 and "already being looked into" in second[1].get("detail", ""), str(second))
    for _ in range(40):  # the 202 comes back before the background review ends
        time.sleep(3)
        firings = [
            f for f in e2e.request("GET", f"{base}/manager/activity")[1].get("firings", [])
            if f.get("job") == "vault-reports" and (f.get("subject") or {}).get("report") == report
        ]
        if firings:
            break
    time.sleep(15)  # a second, wrongly spawned review would finish inside this
    firings = [
        f for f in e2e.request("GET", f"{base}/manager/activity")[1].get("firings", [])
        if f.get("job") == "vault-reports" and (f.get("subject") or {}).get("report") == report
    ]
    check("exactly one firing", len(firings) == 1, str([(f["outcome"], f["detail"]) for f in firings]))
    check("no failed firing", all(f["outcome"] != "failed" for f in firings))
    after = [r for r in e2e.request("GET", f"{base}/vault/reports")[1]["reports"] if r["id"] == report][0]
    check("the report left pending", after["status"] != "pending", after["status"])
    print("FAILURES:" if failures else "ALL PASS", failures)


if __name__ == "__main__":
    main(sys.argv[1])
