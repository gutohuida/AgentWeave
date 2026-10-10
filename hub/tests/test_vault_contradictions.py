"""Sources that disagree are pointed out, and the operator decides.

`sources-that-disagree-are-pointed-out` (Tier 2). As in `test_vault_distillation.py`, the worker is
faked: a test hands `distillation.run_worker` what a model would answer, first the distillation's
facts and then the check's contradictions, so what is checked is what the Hub does with them --
which pairs it keeps, what it writes where, which fact is presumed, and what each read derives. The
real spawn is the acceptance drive's (`scripts/drive/d1017_contradictions.py`).
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import distillation, manager
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
JOB = "vault-distillation"
HAIKU = "claude-haiku-4-5-20251001"
NEWER = "Follow-up, 2026-10-01.\nDana: the refund limit is 300 euros.\n"
OLDER = "Kickoff, 2026-09-01.\nDana: the refund limit is 437 euros.\nDana: returns take 30 days.\n"
F300 = ("The refund limit is 300 euros.", ["the refund limit is 300 euros."])
F437 = ("The refund limit is 437 euros.", ["the refund limit is 437 euros."])
F30 = ("Returns take 30 days.", ["returns take 30 days."])


class _Worker:
    """Stands in for `run_worker`: answers each call with the next scripted answer.

    A distillation's answer is a list of (claim, [quotes]); a check's is a list of
    (new, existing, explanation) or a callable that builds one from the prompt. None is a spawn
    that failed."""

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
        if kwargs["output_model"] is distillation.Contradictions:
            parsed = distillation.Contradictions(
                contradictions=[
                    distillation.ContradictionDraft(new=new, existing=old, explanation=why)
                    for new, old, why in answer
                ]
            )
        else:
            parsed = distillation.Distilled(
                facts=[distillation.FactDraft(claim=c, quotes=q) for c, q in answer]
            )
        return WorkerResult("ok", parsed=parsed)

    def checks(self) -> list:
        return [c for c in self.calls if c["output_model"] is distillation.Contradictions]


@pytest.fixture
def worker(monkeypatch):
    def install(*answers) -> _Worker:
        fake = _Worker(*answers)
        monkeypatch.setattr(distillation, "run_worker", fake)
        return fake

    return install


def _section(prompt: str, start: str) -> list:
    """The (id, claim) lines of one section of a check's prompt."""
    body = prompt[
        prompt.index(start) + len(start) : prompt.index(distillation.FACTS_END, prompt.index(start))
    ]
    lines = [line for line in body.splitlines() if line.strip()]
    return [tuple(line.split(": ", 1)) for line in lines]


def _id(prompt: str, start: str, needle: str) -> str:
    return next(fact_id for fact_id, claim in _section(prompt, start) if needle in claim)


def _new(prompt: str, needle: str) -> str:
    return _id(prompt, distillation.NEW_START, needle)


def _old(prompt: str, needle: str) -> str:
    return _id(prompt, distillation.EXISTING_START, needle)


def pair(new_needle: str, old_needle: str, why: str = "They disagree."):
    """A check answer naming the new fact containing *new_needle* against the sent one."""
    return lambda prompt: [(_new(prompt, new_needle), _old(prompt, old_needle), why)]


async def _runner(app, auth_headers) -> str:
    payload = {"name": "distiller", "cli": "claude", "model": HAIKU}
    created = await app.post(f"{BASE}/runners", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _enable(app, auth_headers) -> None:
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": await _runner(app, auth_headers)},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text


async def _post_source(app, auth_headers, content, **fields):
    body = {"name": "Acme meeting", "type": "transcript", "content": content, **fields}
    return await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)


async def _upload(app, auth_headers, content, **fields) -> dict:
    created = await _post_source(app, auth_headers, content, **fields)
    assert created.status_code == 201, created.text
    return created.json()


async def _distil(app, auth_headers, source_id: str):
    return await app.post(f"{BASE}/vault/sources/{source_id}/distil", headers=auth_headers)


async def _map(app, auth_headers) -> dict:
    listed = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return {entry["id"]: entry for entry in listed.json()["entries"]}


async def _contradictions(app, auth_headers) -> list:
    listed = await app.get(f"{BASE}/vault/contradictions", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()["contradictions"]


async def _resolve(app, auth_headers, ctr_id: str, **body):
    return await app.post(
        f"{BASE}/vault/contradictions/{ctr_id}/resolve", json=body, headers=auth_headers
    )


async def _checks() -> list:
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
    return [
        row.data
        for row in rows
        if (row.data or {}).get("job") == JOB and row.data.get("trigger") == "facts_written"
    ]


def _records(folder: Path, prefix: str) -> list:
    if not folder.is_dir():
        return []
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob(f"{prefix}-*.json"))
    ]


