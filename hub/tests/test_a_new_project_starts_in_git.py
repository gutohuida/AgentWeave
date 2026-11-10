"""A new project starts as a git repository with an AGENTS.md (FR-1 to FR-4).

Spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`, task `fresh-folder-repository`.
The acceptance drive: creating a project through the Hub in a folder that does not exist leaves a
repository whose single commit holds AGENTS.md alone, the Hub's own files ignored, and the
project's main branch naming the branch that commit is on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hub import project_repository
from hub.project_repository import (
    AGENTS_MD,
    AGENTS_MD_TEMPLATE,
    PROJECT_INSTRUCTIONS_HEADING,
    initialise_repository,
    should_create_agents_md,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.asyncio
async def test_a_project_created_in_a_new_folder_is_a_repository_with_one_commit_of_agents_md(
    app, auth_headers, tmp_path
) -> None:
    target = tmp_path / "fresh"
    assert not target.exists()

    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(target), "name": "Fresh"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    # FR-1: exactly one commit, holding AGENTS.md and nothing else.
    commits = _git(target, "rev-list", "--all").split()
    assert len(commits) == 1
    assert _git(target, "ls-tree", "-r", "--name-only", commits[0]).split() == [AGENTS_MD]

    # ... and the project's main branch names the branch that commit is on.
    branch = _git(target, "rev-parse", "--abbrev-ref", "HEAD").strip()
    assert _git(target, "rev-parse", branch).strip() == commits[0]
    settings = await app.get(f"/api/v1/projects/{project_id}/settings", headers=auth_headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["main_branch"] == branch

    # FR-2: the Hub has written .agentweave/ by now (the marker); none of it is untracked change.
    assert (target / ".agentweave" / "project.json").is_file()
    (target / ".agentweave" / "something-new.txt").write_text("hub scratch", encoding="utf-8")
    porcelain = _git(target, "status", "--porcelain", "--untracked-files=all")
    assert ".agentweave" not in porcelain
    assert porcelain.strip() == ""

    # FR-4: the file opens with the AgentWeave section, then an empty instructions area.
    content = (target / AGENTS_MD).read_text(encoding="utf-8")
    assert content == AGENTS_MD_TEMPLATE
    _assert_agentweave_section_then_empty_instructions(content)


def _assert_agentweave_section_then_empty_instructions(content: str) -> None:
    lines = content.splitlines()
    assert lines[0].startswith("# ") and "AgentWeave" in lines[0]
    assert "AgentWeave" in content.split(PROJECT_INSTRUCTIONS_HEADING)[0]
    assert "spec/" in content.split(PROJECT_INSTRUCTIONS_HEADING)[0]
    after = content.split(PROJECT_INSTRUCTIONS_HEADING, 1)[1]
    # Nothing but blank lines and comment lines (invisible when rendered) below the heading.
    assert all(
        not line.strip() or (line.strip().startswith("<!--") and line.strip().endswith("-->"))
        for line in after.splitlines()
    ), after


INSTRUCTION_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    ".agentweave/project.json",
]


@pytest.mark.parametrize("existing", INSTRUCTION_FILES)
def test_no_agents_md_is_written_where_the_folder_already_instructs_its_agents(
    tmp_path, existing
) -> None:
    """FR-3: the rule, and the repository action that applies it, leave such a folder alone."""
    root = tmp_path / "folder"
    path = root / existing
    path.parent.mkdir(parents=True)
    original = "theirs\n"
    path.write_text(original, encoding="utf-8")
    agents_before = (root / AGENTS_MD).read_bytes() if (root / AGENTS_MD).exists() else None

    assert should_create_agents_md(root) is False
    initialise_repository(root)

    agents_after = (root / AGENTS_MD).read_bytes() if (root / AGENTS_MD).exists() else None
    assert agents_after == agents_before
    assert path.read_text(encoding="utf-8") == original
    assert (root / ".git").is_dir()


def test_an_empty_folder_gets_agents_md(tmp_path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    assert should_create_agents_md(root) is True
    branch = initialise_repository(root)
    assert branch == project_repository.MAIN_BRANCH
    assert (root / AGENTS_MD).read_text(encoding="utf-8") == AGENTS_MD_TEMPLATE
    _assert_agentweave_section_then_empty_instructions(AGENTS_MD_TEMPLATE)


def test_the_first_commit_is_made_without_a_configured_git_identity(tmp_path, monkeypatch) -> None:
    """A machine with no user.name/user.email still gets its first commit."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    root = tmp_path / "anonymous"
    root.mkdir()

    initialise_repository(root)

    assert len(_git(root, "rev-list", "--all").split()) == 1


@pytest.mark.asyncio
async def test_a_repository_that_cannot_be_made_leaves_no_folder_and_no_project(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    real = project_repository.initialise_repository

    def half_made(root: Path, **kwargs):
        real(root, **kwargs)
        raise project_repository.RepositoryInitError("git said no")

    monkeypatch.setattr(project_repository, "initialise_repository", half_made)
    target = tmp_path / "doomed"

    refused = await app.post(
        "/api/v1/projects/create",
        json={"path": str(target), "name": "Doomed"},
        headers=auth_headers,
    )

    assert 400 <= refused.status_code < 500, refused.text
    assert "git said no" in refused.text
    assert not target.exists()
    listed = await app.get("/api/v1/projects", headers=auth_headers)
    assert all(row["name"] != "Doomed" for row in listed.json())


@pytest.mark.asyncio
async def test_a_hub_with_no_git_still_creates_the_project_as_a_plain_folder(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    """The Hub's Docker image ships no git; creating a project there keeps working as before."""
    real_run = subprocess.run

    def no_git(command, *args, **kwargs):
        if command and command[0] == "git":
            raise FileNotFoundError("git")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(project_repository.subprocess, "run", no_git)
    target = tmp_path / "gitless"

    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(target), "name": "Gitless"},
        headers=auth_headers,
    )

    assert created.status_code == 201, created.text
    assert not (target / ".git").exists()
    assert not (target / AGENTS_MD).exists()


@pytest.mark.asyncio
async def test_a_writing_agent_in_the_fresh_project_gets_its_own_worktree_and_branch(
    app, auth_headers, tmp_path
) -> None:
    """ac-first-worktree's precondition at the seam: the first commit is what lets a worktree be
    made. An empty repository (`git init` alone) is refused by `ensure_worktree`."""
    from hub import worktrees

    target = tmp_path / "fresh-worktree"
    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(target), "name": "Fresh worktree"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    worktree = worktrees.ensure_worktree(target, "Writer")

    assert worktree != target and worktree.is_dir()
    assert (worktree / AGENTS_MD).is_file()
    assert _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").strip() == worktrees.branch_name(
        "Writer"
    )
    # The agent's checkout is ignored by the primary one.
    assert _git(target, "status", "--porcelain", "--untracked-files=all").strip() == ""
