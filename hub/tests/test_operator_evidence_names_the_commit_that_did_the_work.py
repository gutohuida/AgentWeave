"""F529: operator evidence can name the commit that did the work, beside a locator naming a file.

F71 footprints operator evidence at a commit its `locator` names. But a locator is one string: the
close-out names the test file that demonstrates the requirement, so it cannot name the commit too,
and every row was pinned to the HEAD it was recorded at (`0300f0f`, a one-line script commit) rather
than the commits that built each change. Drift and "what does this evidence describe" then read the
wrong tree. `commit` on the record names it explicitly, through F71's own verification.
"""

import pytest

from .test_evidence_footprint_root import (
    builder,  # noqa: F401 - the fixture, used by name
    commit_in,
    head_of,
    init_repo,
    make_document,
    only_footprint,
)

OPERATOR_EVIDENCE = "/api/v1/projects/proj-test/project/spec/evidence"


@pytest.mark.asyncio
async def test_a_named_commit_is_footprinted_beside_a_file_locator(
    app, auth_headers, builder, bind_project_workspace, tmp_path  # noqa: F811
):
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    work = commit_in(repo, "cart.py", "import math\n")
    commit_in(repo, "notes.md", "an unrelated later commit\n")
    assert head_of(repo) != work

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        OPERATOR_EVIDENCE,
        json={
            "identifier": "FR-1",
            "summary": "the cart test passes",
            "locator": "cart.py",
            "commit": work,
        },
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text

    footprint = await only_footprint()
    assert footprint.commit_sha == work
    assert "cart.py" in (footprint.entries or {})
    assert recorded.json()["locator"] == "cart.py"


@pytest.mark.asyncio
async def test_without_a_commit_the_checkout_is_still_the_answer(
    app, auth_headers, builder, bind_project_workspace, tmp_path  # noqa: F811
):
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    commit_in(repo, "cart.py", "import math\n")

    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        OPERATOR_EVIDENCE,
        json={"identifier": "FR-1", "summary": "s", "locator": "cart.py"},
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert (await only_footprint()).commit_sha == head_of(repo)


@pytest.mark.asyncio
async def test_a_commit_the_repository_does_not_have_is_refused(
    app, auth_headers, builder, bind_project_workspace, tmp_path  # noqa: F811
):
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)

    await make_document(app, auth_headers, builder)
    refused = await app.post(
        OPERATOR_EVIDENCE,
        json={"identifier": "FR-1", "summary": "s", "locator": "cart.py", "commit": "deadbeef"},
        headers=auth_headers,
    )
    assert refused.status_code == 409, refused.text
    assert "deadbeef" in refused.text


@pytest.mark.asyncio
async def test_a_commit_that_is_not_a_sha_is_refused_at_the_door(
    app, auth_headers, builder, bind_project_workspace, tmp_path  # noqa: F811
):
    repo = init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)

    await make_document(app, auth_headers, builder)
    refused = await app.post(
        OPERATOR_EVIDENCE,
        json={"identifier": "FR-1", "summary": "s", "commit": "HEAD~3"},
        headers=auth_headers,
    )
    assert refused.status_code == 422, refused.text
