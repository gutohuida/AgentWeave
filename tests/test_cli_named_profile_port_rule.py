"""F723 / F732: every command that names a profile follows the one port rule.

F723: `doctor --profile X` without `--port` probed :8000 (the default profile's instance) beside
X's database. F732: `reset --profile X` ended "Run 'agentweave --profile X' to start fresh", a
command the CLI then refuses for want of `--port`.
"""

import pytest

from agentweave import cli, diagnostics


@pytest.fixture
def hub_home(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(diagnostics, "NATIVE_HUB_DIR", tmp_path)
    probed = []

    def _probe(port):
        probed.append(port)
        return diagnostics.ok("hub_running", f"port:{port}", "answering", category="environment")

    monkeypatch.setattr(diagnostics, "check_hub_instance", _probe)
    monkeypatch.setattr(diagnostics, "_port_is_available", lambda _p: True)
    return tmp_path, probed


def test_doctor_with_a_named_profile_and_no_port_is_refused(hub_home, capsys):
    _, probed = hub_home

    code = cli.main(["doctor", "--profile", "sweepdcli"])

    captured = capsys.readouterr()
    assert code == 1
    assert "needs an explicit --port" in captured.out + captured.err
    assert probed == []  # nothing was examined, least of all :8000


def test_doctor_with_a_named_profile_and_a_port_examines_that_port(hub_home, capsys):
    _, probed = hub_home

    cli.main(["doctor", "--json", "--profile", "sweepdcli", "--port", "8035"])

    assert probed == [8035]


def test_reset_of_a_named_profile_hints_a_command_the_cli_accepts(hub_home, capsys):
    tmp_path, _ = hub_home
    (tmp_path / "profiles" / "sweepdcli").mkdir(parents=True)

    assert cli.main(["reset", "--profile", "sweepdcli", "--yes"]) == 0

    out = capsys.readouterr().out
    hint = out.split("Run '", 1)[1].split("'", 1)[0]
    words = hint.split()[1:]
    profile = words[words.index("--profile") + 1]
    port = words[words.index("--port") + 1] if "--port" in words else None
    # The hinted command must pass the same rule that refused the old hint.
    assert cli._hub_require_port_for_named_profile(profile, port) is None


@pytest.mark.parametrize("port", [None, 8000, 8035])
def test_a_named_profiles_start_hint_always_names_a_port(port):
    assert "--port" in cli._hub_start_hint("beta", port)


def test_the_default_profiles_hint_is_unchanged():
    assert cli._hub_start_hint("default", None) == "agentweave"
    assert cli._hub_start_hint("default", 8000) == "agentweave"
    assert cli._hub_start_hint("default", 8010) == "agentweave --port 8010"