def _fact(root: Path, source_id: str, needle: str) -> str:
    return next(
        f["id"]
        for f in _records(root / "knowledge" / "facts", "fct")
        if source_id in f["sources"] and needle in f.get("claim", "")
    )


async def _one_open(app, auth_headers, worker, tmp_path):
    """The newer meeting uploaded first, the older second, and the check pairing their limits."""
    fake = worker([F300], [F437, F30], pair("437", "300"))
    await _enable(app, auth_headers)
    newer = await _upload(app, auth_headers, NEWER, dated="2026-10-01")
    older = await _upload(app, auth_headers, OLDER, dated="2026-09-01")
    fact300 = _fact(tmp_path, newer["id"], "300")
    fact437 = _fact(tmp_path, older["id"], "437")
    [record] = _records(tmp_path / "knowledge" / "contradictions", "ctr")
    return fake, newer, older, fact300, fact437, record


# ---------------------------------------------------------------------------
# dated-upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_source_carries_its_date_and_a_bad_one_is_refused(
    app, auth_headers, worker, tmp_path
) -> None:
    worker()
    dated = await _upload(app, auth_headers, NEWER, dated="2026-09-01")
    undated = await _upload(app, auth_headers, OLDER)
    assert dated["dated"] == "2026-09-01" and undated["dated"] is None
    for bad in ("01/09/2026", "2026-13-01", "2026-9-1"):
        refused = await _post_source(app, auth_headers, NEWER, dated=bad)
        assert refused.status_code == 400, (bad, refused.text)
    listed = await _map(app, auth_headers)
    assert set(listed) == {dated["id"], undated["id"]}
    assert listed[dated["id"]]["dated"] == "2026-09-01"
    assert listed[undated["id"]]["dated"] is None
    meta = json.loads(
        (tmp_path / "knowledge" / "sources" / f"{dated['id']}.json").read_text(encoding="utf-8")
    )
    assert meta["dated"] == "2026-09-01"


@pytest.mark.asyncio
async def test_a_private_sources_stub_carries_its_date(
    app, auth_headers, worker, tmp_path, tmp_path_factory
) -> None:
    worker()
    private = tmp_path_factory.mktemp("private-vault")
    put = await app.put(
        f"{BASE}/vault/settings", json={"private_location": str(private)}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    source = await _upload(app, auth_headers, NEWER, visibility="private", dated="2026-10-01")
    stub = json.loads(
        (tmp_path / "knowledge" / "sources" / f"{source['id']}.json").read_text(encoding="utf-8")
    )
    assert stub["dated"] == "2026-10-01"


# ---------------------------------------------------------------------------
# check-firing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_storing_distillation_is_followed_by_one_check(
    app, auth_headers, worker, tmp_path
) -> None:
    fake = worker(
        [F300],  # the first source: nothing else to compare with, so no check
        [F437],
        pair("437", "300"),
        [F437],
        [],
        [F437],
        None,
        [("Invented.", ["not in the source"])],
    )
    await _enable(app, auth_headers)
    await _upload(app, auth_headers, NEWER, dated="2026-10-01")
    assert fake.checks() == [] and await _checks() == []

    older = await _upload(app, auth_headers, OLDER, dated="2026-09-01")
    for _ in range(3):
        assert (await _distil(app, auth_headers, older["id"])).status_code == 202
    firings = await _checks()
    assert [f["outcome"] for f in firings] == ["written", "empty", "failed"]
    assert len(fake.checks()) == 3
    for firing in firings:
        assert firing["subject"] == {"source": older["id"]}
        assert firing["model"] == HAIKU
    assert "1 contradiction recorded" in firings[0]["detail"]
    assert all(call["kind"] == JOB for call in fake.checks())


@pytest.mark.asyncio
async def test_a_decision_source_is_not_distilled(app, auth_headers, worker) -> None:
    fake = worker()
    await _enable(app, auth_headers)
    source = await _upload(app, auth_headers, "We decided.\n", type="decision")
    assert fake.calls == []
    refused = await _distil(app, auth_headers, source["id"])
    assert refused.status_code == 409, refused.text
    assert "decision" in refused.json()["detail"].lower()


# ---------------------------------------------------------------------------
# cap
# ---------------------------------------------------------------------------


