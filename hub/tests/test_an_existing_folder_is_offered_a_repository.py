"""An existing folder is offered a repository, and is never made one unasked (FR-3, FR-5, FR-6).

Spec `a-new-project-starts-as-a-git-repository-with-an-agents-md`, task `make-it-a-repository`.
Opening a folder that is not a repository writes nothing into it but the Hub's marker. 'Make this a
git repository' first lists every file the first commit would hold, by the ignore rules the
repository will have, and creates nothing until the operator confirms that list.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hub import project_repository, project_workspace
from hub.project_repository import AGENTS_MD, AGENTS_MD_TEMPLATE
from hub.project_workspace import PROJECT_MARKER_VERSION

#: Taken at import, before conftest's autouse `_default_project_workspace` roots every project at
#: `tmp_path`: these tests are about the folder each project was really opened in.
_REAL_RESOLVE = project_workspace.resolve_project_workspace


@pytest.fixture(autouse=True)
def _projects_resolve_to_their_own_folders(monkeypatch) -> None:
    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _REAL_RESOLVE)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout


def _listing(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _outside_hub_folder(listing: dict[str, bytes]) -> dict[str, bytes]:
    return {name: data for name, data in listing.items() if not name.startswith(".agentweave/")}


def _existing_folder(tmp_path: Path, name: str = "existing") -> Path:
    root = tmp_path / name
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text("# Theirs\n", encoding="utf-8")
    (root / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    # Matched by the Hub's ignore rules (`repo_hygiene.EXCLUDE_PATTERNS`), so never committed.
    (root / "src" / "__pycache__").mkdir()
    (root / "src" / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00bytecode")
    return root


async def _open(app, auth_headers, root: Path) -> str:
    opened = await app.post("/api/v1/projects/open", json={"path": str(root)}, headers=auth_headers)
    assert opened.status_code == 200, opened.text
    return opened.json()["id"]


@pytest.mark.asyncio
async def test_opening_an_existing_folder_writes_nothing_but_the_hub_folder(
    app, auth_headers, tmp_path
) -> None:
    """ac-open-existing (FR-5)."""
    root = _existing_folder(tmp_path)
    before = _listing(root)

    await _open(app, auth_headers, root)

    assert not (root / ".git").exists()
    assert _outside_hub_folder(_listing(root)) == before


@pytest.mark.asyncio
async def test_the_preview_names_every_file_but_the_ignored_one_and_creates_nothing(
    app, auth_headers, tmp_path
) -> None:
    """ac-preview (FR-6): the list, then nothing written until the operator confirms."""
    root = _existing_folder(tmp_path)
    project_id = await _open(app, auth_headers, root)
    before = _listing(root)

    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["files"] == ["README.md", "src/main.py"]
    assert body["agents_md"] is True
    assert not (root / ".git").exists()
    assert _listing(root) == before

    confirmed = await app.post(
        f"/api/v1/projects/{project_id}/repository",
        json={"files": body["files"]},
        headers=auth_headers,
    )

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["main_branch"] == project_repository.MAIN_BRANCH
    commits = _git(root, "rev-list", "--all").split()
    assert len(commits) == 1
    committed = _git(root, "ls-tree", "-r", "--name-only", commits[0]).split()
    assert committed == sorted([AGENTS_MD, "README.md", "src/main.py"])
    assert (root / AGENTS_MD).read_text(encoding="utf-8") == AGENTS_MD_TEMPLATE
    # The ignored file and the Hub's own folder are still there, and are not untracked changes.
    assert (root / "src" / "__pycache__" / "main.cpython-311.pyc").is_file()
    assert _git(root, "status", "--porcelain", "--untracked-files=all").strip() == ""
    after = {name: data for name, data in _listing(root).items() if not name.startswith(".git/")}
    assert _outside_hub_folder(after) == {
        **_outside_hub_folder(before),
        AGENTS_MD: AGENTS_MD_TEMPLATE.encode("utf-8"),
    }


@pytest.mark.asyncio
async def test_the_preview_follows_the_folders_own_gitignore(app, auth_headers, tmp_path) -> None:
    """What `git add` would leave out under the folder's own rules is left out of the list too."""
    root = _existing_folder(tmp_path)
    (root / ".gitignore").write_text("secrets.env\n", encoding="utf-8")
    (root / "secrets.env").write_text("TOKEN=1\n", encoding="utf-8")
    (root / "notes ünïcode.md").write_text("x\n", encoding="utf-8")
    project_id = await _open(app, auth_headers, root)

    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )
    files = preview.json()["files"]
    assert files == sorted([".gitignore", "README.md", "notes ünïcode.md", "src/main.py"])

    confirmed = await app.post(
        f"/api/v1/projects/{project_id}/repository", json={"files": files}, headers=auth_headers
    )
    assert confirmed.status_code == 200, confirmed.text
    committed = _git(root, "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "HEAD")
    assert sorted(committed.splitlines()) == sorted([AGENTS_MD, *files])


@pytest.mark.asyncio
async def test_a_folder_that_changed_since_the_preview_is_refused_and_left_alone(
    app, auth_headers, tmp_path
) -> None:
    root = _existing_folder(tmp_path)
    project_id = await _open(app, auth_headers, root)
    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )
    (root / "new-since.txt").write_text("not shown\n", encoding="utf-8")

    refused = await app.post(
        f"/api/v1/projects/{project_id}/repository",
        json={"files": preview.json()["files"]},
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "preview_stale"
    assert not (root / ".git").exists()
    assert not (root / AGENTS_MD).exists()


@pytest.mark.asyncio
async def test_a_folder_that_is_already_a_repository_is_not_offered_one(
    app, auth_headers, tmp_path
) -> None:
    root = _existing_folder(tmp_path)
    _git(root, "init", "--quiet")
    project_id = await _open(app, auth_headers, root)

    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )
    confirm = await app.post(
        f"/api/v1/projects/{project_id}/repository", json={"files": []}, headers=auth_headers
    )

    assert preview.status_code == 409 and confirm.status_code == 409
    assert preview.json()["detail"]["code"] == "already_repository"


