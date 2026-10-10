"""A working agent tells the manager a vault entry is wrong.

`a-working-agent-tells-the-manager-an-entry-is-wrong` (Tier 2). As in `test_vault_distillation.py`
the worker is faked: a test hands `vault_reports.run_worker` what the manager's model would answer,
so what is checked is what the Hub does with it -- where a report is written, which outcome it
takes, whether a correction is anchored in its source, and what each read then derives. The real
spawn is the acceptance drive's (`scripts/drive/d1024_reports.py`).
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import manager, vault, vault_reports
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.worker import WorkerResult

BASE = "/api/v1/projects/proj-test"
AGENT_ACTIONS = "/api/v1/agent-actions"
JOB = "vault-reports"
HAIKU = "claude-haiku-4-5-20251001"
SOURCE = (
    "Acme refund policy, 2026-10-01.\n"
    "Dana: refunds are paid to the original card.\n"
    "Dana: approval is needed above the limit.\n"
    "Dana: the refund limit without approval is 300 euros.\n"
)
QUOTE = "the refund limit without approval is 300 euros."


class _Worker:
    """Stands in for `run_worker`: answers each call with the next scripted answer, a tuple
    (outcome, answer, claim, quotes), or None for a spawn that failed."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list = []

    async def __call__(self, **kwargs) -> WorkerResult:
        self.calls.append(kwargs)
        answer = self.answers.pop(0) if self.answers else ("answered", "It stands.", None, [])
        if answer is None:
            return WorkerResult("spawn_failed", error="boom")
        outcome, said, claim, quotes = answer
        parsed = vault_reports.ReportAnswer(
            outcome=outcome, answer=said, new_claim=claim, quotes=quotes
        )
        return WorkerResult("ok", parsed=parsed)


@pytest.fixture
def worker(monkeypatch):
    def install(*answers) -> _Worker:
        fake = _Worker(*answers)
        monkeypatch.setattr(vault_reports, "run_worker", fake)
        return fake

    return install


async def _runner(app, auth_headers) -> str:
    payload = {"name": "reviewer", "cli": "claude", "model": HAIKU}
    created = await app.post(f"{BASE}/runners", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _set_job(app, auth_headers, **body) -> None:
    patched = await app.patch(f"{BASE}/manager/jobs/{JOB}", json=body, headers=auth_headers)
    assert patched.status_code == 200, patched.text


async def _enable(app, auth_headers) -> None:
    await _set_job(app, auth_headers, enabled=True, runner_id=await _runner(app, auth_headers))


async def _private_root(app, auth_headers) -> Path:
    settings = await app.get(f"{BASE}/vault/settings", headers=auth_headers)
    return Path(settings.json()["effective_private_location"])


async def _source(app, auth_headers, content: str = SOURCE, **fields) -> dict:
    body = {"name": "Acme refund policy", "type": "rules", "content": content, **fields}
    created = await app.post(f"{BASE}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _fact(app, auth_headers, tmp_path, source: dict, claim: str) -> str:
    """A fact citing the source's last line, written as the distillation job writes one."""
    meta = vault.add_fact(
        tmp_path,
        await _private_root(app, auth_headers),
        claim=claim,
        citations=[{"source": source["id"], "quote": QUOTE, "line_start": 4, "line_end": 4}],
        visibility=source["visibility"],
        made_by={"job": "vault-distillation", "model": HAIKU},
    )
    return meta["id"]


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


async def _file(app, headers, entry_id: str, message: str = "This looks wrong.", **extra):
    body = {"entry_id": entry_id, "message": message, **extra}
    return await app.post(f"{AGENT_ACTIONS}/vault/reports", json=body, headers=headers)


async def _filed(app, headers, entry_id: str, message: str = "This looks wrong.") -> dict:
    created = await _file(app, headers, entry_id, message)
    assert created.status_code == 201, created.text
    return created.json()


def _records(folder: Path, prefix: str) -> list:
    if not folder.is_dir():
        return []
    return [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob(f"{prefix}-*.json"))
    ]


def _report(tmp_path: Path, report_id: str) -> dict:
    return json.loads(
        (tmp_path / "knowledge" / "reports" / f"{report_id}.json").read_text(encoding="utf-8")
    )


async def _events(event_type: str) -> list:
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog)
                    .where(EventLog.event_type == event_type)
                    .order_by(EventLog.timestamp, EventLog.id)
                )
            )
            .scalars()
            .all()
        )
    return rows


