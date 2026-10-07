"""`drift-watches-the-files-its-evidence-is-about` (F427, F217, F432), against real repositories.

A footprint used to record the whole tree, so one unrelated commit raised a drift candidate for every
piece of evidence (F427); and once work merged, drift kept comparing against the agent's branch, so a
later change on the main line was never noticed (F217). A footprint now watches the files its
evidence is about -- the first of its locator's words that are paths in the tree, the commit an
operator named, or its branch's changes -- and merged work is compared against the main line.
"""

import subprocess

import pytest
from sqlalchemy import select

from hub import requirement_evidence
from hub.db.engine import async_session_factory
from hub.db.models import EvidenceFootprint, Project

from . import test_requirement_drift as _drift
from .test_requirement_drift import BASE, _detect, _document

builder = _drift.builder
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"


def git(root, *args):
    result = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def repo(root, files):
    git(root, "init", "-q", "-b", "main")
    for name, body in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")


def commit(root, name, body, message="change"):
    (root / name).write_text(body, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


async def operator(app, auth_headers, locator):
    response = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "kind": "test_result", "summary": "s", "locator": locator},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def agent(app, run_headers, locator):
    response = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "s", "locator": locator},
        headers=run_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def footprint(evidence_id):
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence_id)
            )
        ).scalar_one_or_none()


async def unwatched(app, auth_headers):
    response = await app.get(f"{BASE}/spec/drift", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["unwatched"]


async def set_main_branch(name):
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).main_branch = name
        await session.commit()


# --------------------------------------------------------------------------- what is watched


@pytest.mark.asyncio
async def test_a_commit_to_a_file_the_evidence_is_not_about_raises_nothing(
    app, auth_headers, builder, tmp_path
):
    """1.1 (F427). FAILS before: the whole tree was watched, so other.py raised a candidate."""
    repo(tmp_path, {"ledger.py": "one\n", "other.py": "x\n"})
    await _document(app, auth_headers, builder)
    await operator(app, auth_headers, "ledger.py")

    commit(tmp_path, "other.py", "y\n")
    assert await _detect(app, auth_headers) == []

    commit(tmp_path, "ledger.py", "two\n")
    raised = await _detect(app, auth_headers)
    assert len(raised) == 1, "1.2 control: the watched file still raises"
    listed = (await app.get(f"{BASE}/spec/drift", headers=auth_headers)).json()["drift"]
    assert set(listed[0]["observed"]) == {"ledger.py"}


@pytest.mark.asyncio
async def test_agent_work_on_a_branch_watches_what_the_branch_changed(
    app, auth_headers, builder, tmp_path
):
    """1.3 (rule 3): with no locator, the branch's changes since it left main."""
    repo(tmp_path, {"README.md": "r\n"})
    git(tmp_path, "checkout", "-q", "-b", "agentweave/builder")
    commit(tmp_path, "ledger.py", "one\n")
    await _document(app, auth_headers, builder)
    ev = await agent(app, builder, "")

    row = await footprint(ev["id"])
    assert set(row.entries) == {"ledger.py"}
    assert row.watched_from == ["branch"]


@pytest.mark.asyncio
async def test_a_locator_naming_one_file_narrows_agent_evidence(
    app, auth_headers, builder, tmp_path
):
    """1.16 (D1'): the locator wins over the branch diff; the rules are not a union."""
    repo(tmp_path, {"README.md": "r\n"})
    git(tmp_path, "checkout", "-q", "-b", "agentweave/builder")
    commit(tmp_path, "a.py", "a\n")
    commit(tmp_path, "b.py", "b\n")
    await _document(app, auth_headers, builder)
    ev = await agent(app, builder, "a.py")

    row = await footprint(ev["id"])
    assert set(row.entries) == {"a.py"}
    assert row.watched_from == ["locator"]
    assert ev["footprint"]["provisional"] is True, "1.20: an agent's mid-turn footprint says so"
    assert ev["footprint"]["watched_count"] == 1


@pytest.mark.asyncio
async def test_prose_in_a_locator_counts_only_where_it_names_files_in_the_tree(
    app, auth_headers, builder, tmp_path
):
    """1.17 (D1''): words split out of prose; only real paths count."""
    repo(tmp_path, {"src/engine.js": "e\n", "test/engine.test.js": "t\n", "README.md": "r\n"})
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, "src/engine.js (Engine.currentRun); test/engine.test.js")
    row = await footprint(ev["id"])
    assert set(row.entries) == {"src/engine.js", "test/engine.test.js"}
    assert row.watched_from == ["locator"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "locator, expected",
    [
        ("ledger.py::test_x", {"ledger.py"}),
        ("ledger.py:12", {"ledger.py"}),
        ("./ledger.py", {"ledger.py"}),
        # Under D1'' a command's words are read too: `ledger.py` is a path in the tree, so it counts.
        ("pytest ledger.py -q", {"ledger.py"}),
        (".", set()),
    ],
)
async def test_a_locator_is_normalised_before_it_is_matched(
    app, auth_headers, builder, tmp_path, locator, expected
):
    """1.15 (rule 1)."""
    repo(tmp_path, {"ledger.py": "one\n", "other.py": "x\n"})
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, locator)
    assert set((await footprint(ev["id"])).entries) == expected


