"""The manager distils vault sources into cited facts.

`the-manager-distils-vault-sources-into-cited-facts` (Tier 2). The worker is faked throughout: a
test hands `distillation.run_worker` the facts a model would answer, so what is checked is what the
Hub does with them -- where quotes are found, which facts are kept, what is written where, and
what is recorded. The real spawn is the acceptance drive's (`scripts/drive/d1016_distillation.py`).
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import distillation, manager, vault
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
JOB = "vault-distillation"
HAIKU = "claude-haiku-4-5-20251001"
TRANSCRIPT = (
    "Kickoff with Acme.\n"
    "Dana: customers may return goods\n"
    "within 30 days of purchase.\n"
    "Dana: the refund limit is 437 euros.\n"
)


class _Worker:
    """Stands in for `run_worker`: answers each call with the next scripted answer.

    An answer is a list of (claim, [quotes]) pairs, or None for a spawn that failed."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list = []

    async def __call__(self, **kwargs) -> WorkerResult:
        self.calls.append(kwargs)
        answer = self.answers.pop(0) if self.answers else []
        if callable(answer):
            answer = answer(kwargs["prompt"])
        if answer is None:
            return WorkerResult("spawn_failed", error="boom")
        parsed = distillation.Distilled(
            facts=[distillation.FactDraft(claim=claim, quotes=quotes) for claim, quotes in answer]
        )
        return WorkerResult("ok", parsed=parsed)


@pytest.fixture
def worker(monkeypatch):
    def install(*answers) -> _Worker:
        fake = _Worker(*answers)
        monkeypatch.setattr(distillation, "run_worker", fake)
        return fake

    return install


async def _runner(app, auth_headers, model=HAIKU) -> str:
    payload = {"name": "distiller", "cli": "claude", "model": model}
    created = await app.post(f"{BASE}/runners", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _enable(app, auth_headers, **fields) -> dict:
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"enabled": True, **fields}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _upload(app, auth_headers, content=TRANSCRIPT, **fields) -> dict:
    body = {"name": "Acme kickoff", "type": "transcript", "content": content, **fields}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _distil(app, auth_headers, source_id: str):
    return await app.post(f"{BASE}/vault/sources/{source_id}/distil", headers=auth_headers)


async def _firings() -> list:
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog)
                    .where(EventLog.event_type == manager.FIRED_EVENT)
                    .order_by(EventLog.timestamp, EventLog.id)
                )
            )
            .scalars()
            .all()
        )
    return [row.data for row in rows if (row.data or {}).get("job") == JOB]


def _facts(folder: Path) -> list:
    if not folder.is_dir():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("fct-*.json"))
    ]


