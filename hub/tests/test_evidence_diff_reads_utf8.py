"""F760: the evidence diff reads git's output as UTF-8 and names a non-ASCII path as itself.

`requirement_evidence._git` ran `text=True` with no encoding, so on a cp1252 machine git's UTF-8
bytes were decoded as cp1252 (a 500 when a byte had no mapping, mojibake otherwise), and
`core.quotepath` left a non-ASCII path quoted so the `diff --git` header never matched and the
file showed +0 -0 with no patch. Real repositories, never the checkout.
"""

import subprocess
from pathlib import Path

from hub.requirement_evidence import work_diff


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "base.txt").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _commit(repo: Path, branch: str, name: str, text: str) -> str:
    _git(repo, "checkout", "-q", "-b", branch)
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "work")
    return _git(repo, "rev-parse", "HEAD")


def test_content_with_a_byte_cp1252_cannot_decode_is_read_not_a_crash(tmp_path):
    repo = _repo(tmp_path)
    sha = _commit(repo, "work", "notes.md", 'name = "Ángel → café"\n')

    result = work_diff(repo, sha, "main")

    assert [file["path"] for file in result["files"]] == ["notes.md"]
    assert '+name = "Ángel → café"' in result["files"][0]["patch"]


def test_a_non_ascii_path_is_named_as_itself_with_its_patch(tmp_path):
    repo = _repo(tmp_path)
    sha = _commit(repo, "work", "todo/ñandú.py", "x = 1\n")

    result = work_diff(repo, sha, "main")

    assert [file["path"] for file in result["files"]] == ["todo/ñandú.py"]
    assert "+x = 1" in result["files"][0]["patch"]
