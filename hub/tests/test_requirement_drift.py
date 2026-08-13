"""Drift: a changed implementation raises a candidate, and never an edit.

That an implementation changed is observable. That a requirement *should* change is a judgement, and
a system that inferred it would rewrite an approved specification on the strength of a file diff. So
the load-bearing test here is the negative one — after drift is raised, the document on disk is byte
for byte what it was.
"""

import subprocess

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceFootprint, RequirementDrift, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/drift-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-drift", project_id="proj-test", name="drift-builder"))
        session.add(
            Run(
                id="run-drift",
                project_id="proj-test",
                agent="drift-builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_drift-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_drift-secret"}


async def _document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Drift demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Drift demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _record(app, auth_headers):
    response = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _detect(app, auth_headers):
    response = await app.post(f"{BASE}/spec/drift/detect", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["raised"]


# ---------------------------------------------------------------------------
# A project that is not a repository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_project_without_a_repository_still_records_a_footprint(
    app, auth_headers, builder, tmp_path
):
    """A git-only first cut would leave every non-repository project permanently
    unverifiable, and those are a supported first-class case."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")

    evidence_id = await _record(app, auth_headers)

    async with async_session_factory() as session:
        footprint = (
            (
                await session.execute(
                    select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence_id)
                )
            )
            .scalars()
            .first()
        )

    assert footprint.kind == "paths"
    assert "ledger.py" in footprint.entries
    assert footprint.reachable_from_main is None


@pytest.mark.asyncio
async def test_a_changed_file_raises_a_candidate(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    await _record(app, auth_headers)

    (tmp_path / "ledger.py").write_text("def split(a, b): return a - b\n", encoding="utf-8")
    raised = await _detect(app, auth_headers)

    assert len(raised) == 1
    listed = await app.get(f"{BASE}/spec/drift", headers=auth_headers)
    entry = listed.json()["drift"][0]
    assert entry["state"] == "candidate"
    assert "ledger.py" in entry["observed"]


@pytest.mark.asyncio
async def test_an_unchanged_tree_raises_nothing(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    await _record(app, auth_headers)

    assert await _detect(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_candidate_is_not_raised_twice(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    await _detect(app, auth_headers)

    assert await _detect(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_resolved_candidate_does_not_return(app, auth_headers, builder, tmp_path):
    """A resolution that did not record what was current would make the feature a
    nuisance within a day."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    raised = await _detect(app, auth_headers)

    resolved = await app.post(
        f"{BASE}/spec/drift/{raised[0]}/resolve",
        json={"resolution": "no_change_required"},
        headers=auth_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["state"] == "resolved"

    assert await _detect(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_reworded_requirement_is_not_also_drift(app, auth_headers, builder, tmp_path):
    """Already reported as stale evidence. Calling it drift as well would ask the
    operator the same question twice in two vocabularies."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)

    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Drift demo",
                "requirements": [{**ALPHA, "statement": "It lists what is due this week"}],
            },
        },
        headers=builder,
    )
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")

    assert await _detect(app, auth_headers) == []


@pytest.mark.asyncio
async def test_drift_never_writes_the_document(app, auth_headers, builder, tmp_path):
    """The load-bearing negative. There is no path from detection to a document."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    before = (tmp_path / PATH).read_bytes()

    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    await _detect(app, auth_headers)

    assert (tmp_path / PATH).read_bytes() == before


@pytest.mark.asyncio
async def test_only_the_operator_resolves_a_candidate(app, auth_headers, builder, tmp_path):
    from hub import requirement_evidence
    from hub.spec_lifecycle import Actor

    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    raised = await _detect(app, auth_headers)

    async with async_session_factory() as session:
        candidate = await session.get(RequirementDrift, raised[0])
        with pytest.raises(requirement_evidence.EvidenceRefusedError) as refusal:
            await requirement_evidence.resolve_drift(
                session,
                candidate,
                resolution="no_change_required",
                actor=Actor(kind="agent", name="drift-builder", run_id="run-drift"),
            )
    assert refusal.value.code == "resolution_is_the_operators"


# ---------------------------------------------------------------------------
# A project that is a repository
# ---------------------------------------------------------------------------


def _git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
    )


@pytest.mark.asyncio
async def test_a_git_footprint_names_its_commit_and_says_whether_it_landed(
    app, auth_headers, builder, tmp_path
):
    """Approved work in this product routinely sits on a per-agent branch that
    nothing merges, so a footprint naming an unmerged commit is the normal case
    rather than the exception."""
    if _git(tmp_path, "init").returncode != 0:
        pytest.skip("git is not available")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    _git(tmp_path, "add", "ledger.py")
    _git(tmp_path, "commit", "-m", "first")
    _git(tmp_path, "branch", "-M", "main")

    await _document(app, auth_headers, builder)
    evidence_id = await _record(app, auth_headers)

    async with async_session_factory() as session:
        footprint = (
            (
                await session.execute(
                    select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence_id)
                )
            )
            .scalars()
            .first()
        )

    assert footprint.kind == "git"
    assert footprint.commit_sha
    assert footprint.branch == "main"
    assert footprint.entries["ledger.py"]
    assert footprint.reachable_from_main is True


@pytest.mark.asyncio
async def test_work_on_an_agent_branch_reports_as_not_integrated(
    app, auth_headers, builder, tmp_path
):
    if _git(tmp_path, "init").returncode != 0:
        pytest.skip("git is not available")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("only a readme\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "readme")
    _git(tmp_path, "branch", "-M", "main")
    _git(tmp_path, "checkout", "-b", "agentweave/builder")
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    _git(tmp_path, "add", "ledger.py")
    _git(tmp_path, "commit", "-m", "Auto-snapshot: builder's turn")

    await _document(app, auth_headers, builder)
    await _record(app, auth_headers)

    coverage = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    entry = coverage.json()["requirements"][0]
    assert entry["state"] == "verified"
    assert entry["integration"] == "not_integrated"


@pytest.mark.asyncio
async def test_a_changed_blob_in_a_repository_raises_a_candidate(
    app, auth_headers, builder, tmp_path
):
    if _git(tmp_path, "init").returncode != 0:
        pytest.skip("git is not available")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    _git(tmp_path, "add", "ledger.py")
    _git(tmp_path, "commit", "-m", "first")
    _git(tmp_path, "branch", "-M", "main")

    await _document(app, auth_headers, builder)
    await _record(app, auth_headers)

    (tmp_path / "ledger.py").write_text("def split(a, b): return a - b\n", encoding="utf-8")
    _git(tmp_path, "add", "ledger.py")
    _git(tmp_path, "commit", "-m", "second")

    raised = await _detect(app, auth_headers)

    assert len(raised) == 1
