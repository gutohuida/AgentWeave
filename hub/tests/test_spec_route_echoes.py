"""F657: small echoes and asymmetries in the spec and evidence routes.

- An unknown rigor is a malformed value (422), not a conflict (409).
- An approval report for a no-flow document with no tasks does not say "the tasks are on the
  board".
(The decision response's footprint: `test_evidence_footprint_root.py`.)
"""

from types import SimpleNamespace

import pytest

from hub.api.v1.spec import _approval_flow
from hub.db.engine import async_session_factory

BASE = "/api/v1/projects/proj-test/project"


@pytest.mark.asyncio
async def test_an_unknown_rigor_is_a_malformed_value(app, auth_headers):
    created = await app.post(f"{BASE}/documents", json={"title": "R"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    path = created.json()["path"]
    resp = await app.post(
        f"{BASE}/documents/{path}/rigor", json={"rigor": "bogus"}, headers=auth_headers
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_rigor"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tasks, expected, absent",
    [
        ([], "declares no tasks", "on the board"),
        ([{"key": "t1", "title": "Do it"}], "on the board", "declares no tasks"),
    ],
)
async def test_a_no_flow_approval_says_whether_there_are_tasks(app, tasks, expected, absent):
    document = SimpleNamespace(id="spdoc-f657", kind="change-spec", path="spec/changes/x/spec.json")
    payload = {"delivery": {"mode": "none"}, "tasks": tasks}
    async with async_session_factory() as session:
        entry, job = await _approval_flow(session, "proj-test", document, payload, None)
    assert job is None
    text = " ".join(entry["messages"])
    assert expected in text and absent not in text
