"""A system map proposes capabilities and each draft is approved and folded
(`a-project-with-no-specs-is-offered-a-start`, spdoc-7d247666f76a, task `drafts`).

FR-12: a system map carries `capabilities.creates` only. FR-11: a no-task change drafting only
titles a map proposes draws no `requirement_without_task`, on save, Check and Approve alike, and is
approved and folded. FR-8: the map lists each proposed title with its draft, matched
case-insensitively, and its state. FR-7: archiving a draft declines it and creates nothing.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
from hub.spec_payload import SCHEMA_VERSION

from ._spec_confirmations import confirm_criteria
from ._spec_versions import content_version
from .test_spec_tidy import _agent

BASE = "/api/v1/projects/proj-test/project"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
MAP = "spec/agentweave-map/spec.json"
ROADMAP = "spec/changes/plan/spec.json"
BILLING = "spec/changes/billing-draft/spec.json"
PAYROLL = "spec/changes/payroll-draft/spec.json"
MIXED = "spec/changes/mixed-draft/spec.json"
BARE = "spec/changes/bare-draft/spec.json"
AUTH = "spec/changes/auth-draft/spec.json"
CAP_ALPHA = "spec/capabilities/alpha/spec.json"
BILLING_CAP = "spec/capabilities/billing/spec.json"


@pytest.fixture
async def writer():
    """An agent's run credential, to submit as an agent does."""
    return await _agent("writer", "aw_run_writer-secret", switch=True)


def _creates(*titles):
    return {"creates": [{"title": t} for t in titles]}


