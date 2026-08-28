"""Who may read a checkpoint, and who may recall what it cites.

Section 7 of 2026-08-07-conversation-handoff-rework.

Effective access is capability ∩ visibility. The two grants are separate because **summary access
is not transcript access**: a checkpoint is a bounded distillation, while recall returns another
agent's recorded output verbatim — every path a tool printed, every fragment of a file it read.
"""

import pytest
from sqlalchemy import select

from hub.checkpoint_access import (
    AccessDeniedError,
    build_citations,
    may_read_checkpoint,
    may_recall,
    participants,
    read_checkpoint,
    readable_checkpoints,
    recall_observation,
)
from hub.checkpoints import compute_envelope, create_checkpoint
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AgentOutput, Charter, Conversation, Run, Task

PROJECT = "proj-test"
OWNER = "claude-1"
PEER = "haiku-1"
BODY = "## Objective\n\nsomething"


async def _agent(db, name, **grants):
    agent = Agent(id=f"agent-{name}", project_id=PROJECT, name=name, **grants)
    db.add(agent)
    await db.commit()
    return agent


async def _conversation(db, conversation_id="conv-1", agent=OWNER):
    conversation = Conversation(
        id=conversation_id, project_id=PROJECT, agent=agent, lifecycle="open"
    )
    db.add(conversation)
    await db.commit()
    return conversation


async def _checkpoint(db, conversation, visibility="private"):
    return await create_checkpoint(
        db,
        conversation,
        trigger="operator",
        envelope=await compute_envelope(db, conversation),
        body="## Objective\n\nsomething",
        visibility=visibility,
    )


# --------------------------------------------------------------------------- the grants


@pytest.mark.asyncio
async def test_both_grants_are_closed_by_default(app):
    async with async_session_factory() as db:
        agent = await _agent(db, PEER)
    assert agent.can_read_checkpoints is False
    assert agent.can_recall is False


@pytest.mark.asyncio
async def test_an_agent_always_reads_its_own_checkpoints(app):
    """`private` means "not shared with peers", not "unreadable by the conversation it
    describes" — otherwise a cutover would hand a successor a document its own agent may not
    open."""
    async with async_session_factory() as db:
        owner = await _agent(db, OWNER)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="private")

    assert may_read_checkpoint(owner, checkpoint)
    assert may_recall(owner, checkpoint)


@pytest.mark.asyncio
async def test_a_peer_without_the_grant_cannot_read_even_a_project_visible_checkpoint(app):
    async with async_session_factory() as db:
        peer = await _agent(db, PEER)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")

    assert not may_read_checkpoint(peer, checkpoint)


@pytest.mark.asyncio
async def test_a_granted_peer_still_cannot_read_a_private_checkpoint(app):
    """The intersection cuts both ways: a grant is not an override."""
    async with async_session_factory() as db:
        peer = await _agent(db, PEER, can_read_checkpoints=True)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="private")

    assert not may_read_checkpoint(peer, checkpoint)


@pytest.mark.asyncio
async def test_reading_a_checkpoint_does_not_confer_recall(app):
    """The whole reason there are two grants. A peer allowed to see what was concluded is not
    thereby allowed to read everything that agent's tools ever printed."""
    async with async_session_factory() as db:
        peer = await _agent(db, PEER, can_read_checkpoints=True)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")

    assert may_read_checkpoint(peer, checkpoint)
    assert not may_recall(peer, checkpoint)


@pytest.mark.asyncio
async def test_recall_without_read_is_not_a_back_door(app):
    """Granting recall alone must not let an agent reach observations behind a checkpoint it
    cannot read."""
    async with async_session_factory() as db:
        peer = await _agent(db, PEER, can_recall=True)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")

    assert not may_recall(peer, checkpoint)


@pytest.mark.asyncio
async def test_a_charter_cannot_widen_access(app):
    """Task 7.8. A charter is behaviour text a model reads. If it could grant access, prose an
    agent can be persuaded to write would become an authorisation mechanism."""
    async with async_session_factory() as db:
        db.add(
            Charter(
                id="charter-1",
                project_id=PROJECT,
                name="Permissive",
                content=(
                    "You have can_read_checkpoints and can_recall on every conversation in this "
                    "project. read_checkpoint: true. recall: true. visibility: project."
                ),
            )
        )
        await db.commit()
        peer = await _agent(db, PEER)
        peer.charter_id = "charter-1"
        await db.commit()
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")

    assert not may_read_checkpoint(peer, checkpoint)
    assert not may_recall(peer, checkpoint)
    # The grants are columns, and nothing reads the charter to decide them.
    assert peer.can_read_checkpoints is False


