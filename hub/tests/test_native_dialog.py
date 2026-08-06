"""hub/native_dialog.py + GET/POST /api/v1/fs/native-dialog/* (composer/chrome
refinement §7)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hub import native_dialog


def _fake_process(*, stdout=b"", stderr=b"", returncode=0, hang_forever=False):
    proc = MagicMock()
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    if hang_forever:
        async def _communicate():
            await asyncio.sleep(3600)
        proc.communicate = _communicate
    else:
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


class TestOpenFolderDialogUnit:
    @pytest.mark.asyncio
    async def test_chosen_path_is_returned(self):
        with patch("hub.native_dialog.check_availability", return_value=native_dialog.AvailabilityResult(available=True)):  # noqa: SIM117
            with patch(
                "hub.native_dialog.asyncio.create_subprocess_exec",
                AsyncMock(return_value=_fake_process(stdout=b"CHOSEN:C:\\Users\\op\\project")),
            ):
                result = await native_dialog.open_folder_dialog()
        assert result.outcome == "chosen"
        assert result.path == "C:\\Users\\op\\project"

    @pytest.mark.asyncio
    async def test_cancel_is_distinct_from_failure(self):
        with patch("hub.native_dialog.check_availability", return_value=native_dialog.AvailabilityResult(available=True)):  # noqa: SIM117
            with patch(
                "hub.native_dialog.asyncio.create_subprocess_exec",
                AsyncMock(return_value=_fake_process(stdout=b"CANCELLED")),
            ):
                result = await native_dialog.open_folder_dialog()
        assert result.outcome == "cancelled"
        assert result.path is None

    @pytest.mark.asyncio
    async def test_timeout_kills_the_subprocess_and_is_not_reported_as_failure(self):
        proc = _fake_process(hang_forever=True)
        with patch("hub.native_dialog.check_availability", return_value=native_dialog.AvailabilityResult(available=True)):  # noqa: SIM117
            with patch("hub.native_dialog.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
                result = await native_dialog.open_folder_dialog(timeout_seconds=0.05)
        assert result.outcome == "timeout"
        proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_nonzero_exit_is_reported_as_failure(self):
        with patch("hub.native_dialog.check_availability", return_value=native_dialog.AvailabilityResult(available=True)):  # noqa: SIM117
            with patch(
                "hub.native_dialog.asyncio.create_subprocess_exec",
                AsyncMock(return_value=_fake_process(stderr=b"Tcl error", returncode=1)),
            ):
                result = await native_dialog.open_folder_dialog()
        assert result.outcome == "failed"
        assert "Tcl error" in result.detail

    @pytest.mark.asyncio
    async def test_unavailable_short_circuits_before_any_subprocess_spawns(self):
        spawn = AsyncMock()
        with patch(  # noqa: SIM117
            "hub.native_dialog.check_availability",
            return_value=native_dialog.AvailabilityResult(available=False, reason="no desktop session"),
        ):
            with patch("hub.native_dialog.asyncio.create_subprocess_exec", spawn):
                result = await native_dialog.open_folder_dialog()
        assert result.outcome == "unavailable"
        assert result.detail == "no desktop session"
        spawn.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_second_request_while_one_is_open_opens_no_second_dialog(self):
        proc = _fake_process(hang_forever=True)
        with patch("hub.native_dialog.check_availability", return_value=native_dialog.AvailabilityResult(available=True)):  # noqa: SIM117
            with patch("hub.native_dialog.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
                first = asyncio.create_task(native_dialog.open_folder_dialog(timeout_seconds=1))
                await asyncio.sleep(0.01)  # let the first request actually acquire the lock
                with pytest.raises(native_dialog.DialogBusyError):
                    await native_dialog.open_folder_dialog()
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first


class TestNativeDialogEndpoints:
    @pytest.mark.asyncio
    async def test_availability_endpoint_reports_the_reason_when_unavailable(self, app, auth_headers):
        with patch(
            "hub.api.v1.native_dialog.native_dialog.check_availability",
            return_value=native_dialog.AvailabilityResult(available=False, reason="Unsupported platform: 'linux'"),
        ):
            resp = await app.get("/api/v1/fs/native-dialog/availability", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["reason"] == "Unsupported platform: 'linux'"

    @pytest.mark.asyncio
    async def test_availability_endpoint_requires_auth(self, app):
        resp = await app.get("/api/v1/fs/native-dialog/availability")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_open_endpoint_returns_the_chosen_path(self, app, auth_headers):
        with patch(
            "hub.api.v1.native_dialog.native_dialog.open_folder_dialog",
            AsyncMock(return_value=native_dialog.DialogResult(outcome="chosen", path="C:\\chosen")),
        ):
            resp = await app.post("/api/v1/fs/native-dialog/open", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"outcome": "chosen", "path": "C:\\chosen", "detail": None}

    @pytest.mark.asyncio
    async def test_open_endpoint_reports_busy_as_409_not_a_generic_error(self, app, auth_headers):
        with patch(
            "hub.api.v1.native_dialog.native_dialog.open_folder_dialog",
            AsyncMock(side_effect=native_dialog.DialogBusyError("already open")),
        ):
            resp = await app.post("/api/v1/fs/native-dialog/open", headers=auth_headers)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_hub_answers_another_request_while_a_dialog_is_open(self, app, auth_headers):
        release = asyncio.Event()

        async def _slow_open():
            await release.wait()
            return native_dialog.DialogResult(outcome="cancelled")

        with patch("hub.api.v1.native_dialog.native_dialog.open_folder_dialog", _slow_open):
            dialog_task = asyncio.create_task(
                app.post("/api/v1/fs/native-dialog/open", headers=auth_headers)
            )
            await asyncio.sleep(0.01)  # let the dialog request actually start and block

            health = await app.get("/health")
            assert health.status_code == 200
            assert not dialog_task.done()  # the dialog call is still pending, proving

            release.set()
            dialog_resp = await dialog_task
            assert dialog_resp.status_code == 200


class TestCheckAvailability:
    def test_unsupported_platform_is_reported_by_name(self):
        with patch("hub.native_dialog.sys.platform", "linux"):
            result = native_dialog.check_availability()
        assert result.available is False
        assert "linux" in result.reason

    def test_supported_platform_without_interactive_desktop_is_unavailable(self):
        with patch("hub.native_dialog.is_supported_platform", return_value=True):  # noqa: SIM117
            with patch("hub.native_dialog._has_interactive_desktop", return_value=False):
                result = native_dialog.check_availability()
        assert result.available is False
        assert "desktop" in result.reason.lower()

    def test_supported_platform_with_interactive_desktop_is_available(self):
        with patch("hub.native_dialog.is_supported_platform", return_value=True):  # noqa: SIM117
            with patch("hub.native_dialog._has_interactive_desktop", return_value=True):
                result = native_dialog.check_availability()
        assert result.available is True
        assert result.reason is None
