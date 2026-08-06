"""GET /api/v1/fs/list (2026-08-04-hub-model-control-and-provisioning)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from hub.fs_browse import DirectoryBrowseError, list_directory, list_roots


def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "alpha").mkdir(parents=True)
    (root / "beta").mkdir()
    (root / "not-a-dir.txt").write_text("hello")
    return root


class TestListDirectoryUnit:
    def test_lists_directories_only_never_file_names(self, tmp_path):
        root = _make_tree(tmp_path)
        listing = list_directory(str(root))
        names = {e.name for e in listing.entries}
        assert names == {"alpha", "beta"}
        assert "not-a-dir.txt" not in names

    def test_returns_the_parent_path(self, tmp_path):
        root = _make_tree(tmp_path)
        listing = list_directory(str(root))
        assert listing.parent == str(root.parent)

    def test_a_relative_path_is_refused(self):
        with pytest.raises(DirectoryBrowseError):
            list_directory("relative/path")

    def test_a_bare_root_is_accepted_as_a_browsing_starting_point(self):
        # Found via live verification: Windows' pathlib.is_absolute() requires a drive
        # letter, so "/" alone (the directory picker's own default starting point) was
        # being wrongly refused as "not absolute" on that platform. "/" is anchored (has a
        # root) even without a drive, and resolve() fills the current drive in correctly.
        listing = list_directory("/")  # must not raise DirectoryBrowseError
        assert listing.path
        assert isinstance(listing.entries, list)

    def test_an_unreadable_directory_returns_an_empty_listing_with_a_reason(self, tmp_path):
        root = _make_tree(tmp_path)
        with patch("hub.fs_browse.os.scandir", side_effect=PermissionError("denied")):
            listing = list_directory(str(root))
        assert listing.entries == []
        assert listing.reason is not None

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation requires elevated privileges on Windows")
    def test_a_symlinked_directory_is_not_traversed(self, tmp_path):
        root = _make_tree(tmp_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / "escape-link").symlink_to(outside, target_is_directory=True)
        listing = list_directory(str(root))
        names = {e.name for e in listing.entries}
        assert "escape-link" not in names

    def test_workspace_root_bounds_listings_when_configured(self, tmp_path):
        root = _make_tree(tmp_path)
        outside = tmp_path / "outside-root"
        outside.mkdir()
        with patch("hub.fs_browse.configured_workspace_root", return_value=root):
            list_directory(str(root / "alpha"))  # inside — succeeds
            with pytest.raises(DirectoryBrowseError):
                list_directory(str(outside))

    def test_no_workspace_root_configured_allows_any_readable_directory(self, tmp_path):
        root = _make_tree(tmp_path)
        with patch("hub.fs_browse.configured_workspace_root", return_value=None):
            listing = list_directory(str(root))
        assert {e.name for e in listing.entries} == {"alpha", "beta"}


class TestListRootsUnit:
    """composer/chrome refinement §9.1."""

    def test_windows_reports_only_drives_present_in_the_logical_drive_bitmask(self):
        # Bit 0 (A) and bit 2 (C) set — B and every other letter absent.
        with patch("hub.fs_browse.os.name", "nt"):  # noqa: SIM117
            with patch(
                "hub.fs_browse.ctypes.windll.kernel32.GetLogicalDrives", return_value=0b101
            ):
                with patch("hub.fs_browse.configured_workspace_root", return_value=None):
                    roots = list_roots()
        assert [r.path for r in roots] == ["A:\\", "C:\\"]

    def test_posix_reports_the_single_root(self):
        with patch("hub.fs_browse.os.name", "posix"):  # noqa: SIM117
            with patch("hub.fs_browse.configured_workspace_root", return_value=None):
                roots = list_roots()
        assert [r.path for r in roots] == ["/"]

    def test_a_configured_workspace_root_replaces_the_os_roots(self, tmp_path):
        # An OS root is always an ancestor of a real workspace root, never a descendant —
        # filtering by containment would silently return nothing; the workspace root itself
        # is the only real starting point browsing can offer in that mode.
        with patch("hub.fs_browse.configured_workspace_root", return_value=tmp_path):
            roots = list_roots()
        assert [r.path for r in roots] == [str(tmp_path)]


class TestFsRootsEndpoint:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, app):
        response = await app.get("/api/v1/fs/roots")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_the_configured_roots(self, app, auth_headers):
        with patch("hub.api.v1.fs_browse.list_roots") as mocked:
            from hub.fs_browse import DirectoryEntry

            mocked.return_value = [DirectoryEntry(name="/", path="/")]
            response = await app.get("/api/v1/fs/roots", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"roots": [{"name": "/", "path": "/"}]}


class TestFsListEndpoint:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, app, tmp_path):
        response = await app.get("/api/v1/fs/list", params={"path": str(tmp_path)})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_lists_directories_only(self, app, auth_headers, tmp_path):
        root = _make_tree(tmp_path)
        response = await app.get(
            "/api/v1/fs/list", params={"path": str(root)}, headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        names = {e["name"] for e in body["entries"]}
        assert names == {"alpha", "beta"}
        assert body["path"] == str(root)
        assert body["parent"] == str(root.parent)

    @pytest.mark.asyncio
    async def test_a_relative_path_is_refused(self, app, auth_headers):
        response = await app.get(
            "/api/v1/fs/list", params={"path": "relative/path"}, headers=auth_headers
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unreadable_directory_reports_a_reason_not_an_error(
        self, app, auth_headers, tmp_path
    ):
        root = _make_tree(tmp_path)
        with patch("hub.fs_browse.os.scandir", side_effect=PermissionError("denied")):
            response = await app.get(
                "/api/v1/fs/list", params={"path": str(root)}, headers=auth_headers
            )
        assert response.status_code == 200
        body = response.json()
        assert body["entries"] == []
        assert body["reason"]
