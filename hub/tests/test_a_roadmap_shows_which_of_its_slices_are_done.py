"""A roadmap shows which of its slices are done (F579), and a change document naming no slice is
asked to while a roadmap has unclaimed slices (F674) -- a gap, never a refusal."""

import re

from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
ROADMAP = "spec/changes/the-roadmap/spec.json"
FIRST = "spec/changes/the-first-slice/spec.json"
LOOSE = "spec/changes/not-a-slice/spec.json"


def _change(title, roadmap=None):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": title,
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "requirements": [{"key": "r1", "statement": "It MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "r1", "given": "a", "when": "b", "then": "c"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["r1"]}],
        "delivery": {"mode": "none"},
    }
    if roadmap:
        payload["roadmap"] = roadmap
    return payload


ROADMAP_PAYLOAD = {
    "schema_version": SCHEMA_VERSION,
    "kind": "roadmap",
    "title": "The roadmap",
    "scope": {"in_scope": ["two slices"], "non_goals": ["more"]},
    "slices": [
        {"key": "first", "title": "First", "intent": "One.", "done": "It exists."},
        {"key": "second", "title": "Second", "intent": "Two.", "done": "It exists too."},
    ],
}


async def _write(app, auth_headers, path, title, payload, kind="change-spec"):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title, "kind": kind}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    written = await app.put(
        f"{BASE}/documents/{path}/content", json={"document": payload}, headers=auth_headers
    )
    assert written.status_code == 200, written.text
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": path}, headers=auth_headers)


async def _approve(app, auth_headers, path, anyway=True):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": "approved"},
        json={"approve_anyway": anyway},
        headers=auth_headers,
    )


async def _roadmap_with_first_claimed(app, auth_headers):
    await _write(app, auth_headers, ROADMAP, "The roadmap", ROADMAP_PAYLOAD, kind="roadmap")
    assert (await _approve(app, auth_headers, ROADMAP)).status_code == 200
    await _write(
        app,
        auth_headers,
        FIRST,
        "The first slice",
        _change("The first slice", {"document": ROADMAP, "slice": "first"}),
    )
    assert (await _approve(app, auth_headers, FIRST)).status_code == 200


async def test_each_slice_says_where_it_stands(app, auth_headers, tmp_path):
    await _roadmap_with_first_claimed(app, auth_headers)
    page = (await app.get(f"{BASE}/spec", params={"path": ROADMAP}, headers=auth_headers)).json()
    html = page["content"]
    first = re.search(r'<li id="slice-first".*?</li>', html, flags=re.S).group(0)
    second = re.search(r'<li id="slice-second".*?</li>', html, flags=re.S).group(0)
    assert "approved" in first and FIRST in first
    assert "not started" in second


async def test_a_document_naming_no_slice_is_asked_to_as_a_gap(app, auth_headers, tmp_path):
    await _roadmap_with_first_claimed(app, auth_headers)
    await _write(app, auth_headers, LOOSE, "Not a slice", _change("Not a slice"))
    refused = await _approve(app, auth_headers, LOOSE, anyway=False)
    assert refused.status_code == 409, refused.text
    assert "roadmap_slice_unclaimed" in refused.text and "second" in refused.text
    assert "first" not in re.findall(r"names: ([^.]*)", refused.text)[0]
    assert (await _approve(app, auth_headers, LOOSE)).status_code == 200


async def test_no_gap_without_an_approved_roadmap(app, auth_headers, tmp_path):
    await _write(app, auth_headers, LOOSE, "Not a slice", _change("Not a slice"))
    response = await _approve(app, auth_headers, LOOSE, anyway=False)
    assert "roadmap_slice_unclaimed" not in response.text
