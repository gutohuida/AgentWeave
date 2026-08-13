"""The requirement index: populated, rebuildable, and honest about what moved.

The assertions worth reading here are the ones about *not* losing things. An
index that merely reflects the current document is easy; what this change needs
is an index that keeps a retired requirement, records the meaning it had when it
was removed, and rebuilds to the same answer from the files after being thrown
away. Each of those fails silently if it fails at all.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocument, SpecRequirement, SpecRequirementRevision
from hub.spec_payload import SCHEMA_VERSION, extract_payload

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/index-demo/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_spec-index-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-spec-index",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _payload(requirements, criteria=None, **overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Index demo",
        "requirements": requirements,
        "acceptance_criteria": criteria or [],
    }
    payload.update(overrides)
    return payload


ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}


async def _create(app, auth_headers, path=PATH):
    response = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Index demo"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _submit(app, run_headers, requirements, criteria=None, path=PATH):
    response = await app.post(
        SUBMIT,
        json={"path": path, "document": _payload(requirements, criteria)},
        headers=run_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _rows(path=PATH):
    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == path)))
            .scalars()
            .first()
        )
        result = await session.execute(
            select(SpecRequirement)
            .where(SpecRequirement.document_id == document.id)
            .order_by(SpecRequirement.identifier)
        )
        return {row.identifier: row for row in result.scalars().all()}


async def _revisions(identifier, path=PATH):
    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == path)))
            .scalars()
            .first()
        )
        row = (
            (
                await session.execute(
                    select(SpecRequirement).where(
                        SpecRequirement.document_id == document.id,
                        SpecRequirement.identifier == identifier,
                    )
                )
            )
            .scalars()
            .first()
        )
        result = await session.execute(
            select(SpecRequirementRevision)
            .where(SpecRequirementRevision.requirement_id == row.id)
            .order_by(SpecRequirementRevision.created_at, SpecRequirementRevision.id)
        )
        return list(result.scalars().all())


def _edit_payload_by_hand(tmp_path, mutate, path=PATH):
    """Rewrite a document's stored payload the way a person with an editor would.

    The Hub is not involved, which is the point: everything reaching the index
    through this helper is an external change and must be recorded as one.
    """
    from hub.spec_payload import embed_payload

    document_file = tmp_path / path
    content = document_file.read_text(encoding="utf-8")
    stored = extract_payload(content)
    mutate(stored)
    block = content[content.index("<script type=") : content.rindex("</script>") + len("</script>")]
    document_file.write_text(content.replace(block, embed_payload(stored)), encoding="utf-8")


async def _reindex(tmp_path, project_id="proj-test"):
    from hub import spec_index
    from hub.project_workspace import ProjectWorkspace

    async with async_session_factory() as session:
        results = await spec_index.reindex_project(
            session,
            ProjectWorkspace(project_id=project_id, root=tmp_path, path_key=f"test:{project_id}"),
            project_id,
        )
        await session.commit()
    return results


# ---------------------------------------------------------------------------
# Populated on save
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_saved_document_populates_the_index(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)

    await _submit(app, run_headers, [ALPHA, BETA])

    rows = await _rows()
    assert sorted(rows) == ["FR-1", "FR-2"]
    assert rows["FR-1"].key == "alpha"
    assert rows["FR-1"].state == "active"
    assert rows["FR-1"].anchor == "#FR-1"
    assert rows["FR-1"].digest
    assert rows["FR-1"].digest != rows["FR-2"].digest


@pytest.mark.asyncio
async def test_the_index_digest_is_the_one_the_document_row_carries(
    app, auth_headers, run_headers, tmp_path
):
    """Two definitions of "has this changed" disagree eventually, and the
    disagreement is invisible until someone compares two screens."""
    await _create(app, auth_headers)

    await _submit(app, run_headers, [ALPHA, BETA])

    rows = await _rows()
    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
    assert document.requirement_digests == {
        identifier: row.digest for identifier, row in rows.items()
    }


@pytest.mark.asyncio
async def test_a_first_save_records_a_created_revision(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)

    await _submit(app, run_headers, [ALPHA])

    revisions = await _revisions("FR-1")
    assert len(revisions) == 1
    assert revisions[0].classification == "created"
    assert revisions[0].previous_digest is None
    assert revisions[0].source == "hub"
    assert revisions[0].actor_kind == "agent"
    assert revisions[0].run_id == "run-spec-index"


# ---------------------------------------------------------------------------
# What a rewording does
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reworded_requirement_records_both_digests(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA])
    before = (await _rows())["FR-1"].digest

    await _submit(app, run_headers, [{**ALPHA, "statement": "It lists what is due this week"}])

    after = (await _rows())["FR-1"].digest
    assert after != before
    revisions = await _revisions("FR-1")
    assert [r.classification for r in revisions] == ["created", "reworded"]
    assert revisions[1].previous_digest == before
    assert revisions[1].digest == after


@pytest.mark.asyncio
async def test_an_unchanged_requirement_records_no_revision(
    app, auth_headers, run_headers, tmp_path
):
    """Every save would otherwise look like a rewording, and "the meaning moved"
    would stop meaning anything."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA])

    await _submit(app, run_headers, [ALPHA])

    assert [r.classification for r in await _revisions("FR-1")] == ["created"]


