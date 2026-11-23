"""The facts' uses by specs, project-wide (`a-vault-page-that-says-what-it-holds` FR-3).

`GET /vault/fact-uses` answers, per fact, the requirements citing it and the conflicts the newest
spec-vault-check firing of each document found, kept by the rule `GET /vault/warnings` applies
(`vault_spec_check.standing_conflicts`), so the Vault page and a spec's warnings never disagree.
Its timed call on a read-only copy of the project's database is the evidence's, not this file's.
"""

import pytest

from hub import manager, vault_spec_check
from hub.db.engine import async_session_factory

from ._spec_confirmations import confirm_criteria
from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    PATH,
    _create,
    _submit,
    run_headers,
)
from .test_vault_spec_check import (
    HAIKU,
    JANUARY,
    JOB,
    MARCH,
    PROJECT,
    _contradiction,
    _fact,
    _payload,
    _requirement,
    _source,
    _warnings,
)

OTHER = "spec/changes/refunds/spec.json"


async def _save(app, run_headers, path: str, title: str, *requirements) -> None:  # noqa: F811
    payload = _payload(*requirements)
    payload["title"] = title
    saved = await _submit(app, run_headers, payload, path=path)
    assert saved.status_code == 200, saved.text
    await confirm_criteria(path)


async def _fire(path: str, conflicts: list) -> None:
    async with async_session_factory() as db:
        await manager.record_firing(
            db,
            "proj-test",
            job=JOB,
            trigger="document_proposed",
            subject={"document": path},
            runner_id="runner-x",
            cli="claude",
            model=HAIKU,
            outcome="written",
            detail=f"{len(conflicts)} conflicts kept",
            duration_ms=1,
            usage=None,
            extra={"conflicts": conflicts},
        )


async def _uses(app, auth_headers) -> dict:
    answered = await app.get(f"{PROJECT}/vault/fact-uses", headers=auth_headers)
    assert answered.status_code == 200, answered.text
    return answered.json()


@pytest.mark.asyncio
async def test_uses_route_rule(app, auth_headers, run_headers, tmp_path) -> None:  # noqa: F811
    """uses-route-rule: F is answered with its one citation; G (set aside by a decision) and H
    (its requirement reworded since the firing) are not; and the warnings route agrees."""
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    march = await _source(app, auth_headers, MARCH, "2026-03-10")
    f = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    g = await _fact(app, auth_headers, tmp_path, march, "Refunds up to 500 need none.")
    h = await _fact(app, auth_headers, tmp_path, january, "Refunds are paid in euros.")
    i = await _fact(app, auth_headers, tmp_path, january, "Refunds are paid within a week.")
    kept = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 are automatic.")

    await _create(app, auth_headers)
    await _save(app, run_headers, PATH, "Demo", _requirement("r1", "Refunds are logged.", [f]))
    await _create(app, auth_headers, path=OTHER)
    statements = {
        "g1": "Refunds up to 1,000 need none.",
        "h1": "Refunds are paid in dollars.",
        "i1": "Refunds are paid within a month.",
    }
    await _save(
        app, run_headers, OTHER, "Refunds", *(_requirement(k, s) for k, s in statements.items())
    )
    await _fire(
        OTHER,
        [
            {
                "requirement": key,
                "fact": fact,
                "statement": statements[key],
                "explanation": "Differs.",
            }
            for key, fact in (("g1", g), ("h1", h), ("i1", i))
        ],
    )
    # Before anything changed, every conflict is shown, on both routes.
    before = {u["fact"] for u in (await _uses(app, auth_headers))["uses"] if u["conflicts"]}
    assert before == {g, h, i}
    assert {w["fact"] for w in await _warnings(app, auth_headers, OTHER)} == {g, h, i}

    # Since that firing: a decision sets G aside, and the requirement against H is reworded.
    ctr = await _contradiction(app, auth_headers, tmp_path, [kept, g], presumed=g)
    resolved = await app.post(
        f"{PROJECT}/vault/contradictions/{ctr}/resolve",
        json={"stands": kept, "note": "January was right"},
        headers=auth_headers,
    )
    assert resolved.status_code == 200, resolved.text
    statements["h1"] = "Refunds are paid in the customer's currency."
    await _save(
        app, run_headers, OTHER, "Refunds", *(_requirement(k, s) for k, s in statements.items())
    )

    answered = await _uses(app, auth_headers)
    assert answered["unreadable"] == []
    by_fact = {u["fact"]: u for u in answered["uses"]}
    assert by_fact[f] == {
        "fact": f,
        "citations": [
            {
                "document": PATH,
                "title": "Demo",
                "requirement": "FR-1",
                "statement": "Refunds are logged.",
            }
        ],
        "conflicts": [],
    }
    assert g not in by_fact and h not in by_fact
    [conflict] = by_fact[i]["conflicts"]
    assert conflict["document"] == OTHER and conflict["title"] == "Refunds"
    assert conflict["requirement"] == "FR-3"
    assert conflict["statement"] == statements["i1"]
    assert conflict["explanation"] == "Differs." and conflict["checked_at"]

    conflicting = {u["fact"] for u in answered["uses"] if u["conflicts"]}
    warned = {
        w["fact"] for w in await _warnings(app, auth_headers, OTHER) if w["kind"] == "conflict"
    }
    assert conflicting == warned == {i}


@pytest.mark.asyncio
async def test_only_the_newest_firing_of_a_document_counts(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
) -> None:
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    old = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    new = await _fact(app, auth_headers, tmp_path, january, "Refunds are paid in euros.")
    await _create(app, auth_headers)
    await _save(app, run_headers, PATH, "Demo", _requirement("r1", "Refunds need approval."))
    conflict = {"requirement": "r1", "statement": "Refunds need approval.", "explanation": "x"}
    await _fire(PATH, [{**conflict, "fact": old}])
    await _fire(PATH, [{**conflict, "fact": new}])

    uses = (await _uses(app, auth_headers))["uses"]
    assert [u["fact"] for u in uses] == [new]


@pytest.mark.asyncio
async def test_an_unreadable_document_is_named_and_the_others_still_answer(
    app, auth_headers, run_headers, tmp_path, monkeypatch  # noqa: F811
) -> None:
    january = await _source(app, auth_headers, JANUARY, "2026-01-10")
    f = await _fact(app, auth_headers, tmp_path, january, "Refunds up to 300 need none.")
    await _create(app, auth_headers)
    await _save(app, run_headers, PATH, "Demo", _requirement("r1", "Refunds are logged.", [f]))
    await _create(app, auth_headers, path=OTHER)

    real = vault_spec_check.spec_documents.read_payload

    def read_payload(workspace, path):
        if path == OTHER:
            raise OSError("disk says no")
        return real(workspace, path)

    monkeypatch.setattr(vault_spec_check.spec_documents, "read_payload", read_payload)
    answered = await _uses(app, auth_headers)
    assert answered["unreadable"] == [{"document": OTHER, "reason": "disk says no"}]
    assert [u["fact"] for u in answered["uses"]] == [f]


@pytest.mark.asyncio
async def test_an_event_log_that_cannot_be_read_answers_503(app, auth_headers, monkeypatch) -> None:
    async def broken(session, project_id):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(vault_spec_check, "newest_firings", broken)
    answered = await app.get(f"{PROJECT}/vault/fact-uses", headers=auth_headers)
    assert answered.status_code == 503
    assert "database is locked" in answered.json()["detail"]
