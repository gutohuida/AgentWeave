"""`a-specification-is-read-in-results-that-fit` (F363): a read is bounded, and continues.

`read_spec_document` returned every requirement with its criteria in one result. On real documents
that was 52-67 KB, above the 50,000-character threshold at which Claude Code spills a tool result
to a `tool-results/` file the workspace guard then refuses to read (design D1). The Hub now bounds
the whole response to `READ_BUDGET_CHARS` and says how to read the rest (D2), by identifier (D3),
and accepts a document id where a path goes (D4).

The large document is generated, never a copy of a real spec (tasks.md, group 1).
"""

import json
import math
from unittest.mock import patch

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
from hub.spec_documents import parse_hub, parse_stored, serialize
from hub.spec_payload import SCHEMA_VERSION

from . import test_read_spec_document as _reading
from .test_read_spec_document import BASE, PATH, READ, SUBMIT

# Re-exported by assignment: importing the fixture by name would trip F811 in every signature.
builder = _reading.builder

BUDGET = 40_000
PREAMBLE = ("summary", "problem", "scope", "open_questions")


def _budget() -> int:
    from hub import spec_reading

    return getattr(spec_reading, "READ_BUDGET_CHARS", BUDGET)


def _requirement(n: int) -> dict:
    return {"key": f"r{n}", "statement": f"Requirement {n} " + "s" * 600, "modal": "MUST"}


def _criteria(n: int) -> list:
    return [
        {"key": f"r{n}-c{i}", "requirement": f"r{n}", "given": "g", "when": "w", "then": "t" * 400}
        for i in range(3)
    ]


def _document(numbers, **extra) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Large",
        "summary": "A large document",
        "requirements": [_requirement(n) for n in numbers],
        "acceptance_criteria": [c for n in numbers for c in _criteria(n)],
        **extra,
    }


