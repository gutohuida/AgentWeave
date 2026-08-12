"""The step-7b self-check, promoted from a request to a refusal."""

from hub.spec_completeness import check
from hub.spec_payload import SCHEMA_VERSION, validate_payload


def _payload(**overrides):
    base = {"schema_version": SCHEMA_VERSION, "kind": "change-spec", "title": "A change"}
    base.update(overrides)
    return validate_payload(base)


def _complete(**overrides):
    base = {
        "requirements": [{"key": "alpha", "statement": "It responds in 200ms", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
    }
    base.update(overrides)
    return _payload(**base)


def _codes(payload):
    return {finding.code for finding in check(payload)}


def test_a_complete_document_has_no_findings():
    assert check(_complete()) == []


def test_a_requirement_with_no_acceptance_criterion_is_an_orphan():
    payload = _complete(acceptance_criteria=[])
    assert "requirement_without_criterion" in _codes(payload)


def test_a_requirement_with_no_task_is_an_orphan_in_the_other_direction():
    payload = _complete(tasks=[])
    assert "requirement_without_task" in _codes(payload)


def test_a_task_tracing_to_nothing_is_reported():
    payload = _complete(
        tasks=[{"key": "t1", "description": "Build it", "requirements": []}],
    )
    codes = _codes(payload)
    assert "task_without_requirement" in codes
    # And the requirement it should have covered is now an orphan too — both
    # directions reported, not one standing in for the other.
    assert "requirement_without_task" in codes


def test_empty_non_goals_are_refused():
    payload = _complete(scope={"in_scope": ["x"], "non_goals": []})
    assert "non_goals_empty" in _codes(payload)


def test_a_document_with_no_requirements_is_refused():
    assert "no_requirements" in _codes(_payload())


def test_an_unresolved_question_blocks():
    payload = _complete(open_questions=[{"question": "Which store?", "resolved": False}])
    assert "unresolved_question" in _codes(payload)


def test_a_resolved_question_does_not_block():
    payload = _complete(open_questions=[{"question": "Which store?", "resolved": True}])
    assert "unresolved_question" not in _codes(payload)


def test_a_clarification_marker_left_in_the_text_blocks():
    payload = _complete(summary="We will cache it [NEEDS CLARIFICATION: for how long?]")
    assert "clarification_marker" in _codes(payload)


def test_the_clarification_marker_is_matched_loosely():
    """Habits vary; the check should not depend on exact punctuation."""
    for text in ("[needs clarification: x]", "[Needs-Clarification: x]", "[ NEEDS_CLARIFICATION"):
        assert "clarification_marker" in _codes(_complete(problem=text)), text


def test_a_marker_inside_a_requirement_statement_is_found():
    payload = _complete(
        requirements=[
            {
                "key": "alpha",
                "statement": "Responds fast [NEEDS CLARIFICATION: how fast?]",
                "modal": "MUST",
            }
        ]
    )
    findings = {f.code: f.where for f in check(payload)}
    assert findings["clarification_marker"] == "requirements[0].statement"


def test_every_problem_is_reported_not_just_the_first():
    """Five problems reported one at a time is five round trips."""
    payload = _payload(
        requirements=[{"key": "alpha", "statement": "x", "modal": "MUST"}],
        open_questions=[{"question": "q", "resolved": False}],
    )
    codes = _codes(payload)
    assert {
        "non_goals_empty",
        "requirement_without_criterion",
        "requirement_without_task",
        "unresolved_question",
    } <= codes


def test_a_finding_says_where_to_look():
    payload = _complete(acceptance_criteria=[])
    finding = next(f for f in check(payload) if f.code == "requirement_without_criterion")
    assert finding.where == "requirements[0]"
    assert "alpha" in finding.message
