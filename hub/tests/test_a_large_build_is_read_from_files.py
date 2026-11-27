"""A build too large for one call is read from files by a runner that can read them, and divided
again by the provider's own count when a runner that cannot is refused a part as too long.

`spdoc-857c9e7dd18e`'s retrospective failed on 2026-11-27: its record was 2.76M characters, split
in two parts sized at three characters to a token, and the provider counted the first part at
1,006,909 tokens against a 1,000,000 window. As in `test_build_retrospective.py` the worker is
faked; here the fake also looks into the folder it is handed while the call runs.
"""

import json
import os
from pathlib import Path

import pytest

from hub import build_retrospective as br
from hub.runner_adapters.one_shot import OneShotFailure
from hub.worker import WorkerResult, WorkerUsage

from .test_build_retrospective import (
    _configure,
    _document,
    _fire,
    _listed,
    _seed,
    _task,
    finding,
)

LIMIT = 11_000
NOTE = "x" * 3000
TASKS = ("t1", "t2", "t3", "t4")


def _ok(answer):
    return WorkerResult(
        "ok",
        parsed=answer,
        usage=WorkerUsage(input_tokens=11, output_tokens=7, cost_usd_micros=100),
        duration_ms=5,
    )


def _too_long(prompt_tokens, limit_tokens=1_000_000):
    return WorkerResult(
        "nonzero_exit",
        exit_code=1,
        error="exited 1: Prompt is too long",
        failure=OneShotFailure(
            reason="Prompt is too long",
            too_large=True,
            prompt_tokens=prompt_tokens,
            limit_tokens=limit_tokens,
        ),
    )


class _Reader:
    """Answers every call; a reading call's folder is listed and read while the call runs."""

    def __init__(self, answer=None, refuse_inline=False) -> None:
        self.answer = answer or br.RetrospectiveAnswer(lessons=[finding("read it", "t1")])
        self.refuse_inline = refuse_inline
        self.calls = []

    async def __call__(self, **kwargs):
        folder = kwargs.get("cwd")
        files = {}
        if folder:
            for root, _dirs, names in os.walk(folder):
                for name in names:
                    path = Path(root, name)
                    files[path.relative_to(folder).as_posix()] = path.read_text(encoding="utf-8")
        self.calls.append({**kwargs, "files": files})
        if self.refuse_inline and kwargs["prompt_version"] == br.PROMPT_VERSION:
            return _too_long(1_006_909)
        return _ok(self.answer)


async def _four_tasks():
    await _seed(
        _document(),
        *[_task(task, status="approved", notes=f"{task}-marker {NOTE}") for task in TASKS],
    )


def _index(call):
    prompt = call["prompt"]
    start = prompt.index(br.RECORD_START) + len(br.RECORD_START)
    return json.loads(prompt[start : prompt.index(br.RECORD_END)])


@pytest.mark.asyncio
async def test_a_build_too_large_for_one_call_is_read_from_files(app, auth_headers, monkeypatch):
    monkeypatch.setattr(br, "input_limit", lambda model: LIMIT)
    fake = _Reader()
    monkeypatch.setattr(br, "run_worker", fake)
    await _configure(app, auth_headers)
    await _four_tasks()
    assert await _fire() == "written"

    (call,) = fake.calls  # one call, no parts and no last call
    assert call["prompt_version"] == br.READING_PROMPT_VERSION
    assert call["reading"] is True and call["cwd"]
    assert call["system"].startswith(br._FILES_READING)
    assert "copied exactly from the files or the message" in call["system"]
    # The message is the index, not the record: no task's notes are in it.
    assert NOTE not in call["prompt"]
    index = _index(call)
    assert [task["id"] for task in index["files"]["tasks"]] == list(TASKS)
    for task in index["files"]["tasks"]:
        held = call["files"][task["file"]]
        assert f"{task['id']}-marker" in held
        assert all(len(line) <= br.LINE_LIMIT for line in held.splitlines())
        # A note longer than a line is wrapped, and none of it is lost.
        assert held.replace("\n", "").count("x" * 3000) == 1
    assert "build.json" in call["files"]
    assert len(index["figures"]["per_task_time"]) == 4
    # The folder is the call's own, and gone once it returned.
    assert not os.path.exists(call["cwd"])

    (listed,) = await _listed(app, auth_headers)
    assert [row["text"] for row in listed["report"]["lessons"]] == ["read it"]
    assert listed["parts"] == 1


