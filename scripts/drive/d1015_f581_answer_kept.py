"""Acceptance drive for F581: a worker's answer is kept on its firing.

Before: a manager firing kept a count line ("2 facts stored, 0 dropped") and usage, never what the
model answered, so a wrong judgement could not be read afterwards. After: the firing in
GET /manager/activity carries the answer.

  py -3.11 scripts/drive/d1015_f581_answer_kept.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). One Haiku distillation. Exit 1 on any
fail.
"""

import importlib.util
import sys
import time

import pathlib

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-distillation"
TEXT = "Kickoff with Acme, 2026-10-02.\nDana: the refund limit without approval is 437 euros.\n"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(name):
    project = e2e.cmd_setup(name)
    runner = e2e.call(
        "POST", f"/projects/{project}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU}
    )
    e2e.call(
        "PATCH",
        f"/projects/{project}/manager/jobs/{JOB}",
        {"enabled": True, "runner_id": runner["id"]},
    )
    source = e2e.call(
        "POST",
        f"/projects/{project}/vault/sources",
        {"name": "Acme kickoff", "type": "transcript", "content": TEXT},
    )["id"]
    firing, end = None, time.time() + 240
    while firing is None and time.time() < end:
        listed = e2e.call("GET", f"/projects/{project}/manager/activity?job={JOB}")
        firing = next(
            (f for f in listed["firings"] if (f.get("subject") or {}).get("source") == source), None
        )
        time.sleep(3)
    e2e.request("PATCH", f"/projects/{project}/manager/jobs/{JOB}", {"enabled": False})
    check("the distillation fires", firing is not None)
    answer = (firing or {}).get("answer")
    check("the firing keeps the model's answer", isinstance(answer, str) and bool(answer), repr(answer)[:200])
    check(
        "the answer is what the model said about the source",
        isinstance(answer, str) and "437" in answer,
        repr(answer)[:300],
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
