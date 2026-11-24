"""The pre-mortem woven into the spec process: answered by the author, briefed while open, a gap in
the check, and fired on its own only until one completes.

`the-spec-process-uses-what-the-hub-already-knows`, FR-3 (briefing-lists-open), FR-4 (answer-rules),
FR-5 (gap-rule) and FR-6 (rerun-rule). The worker is faked as in `test_pre_mortem.py`; the author is
the run that saved the document (`claude-1`), answering through the agent route its tool calls.
"""

import pytest
from sqlalchemy import select

from hub import pre_mortem
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, EventLog, Run

from ._spec_confirmations import confirm_criteria
from ._spec_versions import content_version
from .test_pre_mortem import (
    BASE,
    JOB,
    PATH,
    _briefing,
    _configure,
    _drafted,
    _firings,
    _listed,
    _move,
    _Worker,
    worker,  # noqa: F401  (fixture)
)
from .test_spec_documents_api import BASE as DOCS
from .test_spec_documents_api import (
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)

ANSWER = "/api/v1/agent-actions/spec/documents/pre-mortem/answer"
P = "proj-test"
HEADING = "### Pre-mortem findings"
STORIES = (
    "The cache key ignores the project, so two projects share a verdict.",
    "The 404 for a trailing slash is never checked, and the UI links one.",
    "A failed migration leaves the column nullable on SQLite only.",
)
THREE = pre_mortem.PreMortemAnswer(
    findings=[
        pre_mortem.Finding(story=STORIES[0], requirement="FR-1", cites=["cache.py:10"]),
        pre_mortem.Finding(story=STORIES[1], requirement="FR-1"),
        pre_mortem.Finding(story=STORIES[2]),
    ]
)


async def _run_for(agent: str, token: str, *, conversation: str = "", lineage: str = "") -> dict:
    """A live run credential for *agent*, in its own conversation when *conversation* is named."""
    async with async_session_factory() as session:
        if conversation:
            session.add(
                Conversation(id=conversation, project_id=P, agent=agent, lineage_id=lineage or None)
            )
            await session.flush()
        session.add(
            Run(
                id=f"run-{token}",
                project_id=P,
                agent=agent,
                status="running",
                turn_depth=0,
                conversation_id=conversation or None,
                capability_token_hash=hash_run_token(f"aw_run_{token}"),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer aw_run_{token}"}


async def _press(app, auth_headers, path=PATH):
    pressed = await app.post(
        f"{BASE}/manager/jobs/{JOB}/run", json={"path": path}, headers=auth_headers
    )
    assert pressed.status_code == 202, pressed.text
    await pre_mortem.settled()


async def _written(app, auth_headers, run_headers, worker, path=PATH):  # noqa: F811
    """A drafted document with one written pre-mortem of three findings; its firing's id."""
    worker(THREE)
    await _configure(app, auth_headers)
    await _drafted(app, auth_headers, run_headers, path=path)
    await _press(app, auth_headers, path=path)
    (firing,) = await _listed(app, auth_headers, path=path)
    assert firing["outcome"] == "written" and len(firing["findings"]) == 3
    return firing["id"]


async def _answer(app, headers, firing, note, finding=None, path=PATH):
    body = {"path": path, "firing": firing, "note": note}
    if finding is not None:
        body["finding"] = finding
    return await app.post(ANSWER, json=body, headers=headers)


async def _answer_events():
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == pre_mortem.ANSWER_EVENT)
                )
            )
            .scalars()
            .all()
        )


async def _check(app, auth_headers, path=PATH):
    checked = await app.post(f"{DOCS}/documents/check", params={"path": path}, headers=auth_headers)
    assert checked.status_code == 200, checked.text
    return checked.json()


def _gaps(body):
    return [w for w in body["warnings"] if w["code"] == "pre_mortem_unanswered"]


