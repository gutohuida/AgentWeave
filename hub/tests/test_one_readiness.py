"""Ready means the same thing to the author and the operator (RMSTA-2).

The save result, Check and Approve list one set of gaps and notes and give one verdict, and an
author or the operator may acknowledge a gap with a reason. Change:
spec/changes/ready-means-the-same-thing-to-the-author-and-the-operator; the acceptance drive is
`scripts/drive/one_readiness_drive.py`.
"""

import pytest
from sqlalchemy import select

from hub import spec_completeness, spec_service
from hub.db.engine import async_session_factory
from hub.db.models import SpecGapAcknowledgement

from ._spec_confirmations import submit_confirmed
from .test_approval_warnings_routes import _check, _checked, _phase
from .test_project_spec_steps import THREAT, _steps, _write
from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    AGENT,
    BASE,
    PATH,
    _create,
    _document,
    run_headers,
)
from .test_spec_documents_api import (
    _submit as _submit_once,
)
from .test_spec_journey_briefing import _place


async def _submit(app, run_headers, document):  # noqa: F811
    """Saved with its criteria confirmed, so readiness here is about everything else."""
    return await submit_confirmed(_submit_once, app, run_headers, document, PATH)


def _gaps(items):
    return sorted(
        {(i["code"], i["where"]) for i in items or [] if i["code"] not in spec_service.NOTE_CODES}
    )


def _notes(items):
    return sorted({i["code"] for i in items or [] if i["code"] in spec_service.NOTE_CODES})


async def _created(app, auth_headers):
    """A document whose recorded step is the journey's last, so `steps_skipped` is not what
    these tests are about (a save moving the step by content is RMSTA-3)."""
    await _create(app, auth_headers)
    await _place(step="build", size="large")


async def _ack_agent(app, run_headers, code, where, reason):  # noqa: F811
    return await app.post(
        f"{AGENT}/acknowledge",
        json={"path": PATH, "code": code, "where": where, "reason": reason},
        headers=run_headers,
    )


async def _ack_operator(app, auth_headers, code, where, reason):
    return await app.post(
        f"{BASE}/documents/acknowledge",
        params={"path": PATH},
        json={"code": code, "where": where, "reason": reason},
        headers=auth_headers,
    )


def _unreviewed(monkeypatch, message=None):
    """One unreviewed amendment, without the tester run it takes to make a real one."""
    said = message if message is not None else ["2 amendments not reviewed"]

    async def one(session, document):
        return [spec_completeness.Finding("amendments_unreviewed", "amendments", said[0])]

    monkeypatch.setattr(spec_service, "_amendments_unreviewed", one)
    return said


def _vault(monkeypatch):
    async def one(session, workspace, document):
        return [spec_completeness.Finding("vault_warning", "requirements[0]", "disputes the vault")]

    monkeypatch.setattr(spec_service, "_vault_warnings", one)


@pytest.mark.asyncio
async def test_save_check_and_approve_list_the_same_gaps_and_notes(
    app, auth_headers, run_headers, tmp_path, monkeypatch  # noqa: F811
):
    """ac-same-list: an unreviewed amendment, a same-file overlap, a criterion with no check and a
    skipped custom step. On master the save omits the amendment and the step."""
    await _create(app, auth_headers)
    _write(tmp_path, _steps(THREAT))
    _unreviewed(monkeypatch)
    tasks = [
        {"key": "t1", "description": "one", "requirements": ["alpha"], "files": ["src/a.py"]},
        {"key": "t2", "description": "two", "requirements": ["alpha"], "files": ["src/a.py"]},
    ]
    saved = (await _submit(app, run_headers, _document(tasks=tasks))).json()
    await _place(step="requirements", size="large")
    checked = (await _check(app, auth_headers)).json()
    refused = await _phase(app, auth_headers, "approved")
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]

    # The save ran before the step was placed, so ask it again for a like-for-like read.
    saved = (await _submit(app, run_headers, _document(tasks=tasks))).json()

    in_save = _gaps(saved["blocking"] + saved["warnings"])
    in_check = _gaps(checked["blocking"] + checked["warnings"])
    in_approve = _gaps(detail.get("blocking", []) + detail["warnings"])
    assert in_save == in_check == in_approve
    assert {code for code, _ in in_save} >= {
        "amendments_unreviewed",
        "unordered_file_overlap",
        "criterion_without_check",
        "steps_skipped",
    }
    assert (
        _notes(saved["warnings"] + saved["notes"])
        == _notes(checked["warnings"] + checked["notes"])
        == _notes(detail["warnings"] + detail.get("notes", []))
    )