async def _submit(app, run_headers, document):
    saved = await app.post(SUBMIT, json={"path": PATH, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def _large(app, auth_headers, run_headers, n=60, **extra):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Large"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    await _submit(app, run_headers, _document(range(1, n + 1), **extra))


async def _read(app, headers, **params):
    response = await app.get(READ, params={"path": PATH, **params}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _identifiers(body) -> list:
    return [row["identifier"] or row["key"] for row in body["requirements"]]


# --------------------------------------------------------------------------- 1.1 the bound


@pytest.mark.asyncio
async def test_a_large_document_read_with_defaults_fits_the_budget(app, auth_headers, builder):
    await _large(app, auth_headers, builder)
    body = await _read(app, builder)

    size = len(json.dumps(body))
    assert size <= _budget(), f"default read is {size} characters"
    assert len(json.dumps(body, separators=(",", ":"), ensure_ascii=False)) <= 50_000
    assert body["truncated"] is True
    returned = _identifiers(body)
    assert returned == [f"FR-{n}" for n in range(1, len(returned) + 1)]
    assert body["remaining_identifiers"] == [f"FR-{n}" for n in range(len(returned) + 1, 61)]
    assert "identifiers=" in body["continue_with"]


# --------------------------------------------------------------------------- 1.2 / 1.15 continuing


async def _continue(app, headers, first, total_hint):
    seen = _identifiers(first)
    remaining = first["remaining_identifiers"]
    reads = 1
    while remaining:
        body = await _read(app, headers, identifiers=",".join(remaining))
        reads += 1
        for name in PREAMBLE:
            assert name not in body, f"a continuation carried {name}"
        seen.extend(_identifiers(body))
        remaining = body.get("remaining_identifiers") or []
        assert reads <= math.ceil(total_hint / _budget()) + 1, "the continuation does not end"
    return seen, reads


@pytest.mark.asyncio
async def test_continuing_by_identifiers_returns_every_requirement_once(app, auth_headers, builder):
    await _large(app, auth_headers, builder)
    first = await _read(app, builder)
    total = (
        sum(len(json.dumps(row)) for row in first["requirements"])
        * 60
        // max(1, len(first["requirements"]))
    )

    seen, _reads = await _continue(app, builder, first, total)

    assert sorted(seen, key=lambda i: int(i.split("-")[1])) == [f"FR-{n}" for n in range(1, 61)]
    assert len(seen) == len(set(seen))


@pytest.mark.asyncio
async def test_a_large_preamble_is_not_resent_on_every_continuation(app, auth_headers, builder):
    """1.15. Without leaving the preamble out, each continuation carries fewer requirements and
    the read count grows past the bound (operator decision, 2026-09-24)."""
    await _large(
        app,
        auth_headers,
        builder,
        n=80,
        summary="u" * 8_000,
        problem="p" * 8_000,
        scope={"in_scope": ["i" * 4_000], "non_goals": ["n" * 4_000]},
        open_questions=[{"question": "q" * 6_000, "resolved": True}],
    )
    first = await _read(app, builder)
    # Sized from an uncut requirement: the first read's own may be cut, the preamble filling it.
    whole = (await _read(app, builder, identifiers="FR-2"))["requirements"][0]
    unbounded = 30_000 + 80 * (len(json.dumps(whole)) + 10)

    seen, reads = await _continue(app, builder, first, unbounded)

    assert len(set(seen)) == 80
    assert reads <= math.ceil(unbounded / _budget()) + 1


# --------------------------------------------------------------------------- 1.3 order


@pytest.mark.asyncio
async def test_the_truncated_prefix_is_in_numeric_identifier_order(app, auth_headers, builder):
    """Identifiers are minted in declaration order, so the second revision lists the requirements
    in reverse: payload order and string order both differ from what the route returns (F190)."""
    await _large(app, auth_headers, builder)
    await _submit(app, builder, _document(range(60, 0, -1)))

    body = await _read(app, builder)
    returned = _identifiers(body)
    assert returned == [f"FR-{n}" for n in range(1, len(returned) + 1)]
    assert len(returned) >= 12 or body["remaining_identifiers"][0] == f"FR-{len(returned) + 1}"


# --------------------------------------------------------------------------- 1.4 / 1.5 targeted


@pytest.mark.asyncio
async def test_unknown_identifiers_are_named_not_refused(app, auth_headers, builder):
    await _large(app, auth_headers, builder, n=5)
    body = await _read(app, builder, identifiers="FR-2,FR-99")
    assert _identifiers(body) == ["FR-2"]
    assert body["unknown_identifiers"] == ["FR-99"]


@pytest.mark.asyncio
async def test_the_outline_carries_five_keys_per_requirement(app, auth_headers, builder, tmp_path):
    await _large(app, auth_headers, builder, n=5)
    _add_an_unindexed_requirement(tmp_path)

    body = await _read(app, builder, include="outline")

    for row in body["requirements"]:
        assert set(row) == {"identifier", "key", "modal", "statement", "state"}
    (unindexed,) = [row for row in body["requirements"] if row["identifier"] is None]
    assert unindexed["key"] == "zeta"


# --------------------------------------------------------------------------- 1.6 / 1.14 sections


@pytest.mark.asyncio
async def test_a_section_too_large_for_the_read_is_named_and_readable(app, auth_headers, builder):
    await _large(app, auth_headers, builder, n=3, design="d" * 60_000)

    full = await _read(app, builder, include="full")
    assert "design" in full["omitted_sections"]
    assert "design" not in full

    design = await _read(app, builder, include="design")
    assert design["design"].startswith("ddd")
    assert design["section_truncated"] == "design"
    assert len(json.dumps(design)) <= _budget()


@pytest.mark.asyncio
async def test_every_omitted_preamble_field_is_readable_by_name(app, auth_headers, builder):
    await _large(app, auth_headers, builder, n=3, problem="p" * 60_000)

    body = await _read(app, builder)
    assert "problem" in body["omitted_sections"]

    problem = await _read(app, builder, include="problem")
    assert problem["problem"].startswith("ppp")
    assert problem["section_truncated"] == "problem"
    for name in ("summary", "scope", "open_questions"):
        assert name in await _read(app, builder, include=name)


# --------------------------------------------------------------------------- 1.7 / 1.8 by id


async def _document_id() -> str:
    from sqlalchemy import select

    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument.id).where(SpecDocument.path == PATH))
        ).scalar_one()