async def _firings() -> list:
    return [
        row.data for row in await _events(manager.FIRED_EVENT) if (row.data or {}).get("job") == JOB
    ]


async def _map(app, auth_headers) -> dict:
    listed = await app.get(f"{BASE}/vault/map", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return {entry["id"]: entry for entry in listed.json()["entries"]}


async def _list(app, auth_headers) -> list:
    listed = await app.get(f"{BASE}/vault/reports", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()["reports"]


async def _close(app, auth_headers, report_id: str, note: str):
    return await app.post(
        f"{BASE}/vault/reports/{report_id}/close", json={"note": note}, headers=auth_headers
    )


# ---------------------------------------------------------------------------
# job-listed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_job_is_listed_disabled_with_nothing_chosen(app, auth_headers) -> None:
    listed = await app.get(f"{BASE}/manager/jobs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    job = next(job for job in listed.json()["jobs"] if job["key"] == JOB)
    assert job["trigger"] == "report_filed"
    assert job["enabled"] is False
    assert job["runner_id"] is None and job["model"] is None
    assert job["title"] and job["description"]


# ---------------------------------------------------------------------------
# filed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_report_is_filed_by_the_runs_agent(app, auth_headers, tmp_path) -> None:
    source = await _source(app, auth_headers)
    fact = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 3,000 euros.")
    agent = await _run_headers("run-reporter", "helper")

    # Identity is never taken from the body: a reporter there is refused by name, not obeyed.
    forged = await _file(app, agent, fact, reporter={"agent": "someone-else"})
    assert forged.status_code == 422 and "reporter" in forged.text
    assert _records(tmp_path / "knowledge" / "reports", "rpt") == []

    report = await _filed(app, agent, fact, "The source says 300, not 3,000.")
    assert report["id"].startswith("rpt-") and len(report["id"]) == 16
    assert report["reporter"] == {"agent": "helper", "run_id": "run-reporter"}
    assert report["entry"] == fact and report["status"] == "pending"
    stored = _report(tmp_path, report["id"])
    assert stored["message"] == "The source says 300, not 3,000."
    assert stored["visibility"] == "tracked" and stored["created_at"]
    assert stored["reporter"] == {"agent": "helper", "run_id": "run-reporter"}

    [event] = await _events("vault_report_filed")
    assert event.agent == "helper" and event.project_id == "proj-test"
    assert event.data["subject"] == {"report": report["id"], "entry": fact}

    # A second report on the same entry while the first is open names the first.
    again = await _file(app, agent, fact, "Still wrong.")
    assert again.status_code == 409 and report["id"] in again.text

    # The source itself can be reported, and a message of exactly 4,000 characters is accepted.
    assert (await _file(app, agent, source["id"], "x" * 4000)).status_code == 201


@pytest.mark.asyncio
async def test_a_report_is_refused_for_what_is_not_here_or_not_a_message(
    app, auth_headers, tmp_path
) -> None:
    source = await _source(app, auth_headers)
    fact = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 3,000 euros.")
    agent = await _run_headers("run-refused", "helper")

    # A private fact's stub, its record held on another machine.
    stub = {
        "id": "fct-0123456789ab",
        "kind": "fact",
        "visibility": "private",
        "holder": "elsewhere",
        "created_at": "2026-10-10T00:00:00.000000Z",
        "sources": [source["id"]],
    }
    folder = tmp_path / "knowledge" / "facts"
    (folder / "fct-0123456789ab.json").write_text(json.dumps(stub), encoding="utf-8")

    for entry_id in ("fct-ffffffffffff", "src-ffffffffffff", "nonsense", "fct-0123456789ab"):
        refused = await _file(app, agent, entry_id)
        assert refused.status_code == 404, (entry_id, refused.text)
    for message in ("", "   ", "x" * 4001):
        refused = await _file(app, agent, fact, message)
        assert refused.status_code == 400, (len(message), refused.text)
    assert _records(tmp_path / "knowledge" / "reports", "rpt") == []
    assert await _events("vault_report_filed") == []

    anonymous = await app.post(
        f"{AGENT_ACTIONS}/vault/reports", json={"entry_id": fact, "message": "m"}
    )
    assert anonymous.status_code in (401, 403)


# ---------------------------------------------------------------------------
# private
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_report_on_a_private_fact_stays_at_the_private_location(
    app, auth_headers, tmp_path, tmp_path_factory
) -> None:
    private = tmp_path_factory.mktemp("private-vault")
    put = await app.put(
        f"{BASE}/vault/settings", json={"private_location": str(private)}, headers=auth_headers
    )
    assert put.status_code == 200, put.text
    source = await _source(app, auth_headers, visibility="private")
    fact = await _fact(app, auth_headers, tmp_path, source, "CANARY-91c4 the limit is 3,000.")
    agent = await _run_headers("run-private", "helper")

    report = await _filed(app, agent, fact, "MESSAGE-5d0e: the source says 300.")
    [stored] = _records(private / "reports", "rpt")
    assert stored["id"] == report["id"] and stored["visibility"] == "private"
    assert stored["message"] == "MESSAGE-5d0e: the source says 300."
    assert not (tmp_path / "knowledge" / "reports").exists()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert "CANARY-91c4" not in text and "MESSAGE-5d0e" not in text, path
    # On this machine it is listed in full.
    [listed] = await _list(app, auth_headers)
    assert listed["message"] == "MESSAGE-5d0e: the source says 300."


# ---------------------------------------------------------------------------
# firing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_report_is_one_firing_and_a_disabled_job_spawns_nothing(
    app, auth_headers, worker, tmp_path
) -> None:
    fake = worker(
        ("corrected", "The source says 300.", "The refund limit is 300 euros.", [QUOTE]),
        ("answered", "The fact matches line 4.", None, []),
        ("disputed", "The source is ambiguous here.", None, []),
        None,
    )
    await _enable(app, auth_headers)
    source = await _source(app, auth_headers)
    agent = await _run_headers("run-firing", "helper")
    claims = ("Limit is 3,000.", "Limit is 300.", "Limit is 30.", "Limit is 3.")
    facts = [await _fact(app, auth_headers, tmp_path, source, claim) for claim in claims]

    reports = []
    for index, fact in enumerate(facts):
        reports.append(await _filed(app, agent, fact, f"MSG-{index}: please check."))
        assert len(fake.calls) == index + 1
        assert len(await _firings()) == index + 1

    first = fake.calls[0]
    assert "MSG-0: please check." in first["prompt"] and SOURCE in first["prompt"]
    assert claims[0] in first["prompt"]
    assert first["model"] == HAIKU and first["output_model"] is vault_reports.ReportAnswer

    firings = await _firings()
    assert [f["outcome"] for f in firings] == ["written", "empty", "written", "failed"]
    assert all(f["trigger"] == "report_filed" for f in firings)
    for firing, report, fact in zip(firings, reports, facts, strict=True):
        assert firing["subject"] == {"report": report["id"], "entry": fact}
        assert firing["model"] == HAIKU
    assert "corrected" in firings[0]["detail"] and "answered" in firings[1]["detail"]
    assert "referred" in firings[2]["detail"]
    statuses = [_report(tmp_path, r["id"])["status"] for r in reports]
    assert statuses == ["corrected", "answered", "referred", "pending"]

    # Disabled: nothing is spawned and the report waits, pending.
    await _set_job(app, auth_headers, enabled=False)
    fifth = await _fact(app, auth_headers, tmp_path, source, "Limit is 3 million.")
    waiting = await _filed(app, agent, fifth)
    assert len(fake.calls) == 4 and len(await _firings()) == 4
    assert _report(tmp_path, waiting["id"])["status"] == "pending"


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_correction_is_stored_only_when_its_quotes_are_in_the_source(
    app, auth_headers, worker, tmp_path
) -> None:
    worker(
        ("corrected", "Line 4 says 300.", "The refund limit is 300 euros.", [QUOTE]),
        ("corrected", "It is 500.", "The refund limit is 500 euros.", ["the limit is 500 euros."]),
        ("corrected", "The source is wrong.", "The refund limit is 300 euros.", [QUOTE]),
        # What Haiku answered in the drive: the entry's own wrong claim, beside the right quote.
        ("corrected", "It is 300.", " the refund limit is  3,000 euros. ", [QUOTE]),
    )
    await _enable(app, auth_headers)
    source = await _source(app, auth_headers)
    agent = await _run_headers("run-outcomes", "helper")
    restated = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 3,000 euros.")
    wrong = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 3,000 euros.")
    other = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 30 euros.")
    old_bytes = (tmp_path / "knowledge" / "facts" / f"{wrong}.json").read_bytes()

    corrected = await _filed(app, agent, wrong)
    record = _report(tmp_path, corrected["id"])
    assert record["status"] == "corrected" and record["answer"] == "Line 4 says 300."
    new_id = record["replaced_by"]
    new = json.loads((tmp_path / "knowledge" / "facts" / f"{new_id}.json").read_text("utf-8"))
    assert new["claim"] == "The refund limit is 300 euros."
    assert new["citations"] == [
        {"source": source["id"], "quote": QUOTE, "line_start": 4, "line_end": 4}
    ]
    assert new["visibility"] == "tracked"
    assert new["made_by"] == {"job": JOB, "model": HAIKU, "report": corrected["id"]}
    assert (tmp_path / "knowledge" / "facts" / f"{wrong}.json").read_bytes() == old_bytes

    facts_before = len(_records(tmp_path / "knowledge" / "facts", "fct"))
    unanchored = await _filed(app, agent, other)
    on_source = await _filed(app, agent, source["id"])
    unchanged = await _filed(app, agent, restated)
    for report in (unanchored, on_source, unchanged):
        record = _report(tmp_path, report["id"])
        assert record["status"] == "referred" and record["answer"]
        assert record.get("replaced_by") is None
    assert len(_records(tmp_path / "knowledge" / "facts", "fct")) == facts_before
    firings = await _firings()
    assert [f["outcome"] for f in firings] == ["written"] * 4
    assert "referred" in firings[1]["detail"] and "not found" in firings[1]["detail"]
    assert "referred" in firings[3]["detail"] and "unchanged" in firings[3]["detail"]


# ---------------------------------------------------------------------------
# flags
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrected_and_referred_reports_mark_their_facts(
    app, auth_headers, worker, tmp_path
) -> None:
    worker(
        ("corrected", "Line 4 says 300.", "The refund limit is 300 euros.", [QUOTE]),
        ("disputed", "ANSWER-77: cannot tell from the source.", None, []),
        ("disputed", "Cannot tell either.", None, []),
    )
    await _enable(app, auth_headers)
    source = await _source(app, auth_headers)
    agent = await _run_headers("run-flags", "helper")
    wrong = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 3,000 euros.")
    doubted = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 30 euros.")
    settled = await _fact(app, auth_headers, tmp_path, source, "The refund limit is 3 euros.")

    corrected = await _filed(app, agent, wrong)
    await _filed(app, agent, doubted, "MESSAGE-31: a colleague says 500.")
    closing = await _filed(app, agent, settled)
    assert (await _close(app, auth_headers, closing["id"], "Checked with Dana.")).status_code == 200
    new_id = _report(tmp_path, corrected["id"])["replaced_by"]

    listed = await _map(app, auth_headers)
    assert listed[wrong]["superseded_by"] == new_id and listed[wrong]["disputed"] is False
    assert listed[doubted]["disputed"] is True and listed[doubted]["superseded_by"] is None
    assert listed[settled]["disputed"] is False and listed[settled]["superseded_by"] is None
    assert listed[new_id]["disputed"] is False and listed[new_id]["superseded_by"] is None

    for prefix, headers in ((BASE, auth_headers), (AGENT_ACTIONS, agent)):
        card = (await app.get(f"{prefix}/vault/entries/{wrong}", headers=headers)).json()
        assert card["superseded_by"] == new_id
        assert "superseded" in card["content"].lower() and new_id in card["content"]
        assert "The refund limit is 300 euros." in card["content"]
        card = (await app.get(f"{prefix}/vault/entries/{doubted}", headers=headers)).json()
        assert card["disputed"] is True and "disputed" in card["content"].lower()
        assert "MESSAGE-31: a colleague says 500." in card["content"]
        assert "ANSWER-77: cannot tell from the source." in card["content"]
        card = (await app.get(f"{prefix}/vault/entries/{settled}", headers=headers)).json()
        assert card["disputed"] is False and "disputed" not in card["content"].lower()
        assert "superseded" not in card["content"].lower()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reports_are_listed_open_first_and_only_a_referred_one_closes(
    app, auth_headers, worker, tmp_path
) -> None:
    worker(
        ("disputed", "Cannot tell.", None, []),
        ("answered", "It matches line 4.", None, []),
    )
    await _enable(app, auth_headers)
    source = await _source(app, auth_headers)
    agent = await _run_headers("run-close", "helper")
    facts = [
        await _fact(app, auth_headers, tmp_path, source, claim)
        for claim in ("Limit is 30.", "Limit is 300.", "Limit is 3.")
    ]
    referred = await _filed(app, agent, facts[0])
    answered = await _filed(app, agent, facts[1])
    await _set_job(app, auth_headers, enabled=False)
    pending = await _filed(app, agent, facts[2])

    listed = await _list(app, auth_headers)
    assert [r["id"] for r in listed] == [pending["id"], referred["id"], answered["id"]]
    assert [r["status"] for r in listed] == ["pending", "referred", "answered"]
    assert listed[2]["answer"] == "It matches line 4."

    assert (await _close(app, auth_headers, referred["id"], "  ")).status_code == 400
    assert (await _close(app, auth_headers, "rpt-ffffffffffff", "n")).status_code == 404
    refused = await _close(app, auth_headers, answered["id"], "n")
    assert refused.status_code == 409 and "answered" in refused.text
    closed = await _close(app, auth_headers, referred["id"], "Checked with Dana: 30 is right.")
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["status"] == "closed" and body["close"]["note"] == "Checked with Dana: 30 is right."
    assert body["close"]["closed_at"]
    assert _report(tmp_path, referred["id"])["status"] == "closed"
    assert (await _close(app, auth_headers, referred["id"], "again")).status_code == 409


# ---------------------------------------------------------------------------
# the tool
# ---------------------------------------------------------------------------


def test_vault_report_is_on_every_runners_surface_and_vault_read_points_to_it() -> None:
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    assert "vault_report" in mcp_server._CALLABLE_TOOLS
    assert "vault_report" in HUB_MCP_TOOLS
    [operation] = [op for op in _operations() if op.tool == "vault_report"]
    assert operation.method == "POST" and operation.path == "/vault/reports"
    assert set(operation.fields) == {"entry_id", "message"}
    assert "vault_report" in (mcp_server._CALLABLE_TOOLS["vault_read"].__doc__ or "")
