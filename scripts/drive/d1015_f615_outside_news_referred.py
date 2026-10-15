"""Acceptance drive for F615: a vault report that brings outside news reaches the operator.

Before: the vault-reports job judged "from the source alone", so a report that the source is out of
date ("renegotiated to 60 days") was answered "the entry stands" and closed. After: it is referred.
A control report the source settles (it claims the source says 30 days; it says 45) must still be
answered, so referring everything does not pass.

  py -3.11 scripts/drive/d1015_f615_outside_news_referred.py <project-name>

Drives the Hub `e2e.py hub-up` started (never :8000 or :8010). Two Haiku agent turns and two Haiku
reports firings. Exit 1 on any fail.
"""

import importlib.util
import json
import pathlib
import secrets
import sys
import time

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-reports"
AGENT = "reporter"
LINE = "Invoices from Nordlicht are due within 45 days of receipt."
SOURCE = "Nordlicht supply contract, 2026-03-01.\n" + LINE + "\nDeliveries arrive on Tuesdays.\n"
failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def write_fact(directory, source_id):
    """A tracked fact beside the source, as distillation writes one (vault.add_fact)."""
    fact_id = "fct-" + secrets.token_hex(6)
    meta = {
        "id": fact_id,
        "kind": "fact",
        "claim": "Invoices from Nordlicht are due within 45 days.",
        "citations": [{"source": source_id, "quote": LINE, "line_start": 2, "line_end": 2}],
        "sources": [source_id],
        "visibility": "tracked",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
        "holder": None,
        "made_by": {"job": "d1015", "model": None},
    }
    folder = directory / "knowledge" / "facts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{fact_id}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return fact_id


def report_status(directory, fact_id, seconds=360):
    """The status of the newest report on *fact_id* once it is no longer pending, or the last seen."""
    end, last = time.time() + seconds, None
    while time.time() < end:
        folder = directory / "knowledge" / "reports"
        reports = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("rpt-*.json"))
        ] if folder.is_dir() else []
        mine = sorted((r for r in reports if r.get("entry") == fact_id), key=lambda r: r["created_at"])
        if mine:
            last = mine[-1]
            if last.get("status") != "pending":
                return last
        time.sleep(4)
    return last


def report(project, directory, fact_id, message):
    run = e2e.cmd_turn(
        project,
        AGENT,
        f"Report the knowledge vault fact {fact_id} to the manager with vault_report, with exactly "
        f"this message: {message!r}. Do nothing else.",
        fresh=True,
    )
    e2e.wait_for(run, 6)
    return report_status(directory, fact_id)


def main(name):
    project = e2e.cmd_setup(name)
    directory = pathlib.Path(e2e.call("GET", f"/projects/{project}")["working_directory"])
    e2e.cmd_agent(project, AGENT, "-", "claude", HAIKU)
    runner = next(r for r in e2e.call("GET", f"/projects/{project}/runners") if r.get("model") == HAIKU)
    e2e.call("PATCH", f"/projects/{project}/manager/jobs/{JOB}", {"enabled": True, "runner_id": runner["id"]})
    source = e2e.call(
        "POST",
        f"/projects/{project}/vault/sources",
        {"name": "Nordlicht contract", "type": "document", "content": SOURCE},
    )["id"]
    news_fact = write_fact(directory, source)
    control_fact = write_fact(directory, source)

    news = report(
        project,
        directory,
        news_fact,
        "Out of date: the accountant told us this morning that the Nordlicht contract was "
        "renegotiated last week to 60-day payment terms.",
    )
    check(
        "a report bringing outside news is referred",
        (news or {}).get("status") == "referred",
        f"{(news or {}).get('status')}: {(news or {}).get('answer')}",
    )
    control = report(
        project,
        directory,
        control_fact,
        "Wrong: the contract says invoices are due within 30 days, not 45.",
    )
    check(
        "a report the source settles is still answered",
        (control or {}).get("status") == "answered",
        f"{(control or {}).get('status')}: {(control or {}).get('answer')}",
    )
    e2e.request("PATCH", f"/projects/{project}/manager/jobs/{JOB}", {"enabled": False})


if __name__ == "__main__":
    main(*sys.argv[1:])
    print("ALL PASS" if not failures else f"{len(failures)} FAILED: {failures}")
    sys.exit(1 if failures else 0)
