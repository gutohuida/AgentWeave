"""Day sweep 2026-10-23: Knowledge vault x Manager jobs — the paths every earlier sweep left
"not reached": `vault_read` paging past one page from an agent, a `corrected` report, the map's
order by reads, spec-vault-check firing on propose, and a Read-only worker transcribing a PDF.

Drives a scratch Hub (never :8000 or :8010) through its real routes only.

Usage (AW_E2E_STATE names the Hub record):
  py -3.11 scripts/drive/s1023_vault.py <project-id> <step> [args]
  steps: long | jobs <runner-id> | pair | spec <cited-fact-id> | warnings | map | off
  (the PDF went in with `e2e.py vault <project> file rate-card.pdf document`)
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("e2e", ROOT / ".claude/skills/e2e-loop/e2e.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)  # type: ignore[union-attr]

#: The answer an agent can find only on the second page (vault.PAGE_CHARS is 50,000).
DEEP_FACT = "The on-call pager escalation timeout is 17 minutes, set by Ines Carvalho."
DEEP_AT = 61_000


def show(label, status, body):
    text = json.dumps(body, ensure_ascii=False)
    print(f"{label}: HTTP {status} {text[:600]}")


def add(project, name, kind, content, dated=None):
    body = {"name": name, "type": kind, "content": content}
    if dated:
        body["dated"] = dated
    status, answer = e2e.request("POST", f"/projects/{project}/vault/sources", body)
    show(f"add {name} ({len(content)} chars)", status, answer)
    return answer


def long_text():
    """~70K characters of a plausible handbook, the one fact past the first page."""
    teams = ["billing", "search", "ingest", "auth", "reports", "mail", "edge", "batch"]
    lines, n = [], 0
    while sum(len(x) + 1 for x in lines) < DEEP_AT:
        team = teams[n % len(teams)]
        lines.append(
            f"Section {n}: the {team} service keeps its runbook in the {team} folder, "
            f"restarts through the standard deploy pipeline, and pages its own rotation first."
        )
        n += 1
    lines.append(DEEP_FACT)
    while sum(len(x) + 1 for x in lines) < 70_000:
        lines.append(f"Appendix {n}: nothing in this appendix changes the rules above.")
        n += 1
    return "\n".join(lines)


def step_long(project):
    add(project, "ops-handbook", "note", "Operations handbook.\n" + long_text())


def step_jobs(project, runner):
    for key in ("vault-distillation", "vault-reports", "spec-vault-check"):
        status, answer = e2e.request(
            "PATCH", f"/projects/{project}/manager/jobs/{key}", {"enabled": True, "runner_id": runner}
        )
        show(f"manager {key} on", status, answer)


def step_pair(project):
    # `note`, not `decision`: a decision source is never distilled (F735).
    add(
        project,
        "release-policy-sept",
        "note",
        "Release policy. Production releases ship on Tuesdays. A hotfix needs two approvers.",
        dated="2026-09-01",
    )
    add(
        project,
        "release-policy-oct",
        "note",
        "Release policy update. Production releases ship on Thursdays from October on. "
        "A hotfix needs two approvers.",
        dated="2026-10-01",
    )


DOC = "spec/changes/release-days/spec.json"


def step_spec(project, cited_fact):
    """A change whose `monday` requirement contradicts an uncited fact (only the spec-vault-check
    job can see it) and whose `backup` requirement cites the fact it contradicts."""
    import urllib.parse

    base = f"/projects/{project}/project/documents"
    doc = {
        "schema_version": 1, "kind": "change-spec", "title": "Release days",
        "summary": "Move releases and the backup window.",
        "problem": "Releases collide with the backup window.",
        "scope": {"in_scope": ["Release day", "Backup window"], "non_goals": []},
        "requirements": [
            {"key": "monday", "statement": "Production releases MUST ship on Mondays.",
             "modal": "MUST", "rationale": None, "party": None},
            {"key": "backup", "statement": "The nightly backup window MUST be 05:00 to 07:00 UTC.",
             "modal": "MUST", "rationale": None, "party": None, "facts": [cited_fact]},
        ],
        "acceptance_criteria": [],
        "tasks": [{"key": "move", "title": "Move the days", "description": "Edit the calendar.",
                   "requirements": ["monday", "backup"], "depends_on": [], "files": ["cal.py"],
                   "from": None, "reviewer": None}],
        "algorithms": [], "design": "Calendar edit.", "lifecycle": "", "open_questions": [],
        "evidence": {"checked": [], "limits": []},
        "delivery": {"mode": "none", "agent": None, "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "*/5 * * * *"},
    }
    q = urllib.parse.quote(DOC)
    show("create", *e2e.request("POST", base, {"title": "Release days", "kind": "change-spec",
                                                "path": DOC}))
    show("content", *e2e.request("PUT", f"{base}/{DOC}/content", {"document": doc}))
    show("journey", *e2e.request("POST", f"{base}/journey?path={q}",
                                 {"size": "small", "step": "intake", "reason": "drive setup"}))
    show("close", *e2e.request("POST", f"{base}/close-exploration?path={q}"))
    show("propose", *e2e.request("POST", f"{base}/propose?path={q}"))


def step_warnings(project):
    import urllib.parse

    q = urllib.parse.quote(DOC)
    show("warnings", *e2e.request("GET", f"/projects/{project}/vault/warnings?path={q}"))


def step_map(project):
    status, answer = e2e.request("GET", f"/projects/{project}/vault/map")
    for area in answer.get("areas", []) if isinstance(answer, dict) else []:
        print("area", area.get("name"), area.get("reads"))
        for entry in area.get("entries", []):
            print("   ", entry.get("id"), entry.get("name"), "reads", entry.get("reads"))
    if not isinstance(answer, dict) or "areas" not in answer:
        show("map", status, answer)


def step_off(project):
    for key in ("vault-distillation", "vault-reports", "spec-vault-check", "conversation-titles"):
        status, answer = e2e.request(
            "PATCH", f"/projects/{project}/manager/jobs/{key}", {"enabled": False}
        )
        print(f"manager {key} off: HTTP {status}")


if __name__ == "__main__":
    project, step, *rest = sys.argv[1:]
    globals()[f"step_{step}"](project, *rest)