@pytest.mark.asyncio
async def test_a_changed_obligation_is_a_rewording(app, auth_headers, run_headers, tmp_path):
    """MUST to MAY changes what must be built. A digest that ignored the modal
    would leave evidence for the old obligation reporting the requirement as
    verified."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA])

    await _submit(app, run_headers, [{**ALPHA, "modal": "MAY"}])

    assert [r.classification for r in await _revisions("FR-1")] == ["created", "reworded"]


@pytest.mark.asyncio
async def test_a_changed_acceptance_criterion_is_a_rewording(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(
        app,
        run_headers,
        [ALPHA],
        [{"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}],
    )

    await _submit(
        app,
        run_headers,
        [ALPHA],
        [
            {
                "key": "c1",
                "requirement": "alpha",
                "given": "g",
                "when": "w",
                "then": "something else",
            }
        ],
    )

    assert [r.classification for r in await _revisions("FR-1")] == ["created", "reworded"]


@pytest.mark.asyncio
async def test_reordering_criteria_is_not_a_rewording(app, auth_headers, run_headers, tmp_path):
    criteria = [
        {"key": "c1", "requirement": "alpha", "given": "g1", "when": "w1", "then": "t1"},
        {"key": "c2", "requirement": "alpha", "given": "g2", "when": "w2", "then": "t2"},
    ]
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA], criteria)

    await _submit(app, run_headers, [ALPHA], list(reversed(criteria)))

    assert [r.classification for r in await _revisions("FR-1")] == ["created"]


@pytest.mark.asyncio
async def test_a_reworded_rationale_is_not_a_rewording(app, auth_headers, run_headers, tmp_path):
    """A rationale exists to make a rule survive an edge case, not to state one.
    Including it would send every piece of evidence stale over prose."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [{**ALPHA, "rationale": "because it is useful"}])

    await _submit(app, run_headers, [{**ALPHA, "rationale": "because operators asked"}])

    assert [r.classification for r in await _revisions("FR-1")] == ["created"]


# ---------------------------------------------------------------------------
# Retirement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_removed_requirement_is_retired_not_deleted(
    app, auth_headers, run_headers, tmp_path
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    digest_before = (await _rows())["FR-2"].digest

    await _submit(app, run_headers, [ALPHA])

    rows = await _rows()
    assert sorted(rows) == ["FR-1", "FR-2"]
    assert rows["FR-2"].state == "retired"
    # The meaning it had when it was removed, kept so evidence pinned to it stays
    # interpretable.
    assert rows["FR-2"].digest == digest_before
    assert [r.classification for r in await _revisions("FR-2")] == ["created", "retired"]