def _write_facts(project: Path, source_id: str, dated: str, count: int, created: str) -> None:
    sources, facts = project / "knowledge" / "sources", project / "knowledge" / "facts"
    sources.mkdir(parents=True, exist_ok=True)
    facts.mkdir(parents=True, exist_ok=True)
    (sources / f"{source_id}.md").write_text("x\n", encoding="utf-8")
    meta = {
        "id": source_id,
        "name": source_id,
        "type": "note",
        "visibility": "tracked",
        "created_at": created,
        "holder": None,
        "dated": dated,
    }
    (sources / f"{source_id}.json").write_text(json.dumps(meta), encoding="utf-8")
    for n in range(count):
        fact_id = f"fct-{source_id[4:10]}{n:06x}"
        fact = {
            "id": fact_id,
            "kind": "fact",
            "claim": f"Rule {n:05d} of {source_id} sets a limit of {n} units.",
            "citations": [{"source": source_id, "quote": "x", "line_start": 1, "line_end": 1}],
            "sources": [source_id],
            "visibility": "tracked",
            "created_at": created,
            "holder": None,
            "made_by": {"job": JOB, "model": HAIKU},
        }
        (facts / f"{fact_id}.json").write_text(json.dumps(fact), encoding="utf-8")


@pytest.mark.asyncio
async def test_the_compared_claims_are_capped_latest_dated_first(
    app, auth_headers, worker, tmp_path
) -> None:
    # Uploaded in an order that is not the order of their dates.
    _write_facts(tmp_path, "src-aaaaaaaaaaaa", "2026-08-01", 1000, "2026-10-09T03:00:00.000000Z")
    _write_facts(tmp_path, "src-bbbbbbbbbbbb", "2026-10-01", 1000, "2026-10-09T01:00:00.000000Z")
    _write_facts(tmp_path, "src-cccccccccccc", "2026-09-01", 1000, "2026-10-09T02:00:00.000000Z")
    fake = worker([F437, F30], [])
    await _enable(app, auth_headers)
    source = await _upload(app, auth_headers, OLDER)

    [check] = fake.checks()
    sent = _section(check["prompt"], distillation.EXISTING_START)
    new = _section(check["prompt"], distillation.NEW_START)
    assert sorted(claim for _, claim in new) == sorted([F437[0], F30[0]])
    assert 0 < len(sent) < 3000
    assert sum(len(claim) for _, claim in sent) <= distillation.COMPARED_CHARS == 50_000
    order = {"bbbbbb": 0, "cccccc": 1, "aaaaaa": 2}
    ranks = [order[fact_id[4:10]] for fact_id, _ in sent]
    assert ranks == sorted(ranks) and ranks[0] == 0
    assert not any(fact_id in {i for i, _ in new} for fact_id, _ in sent)
    [firing] = await _checks()
    assert firing["subject"] == {"source": source["id"]}
    assert f"{3000 - len(sent)} left out" in firing["detail"]


# ---------------------------------------------------------------------------
# ids-checked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_a_pair_of_one_new_and_one_sent_fact_is_kept_once(
    app, auth_headers, worker, tmp_path
) -> None:
    def answer(prompt):
        new437, new30, old300 = _new(prompt, "437"), _new(prompt, "30 days"), _old(prompt, "300")
        return [
            (new437, old300, "300 against 437."),
            (new437, "fct-ffffffffffff", "an id nobody has"),
            (new437, new30, "two new facts"),
            (old300, new437, "the valid pair reversed"),
            (new437, old300, "the valid pair again"),
        ]

    worker([F300], [F437, F30], answer)
    await _enable(app, auth_headers)
    newer = await _upload(app, auth_headers, NEWER, dated="2026-10-01")
    older = await _upload(app, auth_headers, OLDER, dated="2026-09-01")
    fact300, fact437 = _fact(tmp_path, newer["id"], "300"), _fact(tmp_path, older["id"], "437")

    [record] = _records(tmp_path / "knowledge" / "contradictions", "ctr")
    assert record["id"].startswith("ctr-") and len(record["id"]) == 16
    assert record["kind"] == "contradiction"
    assert sorted(record["facts"]) == sorted([fact437, fact300])
    # Uploaded first, but said later: the 300 fact is presumed.
    assert record["presumed"] == fact300
    assert record["explanation"] == "300 against 437."
    assert record["status"] == "open" and record["resolution"] is None
    assert record["visibility"] == "tracked"
    assert record["found_by"] == {"job": JOB, "model": HAIKU}
    [firing] = await _checks()
    assert "1 contradiction recorded" in firing["detail"] and "4 dropped" in firing["detail"]


