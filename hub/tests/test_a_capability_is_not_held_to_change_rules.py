"""F534: a merge into a capability answered with change-spec completeness findings.

A capability states what the system does; the changes folded into it carry the tasks and the
non-goals. `non_goals_empty` and `requirement_without_task` were reported for every capability
merge (77 of them for `spec-document-authority`), so a caller reading `blocking` saw a document
wrong in 77 ways that is wrong in none. The rules a capability can fail are still reported.
"""

import pytest

from hub.spec_completeness import check
from hub.spec_payload import SCHEMA_VERSION, validate_payload

BASE = "/api/v1/projects/proj-test/project"
CAP = "spec/capabilities/widgets/spec.html"


def _capability(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability",
        "title": "Widgets",
        "requirements": [{"key": "exists", "statement": "A widget MUST exist.", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "exists-c", "requirement": "exists", "given": "g", "when": "w", "then": "t"}
        ],
    }
    payload.update(overrides)
    return payload


def test_a_capability_is_not_asked_for_tasks_or_non_goals():
    codes = {finding.code for finding in check(validate_payload(_capability()))}
    assert "requirement_without_task" not in codes
    assert "non_goals_empty" not in codes


def test_a_capability_requirement_without_a_criterion_is_still_reported():
    payload = validate_payload(_capability(acceptance_criteria=[]))
    assert "requirement_without_criterion" in {finding.code for finding in check(payload)}


def test_a_change_is_still_asked_for_both():
    payload = validate_payload(
        _capability(kind="change-spec", delivery={"mode": "none"}, scope={"in_scope": ["x"]})
    )
    codes = {finding.code for finding in check(payload)}
    assert {"requirement_without_task", "non_goals_empty"} <= codes


@pytest.mark.asyncio
async def test_a_capability_merge_answers_with_nothing_blocking(app, auth_headers, tmp_path):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": CAP, "title": "Widgets", "kind": "capability"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text

    merged = await app.post(
        f"{BASE}/documents/{CAP}/merge",
        json={"payload": _capability(), "from_changes": []},
        headers=auth_headers,
    )

    assert merged.status_code == 200, merged.text
    assert merged.json()["blocking"] == []
