"""`a-redistilled-fact-keeps-its-id` (F587, F617).

A re-distil keeps, under its id and unchanged, every earlier fact drawn again from the same lines
(same source and span, the quote equal but for case, spacing and trailing punctuation); facts drawn
from other lines are new, and the earlier ones not drawn again are deleted. A fact that is gone is
warned of as gone, and a private entry whose holder is this machine says its text is missing here.
The worker is faked; the real spawn is `scripts/drive/d1015_f587_redistil_keeps_ids.py`.
"""

import json
import shutil
from pathlib import Path

import pytest

from hub import distillation, vault
from hub.distillation import Distilled, FactDraft
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
TRANSCRIPT = (
    "Kickoff with Acme.\n"
    "Dana: customers may return goods\n"
    "within 30 days of purchase.\n"
    "Dana: the refund limit is 437 euros.\n"
)


@pytest.fixture
def worker(monkeypatch):
    def install(*answers):
        queue = list(answers)

        async def fake(**_kwargs) -> WorkerResult:
            answer = queue.pop(0) if queue else []
            drafts = [FactDraft(claim=claim, quotes=quotes) for claim, quotes in answer]
            return WorkerResult("ok", parsed=Distilled(facts=drafts))

        monkeypatch.setattr(distillation, "run_worker", fake)

    return install


async def _ready(app, auth_headers, **upload) -> str:
    runner = await app.post(
        f"{BASE}/runners",
        json={"name": "distiller", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
        headers=auth_headers,
    )
    assert runner.status_code == 201, runner.text
    job = await app.patch(
        f"{BASE}/manager/jobs/vault-distillation",
        json={"enabled": True, "runner_id": runner.json()["id"]},
        headers=auth_headers,
    )
    assert job.status_code == 200, job.text
    body = {"name": "Acme kickoff", "type": "transcript", "content": TRANSCRIPT, **upload}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _facts(folder: Path) -> dict:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("fct-*.json"))
    }


@pytest.mark.asyncio
async def test_a_fact_drawn_again_from_the_same_lines_keeps_its_id_and_record(
    app, auth_headers, worker, tmp_path
) -> None:
    worker(
        [
            ("Refunds up to 437 euros need no approval.", ["the refund limit is 437 euros."]),
            ("Returns within 30 days.", ["within 30 days of purchase."]),
        ],
        [
            # The same line, quoted without its period and with a doubled space: the same fact.
            ("The refund limit is 437 euros.", ["the refund limit is  437 euros"]),
            # The same claim from another line: new evidence, a new fact.
            ("Returns within 30 days.", ["customers may return goods"]),
            ("Acme had a kickoff.", ["Kickoff with Acme."]),
        ],
    )
    source = await _ready(app, auth_headers)
    folder = tmp_path / "knowledge" / "facts"
    first = _facts(folder)
    refund = next(i for i, f in first.items() if "437" in f["claim"])
    returns = next(i for i, f in first.items() if "30" in f["claim"])
    before = (folder / f"{refund}.json").read_bytes()

    distilled = await app.post(f"{BASE}/vault/sources/{source}/distil", headers=auth_headers)

    assert distilled.status_code == 202, distilled.text
    second = _facts(folder)
    assert refund in second and (folder / f"{refund}.json").read_bytes() == before
    assert returns not in second
    assert len(second) == 3


@pytest.mark.asyncio
async def test_each_earlier_fact_is_kept_at_most_once(app, auth_headers, worker, tmp_path) -> None:
    quote = ["the refund limit is 437 euros."]
    worker(
        [("Refunds up to 437 euros.", quote)],
        [("Refunds up to 437 euros.", quote), ("Managers sign above 437.", quote)],
    )
    source = await _ready(app, auth_headers)
    folder = tmp_path / "knowledge" / "facts"
    [kept] = _facts(folder)

    await app.post(f"{BASE}/vault/sources/{source}/distil", headers=auth_headers)

    after = _facts(folder)
    assert kept in after and len(after) == 2


@pytest.mark.asyncio
async def test_only_new_facts_are_checked_against_the_vault(
    app, auth_headers, worker, monkeypatch
) -> None:
    checked: list = []

    async def record(_plan, ids, **_kwargs) -> None:
        checked.append(list(ids))

    monkeypatch.setattr(distillation, "_check", record)
    worker(
        [("Refunds up to 437 euros.", ["the refund limit is 437 euros."])],
        [
            ("Refunds up to 437 euros.", ["the refund limit is 437 euros."]),
            ("Returns within 30 days.", ["within 30 days of purchase."]),
        ],
    )
    source = await _ready(app, auth_headers)
    await app.post(f"{BASE}/vault/sources/{source}/distil", headers=auth_headers)

    first, second = checked
    assert first[0] not in second and len(second) == 1


def test_a_fact_in_no_record_or_stub_is_warned_of_as_gone(tmp_path) -> None:
    project, private = tmp_path / "project", tmp_path / "private"
    project.mkdir()

    [warning] = vault.fact_warnings(project, private, ["fct-0123456789ab"])["fct-0123456789ab"]

    assert warning["kind"] == "missing"
    assert "no longer in the vault" in warning["message"]
    assert "machine" not in warning["message"]


@pytest.mark.asyncio
async def test_a_private_entry_held_here_without_its_text_says_so(
    app, auth_headers, worker
) -> None:
    worker()
    source = await _ready(app, auth_headers, visibility="private")
    shutil.rmtree(vault.default_private_location("proj-test"))

    read = await app.get(f"{BASE}/vault/entries/{source}", headers=auth_headers)

    assert read.status_code == 200, read.text
    note = read.json()["note"]
    assert "not at this machine's private location" in note
    assert "held on" not in note
