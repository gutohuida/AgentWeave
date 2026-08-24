"""One demonstration, recorded twice, is one demonstration.

Found by driving the product (`scripts/drive/FINDINGS.md`, F7): `builder` recorded evidence for FR-1
unprompted on its first turn, then recorded the same fact again when asked — same requirement, same
task, same commit, near-identical prose. Both were stored, both entered `awaiting`, and coverage read
`evidence_count: 2, accepted_count: 0`. The reviewer had to decide twice about one fact, and the
count overstated what had been shown.

The key is requirement + task + commit, and each third of it is load-bearing. The requirement fixes
what is being shown; the task fixes which piece of work is showing it; the commit fixes the state of
the code it was shown against. Note the pre-existing `digest` column is *not* this check — it pins
the requirement's wording at production time, which is the staleness mechanism, and it is equal
across two genuinely distinct demonstrations for the same reason it is equal across duplicates.

Every test here needs a real repository, because without a commit there is no key and the check is
deliberately silent.
"""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, RequirementEvidence, Run, Task
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/duplicate-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It records a watering", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It lists what is due", "modal": "MUST"}

TASK_ID = "task-dupe"
OTHER_TASK_ID = "task-dupe-other"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)


def init_repo(path: Path, branch: str = "master") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", branch)
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")
    return path


def commit_in(worktree: Path, filename: str, content: str) -> str:
    (worktree / filename).write_text(content, encoding="utf-8")
    git(worktree, "add", filename)
    git(worktree, "commit", "-q", "-m", f"work on {filename}")
    return git(worktree, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-dupe", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-dupe",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_dupe-secret"),
            )
        )
        for task_id in (TASK_ID, OTHER_TASK_ID):
            session.add(
                Task(id=task_id, project_id="proj-test", title=f"Task {task_id}", status="pending")
            )
        await session.commit()
    return {"Authorization": "Bearer aw_run_dupe-secret"}


async def make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Duplicate demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Duplicate demo",
                "requirements": [ALPHA, BETA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def evidence_count() -> int:
    async with async_session_factory() as session:
        return len((await session.execute(select(RequirementEvidence))).scalars().all())


@pytest.fixture
async def worked(app, auth_headers, builder, bind_project_workspace, tmp_path):
    """A project on a real repository, the agent's worktree carrying one commit of its own, and a
    document declaring FR-1 and FR-2.

    Yields `(headers, worktree)`: the headers every test records with, and the checkout the one test
    that needs the work to move on commits into.
    """
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    worktree = worktrees.ensure_worktree(repo, "builder")
    commit_in(worktree, "feature.py", "print('hi')\n")
    await make_document(app, auth_headers, builder)
    return builder, worktree


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_same_fact_recorded_twice_is_refused(app, worked):
    """The measured case. The refusal names the piece that already exists, so the agent can act on
    it rather than retry."""
    headers, _ = worked
    first = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "ran it", "task_id": TASK_ID},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "I ran the tests", "task_id": TASK_ID},
        headers=headers,
    )

    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert detail["code"] == "duplicate_evidence"
    assert first.json()["id"] in detail["message"]
    assert await evidence_count() == 1


@pytest.mark.asyncio
async def test_a_second_requirement_at_the_same_commit_is_ordinary(app, worked):
    """One commit demonstrating two requirements is the normal shape of a turn, not a duplicate."""
    headers, _ = worked
    for identifier in ("FR-1", "FR-2"):
        recorded = await app.post(
            AGENT_EVIDENCE,
            json={"identifier": identifier, "summary": "ran it", "task_id": TASK_ID},
            headers=headers,
        )
        assert recorded.status_code == 201, recorded.text

    assert await evidence_count() == 2


@pytest.mark.asyncio
async def test_the_same_requirement_under_a_different_task_is_ordinary(app, worked):
    """Two pieces of work can each have to demonstrate the same requirement."""
    headers, _ = worked
    for task_id in (TASK_ID, OTHER_TASK_ID):
        recorded = await app.post(
            AGENT_EVIDENCE,
            json={"identifier": "FR-1", "summary": "ran it", "task_id": task_id},
            headers=headers,
        )
        assert recorded.status_code == 201, recorded.text

    assert await evidence_count() == 2


@pytest.mark.asyncio
async def test_evidence_naming_no_task_is_never_a_duplicate(app, worked):
    """Half the key is missing, so there is nothing to be a second copy *of*. Refusing on a guess
    here would reject a first piece of evidence, which is far worse than accepting a second."""
    headers, _ = worked
    for _ in range(2):
        recorded = await app.post(
            AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=headers
        )
        assert recorded.status_code == 201, recorded.text

    assert await evidence_count() == 2


@pytest.mark.asyncio
async def test_work_moving_on_makes_the_next_piece_new(app, worked):
    """The commit is what says the code has changed under the claim. Once the agent commits again,
    evidence for the same requirement on the same task is about a different state of the work."""
    headers, worktree = worked
    first = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "ran it", "task_id": TASK_ID},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    commit_in(worktree, "more.py", "y\n")

    second = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "ran it again after the fix", "task_id": TASK_ID},
        headers=headers,
    )

    assert second.status_code == 201, second.text
    assert await evidence_count() == 2


@pytest.mark.asyncio
async def test_a_rejected_piece_does_not_block_a_second_attempt(app, auth_headers, worked):
    """A rejection is a judgement that the demonstration was inadequate. Re-recording at the same
    commit with a better account of it is the honest response, not a duplicate of one."""
    headers, _ = worked
    first = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "ran it", "task_id": TASK_ID},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    decided = await app.post(
        f"{BASE}/spec/evidence/{first.json()['id']}/decision",
        json={"decision": "rejected", "reason": "that is not what FR-1 says"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text

    second = await app.post(
        AGENT_EVIDENCE,
        json={
            "identifier": "FR-1",
            "summary": "here is the part that covers FR-1",
            "task_id": TASK_ID,
        },
        headers=headers,
    )

    assert second.status_code == 201, second.text
    assert await evidence_count() == 2
