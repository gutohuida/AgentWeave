"""A footprint names the line of work its commit is on (F165, F166).

Function-level tests build real repositories; the route tests reuse `test_task_integration`'s
helpers. Not written: 1.5e (route, unnamed arm), 1.7/1.7a/1.8 (task-bound released workspace).
"""

import importlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from hub import requirement_evidence, task_integration
from hub.db.engine import async_session_factory
from hub.db.models import Task
from hub.task_integration import Target, reduce_by_ancestry

from .test_task_integration import (  # noqa: F401  (builder is a fixture)
    AGENT_BRANCH,
    BASE,
    accept_evidence,
    approve,
    builder,
    commit_on_branch,
    commits_on,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


def sha(root, ref="HEAD"):
    return git(root, "rev-parse", ref).stdout.strip()


def target(commit, branch, evidence_id="ev"):
    return Target(commit_sha=commit, branch=branch, evidence_id=evidence_id)


def two_on_a_branch(root):
    """main; branch `agentweave/builder` with C then D. Returns (C, D)."""
    make_repo(root)
    c = commit_on_branch(root, AGENT_BRANCH, "c.txt", "c\n")
    d = commit_on_branch(root, AGENT_BRANCH, "d.txt", "d\n", create=False)
    return c, d


def unrelated(root):
    """main with two branches, each one commit past it. Returns (X, Y)."""
    make_repo(root)
    x = commit_on_branch(root, "one", "x.txt", "x\n")
    git(root, "checkout", "-q", "main")
    y = commit_on_branch(root, "two", "y.txt", "y\n")
    return x, y


# 1.1 / 1.3 — line_of_work


def test_a_detached_checkout_at_a_non_tip_commit_names_the_containing_branch(tmp_path):
    c, d = two_on_a_branch(tmp_path)
    git(tmp_path, "checkout", "-q", "--detach", c)
    assert requirement_evidence.line_of_work(tmp_path, c) == AGENT_BRANCH
    assert requirement_evidence.read_footprint(tmp_path).branch == AGENT_BRANCH


def test_a_detached_checkout_at_the_task_branch_tip_names_the_task_branch(tmp_path):
    make_repo(tmp_path)
    tip = commit_on_branch(tmp_path, "agentweave/task/task-1", "t.txt", "t\n")
    git(tmp_path, "checkout", "-q", "--detach", tip)
    footprint = requirement_evidence.read_footprint(tmp_path, task_branch="agentweave/task/task-1")
    assert footprint.branch == "agentweave/task/task-1"


def test_a_commit_no_single_branch_contains_is_unknown_never_head(tmp_path):
    make_repo(tmp_path)
    base = sha(tmp_path)  # contained by main and by both branches below
    commit_on_branch(tmp_path, "one", "x.txt", "x\n")
    git(tmp_path, "checkout", "-q", "main")
    commit_on_branch(tmp_path, "two", "y.txt", "y\n")
    commit_on_branch(tmp_path, "main", "z.txt", "z\n", create=False)
    git(tmp_path, "checkout", "-q", "--detach", base)
    assert requirement_evidence.line_of_work(tmp_path, base) == ""
    assert requirement_evidence.read_footprint(tmp_path).branch == ""


# 1.5 / 1.5c / 1.5d / 1.6 — the reduction


def test_a_descendant_outranks_a_later_observation_of_its_ancestor(tmp_path):
    c, d = two_on_a_branch(tmp_path)
    kept = reduce_by_ancestry(tmp_path, [target(d, AGENT_BRANCH, "first"), target(c, AGENT_BRANCH)])
    assert [(t.commit_sha, t.evidence_id) for t in kept] == [(d, "first")]


def test_the_same_commit_twice_keeps_the_later_observation(tmp_path):
    _, d = two_on_a_branch(tmp_path)
    kept = reduce_by_ancestry(
        tmp_path, [target(d, AGENT_BRANCH, "old"), target(d, AGENT_BRANCH, "new")]
    )
    assert [t.evidence_id for t in kept] == ["new"]


def test_a_rebase_later_observation_wins(tmp_path):
    make_repo(tmp_path)
    old = commit_on_branch(tmp_path, "b", "f.txt", "1\n")
    git(tmp_path, "checkout", "-q", "main")
    new = commit_on_branch(tmp_path, "b2", "g.txt", "2\n")
    kept = reduce_by_ancestry(tmp_path, [target(old, "b", "a"), target(new, "b", "b")])
    assert [t.commit_sha for t in kept] == [new]


@pytest.mark.parametrize("empty", ["", None])
def test_unnamed_unrelated_commits_are_both_kept(tmp_path, empty):
    x, y = unrelated(tmp_path)
    kept = reduce_by_ancestry(tmp_path, [target(x, empty), target(y, empty)])
    assert sorted(t.commit_sha for t in kept) == sorted([x, y])


def test_unnamed_drops_only_a_proper_ancestor_whichever_was_observed_later(tmp_path):
    c, d = two_on_a_branch(tmp_path)
    for order in ([d, c], [c, d]):
        kept = reduce_by_ancestry(tmp_path, [target(commit, "") for commit in order])
        assert [t.commit_sha for t in kept] == [d]


def test_unnamed_same_commit_twice_is_one_target_with_the_later_row(tmp_path):
    x, _ = unrelated(tmp_path)
    kept = reduce_by_ancestry(tmp_path, [target(x, "", "old"), target(x, "", "new")])
    assert [t.evidence_id for t in kept] == ["new"]


def test_an_unanswerable_probe_keeps_both_unnamed_commits(tmp_path, monkeypatch):
    x, y = unrelated(tmp_path)
    monkeypatch.setattr(requirement_evidence, "is_reachable_from", lambda *a, **k: None)
    kept = reduce_by_ancestry(tmp_path, [target(x, ""), target(y, "")])
    assert len(kept) == 2


def test_a_null_and_an_empty_branch_are_one_unnamed_arm(tmp_path):
    x, y = unrelated(tmp_path)
    kept = reduce_by_ancestry(tmp_path, [target(x, None), target(y, "")])
    assert len(kept) == 2


# 1.5b / 1.11 / F165 — through the routes


@pytest.mark.asyncio
async def test_approval_merges_the_descendant_when_an_older_commit_was_observed_later(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    c = commit_on_branch(tmp_path, AGENT_BRANCH, "c.txt", "c\n")
    d = commit_on_branch(tmp_path, AGENT_BRANCH, "d.txt", "d\n", create=False)
    await accept_evidence(app, auth_headers, builder)  # footprint at D, observed first
    git(tmp_path, "checkout", "-q", "main")
    recorded = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "summary": "checked C", "locator": c},
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["footprint"]["branch"] == AGENT_BRANCH

    task = await linked_task(app, auth_headers)
    async with async_session_factory() as session:
        row = await session.get(Task, task)
        observed = await task_integration.integration_targets(session, row)
        merged = await task_integration.merge_targets(session, row, tmp_path)
    assert [t.commit_sha for t in observed] == [c]  # observation order, unchanged
    assert [t.commit_sha for t in merged] == [d]

    preview = await app.get(
        f"/api/v1/projects/proj-test/tasks/{task}/integration-preview", headers=auth_headers
    )
    assert preview.status_code == 200, preview.text
    assert [t["commit_sha"] for t in preview.json()["targets"]] == [d], preview.json()

    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text
    assert d in commits_on(tmp_path, "main")


# 1.9 — the migration


def test_the_migration_rewrites_head_and_leaves_real_branches():
    engine = sa.create_engine("sqlite://")
    module = "hub.migrations.versions.0109_footprint_branch_one_unknown_spelling"
    migration = importlib.import_module(module)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE evidence_footprints (id TEXT, branch TEXT)"))
        conn.execute(
            sa.text(
                "INSERT INTO evidence_footprints VALUES "
                "('a','HEAD'),('b','main'),('c',NULL),('d','')"
            )
        )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()  # idempotent
        rows = dict(conn.execute(sa.text("SELECT id, branch FROM evidence_footprints")).all())
    assert rows == {"a": "", "b": "main", "c": None, "d": ""}