@pytest.mark.asyncio
async def test_without_dates_the_later_upload_is_presumed(
    app, auth_headers, worker, tmp_path
) -> None:
    worker([F300], [F437], pair("437", "300"))
    await _enable(app, auth_headers)
    await _upload(app, auth_headers, NEWER)
    older = await _upload(app, auth_headers, OLDER)
    [record] = _records(tmp_path / "knowledge" / "contradictions", "ctr")
    assert record["presumed"] == _fact(tmp_path, older["id"], "437")


# ---------------------------------------------------------------------------
# private-stub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_contradiction_with_a_private_fact_is_private(
    app, auth_headers, worker, tmp_path, tmp_path_factory
) -> None:
    private = tmp_path_factory.mktemp("private-vault")
    put = await app.put(
        f"{BASE}/vault/settings", json={"private_location": str(private)}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    secret = "Board note.\nRule CANARY-7e2f: the refund limit is 300 euros.\n"
    worker(
        [F437],
        [("CANARY-7e2f sets the refund limit to 300 euros.", ["the refund limit is 300 euros."])],
        pair("CANARY", "437", why="CANARY-7e2f says 300."),
    )
    await _enable(app, auth_headers)
    await _upload(app, auth_headers, OLDER)
    await _upload(app, auth_headers, secret, visibility="private")

    [record] = _records(private / "contradictions", "ctr")
    assert record["visibility"] == "private" and record["holder"]
    [stub] = _records(tmp_path / "knowledge" / "contradictions", "ctr")
    assert set(stub) == {"id", "kind", "visibility", "holder", "created_at", "facts"}
    assert stub["id"] == record["id"] and stub["facts"] == record["facts"]
    leaked = [
        p
        for p in tmp_path.rglob("*")
        if p.is_file()
        and ".git" not in p.parts
        and "CANARY-7e2f" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert leaked == []
    # On this machine the record wins over its stub.
    [listed] = await _contradictions(app, auth_headers)
    assert listed["explanation"] == "CANARY-7e2f says 300." and listed["status"] == "open"


# ---------------------------------------------------------------------------
# derived-flags
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
async def test_disputed_facts_are_marked_in_the_map_the_cards_and_the_list(
    app, auth_headers, worker, tmp_path
) -> None:
    _, newer, older, fact300, fact437, record = await _one_open(app, auth_headers, worker, tmp_path)
    listed = await _map(app, auth_headers)
    assert listed[fact300]["disputed"] is True and listed[fact300]["presumed"] is True
    assert listed[fact437]["disputed"] is True and listed[fact437]["presumed"] is False
    assert listed[fact300]["superseded_by"] is None
    other = _fact(tmp_path, older["id"], "30 days")
    assert listed[other]["disputed"] is False and listed[other]["presumed"] is None

    agent = await _run_headers("run-disputed-reader", "reader")
    for url, headers in (
        (f"{BASE}/vault/entries/{fact437}", auth_headers),
        (f"/api/v1/agent-actions/vault/entries/{fact437}", agent),
    ):
        read = await app.get(url, headers=headers)
        assert read.status_code == 200, read.text
        card = read.json()
        assert card["disputed"] is True
        content = card["content"].lower()
        assert "disputed" in content and fact300 in card["content"]
        assert F300[0] in card["content"] and "presumed" in content
    presumed = (await app.get(f"{BASE}/vault/entries/{fact300}", headers=auth_headers)).json()
    assert fact437 in presumed["content"] and "presumed" in presumed["content"].lower()

    # A resolved contradiction written later still lists after the open one.
    resolved = dict(record, id="ctr-0123456789ab", status="resolved", created_at="2099-01-01")
    resolved["resolution"] = {"stands": None, "note": "n", "decision": None, "resolved_at": "x"}
    folder = tmp_path / "knowledge" / "contradictions"
    (folder / "ctr-0123456789ab.json").write_text(json.dumps(resolved), encoding="utf-8")
    listing = await _contradictions(app, auth_headers)
    assert [c["id"] for c in listing] == [record["id"], "ctr-0123456789ab"]
    first = listing[0]
    assert first["presumed"] == fact300 and first["status"] == "open"
    sides = {side["id"]: side for side in first["sides"]}
    assert sides[fact300]["claim"] == F300[0] and sides[fact300]["date"] == "2026-10-01"
    assert sides[fact437]["date"] == "2026-09-01" and sides[fact437]["source"] == older["id"]


# ---------------------------------------------------------------------------
# resolve-route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolving_writes_a_decision_and_supersedes_the_other_fact(
    app, auth_headers, worker, tmp_path
) -> None:
    fake, _, _, fact300, fact437, record = await _one_open(app, auth_headers, worker, tmp_path)
    ctr = record["id"]
    note = "Finance lowered the limit in October."

    assert (
        await _resolve(app, auth_headers, ctr, stands="fct-ffffffffffff", note=note)
    ).status_code == 400
    assert (await _resolve(app, auth_headers, ctr, stands=fact300, note="  ")).status_code == 400
    missing = await _resolve(app, auth_headers, "ctr-ffffffffffff", stands=fact300, note=note)
    assert missing.status_code == 404
    calls = len(fake.calls)
    done = await _resolve(app, auth_headers, ctr, stands=fact300, note=note)
    assert done.status_code == 200, done.text
    answered = done.json()
    assert answered["id"] == ctr and answered["status"] == "resolved"
    resolution = answered["resolution"]
    assert resolution["stands"] == fact300 and resolution["note"] == note
    assert resolution["decision"].startswith("src-") and resolution["resolved_at"]

    listed = await _map(app, auth_headers)
    decision = listed[resolution["decision"]]
    assert decision["type"] == "decision" and decision["visibility"] == "tracked"
    text = (await app.get(f"{BASE}/vault/entries/{decision['id']}", headers=auth_headers)).json()[
        "content"
    ]
    for part in (fact300, fact437, F300[0], F437[0], note):
        assert part in text
    assert listed[fact437]["superseded_by"] == decision["id"]
    assert listed[fact300]["superseded_by"] is None
    assert not listed[fact437]["disputed"] and not listed[fact300]["disputed"]
    card = (await app.get(f"{BASE}/vault/entries/{fact437}", headers=auth_headers)).json()
    assert "superseded" in card["content"].lower() and decision["id"] in card["content"]
    # The decision restates facts the vault holds: it is not distilled.
    assert len(fake.calls) == calls

    again = await _resolve(app, auth_headers, ctr, stands=fact300, note=note)
    assert again.status_code == 409, again.text


@pytest.mark.asyncio
async def test_resolving_for_neither_supersedes_both(app, auth_headers, worker, tmp_path) -> None:
    _, _, _, fact300, fact437, record = await _one_open(app, auth_headers, worker, tmp_path)
    done = await _resolve(app, auth_headers, record["id"], stands=None, note="Neither; ask Dana.")
    assert done.status_code == 200, done.text
    decision = done.json()["resolution"]["decision"]
    listed = await _map(app, auth_headers)
    assert listed[fact300]["superseded_by"] == decision
    assert listed[fact437]["superseded_by"] == decision


# ---------------------------------------------------------------------------
# redistil
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redistilling_drops_open_contradictions_and_keeps_resolved_ones(
    app, auth_headers, worker, tmp_path
) -> None:
    newer_text = NEWER + "Dana: returns take 14 days.\n"

    def both(prompt):
        return [
            (_new(prompt, "437"), _old(prompt, "300"), "limit"),
            (_new(prompt, "30 days"), _old(prompt, "14 days"), "returns"),
        ]

    worker(
        [F300, ("Returns take 14 days.", ["returns take 14 days."])],
        [F437, F30],
        both,
        [("The limit is 437 euros.", ["the refund limit is 437 euros."])],
        [],
    )
    await _enable(app, auth_headers)
    newer = await _upload(app, auth_headers, newer_text, dated="2026-10-01")
    older = await _upload(app, auth_headers, OLDER, dated="2026-09-01")
    folder = tmp_path / "knowledge" / "contradictions"
    fact437, fact30 = _fact(tmp_path, older["id"], "437"), _fact(tmp_path, older["id"], "30 days")
    [limit] = [r for r in _records(folder, "ctr") if fact437 in r["facts"]]
    [returns] = [r for r in _records(folder, "ctr") if fact30 in r["facts"]]
    kept = await _resolve(app, auth_headers, returns["id"], stands=returns["presumed"], note="14.")
    assert kept.status_code == 200, kept.text

    assert (await _distil(app, auth_headers, older["id"])).status_code == 202
    remaining = {record["id"]: record for record in _records(folder, "ctr")}
    assert limit["id"] not in remaining
    assert remaining[returns["id"]]["status"] == "resolved"
    assert newer["id"]