@pytest.mark.asyncio
async def test_a_document_is_read_by_its_id(app, auth_headers, builder):
    await _large(app, auth_headers, builder, n=3)
    document_id = await _document_id()

    response = await app.get(READ, params={"path": document_id}, headers=builder)
    assert response.status_code == 200, response.text
    by_id = response.json()
    by_path = await _read(app, builder)

    assert by_id["requirements"] == by_path["requirements"]
    assert by_id["id"] == document_id
    assert by_id["path"] == PATH


@pytest.mark.asyncio
async def test_another_projects_document_id_is_not_found(app, auth_headers, builder):
    async with async_session_factory() as session:
        session.add(SpecDocument(id="spdoc-0e1e0e", project_id="proj-other", path=PATH))
        await session.commit()

    elsewhere = await app.get(READ, params={"path": "spdoc-0e1e0e"}, headers=builder)
    unknown = await app.get(READ, params={"path": "spdoc-abc123"}, headers=builder)

    assert elsewhere.status_code == unknown.status_code == 404
    assert elsewhere.json()["detail"].replace("0e1e0e", "X") == unknown.json()["detail"].replace(
        "abc123", "X"
    )


# --------------------------------------------------------------------------- 1.12 no identifier


def _add_an_unindexed_requirement(project_root):
    """A requirement the file declares, the index has not seen, and the identity block names not."""
    target = project_root / PATH
    content = target.read_text(encoding="utf-8")
    payload = parse_stored(content)
    payload["requirements"].append(
        {"key": "zeta", "statement": "An unindexed requirement " + "z" * 600, "modal": "MAY"}
    )
    target.write_text(serialize(payload, parse_hub(content)), encoding="utf-8", newline="\n")


@pytest.mark.asyncio
async def test_a_requirement_with_no_identifier_is_continued_by_key(
    app, auth_headers, builder, tmp_path
):
    await _large(app, auth_headers, builder)
    _add_an_unindexed_requirement(tmp_path)

    first = await _read(app, builder)
    assert first["remaining_identifiers"][-1] == "zeta"

    zeta = await _read(app, builder, identifiers="zeta")
    assert [row["key"] for row in zeta["requirements"]] == ["zeta"]


# --------------------------------------------------------------------------- 1.13 D6


@pytest.mark.asyncio
@pytest.mark.parametrize("raised", ["oserror", "unicode", "projectpath"])
async def test_an_unreadable_file_is_a_conflict_not_a_500(app, auth_headers, builder, raised):
    from hub.project_workspace import ProjectPathError

    await _large(app, auth_headers, builder, n=2)
    error = {
        "oserror": PermissionError("access denied"),
        "unicode": UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        "projectpath": ProjectPathError("spec resolves outside the project"),
    }[raised]

    def _raise(*_a, **_k):
        raise error

    with patch("hub.spec_documents.read_document", _raise):
        response = await app.get(READ, params={"path": PATH}, headers=builder)

    assert response.status_code == 409, response.text
    assert "the document's file could not be read" in response.json()["detail"]


# --------------------------------------------------------------------------- 1.10 fit_view


def _view(requirements, **extra):
    return {
        "id": "spdoc-1",
        "path": PATH,
        "title": "T",
        "kind": "change-spec",
        "phase": "exploring",
        "rigor": "sketch",
        "explore_closed": False,
        "updated_at": None,
        "diverged": False,
        "diagnostics": [],
        "summary": "s",
        "requirements": requirements,
        **extra,
    }


def _row(n, size=100):
    return {"identifier": f"FR-{n}", "key": f"r{n}", "statement": "x" * size}


def test_a_view_that_fits_is_returned_unchanged():
    from hub.spec_reading import fit_view

    view = _view([_row(1), _row(2)])
    assert fit_view(dict(view), budget=40_000) == view