@pytest.mark.asyncio
async def test_a_failed_commit_removes_the_repository_and_only_what_it_wrote(
    app, auth_headers, tmp_path, monkeypatch
) -> None:
    root = _existing_folder(tmp_path)
    (root / "CLAUDE.md").write_text("theirs\n", encoding="utf-8")
    project_id = await _open(app, auth_headers, root)
    before = _listing(root)
    files = (
        await app.get(f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers)
    ).json()["files"]
    real = project_repository.initialise_repository

    def half_made(target: Path, **kwargs):
        real(target, **kwargs)
        raise project_repository.RepositoryInitError("git said no")

    monkeypatch.setattr(project_repository, "initialise_repository", half_made)

    refused = await app.post(
        f"/api/v1/projects/{project_id}/repository", json={"files": files}, headers=auth_headers
    )

    assert refused.status_code == 500, refused.text
    assert "git said no" in refused.text
    assert not (root / ".git").exists()
    assert _listing(root) == before


INSTRUCTION_FILES = [
    "CLAUDE.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    "AGENTS.md",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [*INSTRUCTION_FILES, ".agentweave/project.json"])
async def test_no_agents_md_is_created_or_changed_where_the_folder_already_instructs_its_agents(
    app, auth_headers, tmp_path, existing
) -> None:
    """ac-existing-instructions (FR-3), through the offered action.

    `.agentweave/project.json` is a marker the folder carried in before this Hub opened it -- an
    adopted project. The marker this Hub writes on opening a folder does not count (operator,
    2026-11-10); that case is the preview test above, which does get AGENTS.md.
    """
    root = _existing_folder(tmp_path)
    if existing == ".agentweave/project.json":
        marker = root / existing
        marker.parent.mkdir(parents=True)
        marker.write_text(
            json.dumps({"version": PROJECT_MARKER_VERSION, "project_id": "proj-carried0in"}),
            encoding="utf-8",
        )
    else:
        (root / existing).parent.mkdir(parents=True, exist_ok=True)
        (root / existing).write_text("theirs\n", encoding="utf-8")
    project_id = await _open(app, auth_headers, root)
    agents_before = (root / AGENTS_MD).read_bytes() if (root / AGENTS_MD).exists() else None

    preview = await app.get(
        f"/api/v1/projects/{project_id}/repository/preview", headers=auth_headers
    )
    assert preview.json()["agents_md"] is False
    confirmed = await app.post(
        f"/api/v1/projects/{project_id}/repository",
        json={"files": preview.json()["files"]},
        headers=auth_headers,
    )

    assert confirmed.status_code == 200, confirmed.text
    agents_after = (root / AGENTS_MD).read_bytes() if (root / AGENTS_MD).exists() else None
    assert agents_after == agents_before
    committed = _git(root, "ls-tree", "-r", "--name-only", "HEAD").split()
    assert committed == preview.json()["files"]