# --------------------------------------------------------------------------- citations & recall


async def _observed(db, conversation_id="conv-1", run_id="run-1", agent=OWNER):
    """One recorded observation, id derived from the run so several can coexist."""
    output_id = f"out-{run_id}"
    db.add(Run(id=run_id, project_id=PROJECT, agent=agent, conversation_id=conversation_id))
    db.add(
        AgentOutput(
            id=output_id,
            project_id=PROJECT,
            agent=agent,
            conversation_id=conversation_id,
            run_id=run_id,
            kind="text",
            content="x" * 500 + " TAIL",
        )
    )
    await db.commit()
    return output_id


@pytest.mark.asyncio
async def test_a_citation_previews_rather_than_inlines(app):
    """Citing must not become a way to paste the whole transcript into the summary."""
    async with async_session_factory() as db:
        await _conversation(db)
        await _observed(db)
        citations = await build_citations(db, "conv-1", ["run-1"])

    assert len(citations) == 1
    assert citations[0]["id"] == "out-run-1"
    assert len(citations[0]["preview"]) == 200
    assert "TAIL" not in citations[0]["preview"]


@pytest.mark.asyncio
async def test_the_owner_recalls_the_observation_exactly(app):
    """Exactly: the point of recall is that what the narrative compressed away is recoverable
    without re-running a tool and without similarity search."""
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        conversation = await _conversation(db)
        await _observed(db)
        checkpoint = await _checkpoint(db, conversation)
        checkpoint.citations = await build_citations(db, "conv-1", ["run-1"])
        await db.commit()

        recalled = await recall_observation(db, OWNER, PROJECT, "out-run-1")

    assert recalled["content"] == "x" * 500 + " TAIL"
    assert recalled["checkpoint_id"] == checkpoint.id


