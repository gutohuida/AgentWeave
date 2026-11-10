"""AGENTS.md as a project's instructions, where chosen (FR-7 to FR-11).

Spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`, task `instructions-in-agents-md`.
The bootstrap project `proj-test` resolves to the test's `tmp_path` (conftest's
`_default_project_workspace`), which these tests make a real git repository on `main`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import project_workspace
from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Project, ProjectInstructions
from hub.instructions_file import MAX_INSTRUCTIONS_CHARS, with_moved_instructions
from hub.project_repository import AGENTS_MD, PROJECT_INSTRUCTIONS_HEADING
from hub.runner_adapters import ADAPTERS

P = "/api/v1/projects/proj-test/project/instructions"
OWN_AGENTS_MD = "# Our own agents file\n\nMARKER-OWN-FILE: read CLAUDE.md first.\n"
DB_TEXT = "MARKER-DATABASE: always run the linter."


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout


def _repository(root: Path, agents_md: str = OWN_AGENTS_MD) -> None:
    _git(root, "init", "--quiet")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.com")
    (root / AGENTS_MD).write_text(agents_md, encoding="utf-8", newline="\n")
    (root / "README.md").write_text("# readme\n", encoding="utf-8")
    _git(root, "add", AGENTS_MD, "README.md")
    _git(root, "commit", "--quiet", "-m", "first")


def _commits(root: Path) -> list[str]:
    return _git(root, "rev-list", "main").split()


async def _project(**values) -> None:
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        for key, value in values.items():
            setattr(project, key, value)
        await db.commit()


async def _database_instructions(content: str) -> None:
    async with async_session_factory() as db:
        db.add(ProjectInstructions(project_id="proj-test", content=content))
        await db.commit()


async def _database_row() -> str:
    async with async_session_factory() as db:
        row = (
            (
                await db.execute(
                    select(ProjectInstructions).where(ProjectInstructions.project_id == "proj-test")
                )
            )
            .scalars()
            .first()
        )
        return row.content if row else ""


async def _context(runner: str) -> str:
    async with async_session_factory() as db:
        agent_row = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == "builder")
                )
            )
            .scalars()
            .one()
        )
        rendered = await _render_hub_agent_context(
            agent="builder",
            project_id="proj-test",
            db=db,
            session_data=None,
            agent_row=agent_row,
            work_dir="/tmp/project",
            isolated=False,
            runner=runner,
        )
        return rendered["context"]


async def _received(runner: str, root: Path, marker: str) -> int:
    """How many times *marker* reaches a turn on *runner*: the Hub's context, plus the AGENTS.md
    of its working directory where the runner's CLI reads that file itself."""
    in_context = (await _context(runner)).count(marker)
    native = (root / AGENTS_MD).read_text(encoding="utf-8").count(marker)
    return in_context + (native if ADAPTERS[runner].reads_agents_md else 0)


@pytest.mark.asyncio
async def test_a_folder_with_its_own_agents_md_is_unchanged_until_the_operator_opts_in(
    app, auth_headers, add_agent, tmp_path
) -> None:
    """ac-own-agents-md-unchanged (FR-11)."""
    _repository(tmp_path)
    await _project(main_branch="main")
    await _database_instructions(DB_TEXT)
    await add_agent("builder")

    for runner in ADAPTERS:
        context = await _context(runner)
        assert "MARKER-OWN-FILE" not in context, runner
        assert context.count(DB_TEXT) == 1, runner

    shown = (await app.get(P, headers=auth_headers)).json()
    assert shown["content"] == DB_TEXT
    assert shown["source"] == "hub"
    assert shown["agents_md_offered"] is True
    assert shown["max_chars"] == MAX_INSTRUCTIONS_CHARS


@pytest.mark.asyncio
async def test_using_agents_md_is_not_offered_without_one(app, auth_headers, tmp_path) -> None:
    shown = (await app.get(P, headers=auth_headers)).json()
    assert shown["agents_md_offered"] is False
    refused = await app.put(f"{P}/source", json={"agents_md": True}, headers=auth_headers)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "no_agents_md"