@pytest.mark.asyncio
async def test_an_operator_named_commit_watches_what_it_changed(
    app, auth_headers, builder, tmp_path
):
    """1.4 (rule 2)."""
    repo(tmp_path, {"b.py": "b\n"})
    sha = commit(tmp_path, "a.py", "a\n")
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, sha)
    row = await footprint(ev["id"])
    assert set(row.entries) == {"a.py"}
    assert row.watched_from == ["commit"]


@pytest.mark.asyncio
async def test_a_named_merge_commit_watches_what_the_merge_brought_in(
    app, auth_headers, builder, tmp_path
):
    """1.14 (rule 2): without --diff-merges=first-parent a merge commit names nothing."""
    repo(tmp_path, {"b.py": "b\n"})
    git(tmp_path, "checkout", "-q", "-b", "feature")
    commit(tmp_path, "a.py", "a\n")
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    merge = git(tmp_path, "rev-parse", "HEAD")
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, merge)
    row = await footprint(ev["id"])
    assert set(row.entries) == {"a.py"}
    assert row.watched_from == ["commit"]


# --------------------------------------------------------------------------- watching nothing


@pytest.mark.asyncio
async def test_evidence_that_names_nothing_watches_nothing_and_is_listed(
    app, auth_headers, builder, tmp_path
):
    """1.5 (D2, D4)."""
    repo(tmp_path, {"ledger.py": "one\n"})
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, "")
    assert ev["footprint"]["watched_from"] == []
    assert ev["footprint"]["watched_count"] == 0

    commit(tmp_path, "ledger.py", "two\n")
    assert await _detect(app, auth_headers) == []
    (entry,) = await unwatched(app, auth_headers)
    assert entry["reason"] == "names_no_file"
    assert entry["requirement"]["identifier"] == "FR-1"


@pytest.mark.asyncio
async def test_evidence_with_no_footprint_is_listed(app, auth_headers, builder, tmp_path):
    """1.11 (D4, R2)."""
    repo(tmp_path, {"ledger.py": "one\n"})
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, "ledger.py")
    async with async_session_factory() as session:
        await session.delete(await session.get(EvidenceFootprint, (await footprint(ev["id"])).id))
        await session.commit()
    (entry,) = await unwatched(app, auth_headers)
    assert entry["reason"] == "no_footprint"


@pytest.mark.asyncio
async def test_unwatched_evidence_is_listed_oldest_first(app, auth_headers, builder, tmp_path):
    """1.21 (F190): `unwatched` is ordered produced_at, id, and this fails if it is reversed."""
    repo(tmp_path, {"ledger.py": "one\n"})
    await _document(app, auth_headers, builder)
    first = await operator(app, auth_headers, "")
    commit(tmp_path, "ledger.py", "two\n")
    second = await operator(app, auth_headers, "")
    listed = [entry["evidence_id"] for entry in await unwatched(app, auth_headers)]
    assert listed == [first["id"], second["id"]]


# --------------------------------------------------------------------------- the basis (F217)


@pytest.mark.asyncio
async def test_a_change_on_main_to_merged_work_raises_a_candidate(
    app, auth_headers, builder, tmp_path
):
    """1.6 (D3, F217). FAILS before: compared against the feature branch, which did not move."""
    repo(tmp_path, {"ledger.py": "one\n"})
    await set_main_branch("main")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    fix = commit(tmp_path, "ledger.py", "fixed\n")
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, fix)
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    assert await _detect(app, auth_headers) == []
    assert (await footprint(ev["id"])).reachable_from_main is True

    commit(tmp_path, "ledger.py", "regressed\n")
    assert len(await _detect(app, auth_headers)) == 1


@pytest.mark.asyncio
async def test_a_reachable_footprint_with_no_branch_is_compared_against_main(
    app, auth_headers, builder, tmp_path
):
    """1.12 (D3): a detached review checkout's footprint names no branch; main is the basis."""
    repo(tmp_path, {"ledger.py": "one\n"})
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, "ledger.py")
    async with async_session_factory() as session:
        row = await session.get(EvidenceFootprint, (await footprint(ev["id"])).id)
        row.branch = ""
        row.reachable_from_main = True
        await session.commit()
    commit(tmp_path, "ledger.py", "two\n")
    assert len(await _detect(app, auth_headers)) == 1