@pytest.mark.asyncio
async def test_a_build_refused_as_too_long_after_all_is_read_from_files(
    app, auth_headers, monkeypatch
):
    fake = _Reader(refuse_inline=True)
    monkeypatch.setattr(br, "run_worker", fake)
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1", status="approved", notes="short"))
    assert await _fire() == "written"
    assert [call["prompt_version"] for call in fake.calls] == [
        br.PROMPT_VERSION,
        br.READING_PROMPT_VERSION,
    ]


def test_a_transcript_is_a_file_of_its_own_and_the_run_names_it(tmp_path):
    run = {"id": "run-1", "flags": ["sent back"], "transcript": "[text] " + "y" * 4000}
    whole = {
        "document": {"id": "d"},
        "builds": [],
        "tasks": [
            {
                "id": "t1",
                "readable_id": "TSBVD-5",
                "title": "drive",
                "status": "approved",
                "transitions": [],
                "runs": [run, {"id": "run-2", "flags": [], "transcript": None}],
            }
        ],
        "send_backs": [],
        "other_runs": [{"id": "run/3", "flags": ["mender"], "transcript": "z"}],
        "other_evidence": [],
        "other_stalls": [],
        "amendments_and_reconciles": [],
        "requirements_without_accepted_evidence": [],
        "figures": {},
    }
    index = br.write_record_files(tmp_path, whole)

    (task,) = index["files"]["tasks"]
    assert task["file"] == "tasks/TSBVD-5.json"
    assert task["transcripts"] == [
        {"run_id": "run-1", "flags": ["sent back"], "file": "transcripts/run-1.txt"}
    ]
    held = (tmp_path / "tasks/TSBVD-5.json").read_text(encoding="utf-8")
    assert "y" * 100 not in held and '"transcript_file": "transcripts/run-1.txt"' in held
    transcript = (tmp_path / "transcripts/run-1.txt").read_text(encoding="utf-8")
    assert transcript.replace("\n", "") == "[text] " + "y" * 4000
    # An id is a file name only once it is safe as one.
    assert (tmp_path / "transcripts/run_3.txt").read_text(encoding="utf-8") == "z\n"
    assert index["files"]["build"]["other_runs"] == 1


@pytest.mark.asyncio
async def test_a_part_refused_as_too_long_divides_the_build_by_the_providers_count(
    app, auth_headers, monkeypatch
):
    """A runner that cannot read files: the first division's part is refused, with a count that
    says the characters ran at one to a token, and the build is divided again to fit it."""
    monkeypatch.setattr(br, "input_limit", lambda model: 15_000)
    monkeypatch.setattr(br, "reads_files", lambda cli: False)
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        size = len(kwargs["prompt"])
        if size > 12_000:  # one character to a token, against a 12,000-token window
            return _too_long(prompt_tokens=size, limit_tokens=12_000)
        return _ok(br.RetrospectiveAnswer(lessons=[finding("divided", "t1")]))

    monkeypatch.setattr(br, "run_worker", fake)
    await _configure(app, auth_headers)
    await _seed(
        _document(),
        *[
            _task(task, status="approved", notes=f"{task}-marker {'x' * 2000}")
            for task in (*TASKS, "t5", "t6", "t7", "t8")
        ],
    )
    assert await _fire() == "written"

    parts = [c for c in calls if c["prompt_version"] == br.PART_PROMPT_VERSION]
    refused = [c for c in parts if len(c["prompt"]) > 12_000]
    assert len(refused) == 1 and parts[0] is refused[0]
    # Divided again at 12,000 tokens x one character x the usable share: every part fits.
    assert len(parts) > 2
    assert all(len(c["prompt"]) <= 9_600 for c in parts[1:])
    assert calls[-1]["prompt_version"] == br.FINAL_PROMPT_VERSION
