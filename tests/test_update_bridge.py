"""The app window's update bridge (cli._AppWindowApi.update_status / set_auto_update / apply_update).

The launcher's updater (`agentweave.updater`) is stood in for by a fake module, so this checks the
bridge's own seam: what it asks the updater, what it hands the page, and that it reloads the
window after an update ends and never raises.
"""

import json
import sys
import types

import pytest

from agentweave import cli


class _Result:
    def __init__(self, state, detail=""):
        self.state = state
        self.detail = detail


class _Window:
    def __init__(self):
        self.js = []

    def evaluate_js(self, code):
        self.js.append(code)


@pytest.fixture
def updater(monkeypatch, tmp_path):
    fake = types.ModuleType("agentweave.updater")
    fake.calls = []
    fake.installed_version = lambda name: "2.1.0"
    fake.known_latest = lambda path: ("2.1.1", True)
    fake.is_newer = lambda a, b: a != b
    fake.installation_kind = lambda: "pip"
    fake.auto_update_on = lambda path: True
    fake.set_auto_update = lambda path, on, kind="pip": fake.calls.append(("auto", on))

    def apply_update(applier, confirmed, work, describe):
        fake.calls.append(("apply", confirmed))
        if not confirmed:
            return _Result("needs_confirm", describe(work()))
        return _Result("applied")

    fake.apply_update = apply_update
    fake.write_json = lambda path, data: path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setitem(sys.modules, "agentweave.updater", fake)
    import agentweave

    monkeypatch.setattr(agentweave, "updater", fake, raising=False)
    monkeypatch.setattr(cli, "updater", fake)
    for name in ("_update_check_file", "_update_setting_file"):
        monkeypatch.setattr(cli, name, lambda n=name: tmp_path / n, raising=False)
    monkeypatch.setattr(cli, "HUB_DIR", tmp_path)
    (tmp_path / "app-window").mkdir()
    monkeypatch.setattr(cli, "_update_applier", lambda *a: object(), raising=False)
    # A pip install: no git checkout behind the Hub package (the checkout half has its own tests,
    # tests/test_updater_checkout.py).
    monkeypatch.setattr(cli, "_hub_checkout_root", lambda: None)
    monkeypatch.setattr(cli, "_hub_work_running", lambda port: {"running": True, "turns": 1})
    return fake


def _bridge(port=8171, profile="default"):
    bridge = cli._AppWindowApi(cli._AppWindowCloser(port, profile))
    bridge._window = _Window()
    return bridge


def test_status_names_version_and_work(updater):
    status = _bridge().update_status()
    assert status["current"] == "2.1.0" and status["latest"] == "2.1.1"
    assert status["available"] and status["applicable"] and status["auto"]
    assert status["work"] == {"running": True, "description": "1 agent turn is running"}


def test_unanswered_work_check_counts_as_work(updater, monkeypatch):
    monkeypatch.setattr(cli, "_hub_work_running", lambda port: None)
    assert _bridge().update_status()["work"]["running"] is True


def test_status_reads_the_last_failure(updater, tmp_path):
    cli._update_result_file(8171).write_text(
        '{"state": "failed", "detail": "migration broke"}', encoding="utf-8"
    )
    assert _bridge().update_status()["message"]["detail"] == "migration broke"


def test_a_failure_on_one_hub_is_not_shown_in_another_hubs_window(updater):
    """DCUSW-6: the drive's dirty-step Hub, on its own port and profile, read the failed-start
    step's failure from the other Hub."""
    updater.apply_update = lambda applier, confirmed, work, describe: _Result(
        "failed", "master did not start"
    )
    assert _bridge(8171, "d1107a").apply_update(True)["state"] == "failed"
    assert _bridge(8171, "d1107a").update_status()["message"]["detail"] == "master did not start"
    assert _bridge(8172, "d1107b").update_status()["message"] is None  # another port and profile
    assert _bridge(8172, "d1107a").update_status()["message"] is None  # another port
    assert _bridge(8171, "default").update_status()["message"] is None  # another profile


def test_a_failure_stops_showing_once_seen_or_a_later_update_succeeds(updater):
    updater.apply_update = lambda applier, confirmed, work, describe: _Result("failed", "boom")
    bridge = _bridge()
    bridge.apply_update(True)
    assert bridge.update_status()["message"]["state"] == "failed"
    assert bridge.dismiss_update_message() is True
    assert _bridge().update_status()["message"] is None  # seen: not shown at the next launch
    assert bridge.dismiss_update_message() is True  # nothing left to dismiss is not an error

    bridge.apply_update(True)
    assert _bridge().update_status()["message"]["state"] == "failed"
    updater.apply_update = lambda applier, confirmed, work, describe: _Result("applied")
    bridge.apply_update(True)
    assert _bridge().update_status()["message"]["state"] == "applied"  # no failure shown


def test_apply_asks_then_applies_and_reloads(updater):
    bridge = _bridge()
    first = bridge.apply_update(False)
    assert first["state"] == "needs_confirm" and "agent turn" in first["detail"]
    assert bridge._window.js == []  # cancelled or waiting: nothing reloaded
    assert bridge.apply_update(True)["state"] == "applied"
    assert bridge._window.js == ["window.location.reload()"]
    assert updater.calls == [("apply", False), ("apply", True)]


def test_failed_apply_is_recorded_before_the_reload_so_the_window_states_it(updater):
    updater.apply_update = lambda applier, confirmed, work, describe: _Result(
        "failed", "migration broke"
    )
    bridge = _bridge()
    assert bridge.apply_update(True)["state"] == "failed"
    assert bridge._window.js == ["window.location.reload()"]
    assert (
        json.loads(cli._update_result_file(8171).read_text(encoding="utf-8"))["state"] == "failed"
    )
    assert bridge.update_status()["message"]["detail"] == "migration broke"


def test_apply_with_no_applier_fails_and_set_auto_saves(updater, monkeypatch):
    monkeypatch.setattr(cli, "_update_applier", lambda *a: None, raising=False)
    assert _bridge().apply_update(True)["state"] == "failed"
    assert _bridge().set_auto_update(False) is True
    assert ("auto", False) in updater.calls