@pytest.mark.asyncio
async def test_retirement_happens_once(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    await _submit(app, run_headers, [ALPHA])

    await _submit(app, run_headers, [ALPHA])

    assert [r.classification for r in await _revisions("FR-2")] == ["created", "retired"]


@pytest.mark.asyncio
async def test_a_key_that_comes_back_gets_a_new_identifier(
    app, auth_headers, run_headers, tmp_path
):
    """Retirement is permanent, by `spec_identity`'s design: an identifier is
    never reissued, so a key that returns is a new requirement that happens to
    share a handle. The alternative — silently reviving FR-2 — would re-point
    every historical reference to it at something the author never wrote."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    await _submit(app, run_headers, [ALPHA])

    await _submit(app, run_headers, [ALPHA, BETA])

    rows = await _rows()
    assert rows["FR-2"].state == "retired"
    assert rows["FR-3"].state == "active"
    assert rows["FR-3"].key == "beta"
    assert [r.classification for r in await _revisions("FR-2")] == ["created", "retired"]


@pytest.mark.asyncio
async def test_a_retired_identifier_is_not_reissued(app, auth_headers, run_headers, tmp_path):
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    await _submit(app, run_headers, [ALPHA])

    await _submit(app, run_headers, [ALPHA, {"key": "gamma", "statement": "New", "modal": "MUST"}])

    rows = await _rows()
    assert rows["FR-3"].key == "gamma"
    assert rows["FR-2"].state == "retired"


# ---------------------------------------------------------------------------
# Rebuildable from the files alone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_discarded_index_rebuilds_identically(app, auth_headers, run_headers, tmp_path):
    """The property that makes this an index rather than a second source of
    truth. Retired requirements are the hard half: their wording is gone from the
    document, so the digest has to be carried in the file."""
    from hub import spec_index
    from hub.project_workspace import ProjectWorkspace

    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    await _submit(app, run_headers, [ALPHA])

    def described(rows):
        return {
            identifier: (row.key, row.state, row.digest, row.anchor)
            for identifier, row in rows.items()
        }

    before = described(await _rows())

    async with async_session_factory() as session:
        for row in (await session.execute(select(SpecRequirement))).scalars().all():
            for revision in (
                (
                    await session.execute(
                        select(SpecRequirementRevision).where(
                            SpecRequirementRevision.requirement_id == row.id
                        )
                    )
                )
                .scalars()
                .all()
            ):
                await session.delete(revision)
            await session.delete(row)
        await session.commit()

    assert await _rows() == {}

    async with async_session_factory() as session:
        await spec_index.reindex_project(
            session,
            ProjectWorkspace(project_id="proj-test", root=tmp_path, path_key="test:proj-test"),
            "proj-test",
        )
        await session.commit()

    assert described(await _rows()) == before


@pytest.mark.asyncio
async def test_an_edit_made_outside_the_hub_is_recorded_as_external(
    app, auth_headers, run_headers, tmp_path
):
    """A reindex is how a hand-edited file reaches the index, and the record has
    to say the change did not come through the Hub."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA])

    def edit(stored):
        stored["requirements"][0]["statement"] = "Edited by hand"

    _edit_payload_by_hand(tmp_path, edit)
    await _reindex(tmp_path)

    revisions = await _revisions("FR-1")
    assert [r.classification for r in revisions] == ["created", "reworded"]
    assert revisions[1].source == "external"


@pytest.mark.asyncio
async def test_a_requirement_put_back_by_hand_is_restored(app, auth_headers, run_headers, tmp_path):
    """The Hub never revives an identifier — `mint` gives a returning key a new
    one. A file edited outside the Hub can still assert that FR-2 is live again,
    and the index has to say what happened rather than silently disagree with the
    document it is derived from."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    await _submit(app, run_headers, [ALPHA])
    assert (await _rows())["FR-2"].state == "retired"

    def edit(stored):
        stored["requirements"].append(dict(BETA))
        stored["aw_identity"]["requirements"]["beta"] = "FR-2"
        stored["aw_identity"]["retired"] = {}

    _edit_payload_by_hand(tmp_path, edit)
    await _reindex(tmp_path)

    rows = await _rows()
    assert rows["FR-2"].state == "active"
    assert rows["FR-2"].anchor == "#FR-2"
    revisions = await _revisions("FR-2")
    assert [r.classification for r in revisions] == ["created", "retired", "restored"]
    assert revisions[2].source == "external"


@pytest.mark.asyncio
async def test_an_unreadable_document_leaves_the_index_alone(
    app, auth_headers, run_headers, tmp_path
):
    """An editor caught mid-write must not retire every requirement in the file."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, [ALPHA, BETA])
    before = await _rows()

    (tmp_path / PATH).write_text("<html><body>half a fi", encoding="utf-8")

    results = await _reindex(tmp_path)

    assert results[PATH] is None
    after = await _rows()
    assert sorted(after) == sorted(before)
    assert all(after[identifier].state == "active" for identifier in after)
