"""The project's thread feed (slice thread-from-records): `GET /projects/{id}/thread`.

Tests walk the feed the way the page does: the surface first, then a level at a time under a knot,
and compare what they reach with what was seeded.
"""

import re
import time
from datetime import datetime, timedelta, timezone

from hub.api.v1 import thread as thread_routes
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Conversation,
    EvidenceReview,
    JobRun,
    Loop,
    Message,
    PermissionRequest,
    Question,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecDocumentEvent,
    SpecDocumentMerge,
    SpecRequirement,
    Task,
    TaskIntegration,
    TaskTransition,
)

THREAD = "/api/v1/projects/proj-test/thread"
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def doc(i, minutes, title=None):
    return SpecDocument(
        id=f"spdoc-{i}",
        project_id="proj-test",
        path=f"spec/changes/d{i}/spec.json",
        title=title or f"Document {i}",
        created_at=at(minutes),
        updated_at=at(minutes),
    )


def task(i, minutes, document=None, title=None):
    return Task(
        id=f"task-{i}",
        project_id="proj-test",
        title=title or f"Task {i}",
        spec_document_id=document,
        created_at=at(minutes),
    )


def run(i, minutes, task_id=None, agent="builder", conversation=None):
    return Run(
        id=f"run-{i}",
        project_id="proj-test",
        agent=agent,
        status="completed",
        turn_depth=0,
        task_id=task_id,
        conversation_id=conversation,
        started_at=at(minutes),
        ended_at=at(minutes + 1),
    )


def conversation(i, minutes):
    return Conversation(
        id=f"conv-{i}",
        project_id="proj-test",
        agent="builder",
        title=f"Chat {i}",
        created_at=at(minutes),
        updated_at=at(minutes),
    )


def requirement():
    return SpecRequirement(
        id="spreq-1",
        document_id="spdoc-1",
        identifier="FR-1",
        project_id="proj-test",
        key="one",
        digest="d",
    )


def evidence(minutes):
    return RequirementEvidence(
        id="evd-1",
        project_id="proj-test",
        requirement_id="spreq-1",
        digest="d",
        kind="test_result",
        actor_kind="agent",
        actor="builder",
        run_id="run-a",
        task_id="task-a",
        produced_at=at(minutes),
    )


def verdict(minutes):
    return EvidenceReview(
        id="evr-1",
        project_id="proj-test",
        evidence_id="evd-1",
        decision="accepted",
        actor_kind="agent",
        actor="qa",
        created_at=at(minutes),
    )


def merge(minutes):
    return TaskIntegration(
        id="tin-1",
        project_id="proj-test",
        task_id="task-a",
        outcome="merged",
        actor_kind="operator",
        created_at=at(minutes),
    )


def transition(minutes, before="pending", after="in_progress"):
    return TaskTransition(
        id="ttr-1",
        project_id="proj-test",
        task_id="task-a",
        from_status=before,
        to_status=after,
        actor_kind="agent",
        actor_agent="builder",
        created_at=at(minutes),
    )


async def save(*rows):
    # Parents before children, as the schema's foreign keys want: flush after each row.
    async with async_session_factory() as session:
        for row in rows:
            session.add(row)
            await session.flush()
        await session.commit()