def test_a_single_requirement_larger_than_the_budget_is_cut_and_marked():
    from hub.spec_reading import fit_view

    fitted = fit_view(_view([_row(1, size=50_000), _row(2)]), budget=10_000)

    (only,) = fitted["requirements"]
    assert only["identifier"] == "FR-1"
    assert only["section_truncated"] is True
    assert fitted["remaining_identifiers"] == ["FR-2"]
    assert len(json.dumps(fitted)) <= 10_000


def test_the_fixed_fields_are_never_dropped():
    from hub.spec_reading import fit_view

    fitted = fit_view(_view([_row(n, size=2_000) for n in range(30)]), budget=5_000)
    for name in ("id", "path", "title", "kind", "phase", "rigor", "diverged", "diagnostics"):
        assert name in fitted


# --------------------------------------------------------------------------- D7 written to a file
#
# The drive of 2026-10-07: a Haiku agent read through `aw-tool` in PowerShell, whose output spills
# above 30,000 characters, and a 37.6 KB read spilled. A read that does not fit is now written into
# the agent's own workspace, and the answer says where.


@pytest.fixture
async def builder_with_workspace(tmp_path):
    from hub.agent_auth import hash_run_token
    from hub.db.models import Agent, Run

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rw", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-rw",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                workspace_dir=str(workspace),
                capability_token_hash=hash_run_token("aw_run_rw-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rw-secret"}, workspace


@pytest.mark.asyncio
async def test_a_large_read_is_written_into_the_agents_workspace(
    app, auth_headers, builder_with_workspace
):
    headers, workspace = builder_with_workspace
    await _large(app, auth_headers, headers)
    document_id = await _document_id()

    answer = await _read(app, headers)

    assert len(json.dumps(answer)) <= _budget()
    assert answer["written_to"] == f".agentweave/reads/{document_id}.requirements.md"
    assert answer["requirement_identifiers"] == [f"FR-{n}" for n in range(1, 61)]
    assert answer["written_to"] in answer["read_with"]
    text = (workspace / answer["written_to"]).read_text(encoding="utf-8")
    assert max(len(line) for line in text.splitlines()) <= 200
    for n in range(1, 61):
        assert f"### FR-{n} (key: r{n})" in text
    # Every criterion whole: wrapping moves words onto new lines and drops nothing.
    assert "".join(text.split()).count("Then" + "t" * 400) == 180


@pytest.mark.asyncio
async def test_a_read_that_fits_is_answered_inline(app, auth_headers, builder_with_workspace):
    headers, workspace = builder_with_workspace
    await _large(app, auth_headers, headers, n=3)

    answer = await _read(app, headers)

    assert "written_to" not in answer
    assert len(answer["requirements"]) == 3
    assert not (workspace / ".agentweave" / "reads").exists()


@pytest.mark.asyncio
async def test_a_large_selection_has_a_file_of_its_own(app, auth_headers, builder_with_workspace):
    headers, _workspace = builder_with_workspace
    await _large(app, auth_headers, headers)
    document_id = await _document_id()

    answer = await _read(app, headers, identifiers=",".join(f"FR-{n}" for n in range(1, 41)))

    assert answer["written_to"] == f".agentweave/reads/{document_id}.selection.md"
    assert answer["requirement_identifiers"] == [f"FR-{n}" for n in range(1, 41)]


@pytest.mark.asyncio
async def test_a_reads_path_that_is_not_a_directory_falls_back_to_the_bounded_read(
    app, auth_headers, builder_with_workspace
):
    headers, workspace = builder_with_workspace
    (workspace / ".agentweave").mkdir()
    (workspace / ".agentweave" / "reads").write_text("not a directory", encoding="utf-8")
    await _large(app, auth_headers, headers)

    answer = await _read(app, headers)

    assert "written_to" not in answer
    assert answer["truncated"] is True
    assert len(json.dumps(answer)) <= _budget()


def test_the_reads_directory_is_kept_out_of_every_commit():
    from hub.repo_hygiene import EXCLUDE_PATTERNS

    assert ".agentweave/reads/" in EXCLUDE_PATTERNS
