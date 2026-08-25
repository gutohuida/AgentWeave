"""F34: the documented command form must be the one that works, and a running instance must be
described as what it actually is."""

import argparse
import json

import pytest


class TestGlobalPortReachesTheSubcommand:
    """A subparser argument sharing a dest with a global one overwrites it in the same namespace
    when the subcommand omits it. `--help` documents the global form, and that was the one that
    silently did nothing — measured against a Hub confirmed live, it reported `stopped`."""

    def _parse(self, argv):
        from agentweave.cli import create_parser

        return create_parser().parse_args(argv)

    def test_the_documented_form_takes_effect(self):
        assert self._parse(["--port", "8010", "status"]).port == 8010

    def test_the_subcommand_form_still_works(self):
        assert self._parse(["status", "--port", "8010"]).port == 8010

    def test_the_value_nearer_the_subcommand_wins(self):
        assert self._parse(["--port", "8010", "status", "--port", "9999"]).port == 9999

    def test_neither_leaves_the_default(self):
        assert self._parse(["status"]).port is None

    @pytest.mark.parametrize("command", ["status", "stop", "reset"])
    def test_the_global_profile_reaches_every_subcommand_that_takes_one(self, command):
        assert self._parse(["--profile", "beta", command]).profile == "beta"

    @pytest.mark.parametrize("command", ["status", "stop"])
    def test_the_global_port_reaches_every_subcommand_that_takes_one(self, command):
        assert self._parse(["--port", "8010", command]).port == 8010


class TestTheRunningInstanceIsDescribedAsWhatItIs:
    """The CLI used to call a natively started process `docker`, because it inferred the mode from
    whether it found a PID file it had written itself."""

    def _run(self, monkeypatch, capsys, *, health, pid=None):
        import contextlib

        from agentweave import cli

        class _Resp:
            status = 200

            def read(self):
                return json.dumps(health).encode()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(cli, "_hub_pid_running", lambda **kw: pid)
        monkeypatch.setattr(cli, "_hub_project_status_summary", lambda port: "")
        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
        with contextlib.suppress(SystemExit):
            cli.cmd_status(argparse.Namespace(port=8010, profile="default"))
        return capsys.readouterr().out

    def test_a_native_instance_says_native(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, health={"status": "ok", "runtime": "native"})
        assert "running (native)" in out

    def test_a_container_says_docker(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, health={"status": "ok", "runtime": "docker"})
        assert "running (docker)" in out

    def test_a_hand_started_hub_is_not_called_docker(self, monkeypatch, capsys):
        """The measured failure: no PID file this CLI wrote, so it concluded `docker` about a
        `uvicorn` process on the host."""
        out = self._run(monkeypatch, capsys, health={"status": "ok", "runtime": "native"}, pid=None)
        assert "docker" not in out

    def test_an_older_hub_that_says_nothing_is_not_guessed_about(self, monkeypatch, capsys):
        """A Hub predating the `runtime` field is described without a mode rather than assigned
        one. Absence of evidence is not evidence of a container."""
        out = self._run(monkeypatch, capsys, health={"status": "ok"}, pid=None)
        assert "running" in out
        assert "docker" not in out
        assert "native" not in out

    def test_a_pid_file_still_proves_native_on_an_older_hub(self, monkeypatch, capsys):
        out = self._run(monkeypatch, capsys, health={"status": "ok"}, pid=4321)
        assert "running (native)" in out
        assert "4321" in out


class TestDoctorExaminesTheInstanceTheProjectUses:
    """F34's second half. Run from a project bound to a Hub on another port, `doctor` probed 8000
    and the default profile's database — neither of which was that project's Hub — and returned
    every check passing without having examined the running instance at all."""

    def test_the_profile_decides_which_database_is_checked(self):
        from agentweave import diagnostics

        default = diagnostics._profile_data_dir("default")
        named = diagnostics._profile_data_dir("beta")

        assert default.name == "data"
        assert named.parent.name == "profiles"
        assert named.name == "beta"

    def test_doctor_follows_the_profile(self):
        """`diagnostics` restates `cli._hub_profile_data_dir` rather than importing it, because
        `cli` imports `diagnostics`. This is what stops the two drifting apart."""
        from agentweave import diagnostics
        from agentweave.cli import _hub_profile_data_dir

        for profile in ("default", "beta", "trial"):
            assert diagnostics._profile_data_dir(profile) == _hub_profile_data_dir(profile)

    def test_an_unreachable_hub_is_reported_rather_than_omitted(self, monkeypatch):
        from agentweave import diagnostics

        def _boom(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr("urllib.request.urlopen", _boom)

        result = diagnostics.check_hub_instance(8010)

        assert result.status == "warn"
        assert result.id == "hub_not_running"
        assert "8010" in result.message
        assert result.hint

    def test_a_running_hub_reports_what_it_is(self, monkeypatch):
        from agentweave import diagnostics

        _install_health(monkeypatch, {"status": "ok", "runtime": "native"})

        result = diagnostics.check_hub_instance(8010)

        assert result.status == "pass"
        assert "native" in result.message

    def test_a_stale_bundle_is_surfaced_by_doctor_too(self, monkeypatch):
        from agentweave import diagnostics

        _install_health(
            monkeypatch,
            {"status": "ok", "runtime": "docker", "ui_stale": True, "ui_stale_detail": "rebuild"},
        )

        result = diagnostics.check_hub_instance(8010)

        assert result.status == "warn"
        assert result.hint == "rebuild"

    def test_the_operators_own_hub_holding_its_port_is_not_a_failure(self, monkeypatch):
        """A running Hub occupies its port. Reporting that as a conflict would make every healthy
        system report a failure."""
        from agentweave import diagnostics

        monkeypatch.setattr(diagnostics, "_port_is_available", lambda _p: False)

        result = diagnostics.check_port_availability(8010, hub_answered=True)

        assert result.status == "pass"

    def test_something_else_holding_the_port_is_still_a_failure(self, monkeypatch):
        """The signal that must survive: an occupied port with no Hub on it is a real conflict."""
        from agentweave import diagnostics

        monkeypatch.setattr(diagnostics, "_port_is_available", lambda _p: False)

        result = diagnostics.check_port_availability(8010, hub_answered=False)

        assert result.status == "fail"
        assert result.id == "hub_port_unavailable"
        assert result.hint

    def test_the_port_and_profile_reach_the_checks(self, monkeypatch):
        from agentweave import diagnostics

        seen = {}

        def _instance(port):
            seen["port"] = port
            return diagnostics.ok("x", "y", "z", category="environment")

        def _database(profile="default"):
            seen["profile"] = profile
            return diagnostics.ok("db", "y", "z", category="environment")

        monkeypatch.setattr(diagnostics, "check_hub_instance", _instance)
        monkeypatch.setattr(diagnostics, "check_database_accessibility", _database)
        monkeypatch.setattr(diagnostics, "_port_is_available", lambda _p: True)

        diagnostics.collect_diagnostics(port=8010, profile="beta")

        assert seen["port"] == 8010
        assert seen["profile"] == "beta"


def _install_health(monkeypatch, payload):
    import json as _json

    class _Resp:
        status = 200

        def read(self):
            return _json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
