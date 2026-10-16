"""F671: a Copilot worker call on a model the plan does not offer runs on Auto, as the turn does.

`copilot -p ... --model <id>` exits 1 with `Error: Model "<id>" from --model flag is not available.`
when the account's plan does not offer the id, while the same runner's ACP turn lets Copilot choose
(Auto). Found by the F665 live check: the checkpoint failed in 3 s with no credits. The one-shot
call now retries once without `--model` on exactly that refusal.
"""

import subprocess
from types import SimpleNamespace

from hub import worker

REFUSAL = 'Error: Model "claude-haiku-5.5" from --model flag is not available.\n'
CMD = ["C:\\copilot.exe", "-p", "Summarise.", "--output-format", "json", "--model", "claude-haiku-5.5"]


def _fake_run(results, seen):
    def run(cmd, **kwargs):
        seen.append(list(cmd))
        return results.pop(0)

    return run


def test_a_refused_model_is_retried_once_without_it(monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        _fake_run(
            [
                SimpleNamespace(returncode=1, stdout="", stderr=REFUSAL),
                SimpleNamespace(returncode=0, stdout='{"ok": 1}', stderr=""),
            ],
            seen,
        ),
    )
    spawn = worker._run_worker_process(list(CMD), None, 30)
    assert spawn.outcome == "ok", spawn
    assert spawn.stdout == '{"ok": 1}'
    assert seen == [CMD, CMD[:-2]], "the retry drops exactly the --model pair"


def test_any_other_failure_is_not_retried(monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        _fake_run([SimpleNamespace(returncode=1, stdout="", stderr="Error: not signed in\n")], seen),
    )
    spawn = worker._run_worker_process(list(CMD), None, 30)
    assert spawn.outcome == "nonzero_exit"
    assert len(seen) == 1


def test_a_refusal_naming_another_model_is_not_retried(monkeypatch):
    """Only the model the call itself named: a message about some other id is not this case."""
    seen = []
    monkeypatch.setattr(worker, "resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        _fake_run(
            [
                SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr='Error: Model "gpt-9" from --model flag is not available.\n',
                )
            ],
            seen,
        ),
    )
    spawn = worker._run_worker_process(list(CMD), None, 30)
    assert spawn.outcome == "nonzero_exit"
    assert len(seen) == 1


def test_a_failed_retry_reports_the_retry(monkeypatch):
    seen = []
    monkeypatch.setattr(worker, "resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(
        worker.subprocess,
        "run",
        _fake_run(
            [
                SimpleNamespace(returncode=1, stdout="", stderr=REFUSAL),
                SimpleNamespace(returncode=1, stdout="", stderr="Error: quota\n"),
            ],
            seen,
        ),
    )
    spawn = worker._run_worker_process(list(CMD), None, 30)
    assert spawn.outcome == "nonzero_exit"
    assert "quota" in spawn.error
    assert len(seen) == 2


def test_a_timeout_is_not_retried(monkeypatch):
    seen = []

    def run(cmd, **kwargs):
        seen.append(cmd)
        raise subprocess.TimeoutExpired(cmd, 30)

    monkeypatch.setattr(worker, "resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(worker.subprocess, "run", run)
    assert worker._run_worker_process(list(CMD), None, 30).outcome == "timeout"
    assert len(seen) == 1
