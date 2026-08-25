"""Conferring, and reading back, the authority to accept evidence.

`Agent.can_accept_evidence` and its migration have existed since `0068`. Nothing could set it — no
schema field, no route, no control — so `requirement_evidence.may_accept` refused every agent in
every project. Authority over what ships is the operator's to give, and a capability enforced
everywhere and grantable nowhere is a refusal of everyone.

The read-back assertions are the load-bearing ones. `AgentSummary` is constructed by hand in the
roster route, so a grant added to the schema and not added there reads back as its default no
matter what the row says — the operator would set a switch and watch it turn itself off.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent

AGENTS = "/api/v1/projects/proj-test/agents"


@pytest.fixture
async def reviewer():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-grant", project_id="proj-test", name="reviewer"))
        await session.commit()
    return "reviewer"


async def _row(name: str) -> Agent:
    async with async_session_factory() as session:
        return (
            (
                await session.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == name)
                )
            )
            .scalars()
            .first()
        )


@pytest.mark.asyncio
async def test_a_new_agent_holds_no_authority_over_what_ships(app, auth_headers, reviewer):
    listed = await app.get(AGENTS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    summary = next(row for row in listed.json() if row["name"] == "reviewer")
    assert summary["can_accept_evidence"] is False


@pytest.mark.asyncio
async def test_the_operator_grants_it_and_reads_it_back(app, auth_headers, reviewer):
    """The read-back is the point.

    `AgentSummary` is built field by field, so a schema default of `False` silently wins over the
    row unless that construction names the grant too.
    """
    patched = await app.patch(
        f"{AGENTS}/reviewer", json={"can_accept_evidence": True}, headers=auth_headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["can_accept_evidence"] is True

    listed = await app.get(AGENTS, headers=auth_headers)
    summary = next(row for row in listed.json() if row["name"] == "reviewer")
    assert summary["can_accept_evidence"] is True, "the roster reads back its own default"

    assert (await _row("reviewer")).can_accept_evidence is True


@pytest.mark.asyncio
async def test_the_grant_is_withdrawable(app, auth_headers, reviewer):
    await app.patch(f"{AGENTS}/reviewer", json={"can_accept_evidence": True}, headers=auth_headers)
    withdrawn = await app.patch(
        f"{AGENTS}/reviewer", json={"can_accept_evidence": False}, headers=auth_headers
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["can_accept_evidence"] is False
    assert (await _row("reviewer")).can_accept_evidence is False


@pytest.mark.asyncio
async def test_it_is_a_boolean_and_says_so(app, auth_headers, reviewer):
    refused = await app.patch(
        f"{AGENTS}/reviewer", json={"can_accept_evidence": "yes"}, headers=auth_headers
    )
    assert refused.status_code == 400, refused.text
    assert "true or false" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_granting_it_leaves_the_checkpoint_grants_alone(app, auth_headers, reviewer):
    """Separate capabilities, separately conferred.

    Those two widen what an agent may read; this one decides whether work may merge. Folding them
    into one tuple would make each imply the others.
    """
    await app.patch(f"{AGENTS}/reviewer", json={"can_accept_evidence": True}, headers=auth_headers)

    row = await _row("reviewer")
    assert row.can_accept_evidence is True
    assert row.can_read_checkpoints is False
    assert row.can_recall is False


@pytest.mark.asyncio
async def test_a_charter_confers_nothing(app, auth_headers, reviewer):
    """A charter says how an agent behaves, and behaviour is not authority.

    A "Verifier" charter may well describe an agent that accepts evidence; it grants it nothing.
    """
    charters = await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)
    assert charters.status_code == 200, charters.text
    rows = charters.json()
    rows = rows.get("charters", rows) if isinstance(rows, dict) else rows
    verifier = next((row for row in rows if "erif" in row["name"]), None)
    if verifier is None:
        pytest.skip("no verifier-like charter seeded in this project")

    bound = await app.patch(
        f"{AGENTS}/reviewer", json={"charter_id": verifier["id"]}, headers=auth_headers
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["can_accept_evidence"] is False
    assert (await _row("reviewer")).can_accept_evidence is False


@pytest.mark.asyncio
async def test_a_granted_agent_is_told_it_can_decide(app, auth_headers, reviewer):
    """A capability an agent does not know it holds is one it does not use.

    This is the `submit_spec_document` failure mode exactly: served, correct, and invisible. An
    agent that guesses instead is refused in the middle of a turn it has already spent.
    """
    await app.patch(f"{AGENTS}/reviewer", json={"can_accept_evidence": True}, headers=auth_headers)

    rendered = await app.get(
        f"{AGENTS}/agent-context", params={"agent": "reviewer"}, headers=auth_headers
    )
    assert rendered.status_code == 200, rendered.text
    context = rendered.json()["context"]

    assert "You can decide evidence" in context
    assert "decide_evidence" in context
    # And the rule it would otherwise discover by being refused.
    assert "cannot decide evidence you produced yourself" in context


@pytest.mark.asyncio
async def test_an_ungranted_agent_is_not_told_it_can(app, auth_headers, reviewer):
    rendered = await app.get(
        f"{AGENTS}/agent-context", params={"agent": "reviewer"}, headers=auth_headers
    )
    assert rendered.status_code == 200, rendered.text
    assert "You can decide evidence" not in rendered.json()["context"]


@pytest.mark.asyncio
async def test_the_tools_are_named_to_every_agent_regardless(app, auth_headers, reviewer):
    """Recording is open; only deciding is granted. An agent that cannot see `record_evidence`
    cannot produce the evidence approval waits for."""
    rendered = await app.get(
        f"{AGENTS}/agent-context", params={"agent": "reviewer"}, headers=auth_headers
    )
    context = rendered.json()["context"]
    assert "record_evidence(" in context
    assert "list_evidence(" in context


@pytest.mark.asyncio
async def test_an_ungranted_agent_is_told_it_cannot_decide(app, auth_headers, reviewer):
    """F32: the principle was applied in one direction only.

    Measured 2026-08-25: `rev` spent a full 97-row Codex turn reviewing — running the suite twice
    and writing a hand reproducer — and only then hit a 403 on `decide_evidence`. `list_evidence`
    had succeeded moments earlier, so it could read the queue it was not permitted to answer.
    """
    rendered = await app.get(
        f"{AGENTS}/agent-context", params={"agent": "reviewer"}, headers=auth_headers
    )
    assert rendered.status_code == 200, rendered.text
    context = rendered.json()["context"]

    assert "### You cannot decide evidence" in context
    # Named, so the agent does not plan a turn around reaching for it.
    assert "decide_evidence" in context
    # Reading the queue is not an invitation to answer it — the exact trap `rev` fell into.
    assert "list_evidence" in context


@pytest.mark.asyncio
async def test_the_withheld_case_says_where_a_verdict_goes_instead(app, auth_headers, reviewer):
    """The downstream cost of F32, not the 403 itself.

    Unable to record its verdict, `rev` wrote the review to `.reviews/review-0001-...md` inside its
    own worktree, which is isolated by design. Its conclusion — "ship it", with its checks — is on
    a branch nobody reads. A refusal that does not say where the work should go loses the work.
    """
    rendered = await app.get(
        f"{AGENTS}/agent-context", params={"agent": "reviewer"}, headers=auth_headers
    )
    context = rendered.json()["context"]

    lowered = context.lower()
    assert "message" in lowered or "record it on the task" in lowered
    assert "worktree" in lowered


@pytest.mark.asyncio
async def test_a_granted_agent_is_not_told_it_cannot(app, auth_headers, reviewer):
    """The two halves are exclusive: exactly one is emitted, never both."""
    await app.patch(f"{AGENTS}/reviewer", json={"can_accept_evidence": True}, headers=auth_headers)

    rendered = await app.get(
        f"{AGENTS}/agent-context", params={"agent": "reviewer"}, headers=auth_headers
    )
    context = rendered.json()["context"]

    assert "You can decide evidence" in context
    # The granted branch already contains the sentence "You cannot decide evidence you produced
    # yourself", so the heading is what distinguishes the two branches.
    assert "### You cannot decide evidence" not in context
