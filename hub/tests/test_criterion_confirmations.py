"""Confirmed acceptance criteria and the approval gate
(`existing-behaviour-is-caught-before-the-build`, task confirmations-and-the-gate).

Each test is named by the criterion it demonstrates. The whole drive is
`test_existing_behaviour_caught_before_build.py`; this file covers the rest of FR-2, FR-3, FR-4,
FR-5 and FR-8 through the real routes: an agent's save, its `confirm-criteria`, its read, and the
operator's Check and approval.
"""

import pytest

from hub import spec_completeness
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.spec_digest import criterion_digest
from hub.spec_payload import SpecPayload

from ._spec_confirmations import confirm_criteria
from ._spec_versions import content_version
from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    AGENT,
    BASE,
    PATH,
    _create,
    _document,
    _submit,
    run_headers,
)

CONFIRM = f"{AGENT}/confirm-criteria"
OTHER = "spec/changes/no-criteria/spec.json"


@pytest.fixture
async def second_agent_headers():
    """A run of a different agent than the one `run_headers` authenticates (claude-1)."""
    token = "aw_run_second-agent-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-second-agent",
                project_id="proj-test",
                agent="claude-2",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _criterion(key, then="t", guard=None, requirement="alpha"):
    criterion = {"key": key, "requirement": requirement, "given": "g", "when": "w", "then": then}
    if guard is not None:
        criterion["guard"] = guard
    return criterion


async def _write(app, auth_headers, run_headers, criteria, path=PATH):  # noqa: F811
    await _create(app, auth_headers, path)
    return await _save(app, run_headers, criteria, path)


async def _save(app, run_headers, criteria, path=PATH):  # noqa: F811
    saved = await _submit(app, run_headers, _document(acceptance_criteria=criteria), path)
    assert saved.status_code == 200, saved.text
    return saved.json()


async def _confirm(app, headers, *pairs, path=PATH):
    return await app.post(
        CONFIRM,
        json={"path": path, "confirmations": [{"criterion": c, "kind": k} for c, k in pairs]},
        headers=headers,
    )


async def _check(app, auth_headers, path=PATH):
    response = await app.post(
        f"{BASE}/documents/check", params={"path": path}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _phase(app, auth_headers, to, path=PATH, **body):
    if to == "approved":
        body["content_version"] = await content_version(app, auth_headers, path)
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": to},
        json={"reason": "", **body},
        headers=auth_headers,
    )


def _gap(findings):
    found = [f for f in findings if f["code"] == "criteria_unconfirmed"]
    return found[0] if found else None


async def _criteria_read(app, run_headers):  # noqa: F811
    read = await app.get(AGENT, params={"path": PATH}, headers=run_headers)
    assert read.status_code == 200, read.text
    return {
        criterion["key"]: criterion
        for requirement in read.json()["requirements"]
        for criterion in requirement["acceptance_criteria"]
    }


