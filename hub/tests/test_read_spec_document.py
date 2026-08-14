"""An agent can read the specification it was told to implement.

Found by driving the product: a builder tried Bash, Read, ToolSearch, `ListMcpResourcesTool`, HTTP to
`HUB_URL` and PowerShell, then reported *"the specification document isn't reachable from my
sandboxed worktree"*. A second agent on a different runner reached the same conclusion
independently: *"the Hub exposes the requirement links but not a read-back endpoint for the rendered
spec."* Both were right — the surface had `submit` and `rename` and no read.

What it cost was not the failure but the workaround: the builder asked the author to describe the
document, and implemented from the paraphrase. Nothing then compared what was built to what was
approved, because the thing that was approved could not be read.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
READ = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/read-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {
    "key": "beta",
    "statement": "It records a completed watering",
    "modal": "SHOULD",
    "rationale": "so the streak survives a forgetful week",
}
CRITERIA = [
    {
        "key": "alpha-lists",
        "requirement": "alpha",
        "given": "two things are due",
        "when": "the list is shown",
        "then": "both appear",
    },
    {
        "key": "beta-records",
        "requirement": "beta",
        "given": "a watering happened",
        "when": "it is recorded",
        "then": "today shows as done",
    },
]


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rd", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-rd",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_rd-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rd-secret"}


async def make_document(app, auth_headers, run_headers, **extra):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Read demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Read demo",
        "summary": "A watering tracker",
        "requirements": [ALPHA, BETA],
        "acceptance_criteria": CRITERIA,
        **extra,
    }
    saved = await app.post(SUBMIT, json={"path": PATH, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


@pytest.mark.asyncio
async def test_an_agent_reads_the_document_with_its_identifiers(app, auth_headers, builder):
    await make_document(app, auth_headers, builder)

    response = await app.get(READ, params={"path": PATH}, headers=builder)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["path"] == PATH
    assert body["phase"] == "exploring"
    assert body["rigor"] == "sketch"
    assert body["summary"] == "A watering tracker"
    assert body["diagnostics"] == []

    by_identifier = {row["identifier"]: row for row in body["requirements"]}
    assert set(by_identifier) == {"FR-1", "FR-2"}
    assert by_identifier["FR-1"]["statement"] == ALPHA["statement"]
    assert by_identifier["FR-1"]["modal"] == "MUST"
    assert by_identifier["FR-1"]["key"] == "alpha"
    assert by_identifier["FR-2"]["rationale"] == BETA["rationale"]


@pytest.mark.asyncio
async def test_acceptance_criteria_are_grouped_under_their_requirement(app, auth_headers, builder):
    """They arrive as a sibling list keyed by requirement key. An agent handed two flat lists has
    to perform a join the caller already knows how to do, and will get it wrong for a document
    whose criteria interleave."""
    await make_document(app, auth_headers, builder)

    body = (await app.get(READ, params={"path": PATH}, headers=builder)).json()
    by_identifier = {row["identifier"]: row for row in body["requirements"]}

    assert [c["key"] for c in by_identifier["FR-1"]["acceptance_criteria"]] == ["alpha-lists"]
    assert [c["key"] for c in by_identifier["FR-2"]["acceptance_criteria"]] == ["beta-records"]
    assert by_identifier["FR-1"]["acceptance_criteria"][0]["then"] == "both appear"


@pytest.mark.asyncio
async def test_requirements_come_back_in_identifier_order(app, auth_headers, builder):
    """`FR-2` before `FR-10`. Sorting as strings is how a reader loses the tenth requirement."""
    many = [
        {"key": f"k{index}", "statement": f"Requirement {index}", "modal": "MUST"}
        for index in range(1, 12)
    ]
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Read demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Read demo",
                "requirements": many,
            },
        },
        headers=builder,
    )
    assert saved.status_code == 200, saved.text

    body = (await app.get(READ, params={"path": PATH}, headers=builder)).json()
    assert [row["identifier"] for row in body["requirements"]][:11] == [
        f"FR-{n}" for n in range(1, 12)
    ]


@pytest.mark.asyncio
async def test_an_unapproved_document_is_readable(app, auth_headers, builder):
    """Reading is not authoring. A refusal that depends on phase is one an agent concludes it does
    not have at all — and the phase is returned instead, so it can judge rather than guess."""
    await make_document(app, auth_headers, builder)

    body = (await app.get(READ, params={"path": PATH}, headers=builder)).json()
    assert body["phase"] == "exploring"
    assert body["requirements"], "an exploring document is still worth reading"


@pytest.mark.asyncio
async def test_include_full_adds_the_rest(app, auth_headers, builder):
    await make_document(
        app,
        auth_headers,
        builder,
        tasks=[{"key": "build", "description": "Build it", "requirements": ["alpha"]}],
    )

    lean = (await app.get(READ, params={"path": PATH}, headers=builder)).json()
    assert "tasks" not in lean

    full = (await app.get(READ, params={"path": PATH, "include": "full"}, headers=builder)).json()
    assert [task["key"] for task in full["tasks"]] == ["build"]


@pytest.mark.asyncio
async def test_a_document_with_no_payload_says_so(app, auth_headers, builder, tmp_path):
    """ "Unknown" is not "empty" — a reader told there are no requirements would draw the wrong
    conclusion from the right data."""
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Hand written"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    target = tmp_path / PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("<html><body>somebody wrote this by hand</body></html>", encoding="utf-8")

    body = (await app.get(READ, params={"path": PATH}, headers=builder)).json()
    assert body["requirements"] == []
    assert body["diagnostics"] == [{"problem": "payload_missing"}]


@pytest.mark.asyncio
async def test_an_unknown_document_is_refused_by_name(app, auth_headers, builder):
    response = await app.get(
        READ, params={"path": "spec/changes/nothing-here/spec.html"}, headers=builder
    )
    assert response.status_code == 404, response.text
    assert "nothing-here" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_path_outside_the_spec_tree_is_refused(app, auth_headers, builder):
    """The path is a query parameter precisely so it cannot become extra routing, and it is still
    validated as a specification path."""
    response = await app.get(READ, params={"path": "../../etc/passwd"}, headers=builder)
    assert response.status_code == 400, response.text


def test_the_tool_is_described_in_the_surface_the_agent_is_given():
    """A tool that is served and undescribed is one an agent concludes does not exist — which is
    exactly what happened to `submit_spec_document`, and cost a completed interview."""
    from hub.api.v1.agents import _tool_surface_lines

    described = "\n".join(_tool_surface_lines())
    assert "read_spec_document" in described
    # And the reason to reach for it, not merely the name: the document is not in the agent's
    # working copy, which is the fact that makes the tool necessary rather than convenient.
    assert "working" in described.lower()


@pytest.mark.asyncio
async def test_the_open_document_context_names_the_tool(app, auth_headers, builder, tmp_path):
    """Named at the moment it applies, not only in a tool list further up the prompt.

    Being served but undiscovered at the point of use is the same failure with a different
    mechanism — the builder that hit this had the document's path in its context and concluded
    there was no way to open it.
    """
    from hub.api.v1.agents import _render_hub_agent_context

    await make_document(app, auth_headers, builder)

    async with async_session_factory() as session:
        rendered = await _render_hub_agent_context(
            agent="builder",
            project_id="proj-test",
            db=session,
            session_data=None,
            agent_row=None,
            spec_document=PATH,
        )
    assert "read_spec_document" in str(rendered), str(rendered)[-2000:]