# briefing-lists-open
@pytest.mark.asyncio
async def test_the_briefing_lists_only_the_unanswered_findings_and_none_once_all_are_answered(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    firing = await _written(app, auth_headers, run_headers, worker)
    answered = await _answer(app, run_headers, firing, "Scoped the key by project.", finding=1)
    assert answered.status_code == 201, answered.text

    text = await _briefing(app, auth_headers)

    assert text.count(HEADING) == 1
    block = text[text.index(HEADING) :]
    assert STORIES[0] not in block, "an answered finding is not listed again"
    assert f"2. FR-1: {STORIES[1]}" in block
    assert f"3. {STORIES[2]}" in block
    assert "2 of its 3 findings are unanswered" in block
    assert f'answer_pre_mortem(path="{PATH}", firing="{firing}", note=...)' in block
    assert "`finding=<number>`" in block

    rest = await _answer(app, run_headers, firing, "Checked the slash and the migration.")
    assert rest.status_code == 201, rest.text
    assert rest.json()["answered"] == [2, 3] and rest.json()["unanswered"] == []

    assert HEADING not in await _briefing(app, auth_headers)


@pytest.mark.asyncio
async def test_a_profile_that_is_not_the_author_is_not_briefed_the_findings(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    await _written(app, auth_headers, run_headers, worker)

    response = await app.get(
        f"{BASE}/agents/agent-context",
        params={"agent": "claude-2", "spec_document": PATH},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert HEADING not in response.json()["context"]


# answer-rules
@pytest.mark.asyncio
async def test_the_author_answers_one_then_the_rest_from_another_conversation(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    firing = await _written(app, auth_headers, run_headers, worker)
    # The author's turns after a cutover come from a successor conversation of the same lineage.
    before = await _run_for("claude-1", "before-cut", conversation="conv-before", lineage="lin-1")
    after = await _run_for("claude-1", "after-cut", conversation="conv-after", lineage="lin-1")

    one = await _answer(app, before, firing, "Added the trailing-slash criterion.", finding=2)
    rest = await _answer(app, after, firing, "Both handled in the design's Today section.")

    assert one.status_code == 201, one.text
    assert one.json() == {
        "path": PATH,
        "firing": firing,
        "answered": [2],
        "unanswered": [1, 3],
        "total": 3,
    }
    assert rest.status_code == 201, rest.text
    assert rest.json()["answered"] == [1, 3] and rest.json()["unanswered"] == []
    (listed,) = await _listed(app, auth_headers)
    first, second, third = (finding["answer"] for finding in listed["findings"])
    assert second["note"] == "Added the trailing-slash criterion." and second["by"] == "claude-1"
    assert second["at"]
    assert first["note"] == third["note"] == "Both handled in the design's Today section."
    assert first["by"] == third["by"] == "claude-1"
    # The listed findings keep the fields they had, with the answer beside them.
    assert listed["findings"][0]["story"] == STORIES[0]
    assert listed["findings"][0]["cites"] == ["cache.py:10"]


@pytest.mark.asyncio
async def test_an_empty_note_another_profile_and_an_old_firing_are_refused_recording_nothing(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    first = await _written(app, auth_headers, run_headers, worker)
    other = await _run_for("claude-2", "other-profile")

    empty = await _answer(app, run_headers, first, "   ", finding=1)
    stranger = await _answer(app, other, first, "Not mine to answer.", finding=1)

    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "note_required"
    assert "note" in empty.json()["detail"]["message"]
    assert stranger.status_code == 403
    assert stranger.json()["detail"]["code"] == "not_author"

    worker(THREE)
    await _press(app, auth_headers)  # the operator runs a new pre-mortem
    newest, _ = await _listed(app, auth_headers)
    stale = await _answer(app, run_headers, first, "Answering the old one.", finding=1)

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "firing_not_newest"
    assert stale.json()["detail"]["newest"] == newest["id"]
    assert newest["id"] in stale.json()["detail"]["message"]
    assert await _answer_events() == [], "no refused answer records anything"
    assert [finding["answer"] for finding in newest["findings"]] == [None, None, None]


@pytest.mark.asyncio
async def test_the_answer_route_says_what_is_missing(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    """No written firing is a 404; a missing or unknown firing id on a document that has one is
    the 409 naming the newest; a finding number the firing lacks is a 422."""
    await _drafted(app, auth_headers, run_headers)
    none_yet = await _answer(app, run_headers, "evt-nope", "A note.", finding=1)
    unknown_document = await _answer(
        app, run_headers, "evt-nope", "A note.", path="spec/changes/nope/spec.json"
    )
    assert none_yet.status_code == 404
    assert none_yet.json()["detail"]["code"] == "no_written_pre_mortem"
    assert unknown_document.status_code == 404

    firing = await _written(app, auth_headers, run_headers, worker, path="spec/changes/b/spec.json")
    missing = await app.post(
        ANSWER,
        json={"path": "spec/changes/b/spec.json", "note": "A note."},
        headers=run_headers,
    )
    beyond = await _answer(
        app, run_headers, firing, "A note.", finding=4, path="spec/changes/b/spec.json"
    )

    assert missing.status_code == 409
    assert missing.json()["detail"] == {
        "message": missing.json()["detail"]["message"],
        "code": "firing_not_newest",
        "newest": firing,
    }
    assert beyond.status_code == 422 and beyond.json()["detail"]["code"] == "finding_unknown"
    assert await _answer_events() == []


# gap-rule
@pytest.mark.asyncio
async def test_only_a_document_with_unanswered_findings_reports_the_gap(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    none, some, every = (f"spec/changes/{name}/spec.json" for name in ("none", "some", "every"))
    await _drafted(app, auth_headers, run_headers, path=none)
    some_firing = await _written(app, auth_headers, run_headers, worker, path=some)
    every_firing = await _written(app, auth_headers, run_headers, worker, path=every)
    assert (await _answer(app, run_headers, some_firing, "Fixed.", finding=1, path=some)).is_success
    assert (await _answer(app, run_headers, every_firing, "All fixed.", path=every)).is_success

    saves = {}
    for path in (none, some, every):
        saved = await _submit(app, run_headers, _document(), path=path)
        assert saved.status_code in (200, 201), saved.text
        saves[path] = saved.json()
    checks = {path: await _check(app, auth_headers, path=path) for path in (none, some, every)}

    for path in (none, every):
        assert _gaps(saves[path]) == [] and _gaps(checks[path]) == []
    (saved_gap,) = _gaps(saves[some])
    (checked_gap,) = _gaps(checks[some])
    assert saved_gap == checked_gap
    assert saved_gap["message"].startswith("2 of 3 pre-mortem findings unanswered")
    assert saves[some]["ready_to_approve"] is False
    assert checks[some]["ready"] is False

    # A gap, not a gate: the operator approves over it.
    await confirm_criteria(some)
    await app.post(
        f"{DOCS}/documents/close-exploration", params={"path": some}, headers=auth_headers
    )
    approved = await app.post(
        f"{DOCS}/documents/phase",
        params={"path": some, "to": "approved"},
        json={
            "content_version": await content_version(app, auth_headers, some),
            "reason": "the operator judged the open finding not worth acting on",
            "approve_anyway": True,
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"


@pytest.mark.asyncio
async def test_the_author_cannot_acknowledge_the_gap_away(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    await _written(app, auth_headers, run_headers, worker)

    acknowledged = await app.post(
        "/api/v1/agent-actions/spec/documents/acknowledge",
        json={
            "path": PATH,
            "code": "pre_mortem_unanswered",
            "where": "pre_mortem",
            "reason": "not worth it",
        },
        headers=run_headers,
    )

    assert acknowledged.status_code == 403, acknowledged.text


# rerun-rule
@pytest.mark.asyncio
async def test_it_fires_on_its_own_once_and_again_only_on_the_button_or_after_a_failure(
    app, auth_headers, run_headers, tmp_path, monkeypatch  # noqa: F811
):
    first, second = "spec/changes/first/spec.json", "spec/changes/second/spec.json"
    fake = _Worker(THREE)
    monkeypatch.setattr(pre_mortem, "run_worker", fake)
    await _configure(app, auth_headers, mode="automatic")
    for path in (first, second):
        await _drafted(app, auth_headers, run_headers, path=path)
        await _move(app, auth_headers, path=path, size="large", step="acceptance")

    await _move(app, auth_headers, path=first, step="approach")
    assert len(await _listed(app, auth_headers, path=first)) == 1
    await _move(app, auth_headers, path=first, step="acceptance")
    await _move(app, auth_headers, path=first, step="approach")
    assert len(await _listed(app, auth_headers, path=first)) == 1, "a second leave fires nothing"

    original = (await _listed(app, auth_headers, path=first))[0]["id"]
    await app.post(
        ANSWER, json={"path": first, "firing": original, "note": "Done."}, headers=run_headers
    )
    newer = pre_mortem.PreMortemAnswer(
        findings=[pre_mortem.Finding(story="The button's finding."), pre_mortem.Finding(story="b")]
    )
    monkeypatch.setattr(pre_mortem, "run_worker", _Worker(newer))
    await _press(app, auth_headers, path=first)
    button, automatic = await _listed(app, auth_headers, path=first)
    assert (button["trigger"], automatic["trigger"]) == ("requested", "criteria_written")
    # The button's findings are the ones the gap and the briefing count.
    (gap,) = _gaps(await _check(app, auth_headers, path=first))
    assert gap["message"].startswith("2 of 2 pre-mortem findings unanswered")
    block = await _briefing(app, auth_headers, path=first)
    assert "The button's finding." in block and STORIES[0] not in block

    # The second document's first automatic firing fails, so its next leave fires again.
    failing = _Worker(fail=True)
    monkeypatch.setattr(pre_mortem, "run_worker", failing)
    await _move(app, auth_headers, path=second, step="approach")
    (failed,) = await _listed(app, auth_headers, path=second)
    assert failed["outcome"] == "failed"
    monkeypatch.setattr(pre_mortem, "run_worker", _Worker(THREE))
    await _move(app, auth_headers, path=second, step="acceptance")
    await _move(app, auth_headers, path=second, step="approach")
    written, failed_again = await _listed(app, auth_headers, path=second)
    assert (written["outcome"], failed_again["outcome"]) == ("written", "failed")
    assert written["trigger"] == "criteria_written"
    assert len([f for f in await _firings() if f["subject"]["path"] == second]) == 2


@pytest.mark.asyncio
async def test_an_empty_firing_counts_as_the_automatic_one(
    app, auth_headers, run_headers, tmp_path, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(pre_mortem, "run_worker", _Worker(pre_mortem.PreMortemAnswer(findings=[])))
    await _configure(app, auth_headers, mode="automatic")
    await _drafted(app, auth_headers, run_headers)
    await _move(app, auth_headers, size="large", step="acceptance")
    await _move(app, auth_headers, step="approach")
    await _move(app, auth_headers, step="acceptance")
    await _move(app, auth_headers, step="approach")

    (empty,) = await _listed(app, auth_headers)
    assert empty["outcome"] == "empty"
    assert _gaps(await _check(app, auth_headers)) == []
