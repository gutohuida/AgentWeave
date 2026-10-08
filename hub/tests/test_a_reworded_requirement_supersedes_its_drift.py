"""F435: rewording or retiring a requirement supersedes its open drift candidates.

`RequirementDrift.digest` is documented as "the requirement digest at the moment this was raised, so a
rewording supersedes it rather than leaving a candidate about a question that has moved on", and
`DRIFT_STATES` carries `superseded`, but no code wrote it: a reworded requirement left its candidate
open, asking the operator about an implementation measured against words the document no longer has.
"""

import pytest

from hub.spec_payload import SCHEMA_VERSION

from .test_requirement_drift import (
    ALPHA,
    BASE,
    PATH,
    SUBMIT,
    _detect,
    _document,
    _record,
    builder,  # noqa: F401 - the fixture, used by name
)


async def _resubmit(app, run_headers, requirements):
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Drift demo",
                "requirements": requirements,
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _drift(app, auth_headers, state=None):
    params = {"state": state} if state else {}
    listed = await app.get(f"{BASE}/spec/drift", params=params, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()["drift"]


async def _raise_candidate(app, auth_headers, builder, tmp_path):  # noqa: F811
    await _document(app, auth_headers, builder)
    (tmp_path / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    await _record(app, auth_headers)
    (tmp_path / "ledger.py").write_text("def split(a, b): return a - b\n", encoding="utf-8")
    assert len(await _detect(app, auth_headers)) == 1


@pytest.mark.asyncio
async def test_rewording_supersedes_the_open_candidate(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await _raise_candidate(app, auth_headers, builder, tmp_path)

    await _resubmit(app, builder, [dict(ALPHA, statement="It lists what is overdue")])

    assert [d["state"] for d in await _drift(app, auth_headers)] == ["superseded"]
    assert await _drift(app, auth_headers, "candidate") == []
    assert len(await _drift(app, auth_headers, "superseded")) == 1


@pytest.mark.asyncio
async def test_retiring_supersedes_the_open_candidate(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await _raise_candidate(app, auth_headers, builder, tmp_path)

    await _resubmit(app, builder, [{"key": "beta", "statement": "Something else", "modal": "MUST"}])

    assert [d["state"] for d in await _drift(app, auth_headers)] == ["superseded"]


@pytest.mark.asyncio
async def test_an_unchanged_requirement_keeps_its_candidate(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await _raise_candidate(app, auth_headers, builder, tmp_path)

    # Same wording, a requirement added beside it.
    await _resubmit(
        app, builder, [ALPHA, {"key": "beta", "statement": "Something else", "modal": "MUST"}]
    )

    assert [d["state"] for d in await _drift(app, auth_headers)] == ["candidate"]