def _map(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "system-map",
        "title": "Map",
        "scope": {"in_scope": ["the code"], "non_goals": ["unread code"]},
        "requirements": [
            {"key": "areas", "statement": "The code MUST have areas.", "modal": "MUST"},
        ],
        "acceptance_criteria": [
            {
                "key": "areas-c",
                "requirement": "areas",
                "given": "the code",
                "when": "read",
                "then": "it has areas",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _draft(title="Billing", capabilities=None, **overrides):
    """A complete change with no tasks describing current behaviour."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": f"{title} as built",
        "scope": {"in_scope": [title.lower()], "non_goals": ["changing it"]},
        "requirements": [
            {"key": "invoices", "statement": "An invoice MUST be issued.", "modal": "MUST"},
            {"key": "receipts", "statement": "A receipt MUST be sent.", "modal": "MUST"},
        ],
        "acceptance_criteria": [
            {
                "key": "invoices-c",
                "requirement": "invoices",
                "given": "an order",
                "when": "paid",
                "then": "an invoice is issued",
                "how_to_check": "billing/invoice.py:12 and its test",
                "checked_by": "agent",
            },
            {
                "key": "receipts-c",
                "requirement": "receipts",
                "given": "a payment",
                "when": "taken",
                "then": "a receipt is sent",
                "how_to_check": "billing/receipt.py:40 and its test",
                "checked_by": "agent",
            },
        ],
        "delivery": {"mode": "none"},
    }
    if capabilities is not None:
        payload["capabilities"] = capabilities
    payload.update(overrides)
    return payload


async def _create(app, auth_headers, path, title, kind=None):
    body = {"path": path, "title": title}
    if kind:
        body["kind"] = kind
    created = await app.post(f"{BASE}/documents", json=body, headers=auth_headers)
    assert created.status_code == 201, created.text


async def _save(app, auth_headers, path, payload):
    return await app.put(
        f"{BASE}/documents/{path}/content", json={"document": payload}, headers=auth_headers
    )


async def _saved(app, auth_headers, path, payload, kind=None):
    await _create(app, auth_headers, path, payload["title"], kind=kind)
    written = await _save(app, auth_headers, path, payload)
    assert written.status_code == 200, written.text
    return written.json()


async def _page(app, auth_headers, path):
    page = await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    assert page.status_code == 200, page.text
    return page.json()


def _codes(findings):
    return [f["code"] for f in findings]


async def _approve(app, auth_headers, path):
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    await confirm_criteria(path)
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": "approved"},
        json={"content_version": await content_version(app, auth_headers, path)},
        headers=auth_headers,
    )


async def _capability_count():
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(SpecDocument)
                .where(SpecDocument.kind == "capability", SpecDocument.phase == "current")
            )
        ).scalar_one()


async def _fold_new(app, auth_headers, capability, title, change, requirements):
    """The operator creates the capability and folds the draft into it in one merge."""
    await _create(app, auth_headers, capability, title, kind="capability")
    return await app.post(
        f"{BASE}/documents/{capability}/merge",
        json={
            "payload": {
                "schema_version": SCHEMA_VERSION,
                "kind": "capability",
                "title": title,
                "requirements": requirements,
            },
            "from_changes": [change],
        },
        headers=auth_headers,
    )


# ------------------------------------------------------------------ FR-12


@pytest.mark.asyncio
async def test_an_agent_saves_a_map_proposing_two_capabilities_and_reads_them(
    app, auth_headers, writer
):
    """ac-map-creates-saved."""
    await _create(app, auth_headers, MAP, "Map", kind="system-map")
    submitted = await app.post(
        AGENT_DOCS,
        json={"path": MAP, "document": _map(capabilities=_creates("Billing", "Auth"))},
        headers=writer,
    )
    assert submitted.status_code == 200, submitted.text
    want = _creates("Billing", "Auth")
    read = await app.get(AGENT_DOCS, params={"path": MAP}, headers=writer)
    assert read.status_code == 200, read.text
    assert read.json()["capabilities"] == {"changes": [], **want}
    page = await _page(app, auth_headers, MAP)
    assert page["capabilities"] == {"changes": [], **want}
    assert [row["title"] for row in page["proposed_capabilities"]] == ["Billing", "Auth"]
    rows = await app.get(f"{BASE}/documents", headers=auth_headers)
    listed = {row["path"]: row for row in rows.json()["documents"]}
    assert listed[MAP]["capabilities"] == {"changes": [], **want}


@pytest.mark.asyncio
async def test_a_map_naming_changes_and_a_roadmap_naming_creates_are_refused(
    app, auth_headers, writer
):
    """ac-map-changes-refused."""
    await _create(app, auth_headers, MAP, "Map", kind="system-map")
    refused = await app.post(
        AGENT_DOCS,
        json={
            "path": MAP,
            "document": _map(capabilities={"changes": [CAP_ALPHA], "creates": []}),
        },
        headers=writer,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "payload_invalid"
    assert refused.json()["detail"]["field"] == "capabilities"

    await _create(app, auth_headers, ROADMAP, "Plan", kind="roadmap")
    roadmap = {
        "schema_version": SCHEMA_VERSION,
        "kind": "roadmap",
        "title": "Plan",
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "slices": [{"key": "one", "title": "One", "intent": "first", "done": "it works"}],
        "capabilities": _creates("Billing"),
    }
    refused = await app.post(
        AGENT_DOCS, json={"path": ROADMAP, "document": roadmap}, headers=writer
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "payload_invalid"
    assert refused.json()["detail"]["field"] == "capabilities"

    # A change document's capabilities behave as before.
    saved = await _saved(app, auth_headers, BILLING, _draft(capabilities=_creates("Billing")))
    assert "capability_unnamed" not in _codes(saved["warnings"])
    page = await _page(app, auth_headers, BILLING)
    assert page["capabilities"] == {"changes": [], **_creates("Billing")}


# ------------------------------------------------------------------ FR-11


@pytest.mark.asyncio
async def test_a_draft_a_map_proposes_is_ready_checked_approved_and_folded(
    app, auth_headers, writer
):
    """ac-no-task-ready: save, Check, Approve and fold apply one rule."""
    await _saved(app, auth_headers, MAP, _map(capabilities=_creates("Billing")), kind="system-map")
    await _create(app, auth_headers, BILLING, "Billing as built")
    # Written whole in one go, so its journey step is recorded as done (`steps_skipped` is not
    # this slice's gap).
    stepped = await app.post(
        f"{BASE}/documents/journey",
        params={"path": BILLING},
        json={"step": "build"},
        headers=auth_headers,
    )
    assert stepped.status_code == 200, stepped.text
    submitted = await app.post(
        AGENT_DOCS,
        json={"path": BILLING, "document": _draft(capabilities=_creates("Billing"))},
        headers=writer,
    )
    assert submitted.status_code == 200, submitted.text
    # Its criteria are confirmed, and saved again as a confirmed document is.
    await confirm_criteria(BILLING)
    submitted = await app.post(
        AGENT_DOCS,
        json={"path": BILLING, "document": _draft(capabilities=_creates("Billing"))},
        headers=writer,
    )
    assert submitted.status_code == 200, submitted.text
    saved = submitted.json()
    assert "requirement_without_task" not in _codes(saved["warnings"])
    assert saved["ready_to_approve"] is True, (saved["warnings"], saved["blocking"])

    checked = await app.post(
        f"{BASE}/documents/check", params={"path": BILLING}, headers=auth_headers
    )
    assert checked.status_code == 200, checked.text
    assert "requirement_without_task" not in _codes(checked.json()["warnings"])
    assert checked.json()["ready"] is True, checked.json()

    approved = await _approve(app, auth_headers, BILLING)
    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved", approved.text

    before = await _capability_count()
    folded = await _fold_new(
        app,
        auth_headers,
        BILLING_CAP,
        "Billing",
        BILLING,
        [
            {"key": "invoices", "statement": "An invoice MUST be issued.", "modal": "MUST"},
            {"key": "receipts", "statement": "A receipt MUST be sent.", "modal": "MUST"},
        ],
    )
    assert folded.status_code == 200, folded.text
    assert await _capability_count() == before + 1
    page = await _page(app, auth_headers, MAP)
    assert page["proposed_capabilities"] == [
        {
            "title": "Billing",
            "state": "current",
            "draft": {"path": BILLING, "title": "Billing as built", "phase": "approved"},
        }
    ]


@pytest.mark.asyncio
async def test_the_exemption_is_only_for_drafts_of_proposed_titles(app, auth_headers):
    """ac-exemption-narrow: an unproposed title, a draft that also changes a capability, and a
    change naming no capability each draw requirement_without_task for every requirement."""
    await _create(app, auth_headers, CAP_ALPHA, "Alpha", kind="capability")
    merged = await app.post(
        f"{BASE}/documents/{CAP_ALPHA}/merge",
        json={
            "payload": {
                "schema_version": SCHEMA_VERSION,
                "kind": "capability",
                "title": "Alpha",
                "requirements": [{"key": "a", "statement": "A MUST be.", "modal": "MUST"}],
            },
            "from_changes": [],
        },
        headers=auth_headers,
    )
    assert merged.status_code == 200, merged.text
    await _saved(app, auth_headers, MAP, _map(capabilities=_creates("Billing")), kind="system-map")
    cases = {
        PAYROLL: _draft("Payroll", capabilities=_creates("Payroll")),
        MIXED: _draft(capabilities={"changes": [CAP_ALPHA], **_creates("Billing")}),
        BARE: _draft(),
    }
    for path, payload in cases.items():
        saved = await _saved(app, auth_headers, path, payload)
        where = [w["where"] for w in saved["warnings"] if w["code"] == "requirement_without_task"]
        assert where == ["requirements[0]", "requirements[1]"], (path, saved["warnings"])


@pytest.mark.asyncio
async def test_a_draft_stops_being_exempt_when_it_gains_a_task(app, auth_headers):
    await _saved(app, auth_headers, MAP, _map(capabilities=_creates("Billing")), kind="system-map")
    tasked = _draft(
        capabilities=_creates("Billing"),
        tasks=[{"key": "t1", "description": "Build it", "requirements": ["invoices"]}],
    )
    saved = await _saved(app, auth_headers, BILLING, tasked)
    where = [w["where"] for w in saved["warnings"] if w["code"] == "requirement_without_task"]
    assert where == ["requirements[1]"]


# ------------------------------------------------------------------ FR-8, FR-7


@pytest.mark.asyncio
async def test_a_map_links_a_draft_whose_title_differs_only_in_case(app, auth_headers, writer):
    """ac-map-links-case, read by the operator's page and an agent alike."""
    await _saved(
        app,
        auth_headers,
        MAP,
        _map(capabilities=_creates("Billing", "Auth", "Reports")),
        kind="system-map",
    )
    saved = await _saved(app, auth_headers, BILLING, _draft("billing", _creates("billing")))
    # The exemption matches case-insensitively too.
    assert "requirement_without_task" not in _codes(saved["warnings"])
    await _saved(app, auth_headers, AUTH, _draft("Auth", _creates("AUTH")))
    want = [
        {
            "title": "Billing",
            "state": "exploring",
            "draft": {"path": BILLING, "title": "billing as built", "phase": "exploring"},
        },
        {
            "title": "Auth",
            "state": "exploring",
            "draft": {"path": AUTH, "title": "Auth as built", "phase": "exploring"},
        },
        {"title": "Reports", "state": "no-draft", "draft": None},
    ]
    assert (await _page(app, auth_headers, MAP))["proposed_capabilities"] == want
    read = await app.get(AGENT_DOCS, params={"path": MAP}, headers=writer)
    assert read.json()["proposed_capabilities"] == want


@pytest.mark.asyncio
async def test_archiving_a_draft_declines_it_and_creates_no_capability(app, auth_headers):
    """ac-decline."""
    await _saved(app, auth_headers, MAP, _map(capabilities=_creates("Billing")), kind="system-map")
    await _saved(app, auth_headers, BILLING, _draft(capabilities=_creates("Billing")))
    before = await _capability_count()
    archived = await app.post(
        f"{BASE}/documents/phase",
        params={"path": BILLING, "to": "archived"},
        json={"reason": "not how we see it"},
        headers=auth_headers,
    )
    assert archived.status_code == 200, archived.text
    assert await _capability_count() == before
    rows = (await _page(app, auth_headers, MAP))["proposed_capabilities"]
    assert [(r["title"], r["state"], r["draft"]["path"]) for r in rows] == [
        ("Billing", "declined", BILLING)
    ]
    # A fresh draft after the declined one is the title's draft.
    await _saved(app, auth_headers, PAYROLL, _draft("Billing again", _creates("Billing")))
    rows = (await _page(app, auth_headers, MAP))["proposed_capabilities"]
    assert [(r["state"], r["draft"]["path"]) for r in rows] == [("exploring", PAYROLL)]


@pytest.mark.asyncio
async def test_an_ordinary_exploring_change_still_cannot_be_archived(app, auth_headers):
    """Declining is for drafts only: a change creating an unproposed title keeps the refusal."""
    await _saved(app, auth_headers, MAP, _map(capabilities=_creates("Billing")), kind="system-map")
    await _saved(app, auth_headers, PAYROLL, _draft("Payroll", _creates("Payroll")))
    refused = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PAYROLL, "to": "archived"},
        json={"reason": "no"},
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "archive_would_orphan_work"