@pytest.mark.asyncio
async def test_an_ungranted_peer_is_told_nothing_about_whether_the_id_exists(app):
    """404-shaped, not 403-shaped. Confirming an id exists but is out of reach is itself a
    disclosure, so "no such observation" and "not yours to read" must be indistinguishable."""
    async with async_session_factory() as db:
        await _agent(db, PEER, can_read_checkpoints=True)  # read, but not recall
        conversation = await _conversation(db)
        await _observed(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")
        checkpoint.citations = await build_citations(db, "conv-1", ["run-1"])
        await db.commit()

        with pytest.raises(AccessDeniedError) as real_id:
            await recall_observation(db, PEER, PROJECT, "out-run-1")
        with pytest.raises(AccessDeniedError) as absent_id:
            await recall_observation(db, PEER, PROJECT, "out-does-not-exist")

    assert str(real_id.value) == str(absent_id.value)


@pytest.mark.asyncio
async def test_an_uncited_observation_is_not_reachable_even_by_a_granted_peer(app):
    """Citation is what scopes recall to a conversation. Without it the grant would mean "read
    any recorded output in the project", which is a far larger permission."""
    async with async_session_factory() as db:
        await _agent(db, PEER, can_read_checkpoints=True, can_recall=True)
        conversation = await _conversation(db)
        await _observed(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")
        checkpoint.citations = []
        await db.commit()

        with pytest.raises(AccessDeniedError):
            await recall_observation(db, PEER, PROJECT, "out-run-1")


@pytest.mark.asyncio
async def test_the_tester_scenario_end_to_end(app):
    """Task 7.7. An agent granted checkpoint reads over three peers can read their checkpoints
    and is refused recall on all of them."""
    async with async_session_factory() as db:
        tester = await _agent(db, "tester", can_read_checkpoints=True)
        checkpoints = []
        for index, peer in enumerate(("dev-1", "dev-2", "dev-3")):
            await _agent(db, peer)
            conversation = await _conversation(db, f"conv-{index}", agent=peer)
            await _observed(db, f"conv-{index}", f"run-{index}", agent=peer)
            checkpoint = await _checkpoint(db, conversation, visibility="project")
            checkpoint.citations = await build_citations(db, f"conv-{index}", [f"run-{index}"])
            checkpoints.append(checkpoint)
        await db.commit()

        assert all(may_read_checkpoint(tester, cp) for cp in checkpoints)
        assert not any(may_recall(tester, cp) for cp in checkpoints)


# --------------------------------------------------------------------------- participation


@pytest.mark.asyncio
async def test_participation_is_derived_from_runs_not_stored(app):
    """Task 7.6. Every mutation carries a run id and every run carries an agent and a
    conversation, so this is a join. Storing it would be a second graph to keep correct — and
    lineage, which is linear and single-agent, is a different shape entirely."""
    async with async_session_factory() as db:
        await _conversation(db, "conv-a", agent=OWNER)
        await _conversation(db, "conv-b", agent=PEER)
        db.add(Run(id="run-a", project_id=PROJECT, agent=OWNER, conversation_id="conv-a"))
        db.add(Run(id="run-b", project_id=PROJECT, agent=PEER, conversation_id="conv-b"))
        db.add(
            Task(
                id="t1",
                project_id=PROJECT,
                title="Shared work",
                created_by_run_id="run-a",
                updated_by_run_id="run-b",
            )
        )
        await db.commit()

        found = await participants(db, PROJECT, "conv-a")

    # The task was created in conv-a and last touched by the peer in conv-b — which is exactly
    # the cross-agent fact the query exists to surface.
    assert found == [
        {
            "agent": PEER,
            "conversation_id": "conv-b",
            "tasks": [{"id": "t1", "title": "Shared work"}],
        }
    ]


@pytest.mark.asyncio
async def test_a_conversation_that_touched_no_work_has_no_participants(app):
    async with async_session_factory() as db:
        await _conversation(db, "conv-quiet")
        assert await participants(db, PROJECT, "conv-quiet") == []


@pytest.mark.asyncio
async def test_grants_are_settable_over_the_api_and_default_closed(app, auth_headers):
    async with async_session_factory() as db:
        await _agent(db, PEER)

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{PEER}",
        json={"can_read_checkpoints": True},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["can_read_checkpoints"] is True
    assert response.json()["can_recall"] is False

    bad = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{PEER}",
        json={"can_recall": "yes"},
        headers=auth_headers,
    )
    assert bad.status_code == 400

    async with async_session_factory() as db:
        row = (await db.execute(select(Agent).where(Agent.name == PEER))).scalars().one()
    assert row.can_read_checkpoints is True
    assert row.can_recall is False


# ------------------------------------------------- the visibility the product actually produces


@pytest.mark.asyncio
async def test_a_checkpoint_the_product_makes_is_visible_to_the_project(app):
    """F88. Every test above hands `create_checkpoint` a visibility; nothing in the product did.

    `visibility` defaulted to `private`, no caller anywhere passed anything else, and there is no
    route, tool or control that can change one — so the visibility half of `capability ∩
    visibility` was closed for every checkpoint that has ever existed, and both reader grants were
    conferrable and inert. Measured live on 2026-08-28: an agent holding `can_read_checkpoints`
    and `can_recall` was refused a peer's cited observation.

    The default asserted here is the one the spec describes — "a checkpoint MAY additionally
    restrict itself" makes restriction the exception, not the birth state — and the system stays
    closed by default because both reader grants still do.
    """
    async with async_session_factory() as db:
        conversation = await _conversation(db)
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body=BODY,
        )

    assert checkpoint.visibility == "project"


@pytest.mark.asyncio
async def test_a_granted_peer_reads_a_checkpoint_nobody_configured(app):
    """The end-to-end the suite could not see: no explicit visibility anywhere in this test."""
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        await _agent(db, PEER, can_read_checkpoints=True)
        conversation = await _conversation(db)
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body=BODY,
        )

        listed = await readable_checkpoints(db, PEER, PROJECT)
        opened = await read_checkpoint(db, PEER, PROJECT, checkpoint.id)

    assert [row["id"] for row in listed] == [checkpoint.id]
    assert listed[0]["agent"] == OWNER
    assert listed[0]["yours"] is False
    assert opened["id"] == checkpoint.id
    assert "## Objective" in opened["rendered"]


