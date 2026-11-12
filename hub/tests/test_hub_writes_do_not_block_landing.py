"""F1086, F1167: the Hub's own writes to the checkout must not block a landing, and a checkout that
is dirty for real must refuse a batch before its checks run, not after.

The Hub writes `spec/index.json` and the vault's `knowledge/` records into the project's main
checkout and leaves them uncommitted. A landing batch checked for ~30 minutes, then found the
checkout "dirty" with nobody's work but the Hub's, and failed; the operator committed the files by
hand and the checks ran again.
"""

from __future__ import annotations

import pytest

from hub import hub_writes, project_workspace, spec_documents, task_integration, vault
from hub.db.engine import async_session_factory

from .test_approved_work_merges_in_batches import (
    approve,
    batches,
    counting_check,
    landings_of,
    queue,
    runs_in,
    set_checks,
    tasks_under_review,
)
from .test_task_integration import git

FACT = "facts/fct-000000000001.json"


async def _workspace():
    async with async_session_factory() as session:
        return await project_workspace.resolve_project_workspace(session, "proj-test")


async def hub_written_checkout(tmp_path, tmp_path_factory):
    """One task under review, landing through a checked batch, and a main checkout whose only uncommitted tracked changes are the
    Hub's own writes to `spec/index.json` and to a `knowledge/` record."""
    ids, _ = await tasks_under_review(tmp_path, 1)
    await set_checks([counting_check(tmp_path_factory)[0]])
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "index.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "knowledge" / "facts").mkdir(parents=True)
    (tmp_path / "knowledge" / FACT).write_text("{}\n", encoding="utf-8")
    git(tmp_path, "add", "spec/index.json", f"knowledge/{FACT}")
    git(tmp_path, "commit", "-q", "-m", "the corpus, committed")
    (tmp_path / ".agentweave").mkdir(exist_ok=True)

    workspace = await _workspace()
    assert workspace.root.resolve() == tmp_path.resolve()
    spec_documents._write_index_text(workspace, '{"home": "spec/changes/a/spec.json"}\n')
    vault.storage.write(vault.tracked_root(workspace.root), FACT, b'{"id": "fct-000000000001"}\n')
    assert task_integration.has_uncommitted_changes(tmp_path), "the Hub's writes dirtied nothing"
    return ids


@pytest.mark.asyncio
async def test_a_checkout_dirty_only_with_the_hubs_writes_lands(
    app, auth_headers, tmp_path, tmp_path_factory
):
    [task_id] = await hub_written_checkout(tmp_path, tmp_path_factory)
    assert hub_writes.still_written(tmp_path) >= {"spec/index.json", f"knowledge/{FACT}"}

    assert (await approve(app, auth_headers, task_id)).status_code == 200
    await queue().drain()

    [landing] = await landings_of(task_id)
    assert landing.state == "landed", landing.reason
    assert (await batches())[-1].state == "landed"


@pytest.mark.asyncio
async def test_a_hand_edit_to_a_hub_written_file_still_counts_as_dirty(
    app, auth_headers, tmp_path, tmp_path_factory
):
    [task_id] = await hub_written_checkout(tmp_path, tmp_path_factory)
    index = tmp_path / "spec" / "index.json"
    index.write_text(index.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert (await approve(app, auth_headers, task_id)).status_code == 200
    await queue().drain()

    [landing] = await landings_of(task_id)
    assert landing.state == "not_landed"
    assert landing.reason == task_integration.CHECKOUT_DIRTY
    assert (await batches())[-1].state == "failed"


@pytest.mark.asyncio
async def test_a_dirty_checkout_fails_the_batch_before_any_check_runs(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    check, counter = counting_check(tmp_path_factory)
    [task_id], _ = await tasks_under_review(tmp_path, 1)
    await set_checks([check])
    from hub import project_checks

    await project_checks.drain()
    before = len(runs_in(counter))
    invoked = []

    async def never(*args, **kwargs):
        invoked.append(args)
        raise AssertionError("the batch's checks ran over a dirty checkout")

    monkeypatch.setattr(queue(), "run_batch_checks", never)
    (tmp_path / "README.md").write_text("an operator's edit\n", encoding="utf-8")

    assert (await approve(app, auth_headers, task_id)).status_code == 200
    await queue().drain()

    assert invoked == [], "the check runner was invoked"
    assert len(runs_in(counter)) == before
    [landing] = await landings_of(task_id)
    assert landing.state == "not_landed"
    assert landing.reason == task_integration.CHECKOUT_DIRTY
    batch = (await batches())[-1]
    assert batch.state == "failed" and batch.error == task_integration.CHECKOUT_DIRTY
