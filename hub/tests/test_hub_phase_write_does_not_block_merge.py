"""F515: the Hub's own phase write must not block the merges of the document it wrote.

Approving a document re-renders its file so the visible status matches the phase
(`spec_service.rerender_phase`). Where the operator has committed the document -- the trial's own
practice -- that write leaves a tracked file modified, and every task approved afterwards was
skipped with "the project's checkout has uncommitted changes to tracked files", although the only
change was the Hub's. Found on the trial Hub `:8010`, F510 slice, 2026-10-06.
"""

import pytest

from hub import task_integration
from hub.spec_payload import SCHEMA_VERSION

from .test_task_integration import (
    AGENT_BRANCH,
    BASE,
    PATH,
    accept_evidence,
    approve,
    commit_on_branch,
    git,
    linked_task,
    make_repo,
    set_main_branch,
)
from .test_task_integration_retry import builder  # noqa: F401 - fixture

DOC = f"{BASE}/documents"
SUBMIT = "/api/v1/agent-actions/spec/documents"
# Complete enough to propose: the integration fixture's own document is deliberately thin.
PAYLOAD = {
    "schema_version": SCHEMA_VERSION,
    "kind": "change-spec",
    "title": "Integration demo",
    "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
    "requirements": [{"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}],
    "acceptance_criteria": [
        {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
    ],
    "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
    "delivery": {"mode": "none"},
}


async def _document(app, auth_headers, run_headers):
    created = await app.post(
        DOC, json={"path": PATH, "title": "Integration demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(SUBMIT, json={"path": PATH, "document": PAYLOAD}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def _approve_document(app, auth_headers):
    for route in (f"{DOC}/close-exploration", f"{DOC}/propose"):
        response = await app.post(route, params={"path": PATH}, headers=auth_headers)
        assert response.status_code == 200, response.text
        assert not response.json().get("blocking"), response.text
    response = await app.post(
        f"{DOC}/phase",
        params={"path": PATH, "to": "approved"},
        json={"approve_anyway": True},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _committed_document_then_approved(app, auth_headers, builder, root):  # noqa: F811
    make_repo(root)
    await _document(app, auth_headers, builder)
    await set_main_branch("main")
    git(root, "add", PATH)
    git(root, "commit", "-q", "-m", "the operator commits the draft")

    commit_on_branch(root, AGENT_BRANCH, "feature.py", "x\n")
    await accept_evidence(app, auth_headers, builder)
    git(root, "checkout", "-q", "main")

    await _approve_document(app, auth_headers)
    # The precondition this finding is about: the Hub's write is a tracked modification.
    assert git(
        root, "status", "--porcelain", "--untracked-files=no"
    ).stdout.strip(), (
        "the phase write did not dirty the committed document; the test no longer reproduces F515"
    )


async def _outcomes(app, auth_headers, task):
    read = await app.get(
        f"/api/v1/projects/proj-test/tasks/{task}/integrations", headers=auth_headers
    )
    return [(row["outcome"], row["reason"]) for row in read.json()["integrations"]]


@pytest.mark.asyncio
async def test_the_hubs_own_phase_write_does_not_block_a_merge(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await _committed_document_then_approved(app, auth_headers, builder, tmp_path)

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    assert [outcome for outcome, _ in await _outcomes(app, auth_headers, task)] == ["merged"]
    assert (tmp_path / "feature.py").exists()


@pytest.mark.asyncio
async def test_an_operator_edit_to_the_same_document_still_blocks(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """Only the Hub's own bytes are exempt. The operator's edit to that file is their work."""
    await _committed_document_then_approved(app, auth_headers, builder, tmp_path)
    doc = tmp_path / PATH
    doc.write_text(
        doc.read_text(encoding="utf-8") + "<!-- the operator's note -->\n", encoding="utf-8"
    )

    task = await linked_task(app, auth_headers)
    approved = await approve(app, auth_headers, task)
    assert approved.status_code == 200, approved.text

    assert await _outcomes(app, auth_headers, task) == [
        ("skipped", task_integration.CHECKOUT_DIRTY)
    ]
