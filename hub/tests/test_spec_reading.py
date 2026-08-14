"""A task says what its requirements say, and the wording comes from the document.

`SpecRequirement` holds a digest and no wording, deliberately — "so this row cannot come to disagree
with the document about what a requirement says". That is the right call, and it left every task
carrying an identifier and an anchor into a file the reader might have no way to open. An agent
handed `FR-1` and `#FR-1` has been told where the answer is, not what it is.
"""

import pytest

from hub import spec_reading
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
AGENT_TASKS = "/api/v1/agent-actions/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/reading-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}
CRITERION = {
    "key": "alpha-lists",
    "requirement": "alpha",
    "given": "two things are due",
    "when": "the list is shown",
    "then": "both appear",
}


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-read", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-read",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_read-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_read-secret"}


async def make_document(app, auth_headers, run_headers, requirements=(ALPHA, BETA)):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Reading demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Reading demo",
                "requirements": list(requirements),
                "acceptance_criteria": [CRITERION],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def a_task(app, auth_headers, identifiers=("FR-1",), title="Build it"):
    created = await app.post(
        TASKS,
        json={"title": title, "requirement_ids": list(identifiers)},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.asyncio
async def test_a_task_carries_its_requirements_wording(app, auth_headers, author):
    await make_document(app, auth_headers, author)
    created = await a_task(app, auth_headers, ("FR-1", "FR-2"))

    fetched = await app.get(f"{TASKS}/{created['id']}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    links = {row["identifier"]: row for row in fetched.json()["requirement_links"]}

    assert links["FR-1"]["statement"] == ALPHA["statement"]
    assert links["FR-1"]["modal"] == "MUST"
    assert links["FR-1"]["key"] == "alpha"
    assert links["FR-2"]["statement"] == BETA["statement"]
    assert links["FR-2"]["modal"] == "SHOULD"


@pytest.mark.asyncio
async def test_the_agent_plane_gets_the_same_wording(app, auth_headers, author):
    """The agent routes reuse the operator handlers, so this is the same code — asserted rather
    than assumed, because it is the whole reason the fix is one edit."""
    await make_document(app, auth_headers, author)
    created = await a_task(app, auth_headers)

    fetched = await app.get(f"{AGENT_TASKS}/{created['id']}", headers=author)
    assert fetched.status_code == 200, fetched.text
    link = fetched.json()["requirement_links"][0]
    assert link["identifier"] == "FR-1"
    assert link["statement"] == ALPHA["statement"]


@pytest.mark.asyncio
async def test_a_retired_requirement_has_no_current_wording(app, auth_headers, author):
    """Null, not stale. A retired requirement has no current wording by definition — which is
    exactly why only its digest was ever retained."""
    await make_document(app, auth_headers, author)
    created = await a_task(app, auth_headers, ("FR-1", "FR-2"))

    # Resubmit without beta: FR-2 retires.
    resaved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Reading demo",
                "requirements": [ALPHA],
                "acceptance_criteria": [CRITERION],
            },
        },
        headers=author,
    )
    assert resaved.status_code == 200, resaved.text

    fetched = await app.get(f"{TASKS}/{created['id']}", headers=auth_headers)
    links = {row["identifier"]: row for row in fetched.json()["requirement_links"]}
    assert links["FR-1"]["statement"] == ALPHA["statement"]
    assert links["FR-2"]["state"] == "retired"
    assert links["FR-2"]["statement"] is None


@pytest.mark.asyncio
async def test_an_unreadable_workspace_still_returns_the_board(
    app, auth_headers, author, monkeypatch
):
    """A task board must not fail because a specification is unreachable.

    `resolve_project_workspace` raises when a project's directory has moved, and that is a missing
    convenience — not an outage.
    """
    await make_document(app, auth_headers, author)
    created = await a_task(app, auth_headers)

    import hub.api.v1.tasks as tasks_module

    async def _unavailable(*args, **kwargs):
        raise RuntimeError("the project directory has moved")

    monkeypatch.setattr(tasks_module.project_workspace, "resolve_project_workspace", _unavailable)

    fetched = await app.get(f"{TASKS}/{created['id']}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    link = fetched.json()["requirement_links"][0]
    assert link["identifier"] == "FR-1"
    assert link["statement"] is None


@pytest.mark.asyncio
async def test_one_document_is_read_once_for_a_whole_board(app, auth_headers, author, monkeypatch):
    """Batched by document, never by task.

    Reading per task would make a board's cost a function of how finely the work was decomposed,
    which is backwards — decomposing more should not make the board slower.
    """
    await make_document(app, auth_headers, author)
    for index in range(4):
        await a_task(app, auth_headers, ("FR-1",), title=f"Task {index}")

    import hub.spec_documents as spec_documents_module

    reads = []
    original = spec_documents_module.read_document

    def _counting(workspace, path):
        reads.append(path)
        return original(workspace, path)

    monkeypatch.setattr(spec_documents_module, "read_document", _counting)

    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 4
    assert reads.count(PATH) == 1, f"expected one read of the document, got {reads}"


# ---------------------------------------------------------------------------
# The shaping helpers
# ---------------------------------------------------------------------------


def test_criteria_are_grouped_under_the_requirement_they_demonstrate():
    payload = {
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": [
            CRITERION,
            {"key": "beta-records", "requirement": "beta", "given": "g", "when": "w", "then": "t"},
            {"key": "alpha-again", "requirement": "alpha", "given": "g", "when": "w", "then": "t"},
        ],
    }
    grouped = spec_reading.criteria_by_requirement_key(payload)
    assert [row["key"] for row in grouped["alpha"]] == ["alpha-lists", "alpha-again"]
    assert [row["key"] for row in grouped["beta"]] == ["beta-records"]


def test_a_document_with_no_payload_is_reported_rather_than_read_as_empty():
    """ "Unknown" is not "empty". A reader told a document has no requirements would draw the
    wrong conclusion from the right data."""
    requirements, diagnostics = spec_reading.requirement_view(None, [])
    assert requirements == []
    assert diagnostics == [{"problem": spec_reading.PAYLOAD_MISSING}]


def test_identifiers_sort_numerically():
    """`FR-2` before `FR-10`. Sorting as strings is how a reader loses the tenth requirement."""

    class Row:
        def __init__(self, identifier, key):
            self.identifier = identifier
            self.key = key
            self.state = "active"
            self.anchor = ""

    payload = {
        "requirements": [
            {"key": "a", "statement": "one", "modal": "MUST"},
            {"key": "b", "statement": "two", "modal": "MUST"},
            {"key": "c", "statement": "ten", "modal": "MUST"},
        ]
    }
    rows = [Row("FR-10", "c"), Row("FR-2", "b"), Row("FR-1", "a")]
    requirements, _ = spec_reading.requirement_view(payload, rows)
    assert [row["identifier"] for row in requirements] == ["FR-1", "FR-2", "FR-10"]
