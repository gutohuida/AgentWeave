"""Drive for F438 (Tier 0), 2026-10-12: the holder refusal only claims a review in flight when one is.

Starts its own Hub from source on :8113 with a fresh database (never :8000 or :8010). No agent turn:
tasks, evidence and running-run rows are seeded straight into the drive's own database.

  1. a task `under_review` and held by a reviewer with no turn on it: `POST /agent/trigger` naming
     a second reviewer answers 409, names the holder, says no review is in flight, keeps the
     remedy, and does not say "Let the review in flight finish";
  2. the same task with a running run of the holder's bound to it: the old sentence, unchanged.

    py -3.11 scripts/drive/d1012_f438_holder_refusal.py
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402

d.PORT = 8113
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1012-f438" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"

SILENT, ATTENDED = "task-silent-438", "task-attended-438"


def seed(pid):
    sys.path.insert(0, str(d.REPO / "hub"))
    import os

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{d.DB.as_posix()}"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from hub.db.models import (
        Agent,
        EvidenceFootprint,
        RequirementEvidence,
        Run,
        SpecDocument,
        SpecRequirement,
        Task,
    )

    engine = create_engine(f"sqlite:///{d.DB.as_posix()}")
    with Session(engine) as session:
        for name in ("holder", "other", "author"):
            session.add(Agent(id=f"ag-{name}", project_id=pid, name=name))
        session.add(
            SpecDocument(
                id="doc-438",
                project_id=pid,
                path="spec/doc-438.json",
                title="d",
                phase="current",
                kind="capability",
            )
        )
        session.flush()
        for n, task_id in enumerate((SILENT, ATTENDED)):
            session.add(
                Task(
                    id=task_id,
                    project_id=pid,
                    title=task_id,
                    status="under_review",
                    assignee="holder",
                )
            )
            session.add(
                SpecRequirement(
                    id=f"req-{n}",
                    project_id=pid,
                    document_id="doc-438",
                    identifier=f"FR-{n}",
                    key=f"fr-{n}",
                    digest="d" * 64,
                )
            )
            session.flush()
            session.add(
                RequirementEvidence(
                    id=f"ev-{n}",
                    project_id=pid,
                    requirement_id=f"req-{n}",
                    task_id=task_id,
                    digest="d" * 64,
                    kind="commit",
                    actor_kind="agent",
                    actor="author",
                    summary="ok",
                )
            )
            session.flush()
            session.add(
                EvidenceFootprint(
                    id=f"fp-{n}",
                    project_id=pid,
                    evidence_id=f"ev-{n}",
                    kind="git",
                    commit_sha="c" * 40,
                    branch="agentweave/author",
                )
            )
        session.flush()
        session.add(
            Run(
                id="run-438-holder",
                project_id=pid,
                agent="holder",
                status="running",
                task_id=ATTENDED,
                turn_depth=0,
            )
        )
        session.commit()
    engine.dispose()


def drive():
    root = d.TMP / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# f438\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "f438"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    seed(pid)

    def send(task_id):
        return d.api(
            "POST",
            f"/projects/{pid}/agent/trigger",
            {"agent": "other", "message": "review it", "review_task_id": task_id},
        )

    code, out = send(SILENT)
    detail = str(out.get("detail", out)) if isinstance(out, dict) else str(out)
    d.check("1 a silent holder's task is refused", code == 409, f"{code} {detail[:300]}")
    d.check("1 the refusal names the holder", "already under review by 'holder'" in detail, detail)
    d.check(
        "1 it does not send the operator to wait for a review",
        "Let the review in flight finish" not in detail,
        detail,
    )
    d.check("1 it says no review is in flight", "no review is in flight" in detail, detail)
    d.check("1 the remedy stays", "Decide it yourself" in detail, detail)

    code, out = send(ATTENDED)
    detail = str(out.get("detail", out)) if isinstance(out, dict) else str(out)
    d.check("2 an attended holder's task is refused", code == 409, f"{code} {detail[:300]}")
    d.check("2 the old sentence is kept", "Let the review in flight finish" in detail, detail)
    d.check(
        "2 and no claim that nothing is in flight", "no review is in flight" not in detail, detail
    )


if __name__ == "__main__":
    d.drive = drive
    d.main()
