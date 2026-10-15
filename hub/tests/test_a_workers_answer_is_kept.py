"""`a-workers-answer-is-kept` (F581).

Each manager firing that spawned a model keeps what the model answered: its raw text, else its
parsed answer as JSON, cut at 8,000 characters with a marker; a spawn that returned nothing keeps
null. The worker is faked; the real spawn is `scripts/drive/d1015_f581_answer_kept.py`.
"""

import pytest

from hub import distillation, manager
from hub.distillation import Distilled, FactDraft
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
TEXT = "Kickoff with Acme.\nDana: the refund limit is 437 euros.\n"


def test_the_answer_is_the_raw_text_else_the_parsed_answer_and_is_cut() -> None:
    parsed = Distilled(facts=[FactDraft(claim="Limit 437.", quotes=["437 euros"])])

    assert manager.answer_record(WorkerResult("ok", answer_text="raw words", parsed=parsed)) == (
        "raw words"
    )
    assert "Limit 437." in manager.answer_record(WorkerResult("ok", parsed=parsed))
    assert manager.answer_record(WorkerResult("spawn_failed", error="boom")) is None
    cut = manager.answer_record(WorkerResult("ok", answer_text="x" * 9000))
    assert cut.startswith("x" * manager.ANSWER_CHARS) and cut.endswith(manager.ANSWER_CUT)
    assert len(cut) == manager.ANSWER_CHARS + len(manager.ANSWER_CUT)


@pytest.fixture
def distil_job(app, auth_headers, monkeypatch):
    async def ready(answer: WorkerResult) -> list:
        async def fake(**_kwargs) -> WorkerResult:
            return answer

        monkeypatch.setattr(distillation, "run_worker", fake)
        runner = await app.post(
            f"{BASE}/runners",
            json={"name": "d", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
            headers=auth_headers,
        )
        assert runner.status_code == 201, runner.text
        job = await app.patch(
            f"{BASE}/manager/jobs/vault-distillation",
            json={"enabled": True, "runner_id": runner.json()["id"]},
            headers=auth_headers,
        )
        assert job.status_code == 200, job.text
        created = await app.post(
            f"{BASE}/vault/sources",
            json={"name": "Acme", "type": "transcript", "content": TEXT},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        listed = await app.get(
            f"{BASE}/manager/activity?job=vault-distillation", headers=auth_headers
        )
        assert listed.status_code == 200, listed.text
        return listed.json()["firings"]

    return ready


@pytest.mark.asyncio
async def test_a_distillation_firing_lists_what_the_model_answered(distil_job) -> None:
    drafts = [
        FactDraft(claim="Refunds up to 437 euros.", quotes=["the refund limit is 437 euros."])
    ]

    [firing] = await distil_job(WorkerResult("ok", parsed=Distilled(facts=drafts)))

    assert firing["outcome"] == "written"
    assert "Refunds up to 437 euros." in firing["answer"]


@pytest.mark.asyncio
async def test_a_failed_spawn_keeps_no_answer(distil_job) -> None:
    [firing] = await distil_job(WorkerResult("spawn_failed", error="boom"))

    assert firing["outcome"] == "failed"
    assert firing["answer"] is None