# ---------------------------------------------------------------------------
# FR-2 gap-names-unconfirmed-criteria
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gap_names_unconfirmed_criteria(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _write(
        app, auth_headers, run_headers, [_criterion("one"), _criterion("two"), _criterion("three")]
    )
    assert (await _confirm(app, run_headers, ("two", "new"))).status_code == 200
    saved = await _save(
        app, run_headers, [_criterion("one"), _criterion("two"), _criterion("three")]
    )
    checked = await _check(app, auth_headers)

    on_save, in_check = _gap(saved["blocking"]), _gap(checked["blocking"])
    assert on_save is not None and on_save == in_check
    assert on_save["where"] == "acceptance_criteria"
    assert "'one'" in on_save["message"] and "'three'" in on_save["message"]
    assert "'two'" not in on_save["message"]
    assert "confirm_acceptance_criteria" in on_save["message"]
    assert checked["ready"] is False

    await _create(app, auth_headers, OTHER)
    bare = await _submit(app, run_headers, _document(acceptance_criteria=[]), OTHER)
    assert bare.status_code == 200, bare.text
    assert _gap(bare.json()["blocking"]) is None
    assert _gap((await _check(app, auth_headers, OTHER))["blocking"]) is None


def test_the_gap_is_a_refusal_and_only_for_a_change_with_criteria():
    """D5: approve_anyway cannot pass it; a capability or a change with no criteria never draws it."""
    assert "criteria_unconfirmed" in spec_completeness.REFUSAL_CODES
    change = SpecPayload.model_validate(_document(acceptance_criteria=[_criterion("c1")]))
    assert [f.code for f in spec_completeness.unconfirmed_criteria_findings(change, {})] == [
        "criteria_unconfirmed"
    ]
    capability = SpecPayload.model_validate(
        {**_document(acceptance_criteria=[_criterion("c1")]), "kind": "capability", "tasks": []}
    )
    codes = {f.code for f in spec_completeness.check(capability, confirmations={})}
    assert "criteria_unconfirmed" not in codes


# ---------------------------------------------------------------------------
# FR-3 confirmation-records-kind-and-who
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirmation_records_kind_and_who(
    app, auth_headers, run_headers, second_agent_headers, tmp_path  # noqa: F811
):
    await _write(
        app, auth_headers, run_headers, [_criterion("fresh"), _criterion("kept", guard=True)]
    )
    before = await _criteria_read(app, run_headers)
    assert before["fresh"]["confirmation"] is None and before["kept"]["confirmation"] is None

    confirmed = await _confirm(app, second_agent_headers, ("fresh", "new"), ("kept", "guard"))

    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["path"] == PATH and body["unconfirmed"] == []
    assert {(c["criterion"], c["kind"], c["by"]) for c in body["confirmed"]} == {
        ("fresh", "new", "claude-2"),
        ("kept", "guard", "claude-2"),
    }
    read = await _criteria_read(app, run_headers)
    for key, kind in (("fresh", "new"), ("kept", "guard")):
        confirmation = read[key]["confirmation"]
        assert (confirmation["kind"], confirmation["by"], confirmation["current"]) == (
            kind,
            "claude-2",
            True,
        )
        assert confirmation["at"]
    assert read["kept"]["guard"] is True
    assert _gap((await _check(app, auth_headers))["blocking"]) is None


@pytest.mark.asyncio
async def test_a_read_resubmitted_keeps_its_confirmations(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    """F452: the read's `confirmation` is dropped on resubmission and its `guard` kept, so the
    round trip leaves every criterion confirmed."""
    await _write(
        app, auth_headers, run_headers, [_criterion("fresh"), _criterion("kept", guard=True)]
    )
    assert (
        await _confirm(app, run_headers, ("fresh", "new"), ("kept", "guard"))
    ).status_code == 200
    read = await app.get(AGENT, params={"path": PATH}, headers=run_headers)
    document = {**_document(acceptance_criteria=[]), "requirements": read.json()["requirements"]}

    resaved = await _submit(app, run_headers, document)

    assert resaved.status_code == 200, resaved.text
    assert _gap(resaved.json()["blocking"]) is None
    assert "unknown_field" not in {b["code"] for b in resaved.json()["blocking"]}


# ---------------------------------------------------------------------------
# FR-3 confirming-is-refused-outside-exploring-and-for-the-operator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirming_is_refused_outside_exploring_and_for_the_operator(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    approved_path, exploring_path = "spec/changes/signed/spec.json", PATH
    await _write(app, auth_headers, run_headers, [_criterion("late")], approved_path)
    # Approved before this change could gate it: written straight to the phase, as a document
    # approved before the gate shipped is (FR-8 scope: approved documents are not re-checked).
    async with async_session_factory() as session:
        from hub import spec_lifecycle

        document = await spec_lifecycle.get_document(session, "proj-test", approved_path)
        document.phase = spec_lifecycle.APPROVED
        await session.commit()
    await _write(app, auth_headers, run_headers, [_criterion("open")], exploring_path)

    on_approved = await _confirm(app, run_headers, ("late", "new"), path=approved_path)
    by_operator = await _confirm(app, auth_headers, ("open", "new"), path=exploring_path)

    assert on_approved.status_code == 409, on_approved.text
    assert on_approved.json()["detail"]["code"] == "document_not_exploring"
    assert "approved" in on_approved.json()["detail"]["message"]
    assert "reopen" in on_approved.json()["detail"]["message"]
    assert by_operator.status_code == 403, by_operator.text
    assert by_operator.json()["detail"]["code"] == "agent_only"
    assert _gap((await _check(app, auth_headers, approved_path))["blocking"]) is not None
    assert _gap((await _check(app, auth_headers, exploring_path))["blocking"]) is not None

    reopened = await _phase(app, auth_headers, "exploring", approved_path)
    assert reopened.status_code == 200, reopened.text
    after = await _confirm(app, run_headers, ("late", "new"), path=approved_path)
    assert after.status_code == 200, after.text
    assert after.json()["unconfirmed"] == []


@pytest.mark.asyncio
async def test_each_refusal_records_nothing(app, auth_headers, run_headers, tmp_path):  # noqa: F811
    """D4: unknown criterion, unknown kind and a kind against the guard flag, all or none."""
    await _write(
        app, auth_headers, run_headers, [_criterion("plain"), _criterion("kept", guard=True)]
    )
    cases = [
        ((("plain", "new"), ("ghost", "new")), "criterion_unknown", "ghost"),
        ((("plain", "new"), ("kept", "maybe")), "confirmation_kind_unknown", "kept"),
        ((("plain", "guard"),), "confirmation_kind_mismatch", "plain"),
        ((("plain", "new"), ("kept", "new")), "confirmation_kind_mismatch", "kept"),
    ]
    for pairs, code, named in cases:
        refused = await _confirm(app, run_headers, *pairs)
        assert refused.status_code == 422, refused.text
        assert refused.json()["detail"]["code"] == code
        assert named in refused.json()["detail"]["message"]
    missing = await _confirm(app, run_headers, ("plain", "new"), path="spec/changes/nope/spec.json")
    assert missing.status_code == 404
    read = await _criteria_read(app, run_headers)
    assert read["plain"]["confirmation"] is None and read["kept"]["confirmation"] is None


# ---------------------------------------------------------------------------
# FR-4 reword-makes-it-stale
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reword_makes_it_stale(app, auth_headers, run_headers, tmp_path):  # noqa: F811
    first = [_criterion("worded"), _criterion("flagged"), _criterion("untouched")]
    await _write(app, auth_headers, run_headers, first)
    confirmed = await _confirm(
        app, run_headers, ("worded", "new"), ("flagged", "new"), ("untouched", "new")
    )
    assert confirmed.status_code == 200, confirmed.text
    assert _gap((await _check(app, auth_headers))["blocking"]) is None
    # how_to_check and checked_by say how it is shown, not what it is (D2): still confirmed
    shown = {**_criterion("untouched"), "how_to_check": "a test", "checked_by": "agent"}

    saved = await _save(
        app,
        run_headers,
        [
            _criterion("worded", then="reworded"),
            _criterion("flagged", guard=True),
            shown,
            _criterion("added"),
        ],
    )

    message = _gap(saved["blocking"])["message"]
    for key in ("'worded'", "'flagged'", "'added'"):
        assert key in message
    assert "'untouched'" not in message
    read = await _criteria_read(app, run_headers)
    assert read["untouched"]["confirmation"]["current"] is True
    assert read["worded"]["confirmation"]["current"] is False
    assert read["flagged"]["confirmation"]["current"] is False
    assert read["added"]["confirmation"] is None


def test_the_digest_follows_what_the_criterion_says():
    base = criterion_digest("alpha", "g", "w", "t", None)
    assert base == criterion_digest("alpha", " g", "w\n", "t", False)
    assert base != criterion_digest("alpha", "g", "w", "t2", None)
    assert base != criterion_digest("beta", "g", "w", "t", None)
    assert base != criterion_digest("alpha", "g", "w", "t", True)


# ---------------------------------------------------------------------------
# FR-8 existing-document-is-refused-too
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_document_is_refused_too(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    """A document saved in the pre-change shape: its criteria carry no confirmation, and nothing
    in its file can say otherwise. Approval is refused, with or without approve_anyway."""
    criteria = [_criterion("old-one"), _criterion("old-two", guard=True)]
    await _write(app, auth_headers, run_headers, criteria)

    for body in ({}, {"approve_anyway": True}):
        refused = await _phase(app, auth_headers, "approved", **body)
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert detail["code"] == "document_incomplete"
        gap = _gap(detail["blocking"])
        assert "'old-one'" in gap["message"] and "'old-two'" in gap["message"]
        assert detail["guards"] == [{"criterion": "old-two", "requirement": "FR-1"}]
    assert (await _check(app, auth_headers))["phase"] == "exploring"


# ---------------------------------------------------------------------------
# FR-5 approval-lists-guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_lists_guards(app, auth_headers, run_headers, tmp_path):  # noqa: F811
    await _write(
        app, auth_headers, run_headers, [_criterion("plain"), _criterion("kept", guard=True)]
    )
    await confirm_criteria(PATH)

    checked = await _check(app, auth_headers)
    approved = await _phase(app, auth_headers, "approved", approve_anyway=True)

    expected = [{"criterion": "kept", "requirement": "FR-1"}]
    assert checked["guards"] == expected
    assert approved.status_code == 200, approved.text
    assert approved.json()["guards"] == expected
