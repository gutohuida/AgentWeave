"""Agents read and edit chapters through their tools (`the-thread-reads-as-chapters-the-manager-
writes`, FR-3, FR-7, FR-8). The job is never turned on here: the tools work whether it is on or off.
"""

import pytest

from hub import chapters, project_thread
from hub.db.engine import async_session_factory

from .test_chapters_job import P, draft
from .test_chapters_store import doc, seed
from .test_vault import _run_headers

AA = "/api/v1/agent-actions"


async def _keys():
    async with async_session_factory() as session:
        return [k.key for k in (await project_thread.build(session, P)).top]


def _body(keys, **kw):
    chapter = draft("a", keys, **kw).model_dump()
    return {"chapters": [chapter], "reason": "organised by the user's ask"}


@pytest.mark.asyncio
async def test_an_agent_with_the_job_off_creates_a_chapter_and_a_bad_edit_is_refused(
    app, auth_headers
):
    await seed(doc(1, 0))
    headers = await _run_headers("run-chapters-1", "Writer")
    keys = await _keys()

    saved = await app.post(f"{AA}/chapters", json=_body(keys), headers=headers)
    assert saved.status_code == 200, saved.text
    version = saved.json()["version"]
    assert version["author"] == "Writer" and version["version"] == 1

    shown = await app.get(f"/api/v1/projects/{P}/thread", headers=auth_headers)
    assert shown.status_code == 200, shown.text
    assert "Chapter a" in shown.text and "Writer" in shown.text

    bad = _body(keys, cites=["task-nope"])
    refused = await app.post(f"{AA}/chapters", json=bad, headers=headers)
    assert refused.status_code == 422, refused.text
    assert "task-nope" in refused.text
    refused = await app.post(
        f"{AA}/chapters", json=_body(keys, cites=["commit:" + "0" * 40]), headers=headers
    )
    assert refused.status_code == 422 and "commit:" + "0" * 40 in refused.text

    read = (await app.get(f"{AA}/chapters", headers=headers)).json()
    assert [v["version"] for v in read["versions"]] == [1]
    assert read["chapters"][0]["id"] == "a"


@pytest.mark.asyncio
async def test_versions_by_each_author_are_readable_and_reach_the_next_firing(app):
    await seed(doc(1, 0))
    headers = await _run_headers("run-chapters-2", "Writer")
    keys = await _keys()
    async with async_session_factory() as session:
        await chapters.save(
            session,
            P,
            chapters=[draft("a", keys).model_dump()],
            surface=keys,
            author="manager",
            reason="automatic reason",
            asked_for=False,
        )
    saved = await app.post(
        f"{AA}/chapters",
        json={"chapters": [draft("a", keys, title="Renamed").model_dump()], "reason": "agent why"},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text

    read = (await app.get(f"{AA}/chapters", headers=headers)).json()
    assert [(v["author"], v["reason"]) for v in read["versions"]] == [
        ("Writer", "agent why"),
        ("manager", "automatic reason"),
    ]
    assert all(v["at"] for v in read["versions"])
    assert read["chapters"][0]["title"] == "Renamed"


def test_the_tools_are_on_every_runners_surface():
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    for tool in ("read_chapters", "save_chapters"):
        assert tool in mcp_server._CALLABLE_TOOLS and tool in HUB_MCP_TOOLS
        assert any(op.tool == tool for op in _operations())