@pytest.mark.asyncio
async def test_a_save_that_says_ready_is_a_check_with_no_gap_and_an_approve_that_passes(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-verdict."""
    await _created(app, auth_headers)

    saved = (await _submit(app, run_headers, _checked())).json()
    assert saved["ready_to_approve"] is True, str(saved["warnings"])

    checked = (await _check(app, auth_headers)).json()
    assert checked["ready"] is True and _gaps(checked["warnings"]) == []

    approved = await _phase(app, auth_headers, "approved")
    assert approved.status_code == 200, approved.text


@pytest.mark.asyncio
async def test_only_an_unreviewed_amendment_makes_the_save_not_ready(
    app, auth_headers, run_headers, monkeypatch  # noqa: F811
):
    """ac-verdict-false: fails on master, whose save never computes `amendments_unreviewed`."""
    await _created(app, auth_headers)
    _unreviewed(monkeypatch)

    saved = (await _submit(app, run_headers, _checked())).json()

    assert _gaps(saved["warnings"]) == [("amendments_unreviewed", "amendments")]
    assert saved["ready_to_approve"] is False
    assert (await _check(app, auth_headers)).json()["ready"] is False


@pytest.mark.asyncio
async def test_notes_are_listed_everywhere_and_never_stop_anything(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-notes: an unanswered delivery is a note in the save, Check and Approve alike."""
    await _created(app, auth_headers)
    document = _checked()
    del document["delivery"]

    saved = (await _submit(app, run_headers, document)).json()
    checked = (await _check(app, auth_headers)).json()

    assert "delivery_unanswered" in _notes(saved["notes"])
    assert "delivery_unanswered" in _notes(checked["notes"])
    assert saved["ready_to_approve"] is True and checked["ready"] is True
    approved = await _phase(app, auth_headers, "approved")
    assert approved.status_code == 200, approved.text
    assert "delivery_unanswered" in _notes(approved.json()["approval_notes"])


def test_the_three_codes_approve_excluded_are_notes():
    for code in ("import_not_approved", "delivery_unanswered", "delivery_flow_incomplete"):
        assert code in spec_service.NOTE_CODES


@pytest.mark.asyncio
async def test_the_author_acknowledges_a_gap_and_is_refused_for_no_reason_or_a_refusal(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-ack."""
    await _created(app, auth_headers)
    saved = (await _submit(app, run_headers, _document())).json()
    gap = next(w for w in saved["warnings"] if w["code"] == "criterion_without_check")

    empty = await _ack_agent(app, run_headers, gap["code"], gap["where"], "  ")
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "reason_required"

    done = await _ack_agent(app, run_headers, gap["code"], gap["where"], "checked by hand")
    assert done.status_code == 201, done.text
    body = done.json()
    assert body["by"] == "claude-1" and body["reason"] == "checked by hand" and body["at"]

    cycle = [
        {"key": "t1", "description": "one", "requirements": ["alpha"], "depends_on": ["t2"]},
        {"key": "t2", "description": "two", "requirements": ["alpha"], "depends_on": ["t1"]},
    ]
    refusal = _document(tasks=cycle)
    refused_save = (await _submit(app, run_headers, refusal)).json()
    block = refused_save["blocking"][0]
    again = await _ack_agent(app, run_headers, block["code"], block["where"], "fine")
    assert again.status_code == 422
    assert again.json()["detail"]["code"] == "refusal_not_acknowledgeable"


@pytest.mark.asyncio
async def test_a_gap_the_document_does_not_report_is_not_acknowledged(
    app, auth_headers, run_headers  # noqa: F811
):
    await _created(app, auth_headers)
    await _submit(app, run_headers, _checked())

    nothing = await _ack_agent(app, run_headers, "criterion_without_check", "x[0]", "why")

    assert nothing.status_code == 404
    assert nothing.json()["detail"]["code"] == "gap_not_reported"


@pytest.mark.asyncio
async def test_the_operator_acknowledges_from_check_and_the_verdict_updates(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-operator-ack."""
    await _created(app, auth_headers)
    await _submit(app, run_headers, _document())
    checked = (await _check(app, auth_headers)).json()
    gap = next(w for w in checked["warnings"] if w["code"] == "criterion_without_check")
    assert checked["ready"] is False

    done = await _ack_operator(app, auth_headers, gap["code"], gap["where"], "operator says ok")

    assert done.status_code == 200, done.text
    assert done.json()["by_kind"] == "operator" and done.json()["ready"] is True
    after = (await _check(app, auth_headers)).json()
    assert after["ready"] is True
    assert [(a["code"], a["by_kind"], a["reason"]) for a in after["acknowledged"]] == [
        ("criterion_without_check", "operator", "operator says ok")
    ]
    assert gap["code"] not in {w["code"] for w in after["warnings"]}


@pytest.mark.asyncio
async def test_an_unreviewed_amendment_and_a_vault_warning_are_the_operators_to_clear(
    app, auth_headers, run_headers, monkeypatch  # noqa: F811
):
    """ac-operator-only."""
    await _created(app, auth_headers)
    _unreviewed(monkeypatch)
    _vault(monkeypatch)
    await _submit(app, run_headers, _checked())

    for code, where in (
        ("amendments_unreviewed", "amendments"),
        ("vault_warning", "requirements[0]"),
    ):
        refused = await _ack_agent(app, run_headers, code, where, "I judge it fine")
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"]["code"] == "operator_only"
        assert "operator" in refused.json()["detail"]["message"]
        accepted = await _ack_operator(app, auth_headers, code, where, "reviewed")
        assert accepted.status_code == 200, accepted.text

    assert (await _check(app, auth_headers)).json()["ready"] is True


@pytest.mark.asyncio
async def test_an_acknowledgement_holds_while_the_gap_is_reported_and_dies_with_it(
    app, auth_headers, run_headers, monkeypatch  # noqa: F811
):
    """ac-ack-lifetime: reworded at the same code and place it holds; fixed it goes; back, it is open."""
    await _created(app, auth_headers)
    said = _unreviewed(monkeypatch, ["one amendment"])
    await _submit(app, run_headers, _checked())
    assert (
        await _ack_operator(app, auth_headers, "amendments_unreviewed", "amendments", "ok")
    ).status_code == 200

    said[0] = "three amendments, reworded"
    reworded = (await _submit(app, run_headers, _checked())).json()
    assert [a["code"] for a in reworded["acknowledged"]] == ["amendments_unreviewed"]
    assert reworded["ready_to_approve"] is True

    async def none(session, document):
        return []

    monkeypatch.setattr(spec_service, "_amendments_unreviewed", none)
    fixed = (await _submit(app, run_headers, _checked())).json()
    assert fixed["acknowledged"] == []
    async with async_session_factory() as session:
        assert (await session.execute(select(SpecGapAcknowledgement))).scalars().all() == []

    _unreviewed(monkeypatch, ["back again"])
    back = (await _submit(app, run_headers, _checked())).json()
    assert back["acknowledged"] == []
    assert _gaps(back["warnings"]) == [("amendments_unreviewed", "amendments")]
    assert back["ready_to_approve"] is False


@pytest.mark.asyncio
async def test_the_save_lists_an_acknowledged_gap_apart_from_its_warnings(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-save-acks."""
    await _created(app, auth_headers)
    saved = (await _submit(app, run_headers, _document())).json()
    gap = next(w for w in saved["warnings"] if w["code"] == "criterion_without_check")
    await _ack_agent(app, run_headers, gap["code"], gap["where"], "by hand")

    again = (await _submit(app, run_headers, _document())).json()

    assert "criterion_without_check" not in {w["code"] for w in again["warnings"]}
    assert [(a["code"], a["by"], a["reason"]) for a in again["acknowledged"]] == [
        ("criterion_without_check", "claude-1", "by hand")
    ]
    assert again["ready_to_approve"] is True


@pytest.mark.asyncio
async def test_check_approve_and_the_rendered_document_show_the_acknowledged_gap(
    app, auth_headers, run_headers  # noqa: F811
):
    """ac-ack-visible, and Approve passing over only acknowledged gaps (ac-approve-acks)."""
    await _created(app, auth_headers)
    saved = (await _submit(app, run_headers, _document())).json()
    gap = next(w for w in saved["warnings"] if w["code"] == "criterion_without_check")
    await _ack_agent(app, run_headers, gap["code"], gap["where"], "by hand")

    checked = (await _check(app, auth_headers)).json()
    assert [a["reason"] for a in checked["acknowledged"]] == ["by hand"]
    page = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()
    # The page's own read carries the list, so it shows on load without a Check (FR-5).
    assert [(a["code"], a["reason"]) for a in page["acknowledged"]] == [
        ("criterion_without_check", "by hand")
    ]
    assert "acknowledged-gap-criterion_without_check" in page["content"]
    assert "by hand" in page["content"] and "claude-1" in page["content"]

    approved = await _phase(app, auth_headers, "approved")
    assert approved.status_code == 200, approved.text
    assert [a["code"] for a in approved.json()["acknowledged"]] == ["criterion_without_check"]


@pytest.mark.asyncio
async def test_the_page_read_lists_the_open_gaps_the_save_reported(
    app, auth_headers, run_headers  # noqa: F811
):
    """`one-message-count` (FR-11): the page's own read carries every open gap the save reported,
    so the header lists them on load, without a Check; an acknowledged one moves to `acknowledged`.
    """
    await _created(app, auth_headers)
    saved = (await _submit(app, run_headers, _document())).json()
    page = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()
    assert _gaps(page["open_gaps"]) == _gaps(saved["warnings"]) != []
    assert _notes(page["open_gaps"]) == _notes(saved["warnings"])

    gap = next(w for w in saved["warnings"] if w["code"] == "criterion_without_check")
    await _ack_agent(app, run_headers, gap["code"], gap["where"], "by hand")
    page = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()
    assert (gap["code"], gap["where"]) not in _gaps(page["open_gaps"])
    assert [a["code"] for a in page["acknowledged"]] == ["criterion_without_check"]

    approved = await _phase(app, auth_headers, "approved")
    assert approved.status_code == 200, approved.text
    page = (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()
    assert "open_gaps" not in page