def _files(root: Path) -> list:
    if not root.exists():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# distillation-job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_job_is_listed_disabled_with_nothing_chosen(app, auth_headers) -> None:
    listed = await app.get(f"{BASE}/manager/jobs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    job = next(job for job in listed.json()["jobs"] if job["key"] == JOB)
    assert job["enabled"] is False
    assert job["runner_id"] is None and job["model"] is None
    assert job["trigger"] == "source_uploaded"
    assert job["title"] and job["description"]


@pytest.mark.asyncio
async def test_the_jobs_model_wins_over_the_runners(app, auth_headers, worker) -> None:
    fake = worker([], [])
    runner_id = await _runner(app, auth_headers)
    await _enable(app, auth_headers, runner_id=runner_id)
    source = await _upload(app, auth_headers)
    assert fake.calls[-1]["model"] == HAIKU
    assert fake.calls[-1]["runner_id"] == runner_id

    await _enable(app, auth_headers, model="claude-sonnet-4-6")
    answered = await _distil(app, auth_headers, source["id"])
    assert answered.status_code == 202, answered.text
    assert fake.calls[-1]["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_with_no_runner_nothing_is_spawned_or_recorded(app, auth_headers, worker) -> None:
    fake = worker()
    await _enable(app, auth_headers)
    source = await _upload(app, auth_headers)
    refused = await _distil(app, auth_headers, source["id"])
    assert refused.status_code == 409, refused.text
    assert "runner" in refused.json()["detail"].lower()
    assert fake.calls == []
    assert await _firings() == []


# ---------------------------------------------------------------------------
# fact-cited
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quotes_are_found_in_the_source_and_unfound_ones_drop_the_fact(
    app, auth_headers, worker, tmp_path
) -> None:
    worker(
        [
            ("The refund limit without approval is 437 euros.", ["the refund limit is 437 euros."]),
            # The model joined two lines with one space: found with whitespace collapsed.
            (
                "Goods may be returned within 30 days.",
                ["customers may return goods within 30 days of purchase."],
            ),
            ("Deliveries happen on weekdays.", ["Deliveries happen only on weekdays."]),
        ]
    )
    await _enable(app, auth_headers, runner_id=await _runner(app, auth_headers))
    source = await _upload(app, auth_headers)

    facts = {fact["claim"]: fact for fact in _facts(tmp_path / "knowledge" / "facts")}
    assert set(facts) == {
        "The refund limit without approval is 437 euros.",
        "Goods may be returned within 30 days.",
    }
    refund = facts["The refund limit without approval is 437 euros."]
    assert refund["id"].startswith("fct-") and len(refund["id"]) == 16
    assert refund["visibility"] == "tracked"
    assert refund["made_by"] == {"job": JOB, "model": HAIKU}
    assert refund["citations"] == [
        {
            "source": source["id"],
            "quote": "the refund limit is 437 euros.",
            "line_start": 4,
            "line_end": 4,
        }
    ]
    returns = facts["Goods may be returned within 30 days."]["citations"][0]
    assert (returns["line_start"], returns["line_end"]) == (2, 3)

    [firing] = await _firings()
    assert firing["outcome"] == "written"
    assert firing["subject"] == {"source": source["id"]}
    assert firing["trigger"] == "source_uploaded"
    assert firing["model"] == HAIKU
    assert "2 facts stored" in firing["detail"] and "1 dropped" in firing["detail"]


def test_locate_spans_and_misses() -> None:
    text = "one\ntwo three\nfour\n  five   six\n"
    assert distillation.locate(text, "two three") == (2, 2)
    assert distillation.locate(text, "three\nfour") == (2, 3)
    assert distillation.locate(text, "three four five six") == (2, 4)
    assert distillation.locate(text, "seven") is None
    assert distillation.locate(text, "   ") is None


# ---------------------------------------------------------------------------
# pieces-and-firings
# ---------------------------------------------------------------------------


def _long_source() -> str:
    return "".join(f"line {i:05d} ".ljust(99, "x") + "\n" for i in range(1200))


def test_pieces_are_at_most_the_limit_and_end_at_a_line_break() -> None:
    text = _long_source()
    assert len(text) == 120_000
    pieces = distillation.pieces(text)
    assert len(pieces) == 3
    assert "".join(pieces) == text
    for piece in pieces:
        assert len(piece) <= distillation.PIECE_CHARS
        assert piece.endswith("\n")


def _quote_first_line(prompt: str):
    marker = prompt.index("line ", prompt.index(distillation.SOURCE_START))
    line = prompt[marker : prompt.index("\n", marker)]
    return [(f"A fact from {line[:10]}.", [line])]


@pytest.mark.asyncio
async def test_each_piece_is_one_spawn_and_one_firing(app, auth_headers, worker) -> None:
    fake = worker(_quote_first_line, None, _quote_first_line)
    await _enable(app, auth_headers, runner_id=await _runner(app, auth_headers))
    await _upload(app, auth_headers, content=_long_source())
    assert len(fake.calls) == 3
    assert [f["outcome"] for f in await _firings()] == ["written", "failed", "written"]
    assert all(call["kind"] == JOB for call in fake.calls)


# ---------------------------------------------------------------------------
# distil-on-upload, distil-route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_disabled_job_spawns_nothing_on_upload(app, auth_headers, worker, tmp_path) -> None:
    fake = worker()
    runner_id = await _runner(app, auth_headers)
    await _enable(app, auth_headers, runner_id=runner_id)
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"enabled": False}, headers=auth_headers
    )
    assert patched.status_code == 200
    source = await _upload(app, auth_headers)
    assert fake.calls == []
    assert await _firings() == []
    assert not (tmp_path / "knowledge" / "facts").exists()

    refused = await _distil(app, auth_headers, source["id"])
    assert refused.status_code == 409, refused.text
    assert "disabled" in refused.json()["detail"].lower()


@pytest.mark.asyncio
async def test_the_route_refuses_what_it_cannot_distil(app, auth_headers, worker, tmp_path) -> None:
    worker()
    await _enable(app, auth_headers, runner_id=await _runner(app, auth_headers))
    missing = await _distil(app, auth_headers, "src-ffffffffffff")
    assert missing.status_code == 404, missing.text

    sources = tmp_path / "knowledge" / "sources"
    sources.mkdir(parents=True)
    stub = {
        "id": "src-0123456789ab",
        "name": "Colleague's notes",
        "type": "note",
        "visibility": "private",
        "created_at": "2026-10-01T00:00:00.000000Z",
        "holder": "colleague-laptop",
    }
    (sources / "src-0123456789ab.json").write_text(json.dumps(stub), encoding="utf-8")
    foreign = await _distil(app, auth_headers, "src-0123456789ab")
    assert foreign.status_code == 409, foreign.text
    assert "colleague-laptop" in foreign.json()["detail"]


@pytest.mark.asyncio
async def test_a_run_that_stores_nothing_keeps_the_facts_and_one_that_stores_replaces(
    app, auth_headers, worker, tmp_path
) -> None:
    worker(
        [("Refunds up to 437 euros need no approval.", ["the refund limit is 437 euros."])],
        [("Invented.", ["not in the source at all"])],
        [("Returns within 30 days.", ["within 30 days of purchase."])],
    )
    await _enable(app, auth_headers, runner_id=await _runner(app, auth_headers))
    source = await _upload(app, auth_headers)
    folder = tmp_path / "knowledge" / "facts"
    [first] = _facts(folder)

    assert (await _distil(app, auth_headers, source["id"])).status_code == 202
    assert [fact["id"] for fact in _facts(folder)] == [first["id"]]

    assert (await _distil(app, auth_headers, source["id"])).status_code == 202
    [replaced] = _facts(folder)
    assert replaced["claim"] == "Returns within 30 days."
    assert [f["outcome"] for f in await _firings()] == ["written", "empty", "written"]


