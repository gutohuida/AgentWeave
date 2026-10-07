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


async def _record(app, auth_headers, locator="ledger.py"):
    # Rewritten on purpose by `drift-watches-the-files-its-evidence-is-about` (task 1.9): evidence
    # used to watch the whole tree, so these tests recorded none and relied on it. A footprint now
    # watches what its evidence names, so each names the file it changes.
    response = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it", "locator": locator},
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


# ---------------------------------------------------------------------------
# `drift-is-scanned-and-answered-on-the-document` (F129, F430, F436): the routes the panel uses.
# ---------------------------------------------------------------------------

SECOND = "spec/changes/drift-second/spec.html"


async def _second_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": SECOND, "title": "Second"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": SECOND,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Second",
                "requirements": [
                    {"key": "beta", "statement": "It does another thing", "modal": "MUST"}
                ],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _candidate(drift_id, path, *, state="candidate", created_at=None):
    from datetime import datetime, timezone

    from hub.db.models import SpecDocument, SpecRequirement

    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        requirement = (
            (
                await session.execute(
                    select(SpecRequirement).where(SpecRequirement.document_id == document.id)
                )
            )
            .scalars()
            .first()
        )
        session.add(
            RequirementDrift(
                id=drift_id,
                project_id="proj-test",
                requirement_id=requirement.id,
                evidence_id=f"ev-{drift_id}",
                state=state,
                digest=requirement.digest,
                observed={"ledger.py": {"was": "a", "now": "b"}},
                created_at=created_at or datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _listed(app, auth_headers, **params):
    response = await app.get(f"{BASE}/spec/drift", params=params, headers=auth_headers)
    return response


@pytest.mark.asyncio
async def test_drift_is_listed_for_one_document_and_one_state(app, auth_headers, builder):
    """1.1, 1.2 (D1). FAILS before: the filters were ignored and both documents' came back."""
    await _document(app, auth_headers, builder)
    await _second_document(app, auth_headers, builder)
    await _candidate("drift-one", PATH)
    await _candidate("drift-two", SECOND)
    await _candidate("drift-done", PATH, state="resolved")

    only = await _listed(app, auth_headers, document=PATH, state="candidate")
    assert only.status_code == 200, only.text
    assert [row["id"] for row in only.json()["drift"]] == ["drift-one"]

    assert (await _listed(app, auth_headers, state="bogus")).status_code == 422
    unknown = await _listed(app, auth_headers, document="spec/changes/nothing/spec.html")
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_the_route_order_breaks_a_created_at_tie_by_id(app, auth_headers, builder):
    """1.15 (D9, F190): one scan adds candidates in one transaction, so `created_at` ties."""
    from datetime import datetime, timedelta, timezone

    await _document(app, auth_headers, builder)
    tie = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    await _candidate("drift-b", PATH, created_at=tie)
    await _candidate("drift-a", PATH, created_at=tie)
    await _candidate("drift-early", PATH, created_at=tie - timedelta(minutes=5))

    listed = (await _listed(app, auth_headers)).json()["drift"]
    assert [row["id"] for row in listed] == ["drift-early", "drift-a", "drift-b"]


@pytest.mark.asyncio
async def test_a_candidate_is_answered_once(app, auth_headers, builder, tmp_path):
    """1.3 (D4, F430). FAILS before: the second answer overwrote the first."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    (raised,) = await _detect(app, auth_headers)

    first = await app.post(
        f"{BASE}/spec/drift/{raised}/resolve",
        json={"resolution": "no_change_required"},
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    second = await app.post(
        f"{BASE}/spec/drift/{raised}/resolve",
        json={"resolution": "specification_updated"},
        headers=auth_headers,
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "drift_not_open"
    assert "no_change_required" in second.json()["detail"]["message"]
    listed = (await _listed(app, auth_headers)).json()["drift"]
    assert listed[0]["resolution"] == "no_change_required"


@pytest.mark.asyncio
async def test_a_scan_and_an_answer_are_broadcast(app, auth_headers, builder, tmp_path):
    """1.4 (D5): a scan broadcasts even when it raises nothing; an answer broadcasts once."""
    from unittest.mock import AsyncMock, patch

    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    broadcast = AsyncMock()
    with patch("hub.api.v1.spec.sse_manager.broadcast", broadcast):
        assert await _detect(app, auth_headers) == []
        assert broadcast.await_args_list[-1].args[1:] == (
            "spec_updated",
            {"path": None, "drift": True},
        )
        (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
        (raised,) = await _detect(app, auth_headers)
        before = broadcast.await_count
        resolved = await app.post(
            f"{BASE}/spec/drift/{raised}/resolve",
            json={"resolution": "no_change_required"},
            headers=auth_headers,
        )
        assert resolved.status_code == 200, resolved.text
        assert broadcast.await_count == before + 1


def test_the_gate_remedy_for_drift_names_who_answers_it():
    """1.5 (D6): the remedy is performable where it is shown."""
    from hub import requirement_coverage, requirement_gate

    remedy = requirement_gate.REMEDY[requirement_coverage.DRIFTING]
    assert "the operator answers the drift candidate" in remedy
    assert "an agent cannot" in remedy


@pytest.mark.asyncio
async def test_code_corrected_without_a_revert_asks_again(app, auth_headers, builder, tmp_path):
    """1.13 (D8, F436). FAILS before: the answer's fingerprint silenced the same change for good."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    (raised,) = await _detect(app, auth_headers)
    await app.post(
        f"{BASE}/spec/drift/{raised}/resolve",
        json={"resolution": "implementation_corrected"},
        headers=auth_headers,
    )
    async with async_session_factory() as session:
        assert (await session.get(RequirementDrift, raised)).resolved_fingerprint is None

    (again,) = await _detect(app, auth_headers)
    assert again != raised


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["no_change_required", "specification_updated"])
async def test_the_other_answers_stay_answered(app, auth_headers, builder, tmp_path, resolution):
    """1.14 (D8) control: *No change* and *Spec updated* keep their fingerprint."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    (raised,) = await _detect(app, auth_headers)
    await app.post(
        f"{BASE}/spec/drift/{raised}/resolve", json={"resolution": resolution}, headers=auth_headers
    )
    assert await _detect(app, auth_headers) == []


@pytest.mark.asyncio
async def test_code_corrected_and_reverted_raises_nothing(app, auth_headers, builder, tmp_path):
    """1.14 (D8): *Code corrected* that really went back raises nothing."""
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("two\n", encoding="utf-8")
    (raised,) = await _detect(app, auth_headers)
    await app.post(
        f"{BASE}/spec/drift/{raised}/resolve",
        json={"resolution": "implementation_corrected"},
        headers=auth_headers,
    )
    (tmp_path / "ledger.py").write_text("one\n", encoding="utf-8")
    assert await _detect(app, auth_headers) == []
