"""Acceptance drive for F587 + F617: a re-distilled fact keeps its id.

Before: pressing Distil again on a source deleted every earlier fact and wrote the same claims under
new ids, orphaning the decisions and spec requirements that cited them. After: a fact drawn again
from the same lines (same spans, quotes equal but for case, spacing and trailing punctuation) keeps
its id.

  py -3.11 scripts/drive/d1015_f587_redistil_keeps_ids.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Two Haiku distillations. A model that
quotes differently on the second pass churns that fact by design; the drive needs at least one fact
drawn from the same lines, and says so when there is none rather than passing. Exit 1 on any fail.
"""

import importlib.util
import json
import pathlib
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-distillation"
TEXT = (
    "Kickoff meeting with Acme Retail, 2026-10-02.\n"
    "\n"
    "Dana: customers may return goods within 30 days of delivery.\n"
    "Dana: the refund limit without manager approval is 437 euros.\n"
)
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def loose(quote):
    """A quote as the Hub compares it: case, runs of whitespace and trailing punctuation ignored
    (Haiku drops a sentence's final period on one pass and keeps it on the next)."""
    return " ".join(quote.split()).rstrip(".,;:!?\"' ").casefold()


def facts(directory, source_id):
    """Fact id -> the set of its located citations, for the tracked facts citing *source_id*."""
    found = {}
    for path in sorted((directory / "knowledge" / "facts").glob("fct-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if source_id in (record.get("sources") or []):
            found[record["id"]] = frozenset(
                (c["source"], loose(c["quote"]), c["line_start"], c["line_end"])
                for c in record.get("citations") or []
            )
    return found


def firings(project, source_id):
    listed = e2e.call("GET", f"/projects/{project}/manager/activity?job={JOB}&limit=200")
    return [f for f in listed.get("firings", []) if (f.get("subject") or {}).get("source") == source_id]


def wait_for_firings(project, source_id, count, seconds=240):
    end = time.time() + seconds
    while time.time() < end:
        if len(firings(project, source_id)) >= count:
            return True
        time.sleep(3)
    return False


def main(name):
    project = e2e.cmd_setup(name)
    directory = pathlib.Path(e2e.call("GET", f"/projects/{project}")["working_directory"])
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

    check("the first distillation fires", wait_for_firings(project, source, 1))
    first = facts(directory, source)
    check("the first distillation stores facts", bool(first), str(first))

    status, res = e2e.request("POST", f"/projects/{project}/vault/sources/{source}/distil")
    check("Distil answers 202", status == 202, f"{status} {res}")
    check("the second distillation fires", wait_for_firings(project, source, 2))
    second = facts(directory, source)
    check("the second distillation leaves facts", bool(second), str(second))

    by_lines = {lines: fact_id for fact_id, lines in first.items()}
    same = {fact_id: by_lines[lines] for fact_id, lines in second.items() if lines in by_lines}
    check(
        "at least one fact is drawn again from the same lines",
        bool(same),
        "Haiku quoted differently on both facts; re-run before judging the build",
    )
    moved = {now: before for now, before in same.items() if now != before}
    check("every fact drawn from the same lines keeps its id", not moved, f"new id -> old: {moved}")


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
