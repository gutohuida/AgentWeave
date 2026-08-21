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


def _requirements(*keys):
    return [{"key": key, "statement": f"Requirement {key}", "modal": "MUST"} for key in keys]


def _criteria(*keys):
    return [
        {"key": f"c-{key}", "requirement": key, "given": "g", "when": "w", "then": "t"}
        for key in keys
    ]


def test_a_task_naming_four_requirements_is_too_coarse():
    keys = ["a", "b", "c", "d"]
    payload = _complete(
        requirements=_requirements(*keys),
        acceptance_criteria=_criteria(*keys),
        tasks=[{"key": "t1", "description": "Build it", "requirements": keys}],
    )
    finding = next(f for f in check(payload) if f.code == "task_too_coarse")
    assert "t1" in finding.message
    assert "4" in finding.message
    assert "3" in finding.message


def test_a_task_naming_exactly_three_requirements_is_not_refused():
    keys = ["a", "b", "c"]
    payload = _complete(
        requirements=_requirements(*keys),
        acceptance_criteria=_criteria(*keys),
        tasks=[{"key": "t1", "description": "Build it", "requirements": keys}],
    )
    assert "task_too_coarse" not in _codes(payload)


def test_the_same_document_split_into_two_and_two_proposes_cleanly():
    keys = ["a", "b", "c", "d"]
    payload = _complete(
        requirements=_requirements(*keys),
        acceptance_criteria=_criteria(*keys),
        tasks=[
            {"key": "t1", "description": "Build the first half", "requirements": ["a", "b"]},
            {"key": "t2", "description": "Build the second half", "requirements": ["c", "d"]},
        ],
    )
    assert check(payload) == []


# --- task-dependencies section 2: unresolved depends_on, cycles, unapproved imports ---


def test_an_unresolved_depends_on_key_is_reported():
    payload = _complete(
        tasks=[
            {
                "key": "t1",
                "description": "Build it",
                "requirements": ["alpha"],
                "depends_on": ["ghost"],
            }
        ]
    )
    finding = next(f for f in check(payload) if f.code == "depends_on_unresolved")
    assert finding.where == "tasks[0].depends_on[0]"
    assert "ghost" in finding.message


def test_a_depends_on_key_naming_a_declared_sibling_is_not_reported():
    keys = ["a", "b"]
    payload = _complete(
        requirements=_requirements(*keys),
        acceptance_criteria=_criteria(*keys),
        tasks=[
            {"key": "t1", "description": "First", "requirements": ["a"]},
            {"key": "t2", "description": "Second", "requirements": ["b"], "depends_on": ["t1"]},
        ],
    )
    assert "depends_on_unresolved" not in _codes(payload)


def test_a_depends_on_key_naming_an_imported_entrys_key_is_not_reported():
    payload = _complete(
        tasks=[
            {"key": "imported-1", "from": {"document": "spec/other.md", "key": "ot1"}},
            {
                "key": "t1",
                "description": "Build it",
                "requirements": ["alpha"],
                "depends_on": ["imported-1"],
            },
        ]
    )
    assert "depends_on_unresolved" not in _codes(payload)


def test_a_cycle_among_local_tasks_is_reported():
    payload = _complete(
        requirements=_requirements("a", "b"),
        acceptance_criteria=_criteria("a", "b"),
        tasks=[
            {"key": "t1", "description": "First", "requirements": ["a"], "depends_on": ["t2"]},
            {"key": "t2", "description": "Second", "requirements": ["b"], "depends_on": ["t1"]},
        ],
    )
    finding = next(f for f in check(payload) if f.code == "dependency_cycle")
    assert "t1" in finding.message
    assert "t2" in finding.message
    assert "within this document only" in finding.message


def test_a_local_task_depending_on_an_imported_entry_is_not_a_cycle():
    """An imported entry is a leaf by construction — it cannot be part of a within-document cycle."""
    payload = _complete(
        tasks=[
            {"key": "imported-1", "from": {"document": "spec/other.md", "key": "ot1"}},
            {
                "key": "t1",
                "description": "Build it",
                "requirements": ["alpha"],
                "depends_on": ["imported-1"],
            },
        ]
    )
    assert "dependency_cycle" not in _codes(payload)


def test_an_import_naming_an_unapproved_document_is_reported():
    payload = _complete(tasks=[{"key": "t1", "from": {"document": "spec/other.md", "key": "ot1"}}])
    finding = next(f for f in check(payload) if f.code == "import_not_approved")
    assert "spec/other.md" in finding.message
    assert "ot1" in finding.message


def test_an_import_naming_an_approved_document_is_not_reported():
    payload = _complete(tasks=[{"key": "t1", "from": {"document": "spec/other.md", "key": "ot1"}}])
    codes = {f.code for f in check(payload, approved_document_paths={"spec/other.md"})}
    assert "import_not_approved" not in codes


def test_a_document_with_all_three_dependency_problems_returns_all_three_findings():
    """Design D7: these are reported in `blocking`, never a submission refusal — all three survive
    together in one `check()` call, the same way five unrelated problems already do above."""
    payload = _complete(
        requirements=_requirements("a", "b"),
        acceptance_criteria=_criteria("a", "b"),
        tasks=[
            {
                "key": "t1",
                "description": "First",
                "requirements": ["a"],
                "depends_on": ["t2", "ghost"],
            },
            {"key": "t2", "description": "Second", "requirements": ["b"], "depends_on": ["t1"]},
            {"key": "t3", "from": {"document": "spec/other.md", "key": "ot1"}},
        ],
    )
    codes = _codes(payload)
    assert {"depends_on_unresolved", "dependency_cycle", "import_not_approved"} <= codes
