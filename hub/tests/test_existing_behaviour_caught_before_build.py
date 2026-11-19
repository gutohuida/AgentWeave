"""Existing behaviour is caught before the build: the acceptance drive (EBCBB-1).

Change: spec/changes/existing-behaviour-is-caught-before-the-build. The drive goes through the
real routes: an agent's save, the agent's `confirm-criteria`, the operator's Check, and the
operator's approval with and without `approve_anyway`, against the contract in D4-D6.

Each `test_check_*` is one check of the drive, named by the criterion it demonstrates, and builds its
own state, so each is reached and fails at its own assertion on the pre-build code. The test
`test_drive_unattended_approval_is_safe` runs the whole sequence the criterion describes.

The guard `agent-guard-amendment-is-a-proposal` is behaviour the code already has
(hub/hub/spec_amendments.py:76-78, 541-547) and is listed as a guard: `test_tester_amendments.py`
keeps it, and it is not among the checks here.

Every test is marked expected-to-fail until the build lands (`confirmations-and-the-gate`); the
`run-the-drive` task removes the mark.
"""

import pytest

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

UNTIL_BUILT = pytest.mark.xfail(
    reason="the confirmation gate is built by task confirmations-and-the-gate", strict=False
)

CONFIRM = f"{AGENT}/confirm-criteria"


def _criterion(key, then, guard=False):
    return {
        "key": key,
        "requirement": "alpha",
        "given": "g",
        "when": "w",
        "then": then,
        "how_to_check": "a test",
        "checked_by": "agent",
        "guard": guard,
    }


def _two_criteria():
    """One criterion describing behaviour the code already has, one describing new behaviour,
    neither confirmed. The first is written as a guard: confirming it as one must agree."""
    task = {
        "key": "t1",
        "description": "Build it",
        "requirements": ["alpha"],
        "builder": "Developer",
        "builder_reason": "Sonnet is cheap enough for a small task.",
        "checker": "QA",
        "checker_reason": "A different agent, and Opus checks the work well.",
    }
    return _document(
        acceptance_criteria=[
            _criterion("already-holds", "the existing thing still works", guard=True),
            _criterion("brand-new", "the new thing works"),
        ],
        tasks=[task],
    )


async def _written(app, auth_headers, run_headers):  # noqa: F811
    await _create(app, auth_headers)
    saved = await _submit(app, run_headers, _two_criteria())
    assert saved.status_code == 200, saved.text
    return saved.json()


async def _confirm(app, headers, *confirmations):
    return await app.post(
        CONFIRM,
        json={
            "path": PATH,
            "confirmations": [{"criterion": c, "kind": k} for c, k in confirmations],
        },
        headers=headers,
    )


async def _check(app, auth_headers):
    return await app.post(f"{BASE}/documents/check", params={"path": PATH}, headers=auth_headers)


async def _approve(app, auth_headers, **body):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={
            "reason": "",
            "content_version": await content_version(app, auth_headers, PATH),
            **body,
        },
        headers=auth_headers,
    )


def _unconfirmed(findings):
    """The criteria the `criteria_unconfirmed` finding names, from its message."""
    found = [f for f in findings if f.get("code") == "criteria_unconfirmed"]
    assert found, f"no criteria_unconfirmed finding among {[f.get('code') for f in findings]}"
    return found[0]


def _names(finding, *keys):
    return all(key in finding["message"] for key in keys)


# check drive-unattended-approval-is-safe, step 1: the save names both in a blocking gap
@UNTIL_BUILT
@pytest.mark.asyncio
async def test_check_save_names_both_criteria_in_a_blocking_gap(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    saved = await _written(app, auth_headers, run_headers)

    gap = _unconfirmed(saved["blocking"])
    assert _names(gap, "already-holds", "brand-new")
    assert gap["where"] == "acceptance_criteria"

    checked = (await _check(app, auth_headers)).json()
    assert _names(_unconfirmed(checked["blocking"]), "already-holds", "brand-new")


# check drive-unattended-approval-is-safe, step 2: approve_anyway is refused naming both
@UNTIL_BUILT
@pytest.mark.asyncio
async def test_check_approve_anyway_is_refused_naming_both(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _written(app, auth_headers, run_headers)

    refused = await _approve(app, auth_headers, approve_anyway=True)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert _names(_unconfirmed(detail["blocking"]), "already-holds", "brand-new")
    assert (await _check(app, auth_headers)).json()["phase"] == "exploring"


# check drive-unattended-approval-is-safe, step 3: the agent confirms; the gap is gone
@UNTIL_BUILT
@pytest.mark.asyncio
async def test_check_confirming_clears_the_gap(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _written(app, auth_headers, run_headers)

    confirmed = await _confirm(app, run_headers, ("already-holds", "guard"), ("brand-new", "new"))

    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["unconfirmed"] == []
    assert {(c["criterion"], c["kind"]) for c in body["confirmed"]} == {
        ("already-holds", "guard"),
        ("brand-new", "new"),
    }
    checked = (await _check(app, auth_headers)).json()
    assert "criteria_unconfirmed" not in {b["code"] for b in checked["blocking"]}


# check drive-unattended-approval-is-safe, step 4: approval succeeds listing the guard
@UNTIL_BUILT
@pytest.mark.asyncio
async def test_check_approval_succeeds_and_lists_the_guard(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _written(app, auth_headers, run_headers)
    # the confirm route is asserted by the other checks; here it is setup only, so that today's
    # code reaches the approval and fails at the `guards` assertion below
    await _confirm(app, run_headers, ("already-holds", "guard"), ("brand-new", "new"))

    approved = await _approve(app, auth_headers, approve_anyway=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"
    assert approved.json()["guards"] == [{"criterion": "already-holds", "requirement": "FR-1"}]


# the whole drive, in the order the criterion gives
@UNTIL_BUILT
@pytest.mark.asyncio
async def test_drive_unattended_approval_is_safe(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    saved = await _written(app, auth_headers, run_headers)
    assert _names(_unconfirmed(saved["blocking"]), "already-holds", "brand-new")

    checked = (await _check(app, auth_headers)).json()
    assert _names(_unconfirmed(checked["blocking"]), "already-holds", "brand-new")

    refused = await _approve(app, auth_headers, approve_anyway=True)
    assert refused.status_code == 409, refused.text
    assert _names(_unconfirmed(refused.json()["detail"]["blocking"]), "already-holds", "brand-new")

    confirmed = await _confirm(app, run_headers, ("already-holds", "guard"), ("brand-new", "new"))
    assert confirmed.status_code == 200, confirmed.text

    checked = (await _check(app, auth_headers)).json()
    assert "criteria_unconfirmed" not in {b["code"] for b in checked["blocking"]}

    # approve_anyway passes the test document's unrelated `steps_skipped` gap, and nothing more:
    # the same flag was refused above while the criteria were unconfirmed
    approved = await _approve(app, auth_headers, approve_anyway=True)
    assert approved.status_code == 200, approved.text
    assert approved.json()["guards"] == [{"criterion": "already-holds", "requirement": "FR-1"}]
