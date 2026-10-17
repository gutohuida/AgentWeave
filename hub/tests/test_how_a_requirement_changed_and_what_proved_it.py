"""How a requirement changed (slice requirement-story, migration 0131).

`spec_requirement_revisions` recorded that a requirement's meaning moved, as digests, and nothing
read it. Each revision now records the wording it introduced, and the requirement's detail route
answers its revisions, its current wording and document, and every drift row.
"""

from hub.spec_payload import SCHEMA_VERSION

from .test_task_integration import (
    ALPHA,
    BASE,
    PATH,
    builder,  # noqa: F401 - fixture
    make_document,
    make_repo,
)

REWORDED = "It lists what is due today and tomorrow"


def document(requirements):
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Integration demo",
        "requirements": requirements,
    }


async def detail(app, auth_headers):
    response = await app.get(f"{BASE}/spec/requirements/FR-1?document={PATH}", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_each_revision_records_its_wording_and_who_changed_it(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    reworded = await app.put(
        f"{BASE}/documents/{PATH}/content",
        json={"document": document([{**ALPHA, "statement": REWORDED}])},
        headers=auth_headers,
    )
    assert reworded.status_code == 200, reworded.text

    body = await detail(app, auth_headers)
    assert body["requirement"]["statement"] == REWORDED
    assert body["requirement"]["document"] == {"path": PATH, "title": "Integration demo"}
    assert [
        (r["classification"], r["actor_kind"], r["actor"], r["statement"])
        for r in body["revisions"]
    ] == [
        ("created", "agent", "builder", ALPHA["statement"]),
        ("reworded", "operator", "operator", REWORDED),
    ]
    assert body["revisions"][1]["previous_digest"] == body["revisions"][0]["digest"]
    assert body["drift"] == []


async def test_a_retirement_records_no_wording(app, auth_headers, builder, tmp_path):  # noqa: F811
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    other = {"key": "beta", "statement": "It lists overdue items", "modal": "MUST"}
    retired = await app.put(
        f"{BASE}/documents/{PATH}/content",
        json={"document": document([other])},
        headers=auth_headers,
    )
    assert retired.status_code == 200, retired.text

    body = await detail(app, auth_headers)
    assert body["requirement"]["state"] == "retired"
    assert [(r["classification"], r["statement"]) for r in body["revisions"]] == [
        ("created", ALPHA["statement"]),
        ("retired", None),
    ]


async def test_a_folded_requirement_says_which_change_it_came_from(app, auth_headers, tmp_path):
    """A capability's requirement written by a fold names the change and when (the roadmap's
    "folded from change X on date"); one the capability was created with names none."""
    from .test_a_finished_change_is_folded_into_its_capability import (
        CAP,
        CHANGE,
        _approved_change,
        _create_capability,
        _finish_tasks,
    )

    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    await _finish_tasks()
    folded = await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP}, headers=auth_headers
    )
    assert folded.status_code == 200, folded.text

    listed = await app.get(f"{BASE}/spec/requirements?document={CAP}", headers=auth_headers)
    by_key = {row["key"]: row["identifier"] for row in listed.json()["requirements"]}
    glow = next(identifier for key, identifier in by_key.items() if key.endswith("glow"))

    response = await app.get(
        f"{BASE}/spec/requirements/{glow}?document={CAP}", headers=auth_headers
    )
    [created] = response.json()["revisions"]
    assert created["folded_from"]["path"] == CHANGE
    assert created["folded_from"]["title"] == "Widgets glow"
    assert created["folded_from"]["at"]

    own = await app.get(
        f"{BASE}/spec/requirements/{by_key['widgets-exist']}?document={CAP}", headers=auth_headers
    )
    assert [r["folded_from"] for r in own.json()["revisions"]] == [None]
