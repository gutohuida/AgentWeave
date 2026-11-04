"""F1121: a drive's port follows AW_DRIVE_PORT, and a drive stops only a Hub it started."""

import importlib.util
import pathlib
import subprocess

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "drive"
    / "d1029_build_plan_in_spec.py"
)


def _load(monkeypatch, tmp_path, port):
    profile = tmp_path / ".agentweave" / "hub" / "profiles" / "trial"
    profile.mkdir(parents=True)
    (profile / "bootstrap-key.txt").write_text("aw_live_test", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    if port is None:
        monkeypatch.delenv("AW_DRIVE_PORT", raising=False)
    else:
        monkeypatch.setenv("AW_DRIVE_PORT", port)
    spec = importlib.util.spec_from_file_location("d1029_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_port_defaults_to_the_trial_hub(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path, None)
    assert module.PORT == 8010
    assert module.HUB == "http://127.0.0.1:8010"


def test_the_port_follows_the_environment_variable(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path, "8123")
    assert module.PORT == 8123
    assert module.HUB == "http://127.0.0.1:8123"


def test_a_hub_found_running_is_not_stopped(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path, "8123")
    monkeypatch.setattr(module, "api", lambda *a, **k: (200, []))
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    proc = module.start_hub()
    assert proc is None
    module.stop_hub(proc)
    assert calls == []


def test_a_hub_it_started_is_stopped(monkeypatch, tmp_path):
    module = _load(monkeypatch, tmp_path, "8123")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))

    class Started:
        pid = 4242

    module.stop_hub(Started())
    assert len(calls) == 1 and "4242" in calls[0][0]
