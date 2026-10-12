"""F455: `doctor --port N` without `--profile` checked the default profile's database and called
it accessible, although the Hub on N served a named profile's. The profile is recoverable: a
profile's Hub records itself in `hub-<profile>-<port>.pid`."""

import json
import os

import pytest

from agentweave import cli, diagnostics


@pytest.fixture
def hub_home(tmp_path, monkeypatch):
    """Point both modules at one scratch Hub directory, so no real ~/.agentweave is read."""
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    monkeypatch.setattr(diagnostics, "NATIVE_HUB_DIR", tmp_path)
    monkeypatch.setattr(
        diagnostics,
        "check_hub_instance",
        lambda port: diagnostics.ok(
            "hub_running", f"port:{port}", "answering", category="environment"
        ),
    )
    monkeypatch.setattr(diagnostics, "_port_is_available", lambda _p: True)
    return tmp_path


def _database_target(capsys, **namespace) -> str:
    # Through the real parser: its global `--profile` defaults to "default", which a hand-built
    # Namespace leaves out (the first version of this test passed while the fix could not fire).
    argv = ["doctor", "--json", "--no-network"]
    if "port" in namespace:
        argv += ["--port", str(namespace["port"])]
    if "profile" in namespace:
        argv += ["--profile", namespace["profile"]]
    cli.main(argv)
    results = json.loads(capsys.readouterr().out)["results"]
    (database,) = [r for r in results if r["id"].startswith("database_")]
    return database["target"].replace("\\", "/")


def _register(hub_home, profile, port, pid=None):
    (hub_home / f"hub-{profile}-{port}.pid").write_text(f"{pid or os.getpid()}\n{port}")


def test_a_port_alone_checks_the_database_of_the_profile_serving_it(hub_home, capsys):
    _register(hub_home, "sweep0925", 8030)

    target = _database_target(capsys, port=8030)

    assert target.endswith("/profiles/sweep0925/agentweave.db")


def test_a_profile_with_a_dash_in_its_name_is_found(hub_home, capsys):
    _register(hub_home, "my-trial", 8030)

    assert _database_target(capsys, port=8030).endswith("/profiles/my-trial/agentweave.db")


def test_an_explicit_profile_still_wins(hub_home, capsys):
    _register(hub_home, "sweep0925", 8030)

    target = _database_target(capsys, port=8030, profile="other")

    assert target.endswith("/profiles/other/agentweave.db")


def test_a_stale_pid_file_is_not_believed(hub_home, capsys):
    _register(hub_home, "sweep0925", 8030, pid=2**22 + 12345)

    assert _database_target(capsys, port=8030).endswith("/data/agentweave.db")


def test_another_ports_profile_is_not_borrowed(hub_home, capsys):
    _register(hub_home, "sweep0925", 8031)

    assert _database_target(capsys, port=8030).endswith("/data/agentweave.db")


def test_no_port_and_no_profile_is_the_default_profile(hub_home, capsys):
    _register(hub_home, "sweep0925", 8030)

    assert _database_target(capsys).endswith("/data/agentweave.db")
