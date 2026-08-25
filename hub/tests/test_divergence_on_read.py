"""F29: approval attaches to bytes, not to a path.

`spec_lifecycle.divergence` existed with exactly one caller, on the **save** path
(`spec_service.py:236`), so tampering was noticed only when somebody tried to write and never when
somebody read. Measured 2026-08-25 by writing `TAMPERED BEHIND THE HUB` into an approved document:
every reader — the operator in the Spec view, and any agent calling `read_spec_document` — received
that text with nothing marking it.

That inverts the guarantee the phase machine is built to provide. The phase is authoritative
because it is read from a row rather than from the file an agent can write; the *content* was
still served from that file, unchecked.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT_SPEC = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/divergence-demo/spec.html"
TAMPER = "<p>TAMPERED BEHIND THE HUB</p>"


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-div", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-div",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_div-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_div-secret"}


async def _make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Divergence demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        AGENT_SPEC,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Divergence demo",
                "summary": "A document somebody will edit behind the Hub",
                "requirements": [
                    {"key": "alpha", "statement": "It states one thing", "modal": "MUST"}
                ],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


def _tamper(tmp_path):
    """Edit the file behind the Hub's back, exactly as the sweep did."""
    target = tmp_path / PATH
    target.write_text(target.read_text(encoding="utf-8") + TAMPER, encoding="utf-8")


async def _recorded_digest():
    async with async_session_factory() as session:
        row = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
        return row.content_digest


# ---------------------------------------------------------------------------
# The operator's read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_untouched_document_reports_no_divergence(app, auth_headers, author):
    await _make_document(app, auth_headers, author)

    body = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()

    assert body["diverged"] is False
    assert "divergence" not in body


@pytest.mark.asyncio
async def test_a_tampered_document_is_served_marked(app, auth_headers, author, tmp_path):
    """The content is still returned — refusing the read would break the ordinary edit-then-save
    flow, and this module's rule is that the Hub surfaces both versions and waits."""
    await _make_document(app, auth_headers, author)
    recorded = await _recorded_digest()
    _tamper(tmp_path)

    response = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert TAMPER in body["content"]
    assert body["diverged"] is True
    assert body["divergence"]["recorded"] == recorded
    assert body["divergence"]["found"] != recorded
    assert "changed outside the Hub" in body["divergence"]["detail"]


# ---------------------------------------------------------------------------
# The agent's read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_reading_a_tampered_document_is_told(app, auth_headers, author, tmp_path):
    """`read_spec_document`'s own docstring ends on "with no way for anyone to detect divergence
    from what was approved" — which was still true of the content it served."""
    await _make_document(app, auth_headers, author)
    _tamper(tmp_path)

    body = (await app.get(AGENT_SPEC, params={"path": PATH}, headers=author)).json()

    assert body["diverged"] is True
    assert "not what was approved" in body["divergence"]["detail"]


@pytest.mark.asyncio
async def test_an_agent_reading_an_intact_document_is_not_alarmed(app, auth_headers, author):
    await _make_document(app, auth_headers, author)

    body = (await app.get(AGENT_SPEC, params={"path": PATH}, headers=author)).json()

    assert body["diverged"] is False


# ---------------------------------------------------------------------------
# The listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_listing_identifies_which_document_diverged(app, auth_headers, author, tmp_path):
    """Otherwise the operator opens every document to find the one that changed."""
    await _make_document(app, auth_headers, author)
    _tamper(tmp_path)

    body = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()

    entries = {entry["path"]: entry for entry in body["documents"]}
    assert entries[PATH]["diverged"] is True


@pytest.mark.asyncio
async def test_the_listing_does_not_cry_wolf(app, auth_headers, author):
    await _make_document(app, auth_headers, author)

    body = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()

    entries = {entry["path"]: entry for entry in body["documents"]}
    assert entries[PATH]["diverged"] is False
