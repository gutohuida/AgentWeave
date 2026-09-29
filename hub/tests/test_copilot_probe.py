"""`resolve_copilot_executable` (design D2): find the real `copilot.exe`, never the npm
JS shim `pty_runner.resolve_executable` deliberately leaves alone (`pty_runner.py:57-60`).

The module does not exist yet, so every test below fails at collection today
(`ModuleNotFoundError: No module named 'hub.copilot_probe'`) — task 3.1 adds it.
"""

from __future__ import annotations

import shutil

import pytest

from hub.copilot_probe import CopilotExecutableNotFound, resolve_copilot_executable


def _npm_shim(tmp_path, name="copilot.cmd"):
    """An npm-installed `copilot.cmd`: a JS shim that forwards to `npm-loader.js`,
    with the package tree `resolve_copilot_executable` walks to find the real binary.
    """
    shim = tmp_path / name
    shim.write_text('@ECHO off\r\nnode "%~dp0node_modules\\@github\\copilot\\npm-loader.js" %*\r\n')
    pkg_dir = tmp_path / "node_modules" / "@github" / "copilot"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "npm-loader.js").write_text("module.exports = require('./cli.js');\n")
    return shim, pkg_dir


class TestResolveCopilotExecutable:
    def test_npm_shim_with_platform_package_resolves_to_the_exe(self, tmp_path, monkeypatch):
        shim, pkg_dir = _npm_shim(tmp_path)
        platform_dir = pkg_dir / "node_modules" / "@github" / "copilot-win32-x64"
        platform_dir.mkdir(parents=True)
        real_exe = platform_dir / "copilot.exe"
        real_exe.write_text("")

        monkeypatch.setattr(shutil, "which", lambda name: str(shim))
        monkeypatch.setattr("hub.copilot_probe.platform.system", lambda: "Windows")
        monkeypatch.setattr("hub.copilot_probe.platform.machine", lambda: "AMD64")

        resolved = resolve_copilot_executable(None)
        assert resolved == real_exe.resolve()

    def test_shim_with_no_platform_package_raises_naming_the_looked_for_path(
        self, tmp_path, monkeypatch
    ):
        shim, pkg_dir = _npm_shim(tmp_path)
        # No node_modules/@github/copilot-win32-x64 under the package — the optional
        # platform dependency never installed (wrong OS/arch, or a broken install).
        expected_path = pkg_dir / "node_modules" / "@github" / "copilot-win32-x64" / "copilot.exe"

        monkeypatch.setattr(shutil, "which", lambda name: str(shim))
        monkeypatch.setattr("hub.copilot_probe.platform.system", lambda: "Windows")
        monkeypatch.setattr("hub.copilot_probe.platform.machine", lambda: "AMD64")

        with pytest.raises(CopilotExecutableNotFound) as exc_info:
            resolve_copilot_executable(None)
        assert str(expected_path) in str(exc_info.value)

    def test_native_executable_on_path_is_used_as_is(self, tmp_path, monkeypatch):
        native = tmp_path / "copilot.exe"
        native.write_text("")
        monkeypatch.setattr(shutil, "which", lambda name: str(native))

        resolved = resolve_copilot_executable(None)
        assert resolved == native.resolve()

    def test_pinned_override_that_is_a_cmd_is_refused(self, tmp_path, monkeypatch):
        """The pinned `cli` override (D2 step 1) must be a native executable, not a script —
        it is never unwrapped the way a `shutil.which` hit is."""
        pinned = tmp_path / "copilot.cmd"
        pinned.write_text('@ECHO off\r\n"%~dp0copilot.exe" %*\r\n')

        with pytest.raises(CopilotExecutableNotFound):
            resolve_copilot_executable(str(pinned))
