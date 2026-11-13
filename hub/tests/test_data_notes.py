"""The vault note on what the data means, and its traps.

`ask-any-agent-for-a-dashboard-and-get-one-that-stays`, FR-8 (`ac-vault-note`): a project
registered before the Hub started and one created afterwards both hold the note with its two
traps; text an agent appended survives the next start; the dashboard tools' guidance names it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hub import dashboard_query, data_notes, mcp_server, vault
from hub.api.v1 import agents as agent_routes
from hub.db.engine import async_session_factory
from hub.project_lifecycle import ProjectLifecycleService

APPENDED = "\n- Agent's trap: `runs.ended_at` is empty while a run is still going.\n"
TRAPS = (
    "A send-back rejects every piece of evidence from that commit",
    "Cost per spec counts its tasks' building and reviewing runs",
)


def _private(project_id: str) -> Path:
    return vault.default_private_location(project_id)


def _note(root: Path, project_id: str) -> str:
    entry = vault.read_entry(root, _private(project_id), data_notes.NOTE_ID, 0)
    assert entry is not None, f"no data note in {root}"
    return entry["content"]


def _assert_note_with_traps(root: Path, project_id: str) -> None:
    text = _note(root, project_id)
    for trap in TRAPS:
        assert trap in text, f"{trap!r} missing from the note in {root}"
    listed = vault.build_map(root, _private(project_id))
    assert [e["name"] for e in listed if e["id"] == data_notes.NOTE_ID] == [data_notes.NOTE_NAME]
    # Nothing written into the project's folder: opening writes only `.agentweave/`.
    assert not (root / vault.TRACKED_DIRECTORY).exists()


@pytest.mark.asyncio
async def test_ac_vault_note(app, bind_project_workspace, tmp_path, monkeypatch) -> None:
    # A project registered before this shipped: opened while seeding did nothing.
    before = tmp_path / "registered-before"
    before.mkdir()
    import hub.project_lifecycle as lifecycle

    seed = lifecycle.seed_data_notes
    monkeypatch.setattr(lifecycle, "seed_data_notes", AsyncMock())
    before_id = (await bind_project_workspace(before)).id
    monkeypatch.setattr(lifecycle, "seed_data_notes", seed)
    assert (
        vault.read_entry(before, _private(before_id), data_notes.NOTE_ID, 0) is None
    ), "the project was meant to predate the note"

    # The Hub starts.
    await data_notes.seed_every_project()
    _assert_note_with_traps(before, before_id)

    # A project created afterwards holds it from creation.
    after = tmp_path / "created-after"
    async with async_session_factory() as session:
        after_id = (await ProjectLifecycleService(session).create_new(after)).id
    _assert_note_with_traps(after, after_id)

    # An agent appends to it; the Hub starts again and the project is opened again.
    vault.append_text(
        before,
        _private(before_id),
        data_notes.NOTE_ID,
        text=APPENDED,
        actor=vault.agent_actor("Analyst", "run-x"),
    )
    await data_notes.seed_every_project()
    async with async_session_factory() as session:
        await ProjectLifecycleService(session).open_existing(before)
    text = _note(before, before_id)
    assert text.endswith(APPENDED), "the appended text was overwritten"
    assert text.count(f"# {data_notes.NOTE_NAME}") == 1, "seeded twice"
    ids = [e["id"] for e in vault.build_map(before, _private(before_id))]
    assert ids.count(data_notes.NOTE_ID) == 1


def test_an_archived_note_is_not_seeded_again(tmp_path) -> None:
    root, private = tmp_path / "project", tmp_path / "private"
    root.mkdir()
    assert data_notes.seed(root, private) is not None
    vault.archive_source(root, private, data_notes.NOTE_ID, actor=vault.OPERATOR)
    assert data_notes.seed(root, private) is None
    assert [e["id"] for e in vault.build_map(root, private)] == []


def test_the_dashboard_tools_guidance_names_the_note() -> None:
    reference = mcp_server.dashboard_query_reference.__doc__ or ""
    if not reference:  # wrapped by the tool decorator
        reference = getattr(mcp_server.dashboard_query_reference, "description", "") or ""
    assert data_notes.NOTE_ID in reference and data_notes.NOTE_NAME in reference

    described = [
        op.text for op in agent_routes._operations() if op.tool == "dashboard_query_reference"
    ]
    assert described and data_notes.NOTE_ID in described[0]
    assert data_notes.NOTE_NAME in described[0]

    notes = dashboard_query.query_reference()["notes"]
    assert any(data_notes.NOTE_ID in note and "vault_append" in note for note in notes)


@pytest.mark.asyncio
async def test_the_hub_seeds_the_note_at_start(monkeypatch) -> None:
    import hub.main as main

    seeded = AsyncMock()
    monkeypatch.setattr(data_notes, "seed_every_project", seeded)
    for name in (
        "init_db",
        "log_journal_mode",
        "reconcile_interrupted_runs",
        "reconcile_stale_job_runs",
        "init_scheduler",
        "arm_held_queues",
        "terminate_all_active_runs",
        "shutdown_scheduler",
        "_settle_background_runs",
    ):
        monkeypatch.setattr(main, name, AsyncMock(), raising=False)
    monkeypatch.setattr(main.instance_identity, "load_or_create", lambda: None)
    monkeypatch.setattr(main, "_ui_staleness_warning", lambda: None)
    monkeypatch.setattr(main, "engine", SimpleNamespace(dispose=AsyncMock()))
    try:
        async with main.lifespan(None):
            pass
    except Exception:  # noqa: BLE001 -- only whether startup seeded is under test
        pass
    seeded.assert_awaited_once()