async def level(app, headers, under=None, **params):
    if under:
        params["under"] = under
    response = await app.get(THREAD, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def walk(app, headers, under=None):
    """Every knot reachable by opening everything."""
    seen = []
    body = await level(app, headers, under, limit=200, first=True)
    while True:
        for knot in body["knots"]:
            seen.append(knot)
            if knot["child_count"]:
                seen.extend(await walk(app, headers, knot["key"]))
        if not body["has_after"]:
            return seen
        body = await level(app, headers, under, limit=200, after=body["after_cursor"])


async def test_the_surface_folds_what_no_document_holds(app, auth_headers):
    await save(
        doc(1, 0),
        doc(2, 10),
        task("a", 2),
        task("b", 3),
        task("c", 4),
        conversation(1, 5),
    )
    body = await level(app, auth_headers)
    assert [(k["kind"], k["fold_of"]) for k in body["knots"]] == [
        ("document", None),
        ("fold", "group"),
        ("document", None),
    ]
    group = body["knots"][1]
    assert group["child_count"] == 4
    assert group["start"].startswith("2026-10-01T09:02") and group["end"] >= group["start"]
    assert group["title"].startswith("4 items")


async def test_every_seeded_item_is_reached_exactly_once(app, auth_headers, monkeypatch):
    async def one_vault_addition(session, project_id):
        return [
            {
                "id": "vault-entry-1",
                "name": "Kickoff meeting",
                "created_at": at(18).isoformat(),
                "added_by": "operator",
            }
        ]

    monkeypatch.setattr(thread_routes, "vault_additions", one_vault_addition)
    await save(
        doc(1, 0),
        doc("cap", 17, "A capability"),
        task("a", 1, "spdoc-1"),
        task("loose", 2),
        conversation(1, 3),
        run("a", 4, "task-a"),
        run("chat", 5, conversation="conv-1"),
        run("free", 6),
        SpecDocumentEvent(
            id="spev-1",
            document_id="spdoc-1",
            project_id="proj-test",
            kind="phase",
            actor_kind="operator",
            origin="lifecycle",
            detail={"from": "proposed", "to": "approved"},
            created_at=at(7),
        ),
        requirement(),
        transition(8),
        evidence(9),
        verdict(10),
        merge(11),
        Question(
            id="q-1",
            project_id="proj-test",
            from_agent="builder",
            question="Which way?",
            created_by_run_id="run-a",
            created_at=at(12),
        ),
        PermissionRequest(
            id="perm-1",
            project_id="proj-test",
            agent="builder",
            run_id="run-a",
            tool_name="mcp__x__do_thing",
            created_at=at(13),
        ),
        Message(
            id="msg-1",
            project_id="proj-test",
            sender="builder",
            recipient="qa",
            content="hi",
            created_by_run_id="run-a",
            timestamp=at(14),
        ),
        Message(
            id="msg-2",
            project_id="proj-test",
            sender="user",
            recipient="builder",
            content="hello",
            conversation_id="conv-1",
            timestamp=at(15),
        ),
        AIJob(
            id="job-1",
            project_id="proj-test",
            name="Nightly",
            agent="builder",
            message="go",
            cron="* * * * *",
        ),
        JobRun(id="jr-1", job_id="job-1", project_id="proj-test", fired_at=at(16)),
        Loop(id="loop-1", project_id="proj-test", job_id="job-1", spec_document_id="spdoc-1"),
        SpecDocumentMerge(
            id="sdm-1",
            project_id="proj-test",
            capability_document_id="spdoc-cap",
            change_document_id="spdoc-1",
            actor_kind="operator",
            actor="user",
            created_at=at(17),
        ),
    )

    knots = await walk(app, auth_headers)
    names = [r for k in knots if k["kind"] != "fold" for r in k["records"]]
    expected = {
        "spec_documents:spdoc-1",
        "tasks:task-a",
        "tasks:task-loose",
        "conversations:conv-1",
        "runs:run-a",
        "runs:run-chat",
        "runs:run-free",
        "document-event:spev-1",
        "transition:ttr-1",
        "evidence:evd-1",
        "verdict:evr-1",
        "integration:tin-1",
        "question:q-1",
        "permission:perm-1",
        "message:msg-1",
        "message:msg-2",
        "firing:jr-1",
        "spec_documents:spdoc-cap",
        "document-merge:sdm-1",
        "vault:vault-entry-1",
    }
    assert sorted(names) == sorted(expected), "each item once, none invented, none missing"
    assert all(k["records"] for k in knots), "every knot names a stored record"
    assert all(k["actors"] for k in knots), [k["key"] for k in knots if not k["actors"]]
    by_record = {k["records"][0]: k for k in knots if k["kind"] != "fold"}
    assert "builder" in by_record["firing:jr-1"]["actors"], "a firing names its job's agent"
    assert (
        "Operator" in by_record["spec_documents:spdoc-1"]["actors"]
    ), "a document names its events"
    assert by_record["integration:tin-1"]["actors"], "a merge with no stored actor still names one"


async def test_opening_a_document_then_task_then_run(app, auth_headers):
    await save(
        doc(1, 0),
        task("a", 1, "spdoc-1"),
        transition(2, "assigned"),
        run("a", 3, "task-a"),
        requirement(),
        evidence(4),
        verdict(5),
        merge(6),
    )
    [document] = (await level(app, auth_headers))["knots"]
    assert document["kind"] == "document" and document["child_count"] == 1
    [the_task] = (await level(app, auth_headers, document["key"]))["knots"]
    kids = (await level(app, auth_headers, the_task["key"]))["knots"]
    assert [k["kind"] for k in kids] == ["status-change", "run", "verdict", "merge"]
    [found] = (await level(app, auth_headers, kids[1]["key"]))["knots"]
    assert found["kind"] == "evidence" and found["title"] == "Evidence for FR-1"
    # Closing a level is the page's own act; the parent level is the same read again.
    again = (await level(app, auth_headers, document["key"]))["knots"]
    assert [k["key"] for k in again] == [the_task["key"]]


async def test_the_face_has_no_identifiers_or_event_names(app, auth_headers):
    await save(
        doc(1, 0),
        task("a", 1, "spdoc-1"),
        run("a", 3, "task-a"),
        transition(2, "revision_needed", "under_review"),
        PermissionRequest(
            id="perm-1",
            project_id="proj-test",
            agent="builder",
            run_id="run-a",
            tool_name="mcp__agentweave__submit_checkpoint_notes",
            created_at=at(4),
        ),
    )
    knots = await walk(app, auth_headers)
    assert knots
    for knot in knots:
        face = " ".join([knot["word"], knot["title"], *knot["actors"]])
        assert not re.search(r"\b(tsk|task|run|spdoc|fct)-\w+", face), face
        assert not re.search(r"[a-z]+_[a-z_]+", face), face
        assert knot["word"] and knot["title"] and knot["start"]


async def test_a_run_links_to_the_run(app, auth_headers):
    await save(run("x", 1))
    [knot] = (await level(app, auth_headers))["knots"]
    assert knot["link"] == {"object": "run", "id": "run-x", "agent": "builder"}


async def test_siblings_are_in_recorded_time_order_and_paging_walks_both_ways(app, auth_headers):
    # Documents between the tasks, so the surface has no stretch of non-documents to fold.
    await save(*[row for i in range(10) for row in (doc(i, i * 10), task(f"{i:02d}", i * 10 + 5))])
    latest = await level(app, auth_headers, limit=5)
    starts = [k["start"] for k in latest["knots"]]
    assert starts == sorted(starts) and latest["has_before"] and not latest["has_after"]
    earlier = await level(app, auth_headers, limit=5, before=latest["before_cursor"])
    assert earlier["knots"][-1]["start"] <= latest["knots"][0]["start"]
    assert {k["key"] for k in earlier["knots"]}.isdisjoint(k["key"] for k in latest["knots"])
    first = await level(app, auth_headers, limit=5, first=True)
    assert not first["has_before"] and first["has_after"]
    assert first["knots"][0]["key"] == "document:spdoc-0"
    forward = await level(app, auth_headers, limit=5, after=first["after_cursor"])
    assert forward["knots"][0]["start"] >= first["knots"][-1]["start"]
    every = [k["start"] for k in await walk(app, auth_headers)]
    assert every and len(every) == 20


async def test_a_page_can_be_asked_for_around_a_knot(app, auth_headers):
    await save(*[row for i in range(10) for row in (doc(i, i * 10), task(f"{i:02d}", i * 10 + 5))])
    middle = await level(app, auth_headers, limit=5, around="document:spdoc-5")
    keys = [k["key"] for k in middle["knots"]]
    assert "document:spdoc-5" in keys and len(keys) == 5
    assert middle["has_before"] and middle["has_after"]
    newest = await level(app, auth_headers, limit=5, around="document:spdoc-9")
    assert "document:spdoc-9" in [k["key"] for k in newest["knots"]] and len(newest["knots"]) == 5
    refused = await app.get(THREAD, params={"around": "document:nowhere"}, headers=auth_headers)
    assert refused.status_code == 422


async def test_six_runs_then_a_merge_fold_the_runs_only(app, auth_headers):
    await save(task("a", 0), *[run(i, 10 + i * 2, "task-a") for i in range(6)], merge(60))
    kids = (await level(app, auth_headers, "task:task-a"))["knots"]
    assert [(k["kind"], k["title"]) for k in kids] == [
        ("fold", "6 runs"),
        ("merge", "Merged into main"),
    ]
    assert kids[0]["child_count"] == 6
    opened = (await level(app, auth_headers, kids[0]["key"]))["knots"]
    assert [k["kind"] for k in opened] == ["run"] * 6
    found = await app.get(THREAD + "/knot", params={"key": opened[2]["key"]}, headers=auth_headers)
    assert found.json()["ancestors"] == ["task:task-a", kids[0]["key"]]


async def test_a_routine_fold_inside_a_surface_group_opens(app, auth_headers):
    # Firings of a job no loop document claims sit on the surface; five in a row form a surface
    # group whose own level folds them again. That inner fold must open to all five.
    await save(
        doc(1, 0),
        AIJob(
            id="job-1",
            project_id="proj-test",
            name="Nightly",
            agent="builder",
            message="go",
            cron="* * * * *",
        ),
        *[
            JobRun(id=f"jr-{i}", job_id="job-1", project_id="proj-test", fired_at=at(10 + i))
            for i in range(5)
        ],
    )
    knots = await walk(app, auth_headers)
    names = [r for k in knots if k["kind"] != "fold" for r in k["records"]]
    assert sorted(names) == sorted(
        ["spec_documents:spdoc-1"] + [f"firing:jr-{i}" for i in range(5)]
    )
    surface = (await level(app, auth_headers))["knots"]
    group = next(k for k in surface if k["fold_of"] == "group")
    [inner] = (await level(app, auth_headers, group["key"]))["knots"]
    assert (inner["fold_of"], inner["title"], inner["child_count"]) == ("firing", "5 firings", 5)
    one = (await level(app, auth_headers, inner["key"]))["knots"][3]
    found = await app.get(THREAD + "/knot", params={"key": one["key"]}, headers=auth_headers)
    assert found.status_code == 200
    assert found.json()["ancestors"] == [group["key"], inner["key"]]
    own = await app.get(THREAD + "/knot", params={"key": inner["key"]}, headers=auth_headers)
    assert own.json()["ancestors"] == [group["key"]]
    assert own.json()["knot"]["child_count"] == 5


async def test_an_unknown_knot_and_a_bad_cursor_are_refused(app, auth_headers):
    missing = await app.get(THREAD, params={"under": "task:nope"}, headers=auth_headers)
    assert missing.status_code == 404
    bad = await app.get(THREAD, params={"after": "garbage"}, headers=auth_headers)
    assert bad.status_code == 422


async def test_a_busy_project_opens_inside_a_second(app, auth_headers):
    # Rows go in without per-row flushes: the parents are all added in earlier batches.
    async with async_session_factory() as session:
        session.add_all([doc(i, i * 3) for i in range(100)])
        await session.flush()
        session.add_all([task(i, i * 3 + 1, f"spdoc-{i % 100}") for i in range(1000)])
        await session.flush()
        session.add_all([run(i, i + 2, f"task-{i % 1000}") for i in range(3000)])
        await session.flush()
        session.add_all(
            [
                Message(
                    id=f"msg-{i}",
                    project_id="proj-test",
                    sender="builder",
                    recipient="qa",
                    content="x",
                    created_by_run_id=f"run-{i % 3000}",
                    timestamp=at(i),
                )
                for i in range(6000)
            ]
        )
        await session.commit()
    # Best of three per read: the fastest run is what the build costs, the slower ones measure
    # whatever else the machine was doing (the suite runs under -n auto beside live agents).
    timings = {}
    for label, args, params in (
        ("open", (), {}),
        ("beginning", (), {"first": True}),
        ("knot", ("document:spdoc-1",), {}),
    ):
        best = float("inf")
        for _ in range(3):
            started = time.perf_counter()
            body = await level(app, auth_headers, *args, **params)
            best = min(best, time.perf_counter() - started)
            assert body["knots"]
        timings[label] = best
    assert max(timings.values()) < 1.0, timings


async def test_a_firing_names_its_jobs_agent(app, auth_headers):
    await save(
        doc(1, 0),
        AIJob(
            id="job-1",
            project_id="proj-test",
            name="Nightly",
            agent="builder",
            message="go",
            cron="* * * * *",
        ),
        *[
            JobRun(id=f"jr-{i}", job_id="job-1", project_id="proj-test", fired_at=at(10 + i))
            for i in range(5)
        ],
    )
    knots = await walk(app, auth_headers)
    firings = [k for k in knots if k["kind"] == "firing"]
    assert len(firings) == 5
    assert all(k["actors"] == ["builder"] for k in firings)


async def test_vault_entries_and_document_merges_are_in_the_walk_and_knots_name_actors(
    app, auth_headers
):
    from hub import project_thread

    await save(
        doc(1, 0),
        doc(2, 0),
        SpecDocumentMerge(
            id="spmg-1",
            project_id="proj-test",
            capability_document_id="spdoc-2",
            actor_kind="operator",
            change_document_id="spdoc-1",
            created_at=at(3),
        ),
        task("a", 1, "spdoc-1"),
        transition(2),
    )
    async with async_session_factory() as session:
        thread = await project_thread.build(
            session,
            "proj-test",
            [{"id": "vlt-1", "name": "Notes", "created_at": at(5).isoformat()}],
        )
    reached = []

    def visit(key):
        for knot in thread.level(key) or []:
            if knot.kind != "fold":
                reached.extend(knot.records)
            assert knot.actors, knot.key
            visit(knot.key)

    visit(None)
    assert "document-merge:spmg-1" in reached and "vault:vlt-1" in reached
    assert len(reached) == len(set(reached))


async def test_a_system_action_is_done_by_agentweave_not_its_internal_name(app, auth_headers):
    """A spec event the Hub itself recorded names "AgentWeave", never its internal job name.

    The Hub stores its own actions with `actor_kind="system"` and a job name ("reindex",
    "backfill"). QA's review of task-6f1c338db709 saw "reindex" as the actor on 309 knots of the
    trial project; the operator asked for it to read as AgentWeave (2026-10-23).
    """
    from hub import project_thread

    await save(
        doc(1, 0),
        SpecDocumentEvent(
            id="spev-reindex",
            document_id="spdoc-1",
            project_id="proj-test",
            kind="phase",
            actor_kind="system",
            actor="reindex",
            origin="lifecycle",
            detail={"from": "exploring", "to": "proposed"},
            created_at=at(1),
        ),
        SpecDocumentEvent(
            id="spev-agent",
            document_id="spdoc-1",
            project_id="proj-test",
            kind="phase",
            actor_kind="agent",
            actor="Architect",
            origin="lifecycle",
            detail={"from": "proposed", "to": "approved"},
            created_at=at(2),
        ),
    )
    async with async_session_factory() as session:
        thread = await project_thread.build(session, "proj-test", [])
    by_record = {}

    def visit(key):
        for knot in thread.level(key) or []:
            for record in knot.records:
                by_record[record] = knot.actors
            visit(knot.key)

    visit(None)
    assert by_record["document-event:spev-reindex"] == [project_thread.SYSTEM_ACTOR]
    assert by_record["document-event:spev-agent"] == ["Architect"]
    assert all("reindex" not in actors for actors in by_record.values())