@pytest.mark.asyncio
async def test_reachability_asks_the_configured_main_branch(app, auth_headers, builder, tmp_path):
    """1.13 (D3, R3) and 1.21 for the agent route: both answer against `develop`, not `main`."""
    repo(tmp_path, {"ledger.py": "one\n"})
    git(tmp_path, "branch", "develop")
    only_on_main = commit(tmp_path, "ledger.py", "main only\n")
    await set_main_branch("develop")
    await _document(app, auth_headers, builder)

    ev = await operator(app, auth_headers, only_on_main)
    assert (await footprint(ev["id"])).reachable_from_main is False

    ev = await agent(app, builder, "ledger.py")
    assert (await footprint(ev["id"])).reachable_from_main is False


# --------------------------------------------------------------------------- legacy rows (D6)


async def _make_legacy(evidence_id, *, commit_sha, tree):
    async with async_session_factory() as session:
        row = await session.get(EvidenceFootprint, (await footprint(evidence_id)).id)
        row.watched_from = None
        row.entries = tree
        row.commit_sha = commit_sha
        row.reachable_from_main = None
        await session.commit()


@pytest.mark.asyncio
async def test_a_legacy_footprint_is_rebuilt_from_its_merge(app, auth_headers, builder, tmp_path):
    """1.18 (D6): watched_from NULL, whole-tree entries; its commit was merged with --no-ff."""
    repo(tmp_path, {"README.md": "r\n", "other.py": "x\n"})
    await set_main_branch("main")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    work = commit(tmp_path, "ledger.py", "one\n")
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, "")
    tree = requirement_evidence.tree_entries(tmp_path, work)
    await _make_legacy(ev["id"], commit_sha=work, tree=tree)

    detect = await app.post(f"{BASE}/spec/drift/detect", headers=auth_headers)
    assert detect.json()["rebuilt"] == 1
    row = await footprint(ev["id"])
    assert row.watched_from == ["merge"]
    assert set(row.entries) == {"ledger.py"}

    commit(tmp_path, "other.py", "y\n")
    assert await _detect(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_legacy_footprint_whose_merge_is_not_found_is_listed_not_scanned(
    app, auth_headers, builder, tmp_path
):
    """1.8 (D4, D6): FAILS before (it raised on any change to its whole tree)."""
    repo(tmp_path, {"ledger.py": "one\n"})
    git(tmp_path, "checkout", "-q", "-b", "abandoned")
    stranded = commit(tmp_path, "ledger.py", "never merged\n")
    git(tmp_path, "checkout", "-q", "main")
    await _document(app, auth_headers, builder)
    ev = await operator(app, auth_headers, "")
    await _make_legacy(
        ev["id"], commit_sha=stranded, tree=requirement_evidence.tree_entries(tmp_path, stranded)
    )

    commit(tmp_path, "ledger.py", "two\n")
    assert await _detect(app, auth_headers) == []
    assert (await footprint(ev["id"])).watched_from is None
    (entry,) = await unwatched(app, auth_headers)
    assert entry["reason"] == "recorded_before_watching"


# --------------------------------------------------------------------------- the production path


@pytest.mark.asyncio
async def test_agent_evidence_recorded_mid_turn_is_narrowed_at_run_end(
    app, auth_headers, builder, tmp_path
):
    """1.19 (D7): the re-stamp is the main production path; it writes watched_from."""
    repo(tmp_path, {"README.md": "r\n"})
    git(tmp_path, "checkout", "-q", "-b", "agentweave/builder")
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("work in progress\n", encoding="utf-8")
    ev = await agent(app, builder, "")

    final = commit(tmp_path, "ledger.py", "work in progress\n", "Auto-snapshot")
    async with async_session_factory() as session:
        updated = await requirement_evidence.restamp_run_footprints(
            session, project_id="proj-test", run_id="run-drift", root=tmp_path, commit_sha=final
        )
        await session.commit()
    assert updated == 1
    row = await footprint(ev["id"])
    assert row.commit_sha == final
    assert row.watched_from == ["branch"]
    assert set(row.entries) == {"ledger.py"}


def test_a_footprint_cannot_be_built_without_saying_what_it_watches():
    """1.20 (D7): no default, so no constructor silently writes the NULL that means legacy."""
    with pytest.raises(TypeError):
        requirement_evidence.Footprint(kind="git")  # type: ignore[call-arg]

