"""F730 echoes: two operator spec routes that answered something other than what was asked.

`GET /spec/evidence?review_state=` ignored the filter (the agent route applied it), and a phase that
does not exist answered 409, a conflict with the document, where an unknown rigor answers 422.
"""

from .test_task_integration import (  # noqa: F401 - builder is a fixture
    BASE,
    PATH,
    builder,
    make_document,
    make_repo,
)


async def test_the_operator_lists_evidence_by_review_state(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    recorded = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "document": PATH, "summary": "seen working"},
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["review_state"] == "accepted"

    async def listed(**params):
        response = await app.get(f"{BASE}/spec/evidence", params=params, headers=auth_headers)
        return response

    rejected = await listed(review_state="rejected")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["evidence"] == []
    accepted = await listed(review_state="accepted", identifier="FR-1", document=PATH)
    assert [e["id"] for e in accepted.json()["evidence"]] == [recorded.json()["id"]]

    unknown = await listed(review_state="approved")
    assert unknown.status_code == 422, unknown.text
    assert unknown.json()["detail"]["code"] == "unknown_review_state"


async def test_a_phase_that_does_not_exist_is_a_malformed_request(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)

    response = await app.post(
        f"{BASE}/documents/phase", params={"path": PATH, "to": "nonsense"}, headers=auth_headers
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "unknown_phase"
    assert "exploring, proposed, approved, archived" in detail["message"]