# ---------------------------------------------------------------------------
# private-facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_private_sources_facts_stay_private(
    app, auth_headers, worker, tmp_path, tmp_path_factory
) -> None:
    private = tmp_path_factory.mktemp("private-vault")
    put = await app.put(
        f"{BASE}/vault/settings", json={"private_location": str(private)}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    note = "Internal.\nRule CANARY-9d1e: invoices above 5,000 euros need two signatures.\n"
    worker([("Invoices above 5,000 euros need two signatures.", ["Rule CANARY-9d1e: invoices"])])
    await _enable(app, auth_headers, runner_id=await _runner(app, auth_headers))
    source = await _upload(app, auth_headers, content=note, visibility="private")

    [fact] = _facts(private / "facts")
    assert fact["visibility"] == "private"
    assert fact["citations"][0]["source"] == source["id"]
    stub = json.loads(
        (tmp_path / "knowledge" / "facts" / f"{fact['id']}.json").read_text(encoding="utf-8")
    )
    assert stub["visibility"] == "private" and stub["sources"] == [source["id"]]
    assert "claim" not in stub and "citations" not in stub
    leaked = [
        p
        for p in _files(tmp_path)
        if not p.startswith(".git/")
        and any(
            marker in (tmp_path / p).read_text(encoding="utf-8", errors="replace")
            for marker in ("CANARY-9d1e", "5,000")
        )
    ]
    assert leaked == []


def test_a_tracked_fact_never_cites_a_private_source(tmp_path) -> None:
    private = tmp_path / "private"
    source = vault.add_source(
        tmp_path / "proj", private, name="n", type="note", content="a\n", visibility="private"
    )
    with pytest.raises(vault.VaultError):
        vault.add_fact(
            tmp_path / "proj",
            private,
            claim="c",
            citations=[{"source": source["id"], "quote": "a", "line_start": 1, "line_end": 1}],
            visibility="tracked",
            made_by={"job": JOB, "model": None},
        )


# ---------------------------------------------------------------------------
# facts-in-map
# ---------------------------------------------------------------------------


async def _run_headers(run_id: str, agent: str) -> dict:
    from hub.agent_auth import hash_run_token
    from hub.db.models import Agent, Run

    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(Agent(id=f"agent-{agent}", project_id="proj-test", name=agent))
        db.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_facts_are_in_the_map_and_read_as_cards(app, auth_headers, worker, tmp_path) -> None:
    worker([("Refunds up to 437 euros need no approval.", ["the refund limit is 437 euros."])])
    await _enable(app, auth_headers, runner_id=await _runner(app, auth_headers))
    source = await _upload(app, auth_headers)
    facts_dir = tmp_path / "knowledge" / "facts"
    foreign = {
        "id": "fct-0123456789ab",
        "kind": "fact",
        "visibility": "private",
        "holder": "colleague-laptop",
        "created_at": "2026-10-01T00:00:00.000000Z",
        "sources": ["src-0123456789ab"],
    }
    (facts_dir / "fct-0123456789ab.json").write_text(json.dumps(foreign), encoding="utf-8")
    [fact] = [f for f in _facts(facts_dir) if f["id"] != "fct-0123456789ab"]

    listed = (await app.get(f"{BASE}/vault/map", headers=auth_headers)).json()["entries"]
    by_id = {entry["id"]: entry for entry in listed}
    assert by_id[source["id"]]["kind"] == "source"
    assert by_id[fact["id"]]["kind"] == "fact"
    assert by_id[fact["id"]]["sources"] == [source["id"]]
    assert by_id[fact["id"]]["opening"] == "Refunds up to 437 euros need no approval."
    assert by_id["fct-0123456789ab"]["available"] is False
    assert by_id["fct-0123456789ab"]["opening"] is None
    # A source's facts follow it in the map.
    ids = [entry["id"] for entry in listed]
    assert ids.index(fact["id"]) == ids.index(source["id"]) + 1

    for url, headers in (
        (f"{BASE}/vault/entries/{fact['id']}", auth_headers),
        (
            f"/api/v1/agent-actions/vault/entries/{fact['id']}",
            await _run_headers("run-fact-reader", "reader"),
        ),
    ):
        read = await app.get(url, headers=headers)
        assert read.status_code == 200, read.text
        card = read.json()
        assert card["kind"] == "fact"
        assert card["claim"] == "Refunds up to 437 euros need no approval."
        assert card["citations"][0]["line_start"] == 4
        assert "the refund limit is 437 euros." in card["content"]
        assert source["id"] in card["content"] and "line 4" in card["content"]

    stub = await app.get(f"{BASE}/vault/entries/fct-0123456789ab", headers=auth_headers)
    assert stub.status_code == 200 and stub.json()["content"] is None
    assert "colleague-laptop" in stub.json()["note"]