@pytest.mark.asyncio
async def test_a_save_writes_the_file_and_commits_only_agents_md_on_main(
    app, auth_headers, tmp_path
) -> None:
    """ac-edit (FR-7) and ac-committed (FR-9)."""
    _repository(tmp_path)
    await _project(main_branch="main", instructions_in_agents_md=True)
    # Another change staged in the checkout is the operator's, and stays out of the commit.
    (tmp_path / "README.md").write_text("# readme, edited\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    before = _commits(tmp_path)

    shown = (await app.get(P, headers=auth_headers)).json()
    assert shown["content"] == OWN_AGENTS_MD
    assert shown["source"] == "agents_md"
    assert shown["agents_md_offered"] is False

    new_text = OWN_AGENTS_MD + "\nMARKER-SAVED: new rule.\n"
    saved = await app.put(P, json={"content": new_text}, headers=auth_headers)

    assert saved.status_code == 200, saved.text
    assert saved.json()["committed"] is True
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8") == new_text
    assert (await app.get(P, headers=auth_headers)).json()["content"] == new_text
    after = _commits(tmp_path)
    assert len(after) == len(before) + 1 and after[1:] == before
    assert _git(tmp_path, "show", "--name-only", "--format=", "main").split() == [AGENTS_MD]
    assert _git(tmp_path, "show", f"main:{AGENTS_MD}") == new_text
    # README's staged edit is still staged, uncommitted.
    assert _git(tmp_path, "diff", "--cached", "--name-only").split() == ["README.md"]
    # The database is not where these instructions live.
    assert await _database_row() == ""


@pytest.mark.asyncio
async def test_a_save_over_uncommitted_edits_is_refused_and_writes_nothing(
    app, auth_headers, tmp_path
) -> None:
    """ac-dirty-refused (FR-9)."""
    _repository(tmp_path)
    await _project(main_branch="main", instructions_in_agents_md=True)
    theirs = OWN_AGENTS_MD + "an edit the operator has not committed\n"
    (tmp_path / AGENTS_MD).write_text(theirs, encoding="utf-8", newline="\n")
    before = _commits(tmp_path)

    refused = await app.put(P, json={"content": "replacement"}, headers=auth_headers)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "agents_md_uncommitted"
    assert "uncommitted" in detail["message"] and AGENTS_MD in detail["message"]
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8") == theirs
    assert _commits(tmp_path) == before


@pytest.mark.asyncio
async def test_a_save_off_the_main_branch_is_refused_and_writes_nothing(
    app, auth_headers, tmp_path
) -> None:
    _repository(tmp_path)
    await _project(main_branch="main", instructions_in_agents_md=True)
    _git(tmp_path, "checkout", "--quiet", "-b", "elsewhere")

    refused = await app.put(P, json={"content": "replacement"}, headers=auth_headers)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "checkout_off_main"
    assert "elsewhere" in detail["message"] and "main" in detail["message"]
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8") == OWN_AGENTS_MD


@pytest.mark.asyncio
async def test_without_a_main_branch_the_file_is_written_and_said_not_committed(
    app, auth_headers, tmp_path
) -> None:
    _repository(tmp_path)
    await _project(main_branch=None, instructions_in_agents_md=True)
    before = _commits(tmp_path)

    saved = await app.put(P, json={"content": "written only"}, headers=auth_headers)

    assert saved.status_code == 200, saved.text
    assert saved.json()["committed"] is False
    assert "not committed" in saved.json()["notice"]
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8") == "written only"
    assert _commits(tmp_path) == before


@pytest.mark.asyncio
async def test_the_character_limit_still_applies_to_agents_md(app, auth_headers, tmp_path) -> None:
    _repository(tmp_path)
    await _project(main_branch="main", instructions_in_agents_md=True)

    refused = await app.put(
        P, json={"content": "x" * (MAX_INSTRUCTIONS_CHARS + 1)}, headers=auth_headers
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "instructions_too_long"
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8") == OWN_AGENTS_MD


@pytest.mark.asyncio
async def test_switching_on_moves_database_instructions_into_agents_md_once(
    app, auth_headers, add_agent, tmp_path
) -> None:
    """ac-moved (FR-10)."""
    _repository(tmp_path)
    await _project(main_branch="main")
    await _database_instructions(DB_TEXT)
    await add_agent("builder")
    before = _commits(tmp_path)

    switched = await app.put(f"{P}/source", json={"agents_md": True}, headers=auth_headers)

    assert switched.status_code == 200, switched.text
    body = switched.json()
    assert body["source"] == "agents_md" and body["committed"] is True
    on_disk = (tmp_path / AGENTS_MD).read_text(encoding="utf-8")
    assert on_disk.startswith(OWN_AGENTS_MD.rstrip("\n"))
    assert on_disk.count(DB_TEXT) == 1
    assert on_disk.index(PROJECT_INSTRUCTIONS_HEADING) < on_disk.index(DB_TEXT)
    after = _commits(tmp_path)
    assert len(after) == len(before) + 1
    assert _git(tmp_path, "show", "--name-only", "--format=", "main").split() == [AGENTS_MD]
    assert await _database_row() == DB_TEXT
    for runner in ADAPTERS:
        assert await _received(runner, tmp_path, DB_TEXT) == 1, runner

    # Off, and on again: the database row is what it was, and nothing is moved a second time.
    off = await app.put(f"{P}/source", json={"agents_md": False}, headers=auth_headers)
    assert off.json()["source"] == "hub" and off.json()["content"] == DB_TEXT
    again = await app.put(f"{P}/source", json={"agents_md": True}, headers=auth_headers)
    assert again.status_code == 200, again.text
    assert _commits(tmp_path) == after
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8").count(DB_TEXT) == 1


@pytest.mark.asyncio
async def test_switching_on_over_uncommitted_edits_is_refused_and_changes_nothing(
    app, auth_headers, tmp_path
) -> None:
    _repository(tmp_path)
    await _project(main_branch="main")
    await _database_instructions(DB_TEXT)
    theirs = OWN_AGENTS_MD + "uncommitted\n"
    (tmp_path / AGENTS_MD).write_text(theirs, encoding="utf-8", newline="\n")

    refused = await app.put(f"{P}/source", json={"agents_md": True}, headers=auth_headers)

    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "agents_md_uncommitted"
    assert (tmp_path / AGENTS_MD).read_text(encoding="utf-8") == theirs
    assert (await app.get(P, headers=auth_headers)).json()["source"] == "hub"


@pytest.mark.asyncio
async def test_every_runner_receives_the_instructions_exactly_once(
    app, auth_headers, add_agent, tmp_path
) -> None:
    """ac-once (FR-8): a runner that reads AGENTS.md natively (Codex) and one that does not
    (Claude) each receive the marker once."""
    marker = "MARKER-ONCE: the unique sentence."
    _repository(tmp_path, agents_md=f"# Ours\n\n{PROJECT_INSTRUCTIONS_HEADING}\n\n{marker}\n")
    await _project(main_branch="main", instructions_in_agents_md=True)
    # A database row is kept but not read while AGENTS.md is the source.
    await _database_instructions("MARKER-STALE-ROW")
    await add_agent("builder")

    assert ADAPTERS["codex"].reads_agents_md and not ADAPTERS["claude"].reads_agents_md
    for runner in ADAPTERS:
        assert await _received(runner, tmp_path, marker) == 1, runner
        assert "MARKER-STALE-ROW" not in await _context(runner), runner
    assert (await _context("claude")).count(marker) == 1
    assert "reads from your working directory" in await _context("codex")


def test_moved_instructions_land_in_the_instructions_area_once() -> None:
    created = f"# AgentWeave\n\n{PROJECT_INSTRUCTIONS_HEADING}\n\n<!-- below -->\n"
    moved = with_moved_instructions(created, "Rule one.")
    assert moved == f"{created.rstrip()}\n\nRule one.\n"
    assert with_moved_instructions(moved, "Rule one.") == moved
    assert with_moved_instructions(created, "  ") == created
    assert with_moved_instructions("# Theirs\n", "Rule.") == (
        f"# Theirs\n\n{PROJECT_INSTRUCTIONS_HEADING}\n\nRule.\n"
    )


# --- Where AgentWeave created the file, it is the instructions from the start ------------------

_REAL_RESOLVE = project_workspace.resolve_project_workspace


@pytest.mark.asyncio
async def test_a_project_created_in_a_new_folder_uses_its_agents_md(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _REAL_RESOLVE)
    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(tmp_path / "fresh"), "name": "Fresh"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    shown = await app.get(
        f"/api/v1/projects/{project_id}/project/instructions", headers=auth_headers
    )
    assert shown.json()["source"] == "agents_md"
    assert "AgentWeave" in shown.json()["content"]


@pytest.mark.asyncio
async def test_making_a_folder_a_repository_uses_the_agents_md_it_creates(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    """FR-11 and FR-10 together: the created file becomes the instructions, carrying the database
    instructions the project already had."""
    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _REAL_RESOLVE)
    root = tmp_path / "existing"
    root.mkdir()
    (root / "notes.txt").write_text("notes\n", encoding="utf-8")
    opened = await app.post("/api/v1/projects/open", json={"path": str(root)}, headers=auth_headers)
    project_id = opened.json()["id"]
    url = f"/api/v1/projects/{project_id}/project/instructions"
    await app.put(url, json={"content": DB_TEXT}, headers=auth_headers)
    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )

    made = await app.post(
        f"/api/v1/projects/{project_id}/repository",
        json={"files": preview.json()["files"]},
        headers=auth_headers,
    )

    assert made.status_code == 200, made.text
    shown = (await app.get(url, headers=auth_headers)).json()
    assert shown["source"] == "agents_md"
    assert shown["content"].count(DB_TEXT) == 1
    assert _git(root, "status", "--porcelain").strip() == ""
    assert len(_git(root, "rev-list", "main").split()) == 2