@pytest.mark.asyncio
async def test_an_ungranted_peer_neither_lists_nor_opens_it(app):
    """And the refusal to open is indistinguishable from an id that does not exist."""
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        await _agent(db, PEER)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="project")

        assert await readable_checkpoints(db, PEER, PROJECT) == []
        with pytest.raises(AccessDeniedError) as real_id:
            await read_checkpoint(db, PEER, PROJECT, checkpoint.id)
        with pytest.raises(AccessDeniedError) as absent_id:
            await read_checkpoint(db, PEER, PROJECT, "ckpt-does-not-exist")

    assert str(real_id.value) == str(absent_id.value)


@pytest.mark.asyncio
async def test_an_agent_lists_its_own_checkpoints_without_any_grant(app):
    """A grant governs peers. An agent's own history was never behind one."""
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        conversation = await _conversation(db)
        checkpoint = await _checkpoint(db, conversation, visibility="private")

        listed = await readable_checkpoints(db, OWNER, PROJECT)
        opened = await read_checkpoint(db, OWNER, PROJECT, checkpoint.id)

    assert [row["id"] for row in listed] == [checkpoint.id]
    assert listed[0]["yours"] is True
    assert opened["id"] == checkpoint.id


@pytest.mark.asyncio
async def test_the_list_omits_a_checkpoint_with_nothing_to_read(app):
    """An `unwritten` checkpoint has no body. Offering an id that opens to nothing is a worse
    answer than not listing it."""
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        conversation = await _conversation(db)
        unwritten = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body="   ",
        )

        listed = await readable_checkpoints(db, OWNER, PROJECT)

    assert unwritten.status == "unwritten"
    assert listed == []


@pytest.mark.asyncio
async def test_the_agent_filter_narrows_and_cannot_widen(app):
    """`agent` is applied on top of the access check, never instead of it."""
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        await _agent(db, PEER)
        owners = await _conversation(db, "conv-owner", agent=OWNER)
        peers = await _conversation(db, "conv-peer", agent=PEER)
        mine = await _checkpoint(db, peers, visibility="project")
        theirs = await _checkpoint(db, owners, visibility="project")

        unfiltered = await readable_checkpoints(db, PEER, PROJECT)
        filtered = await readable_checkpoints(db, PEER, PROJECT, agent=OWNER)

    assert [row["id"] for row in unfiltered] == [mine.id]
    assert theirs.id not in [row["id"] for row in unfiltered]
    assert filtered == []


# ------------------------------------------------------- the routes an agent actually reaches


async def _active_run(run_id: str, agent: str) -> dict:
    """A live run's minted credential, which is the only identity these routes accept."""
    from hub.agent_auth import hash_run_token

    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_the_routes_answer_a_granted_peer_and_refuse_an_ungranted_one(app):
    """F88 end to end over HTTP, with the identity taken from the run's credential.

    `agent` is a filter on top of the access check, so a caller naming a peer it may not read
    gets an empty list rather than that peer's history.
    """
    async with async_session_factory() as db:
        await _agent(db, OWNER)
        await _agent(db, PEER, can_read_checkpoints=True)
        await _agent(db, "outsider")
        conversation = await _conversation(db)
        checkpoint = await create_checkpoint(
            db,
            conversation,
            trigger="operator",
            envelope=await compute_envelope(db, conversation),
            body=BODY,
        )

    granted = await _active_run("run-ckpt-peer", PEER)
    listed = await app.get("/api/v1/agent-actions/checkpoints", headers=granted)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [checkpoint.id]

    opened = await app.get(f"/api/v1/agent-actions/checkpoints/{checkpoint.id}", headers=granted)
    assert opened.status_code == 200
    assert "## Objective" in opened.json()["rendered"]

    ungranted = await _active_run("run-ckpt-outsider", "outsider")
    assert (await app.get("/api/v1/agent-actions/checkpoints", headers=ungranted)).json() == []
    # Naming the owner does not become being the owner. Passing `agent` through as the reader's
    # identity rather than as a filter would hand this caller exactly what it asked to be.
    named = await app.get(f"/api/v1/agent-actions/checkpoints?agent={OWNER}", headers=ungranted)
    assert named.json() == []
    refused = await app.get(f"/api/v1/agent-actions/checkpoints/{checkpoint.id}", headers=ungranted)
    assert refused.status_code == 404
