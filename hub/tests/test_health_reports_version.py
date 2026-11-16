"""`/health` reports the Hub's version and how it was installed (`agentweave-updates-itself`, FR-1)."""

import json
from types import SimpleNamespace

import pytest

from hub import version as version_mod
from hub.version import __version__


@pytest.mark.asyncio
async def test_health_reports_version_and_install(app, monkeypatch):
    monkeypatch.setattr("hub.main.install_kind", lambda: "pip")
    resp = await app.get("/health")
    body = resp.json()
    assert body["version"] == __version__
    assert body["install"] == "pip"
    # The fields the CLI already reads are untouched.
    assert body["status"] == "ok"
    assert "runtime" in body


def _dist(direct_url):
    return SimpleNamespace(read_text=lambda name: direct_url)


@pytest.mark.parametrize(
    "direct_url, expected",
    [
        (None, "pip"),
        (json.dumps({"url": "file:///x", "dir_info": {"editable": True}}), "editable"),
        (json.dumps({"url": "file:///x", "dir_info": {}}), "checkout"),
        (json.dumps({"url": "file:///x.whl", "archive_info": {"hashes": {}}}), "pip"),
        (json.dumps({"url": "git+https://x", "vcs_info": {"vcs": "git"}}), "checkout"),
        ("not json", "checkout"),
    ],
)
def test_install_kind_from_direct_url(monkeypatch, direct_url, expected):
    monkeypatch.setattr("importlib.metadata.distribution", lambda name: _dist(direct_url))
    assert version_mod.install_kind() == expected


def test_install_kind_without_metadata_is_checkout(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.distribution", missing)
    assert version_mod.install_kind() == "checkout"


@pytest.mark.asyncio
async def test_health_reports_checkout_commit_and_branch(app, monkeypatch):
    monkeypatch.setattr("hub.main.checkout_state", lambda: {"commit": "a" * 40, "branch": "master"})
    body = (await app.get("/health")).json()
    assert body["commit"] == "a" * 40
    assert body["branch"] == "master"


@pytest.mark.asyncio
async def test_health_omits_commit_outside_a_checkout(app, monkeypatch):
    monkeypatch.setattr("hub.main.checkout_state", lambda: {})
    body = (await app.get("/health")).json()
    assert "commit" not in body and "branch" not in body


def test_checkout_state_reads_a_real_clone(tmp_path):
    import subprocess

    def git(*a):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q", "-b", "trunk")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    state = version_mod._read_checkout(tmp_path)
    assert state == {"commit": git("rev-parse", "HEAD"), "branch": "trunk"}


def test_checkout_state_empty_without_git(tmp_path):
    assert version_mod._read_checkout(tmp_path) == {}
