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
