"""A requirement is checked against what the vault recorded.

`a-requirement-is-checked-against-what-the-vault-recorded` (Tier 1, spdoc-e4f531e0b926). A
requirement cites vault facts by id; the Hub derives a warning on read for a cited fact that is
disputed, superseded, reported or missing; the manager's spec-vault-check job judges every
requirement against the vault's facts when a document is proposed; each warning is a
`vault_warning` gap at proposal and approval. As in `test_vault_reports.py` the worker is faked: a
test hands `vault_spec_check.run_worker` what the model would answer, so what is checked is what
the Hub keeps of it. The real spawn is the acceptance drive's
(`scripts/drive/d1025_specs_against_vault.py`).
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from hub import manager, vault, vault_spec_check
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, SpecDocument
from hub.spec_documents import parse_stored
from hub.spec_payload import payload_to_dict, validate_payload
from hub.worker import WorkerResult

from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    PATH,
    _create,
    _document,
    _submit,
    run_headers,
)
from .test_spec_journey_briefing import _place

PROJECT = "/api/v1/projects/proj-test"
DOCS = f"{PROJECT}/project"
JOB = "spec-vault-check"
HAIKU = "claude-haiku-4-5-20251001"
JANUARY = "January call with Acme"
MARCH = "March call with Acme"
TEXT = "Acme call.\nDana: refunds up to 300 euros need no approval.\n"
QUOTE = "Dana: refunds up to 300 euros need no approval."
MISSING = "fct-000000000000"


class _Worker:
    """Stands in for `run_worker`: answers each call with the next scripted list of conflicts,
    each a (requirement, fact, explanation) tuple, or None for a spawn that failed."""

    def __init__(self, *answers, on_call=None) -> None:
        self.answers = list(answers)
        self.calls: list = []
        self.on_call = on_call

    async def __call__(self, **kwargs) -> WorkerResult:
        self.calls.append(kwargs)
        if self.on_call is not None:
            await self.on_call()
        answer = self.answers.pop(0) if self.answers else []
        if answer is None:
            return WorkerResult("spawn_failed", error="boom")
        conflicts = [
            vault_spec_check.ConflictDraft(requirement=r, fact=f, explanation=e)
            for r, f, e in answer
        ]
        return WorkerResult("ok", parsed=vault_spec_check.CheckAnswer(conflicts=conflicts))


@pytest.fixture
def worker(monkeypatch):
    def install(*answers, on_call=None) -> _Worker:
        fake = _Worker(*answers, on_call=on_call)
        monkeypatch.setattr(vault_spec_check, "run_worker", fake)
        return fake

    return install


async def _private_root(app, auth_headers) -> Path:
    settings = await app.get(f"{PROJECT}/vault/settings", headers=auth_headers)
    return Path(settings.json()["effective_private_location"])


async def _source(app, auth_headers, name: str, dated: str) -> dict:
    body = {"name": name, "type": "transcript", "content": TEXT, "dated": dated}
    created = await app.post(f"{PROJECT}/vault/sources", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()


async def _fact(app, auth_headers, tmp_path, source: dict, claim: str) -> str:
    meta = vault.add_fact(
        tmp_path,
        await _private_root(app, auth_headers),
        claim=claim,
        citations=[{"source": source["id"], "quote": QUOTE, "line_start": 2, "line_end": 2}],
        visibility=source["visibility"],
        made_by={"job": "vault-distillation", "model": HAIKU},
    )
    return meta["id"]


async def _contradiction(app, auth_headers, tmp_path, facts, presumed) -> str:
    meta = vault.add_contradiction(
        tmp_path,
        await _private_root(app, auth_headers),
        facts=list(facts),
        presumed=presumed,
        explanation="The limit differs.",
        visibility="tracked",
        found_by={"job": "vault-distillation", "model": HAIKU},
    )
    return meta["id"]


def _requirement(key: str, statement: str, facts=None) -> dict:
    requirement = {"key": key, "statement": statement, "modal": "MUST"}
    if facts is not None:
        requirement["facts"] = facts
    return requirement


def _payload(*requirements) -> dict:
    keys = [r["key"] for r in requirements]
    criteria = [
        {
            "key": f"c-{key}",
            "requirement": key,
            "given": "g",
            "when": "w",
            "then": "t",
            "how_to_check": "a test",
            "checked_by": "agent",
        }
        for key in keys
    ]
    tasks = [{"key": "t1", "description": "Build it", "requirements": keys}]
    return _document(requirements=list(requirements), acceptance_criteria=criteria, tasks=tasks)


async def _saved(app, run_headers, *requirements) -> None:  # noqa: F811
    saved = await _submit(app, run_headers, _payload(*requirements))
    assert saved.status_code == 200, saved.text


async def _warnings(app, auth_headers, path: str = PATH) -> list:
    listed = await app.get(f"{PROJECT}/vault/warnings", params={"path": path}, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()["warnings"]


async def _enable(app, auth_headers) -> None:
    runner = await app.post(
        f"{PROJECT}/runners",
        json={"name": "checker", "cli": "claude", "model": HAIKU},
        headers=auth_headers,
    )
    assert runner.status_code == 201, runner.text
    patched = await app.patch(
        f"{PROJECT}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": runner.json()["id"]},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text


async def _propose(app, auth_headers):
    await _place(step="delivery", size="large")
    proposed = await app.post(
        f"{DOCS}/documents/propose", params={"path": PATH}, headers=auth_headers
    )
    assert proposed.status_code == 200, proposed.text
    return proposed.json()


async def _check_now(app, auth_headers, path: str = PATH):
    return await app.post(
        f"{PROJECT}/vault/warnings/check", params={"path": path}, headers=auth_headers
    )


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


# ---------------------------------------------------------------------------
# cites-kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_requirement_keeps_the_facts_it_cites_and_refuses_anything_else(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
) -> None:
    import json

    await _create(app, auth_headers)
    cited = ["fct-0123456789ab", "fct-ba9876543210"]
    await _saved(app, run_headers, _requirement("alpha", "It responds within 200ms", cited))

    stored = json.loads((tmp_path / PATH).read_text(encoding="utf-8"))
    assert stored["requirements"][0]["facts"] == cited
    # Read back as the Hub reads a stored file, and written out again unchanged.
    payload = validate_payload(parse_stored((tmp_path / PATH).read_text(encoding="utf-8")))
    assert payload.requirements[0].facts == cited
    assert payload_to_dict(payload)["requirements"][0]["facts"] == cited

    refused = await _submit(
        app, run_headers, _payload(_requirement("alpha", "It responds", ["refunds", 300]))
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["field"].startswith("requirements[0]")
    refused = await _submit(
        app, run_headers, _payload(_requirement("alpha", "It responds", ["refunds"]))
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["field"] == "requirements[0].facts"
    assert "fct-" in refused.json()["detail"]["message"]

    # A requirement that cites nothing stores as before: no facts key at all.
    await _saved(app, run_headers, _requirement("alpha", "It responds within 200ms"))
    stored = json.loads((tmp_path / PATH).read_text(encoding="utf-8"))
    assert "facts" not in stored["requirements"][0]


def test_the_schema_tells_an_author_to_cite_fact_ids() -> None:
    from hub.spec_payload import Requirement

    description = Requirement.model_json_schema()["properties"]["facts"]["description"]
    assert "fct-" in description and "vault_map" in description and "vault_read" in description


# ---------------------------------------------------------------------------
# derived
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cited_facts_carry_warnings_derived_from_the_vault(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
) -> None:
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    march = await _source(app, auth_headers, MARCH, "2026-03-01")
    disputed = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    newer = await _fact(app, auth_headers, tmp_path, march, "Refunds up to 500 need none.")
    old = await _fact(app, auth_headers, tmp_path, january, "Refunds are paid in cash.")
    replacing = await _fact(app, auth_headers, tmp_path, march, "Refunds go to the card.")
    reported = await _fact(app, auth_headers, tmp_path, january, "Refunds take a day.")
    favoured = await _fact(app, auth_headers, tmp_path, january, "Refunds are in euros.")
    against = await _fact(app, auth_headers, tmp_path, march, "Refunds are in dollars.")
    private = await _private_root(app, auth_headers)

    await _contradiction(app, auth_headers, tmp_path, (disputed, newer), newer)
    settled = await _contradiction(app, auth_headers, tmp_path, (old, replacing), replacing)
    resolved = await app.post(
        f"{PROJECT}/vault/contradictions/{settled}/resolve",
        json={"stands": replacing, "note": "Card only since March."},
        headers=auth_headers,
    )
    assert resolved.status_code == 200, resolved.text
    report = vault.add_report(
        tmp_path,
        private,
        entry_id=reported,
        message="REPORT-MSG: it takes a week.",
        reporter={"agent": "helper"},
    )
    vault.settle_report(
        tmp_path,
        private,
        report["id"],
        status="referred",
        answer="Cannot tell.",
        reviewed_by={"job": "vault-reports", "model": HAIKU},
    )
    pending = await _contradiction(app, auth_headers, tmp_path, (favoured, against), against)

    await _create(app, auth_headers)
    await _saved(
        app,
        run_headers,
        _requirement("r-disputed", "Refunds up to 300 need no approval.", [disputed]),
        _requirement("r-superseded", "Refunds are paid in cash.", [old]),
        _requirement("r-reported", "Refunds take a day.", [reported]),
        _requirement("r-missing", "Refunds need a form.", [MISSING]),
        _requirement("r-favoured", "Refunds are in euros.", [favoured]),
    )

    warnings = await _warnings(app, auth_headers)
    by_key = {}
    for warning in warnings:
        by_key.setdefault(warning["key"], []).append(warning)
    assert [w["kind"] for w in by_key["r-disputed"]] == ["disputed"]
    assert [w["kind"] for w in by_key["r-superseded"]] == ["superseded"]
    assert [w["kind"] for w in by_key["r-reported"]] == ["reported"]
    assert [w["kind"] for w in by_key["r-missing"]] == ["missing"]
    assert [w["kind"] for w in by_key["r-favoured"]] == ["disputed"]

    first = by_key["r-disputed"][0]
    assert first["fact"] == disputed and first["identifier"] == "FR-1"
    assert first["statement"] == "Refunds up to 300 need no approval."
    assert JANUARY in first["message"] and MARCH in first["message"]
    assert "Refunds up to 500 need none." in first["message"]
    superseded = by_key["r-superseded"][0]["message"]
    assert replacing in superseded and MARCH in superseded and JANUARY in superseded
    assert "REPORT-MSG: it takes a week." in by_key["r-reported"][0]["message"]
    assert JANUARY in by_key["r-reported"][0]["message"]
    assert MISSING in by_key["r-missing"][0]["message"]
    # Document order: requirement, then its facts.
    assert [w["key"] for w in warnings] == [
        "r-disputed",
        "r-superseded",
        "r-reported",
        "r-missing",
        "r-favoured",
    ]

    # Resolved in the cited fact's favour, and the report closed: both warnings clear.
    resolved = await app.post(
        f"{PROJECT}/vault/contradictions/{pending}/resolve",
        json={"stands": favoured, "note": "Euros it is."},
        headers=auth_headers,
    )
    assert resolved.status_code == 200, resolved.text
    closed = await app.post(
        f"{PROJECT}/vault/reports/{report['id']}/close",
        json={"note": "A day is right."},
        headers=auth_headers,
    )
    assert closed.status_code == 200, closed.text
    keys = [w["key"] for w in await _warnings(app, auth_headers)]
    assert keys == ["r-disputed", "r-superseded", "r-missing"]


@pytest.mark.asyncio
async def test_the_warnings_route_answers_404_for_an_unknown_document_and_empty_for_none(
    app, auth_headers, run_headers  # noqa: F811
) -> None:
    missing = await app.get(
        f"{PROJECT}/vault/warnings",
        params={"path": "spec/changes/nothing/spec.json"},
        headers=auth_headers,
    )
    assert missing.status_code == 404, missing.text
    await _create(app, auth_headers)
    assert await _warnings(app, auth_headers) == []
    await _saved(app, run_headers, _requirement("alpha", "It responds within 200ms"))
    assert await _warnings(app, auth_headers) == []


# ---------------------------------------------------------------------------
# job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_job_is_listed_disabled_with_nothing_chosen(app, auth_headers) -> None:
    listed = await app.get(f"{PROJECT}/manager/jobs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    job = next(job for job in listed.json()["jobs"] if job["key"] == JOB)
    assert job["trigger"] == "document_proposed"
    assert job["enabled"] is False and job["runner_id"] is None and job["model"] is None


@pytest.mark.asyncio
async def test_proposal_fires_one_check_keeping_only_conflicts_that_name_real_ids(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    fact = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    await _enable(app, auth_headers)
    await _create(app, auth_headers)
    await _saved(
        app,
        run_headers,
        _requirement("r1", "Refunds up to 300 euros need no approval.", [fact]),
        _requirement("r2", "Refunds up to 3,000 euros need no approval."),
    )

    seen_phases = []

    async def phase_at_spawn() -> None:
        async with async_session_factory() as db:
            seen_phases.append(
                (
                    await db.execute(select(SpecDocument.phase).where(SpecDocument.path == PATH))
                ).scalar_one()
            )

    fake = worker(
        [
            ("r2", fact, "3,000 is above the 300 limit."),
            ("r9", fact, "No such requirement."),
            ("r1", "fct-ffffffffffff", "No such fact."),
        ],
        None,
        on_call=phase_at_spawn,
    )

    proposed = await _propose(app, auth_headers)
    assert proposed["proposed"] is True
    # The spawn ran after the proposal was committed: the answer did not wait on it.
    assert seen_phases == ["proposed"]
    assert len(fake.calls) == 1
    prompt = fake.calls[0]["prompt"]
    assert "r2" in prompt and "Refunds up to 3,000 euros need no approval." in prompt
    assert fact in prompt and "Refunds up to 300 need none." in prompt
    assert fake.calls[0]["model"] == HAIKU
    assert fake.calls[0]["output_model"] is vault_spec_check.CheckAnswer

    firings = await _firings()
    assert len(firings) == 1
    fired = firings[0]
    assert fired["trigger"] == "document_proposed" and fired["outcome"] == "written"
    assert fired["subject"] == {"document": PATH}
    assert fired["conflicts"] == [
        {
            "requirement": "r2",
            "fact": fact,
            "statement": "Refunds up to 3,000 euros need no approval.",
            "explanation": "3,000 is above the 300 limit.",
        }
    ]
    conflicts = [w for w in await _warnings(app, auth_headers) if w["kind"] == "conflict"]
    assert [(w["key"], w["fact"], w["identifier"]) for w in conflicts] == [("r2", fact, "FR-2")]
    assert JANUARY in conflicts[0]["message"]

    # Checked again through the route: the spawn fails, recorded as one more firing, and the
    # newest firing is the document's current judgement.
    again = await _check_now(app, auth_headers)
    assert again.status_code == 202, again.text
    firings = await _firings()
    assert [(f["trigger"], f["outcome"]) for f in firings] == [
        ("document_proposed", "written"),
        ("requested", "failed"),
    ]
    assert [w for w in await _warnings(app, auth_headers) if w["kind"] == "conflict"] == []

    # Disabled: 409 and nothing spawned. Unknown document: 404.
    patched = await app.patch(
        f"{PROJECT}/manager/jobs/{JOB}", json={"enabled": False}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    refused = await _check_now(app, auth_headers)
    assert refused.status_code == 409, refused.text
    assert (
        await _check_now(app, auth_headers, "spec/changes/nothing/spec.json")
    ).status_code == 404
    assert len(fake.calls) == 2 and len(await _firings()) == 2


@pytest.mark.asyncio
async def test_a_disabled_job_spawns_nothing_on_proposal(
    app, auth_headers, run_headers, worker, tmp_path  # noqa: F811
) -> None:
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    fake = worker([])
    await _create(app, auth_headers)
    await _saved(app, run_headers, _requirement("r1", "Refunds up to 3,000 need none."))
    assert (await _propose(app, auth_headers))["proposed"] is True
    assert fake.calls == [] and await _firings() == []


# ---------------------------------------------------------------------------
# reworded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_conflict_judged_against_an_earlier_wording_is_not_shown(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
) -> None:
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    fact = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    await _create(app, auth_headers)
    r1 = _requirement("r1", "Refunds up to 300 euros need no approval.")
    await _saved(app, run_headers, r1, _requirement("r2", "Refunds up to 3,000 need none."))
    async with async_session_factory() as db:
        await manager.record_firing(
            db,
            "proj-test",
            job=JOB,
            trigger="document_proposed",
            subject={"document": PATH},
            runner_id="runner-x",
            cli="claude",
            model=HAIKU,
            outcome="written",
            detail="1 conflict kept",
            duration_ms=1,
            usage=None,
            extra={
                "conflicts": [
                    {
                        "requirement": "r2",
                        "fact": fact,
                        "statement": "Refunds up to 3,000 need none.",
                        "explanation": "Above the limit.",
                    }
                ]
            },
        )
    assert [(w["key"], w["kind"]) for w in await _warnings(app, auth_headers)] == [
        ("r2", "conflict")
    ]

    await _saved(app, run_headers, r1, _requirement("r2", "Refunds up to 250 need none."))
    assert await _warnings(app, auth_headers) == []


async def _firing_with_conflicts(conflicts: list) -> None:
    async with async_session_factory() as db:
        await manager.record_firing(
            db,
            "proj-test",
            job=JOB,
            trigger="document_proposed",
            subject={"document": PATH},
            runner_id="runner-x",
            cli="claude",
            model=HAIKU,
            outcome="written",
            detail=f"{len(conflicts)} conflict kept",
            duration_ms=1,
            usage=None,
            extra={"conflicts": conflicts},
        )


@pytest.mark.asyncio
async def test_a_conflict_against_a_fact_since_overruled_or_gone_is_not_shown(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
) -> None:
    """F588: the page kept a conflict naming a fact the operator had overruled (its message still
    said that fact "supersedes" another), or one that no longer exists, until a check was pressed.
    """
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    march = await _source(app, auth_headers, "march.txt", "2026-03-10")
    kept = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    overruled = await _fact(app, auth_headers, tmp_path, march, "Refunds up to 500 need none.")
    ctr = await _contradiction(app, auth_headers, tmp_path, [kept, overruled], presumed=overruled)
    await _create(app, auth_headers)
    await _saved(app, run_headers, _requirement("r1", "Refunds up to 300 euros need none."))
    await _firing_with_conflicts(
        [
            {
                "requirement": "r1",
                "fact": fact,
                "statement": "Refunds up to 300 euros need none.",
                "explanation": "Differs.",
            }
            for fact in (overruled, "fct-ffffffffffff")
        ]
    )
    shown = await _warnings(app, auth_headers)
    # Open still, the overruled-to-be fact is shown; the one that is not in the vault is not.
    assert [w["fact"] for w in shown] == [overruled]

    resolved = await app.post(
        f"{PROJECT}/vault/contradictions/{ctr}/resolve",
        json={"stands": kept, "note": "January was right"},
        headers=auth_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert await _warnings(app, auth_headers) == []


# ---------------------------------------------------------------------------
# gaps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_warning_is_a_vault_warning_gap_and_approve_anyway_still_approves(
    app, auth_headers, run_headers  # noqa: F811
) -> None:
    await _create(app, auth_headers)
    await _saved(app, run_headers, _requirement("alpha", "It responds within 200ms", [MISSING]))

    proposed = await _propose(app, auth_headers)
    assert proposed["proposed"] is True and proposed["blocking"] == []
    gaps = [w for w in proposed["warnings"] if w["code"] == "vault_warning"]
    assert [g["where"] for g in gaps] == ["requirements[0]"]
    assert MISSING in gaps[0]["message"]

    phase = f"{DOCS}/documents/phase"
    refused = await app.post(
        phase, params={"path": PATH, "to": "approved"}, json={"reason": ""}, headers=auth_headers
    )
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "approval_warnings"
    assert [w["where"] for w in detail["warnings"] if w["code"] == "vault_warning"] == [
        "requirements[0]"
    ]

    approved = await app.post(
        phase,
        params={"path": PATH, "to": "approved"},
        json={"reason": "", "approve_anyway": True},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    listed = await app.get(f"{DOCS}/documents", headers=auth_headers)
    row = next(d for d in listed.json()["documents"] if d["path"] == PATH)
    assert row["phase"] == "approved"
    assert "vault_warning" in {w["code"] for w in row["approval_warnings_overridden"]}
