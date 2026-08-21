"""The payload contract: shape, referential integrity, and forward compatibility.

The distinction these tests protect is shape versus completeness. Validation
here answers "is this well formed?" — not "is this finished?" A document being
written is incomplete by definition, and refusing to store it would make the
explore phase impossible. Completeness is the transition's question.
"""

import pytest

from hub.spec_payload import (
    SCHEMA_VERSION,
    PayloadError,
    embed_payload,
    extract_payload,
    payload_to_dict,
    validate_payload,
)


def minimal(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "A change",
    }
    payload.update(overrides)
    return payload


def test_a_minimal_payload_is_valid_because_a_draft_is_not_a_defect():
    """Only a version, a kind and a title. Everything else accumulates while the
    document is being written."""
    payload = validate_payload(minimal())
    assert payload.title == "A change"
    assert payload.requirements == []
    assert payload.scope.non_goals == []


def test_a_missing_schema_version_is_named_directly():
    with pytest.raises(PayloadError) as exc:
        validate_payload({"kind": "change-spec", "title": "x"})
    assert exc.value.field == "schema_version"
    assert "schema_version" in str(exc.value)


def test_an_unsupported_schema_version_says_what_this_hub_speaks():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(schema_version=99))
    assert exc.value.field == "schema_version"
    assert str(SCHEMA_VERSION) in str(exc.value)


def test_a_non_object_payload_is_refused():
    with pytest.raises(PayloadError):
        validate_payload(["not", "an", "object"])


def test_an_unknown_kind_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(kind="invention"))
    assert exc.value.field == "kind"


def test_an_empty_title_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(title="   "))
    assert exc.value.field == "title"


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------


def _requirement(key="search-latency", modal="MUST", **kw):
    base = {"key": key, "statement": "A search returns within 200ms", "modal": modal}
    base.update(kw)
    return base


def test_a_requirement_without_a_modal_obligation_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(requirements=[_requirement(modal="please")]))
    assert exc.value.field == "requirements[0].modal"


def test_a_malformed_key_is_refused_with_its_position():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(requirements=[_requirement(key="Not A Key")]))
    assert exc.value.field == "requirements[0].key"


def test_duplicate_requirement_keys_are_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(requirements=[_requirement(), _requirement()]))
    assert exc.value.field == "requirements"
    assert "search-latency" in str(exc.value)


def test_an_unknown_party_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(minimal(requirements=[_requirement(party="bystander")]))
    assert exc.value.field == "requirements[0].party"


# ---------------------------------------------------------------------------
# Referential integrity — malformed, not merely incomplete
# ---------------------------------------------------------------------------


def test_a_criterion_naming_an_undefined_requirement_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(
            minimal(
                requirements=[_requirement()],
                acceptance_criteria=[
                    {
                        "key": "c1",
                        "requirement": "does-not-exist",
                        "given": "g",
                        "when": "w",
                        "then": "t",
                    }
                ],
            )
        )
    assert exc.value.field == "acceptance_criteria[0].requirement"


def test_a_task_naming_an_undefined_requirement_is_refused_with_its_position():
    with pytest.raises(PayloadError) as exc:
        validate_payload(
            minimal(
                requirements=[_requirement()],
                tasks=[
                    {
                        "key": "t1",
                        "description": "do the thing",
                        "requirements": ["search-latency", "phantom"],
                    }
                ],
            )
        )
    assert exc.value.field == "tasks[0].requirements[1]"


def test_a_task_with_no_requirements_is_well_formed_but_incomplete():
    """An empty list is shape-valid. It is the transition to `proposed` that
    refuses a task tracing to nothing — an orphan check, not a type check."""
    payload = validate_payload(
        minimal(
            requirements=[_requirement()],
            tasks=[{"key": "t1", "description": "do the thing", "requirements": []}],
        )
    )
    assert payload.tasks[0].requirements == []


# ---------------------------------------------------------------------------
# Dependencies and imports
# ---------------------------------------------------------------------------


def test_a_local_depends_on_names_a_sibling_key():
    payload = validate_payload(
        minimal(
            requirements=[_requirement()],
            tasks=[
                {"key": "build", "description": "build it", "requirements": ["search-latency"]},
                {
                    "key": "ship",
                    "description": "ship it",
                    "requirements": ["search-latency"],
                    "depends_on": ["build"],
                },
            ],
        )
    )
    assert payload.tasks[1].depends_on == ["build"]


def test_an_imported_entry_needs_no_description_or_requirements():
    """The whole point of `from`: it names existing work rather than declaring
    new work, so nothing else on the entry is required."""
    payload = validate_payload(
        minimal(
            tasks=[
                {
                    "key": "adopt-corpus",
                    "from": {"document": "spec/areas/interface.html", "key": "adopt-corpus"},
                },
            ],
        )
    )
    assert payload.tasks[0].description == ""
    assert payload.tasks[0].requirements == []
    assert payload.tasks[0].from_.document == "spec/areas/interface.html"
    assert payload.tasks[0].from_.key == "adopt-corpus"


def test_a_round_trip_with_local_dependencies_and_an_import_loses_nothing():
    """1.5: a payload with both an ordinary depends_on and an imported entry
    survives render -> extract_payload -> validate unchanged — the same
    round-trip discipline as every other field, extended to cover the two new
    ones together in one realistic, cross-document payload."""
    original = minimal(
        requirements=[_requirement()],
        tasks=[
            {
                "key": "adopt-corpus",
                "from": {"document": "spec/areas/interface.html", "key": "adopt-corpus"},
            },
            {
                "key": "render-map",
                "description": "render the arrangement",
                "requirements": ["search-latency"],
                "depends_on": ["adopt-corpus"],
            },
        ],
    )
    stored = payload_to_dict(validate_payload(original))

    document = f"<html><body>rendered</body>{embed_payload(stored)}</html>"
    recovered = extract_payload(document)

    assert recovered == stored

    # And the recovered dict round-trips through validation again unchanged —
    # not just JSON-equal, but re-acceptable as a payload.
    revalidated = payload_to_dict(validate_payload(recovered))
    assert revalidated == stored

    imported, dependent = stored["tasks"]
    assert imported["from"] == {"document": "spec/areas/interface.html", "key": "adopt-corpus"}
    assert imported["description"] == ""
    assert dependent["depends_on"] == ["adopt-corpus"]


def test_a_named_reviewer_survives_round_trip():
    """1.8: a task naming a reviewer survives render -> extract_payload ->
    validate unchanged, the same discipline 1.5 already applies to
    depends_on and from."""
    original = minimal(
        requirements=[_requirement()],
        tasks=[
            {
                "key": "ship",
                "description": "ship it",
                "requirements": ["search-latency"],
                "reviewer": "codex-1",
            },
        ],
    )
    stored = payload_to_dict(validate_payload(original))
    assert stored["tasks"][0]["reviewer"] == "codex-1"

    document = f"<html><body>rendered</body>{embed_payload(stored)}</html>"
    recovered = extract_payload(document)
    assert recovered == stored

    revalidated = payload_to_dict(validate_payload(recovered))
    assert revalidated == stored


def test_naming_no_reviewer_validates_and_materialises_as_before():
    """1.6: a document naming no reviewer must validate and materialise
    exactly as it did before this field existed — reviewer defaults to None
    and every pre-existing task's shape is otherwise untouched."""
    payload = validate_payload(
        minimal(
            requirements=[_requirement()],
            tasks=[
                {"key": "build", "description": "build it", "requirements": ["search-latency"]},
            ],
        )
    )
    assert payload.tasks[0].reviewer is None


# ---------------------------------------------------------------------------
# Forward compatibility
# ---------------------------------------------------------------------------


def test_an_unrecognised_top_level_field_is_preserved():
    """This is what lets a later change add gate fields to documents authored
    before gates existed, without migrating any of them."""
    payload = validate_payload(minimal(gate_policy={"rigor": "contract"}))
    stored = payload_to_dict(payload)
    assert stored["gate_policy"] == {"rigor": "contract"}


def test_an_unrecognised_nested_field_is_preserved():
    payload = validate_payload(
        minimal(requirements=[_requirement(rigor="gate", evidence_refs=["t-1"])])
    )
    stored = payload_to_dict(payload)
    assert stored["requirements"][0]["rigor"] == "gate"
    assert stored["requirements"][0]["evidence_refs"] == ["t-1"]


def test_a_round_trip_through_a_document_loses_nothing():
    original = minimal(
        requirements=[_requirement()],
        future_section={"nested": {"deep": [1, 2, 3]}},
    )
    stored = payload_to_dict(validate_payload(original))

    document = f"<html><body>rendered</body>{embed_payload(stored)}</html>"
    recovered = extract_payload(document)

    assert recovered == stored
    assert recovered["future_section"] == {"nested": {"deep": [1, 2, 3]}}


# ---------------------------------------------------------------------------
# The embedded payload block
# ---------------------------------------------------------------------------


def test_content_cannot_close_the_payload_element_early():
    """Escaping `<` is what stops a title containing `</script>` from ending the
    block and spilling the rest of the payload into the document body."""
    stored = payload_to_dict(validate_payload(minimal(title="</script><img src=x>")))
    block = embed_payload(stored)

    assert block.endswith("</script>")
    assert block.count("</script>") == 1
    assert extract_payload(f"<html>{block}</html>")["title"] == "</script><img src=x>"


def test_the_payload_block_is_not_an_executable_script_type():
    block = embed_payload(payload_to_dict(validate_payload(minimal())))
    assert 'type="application/agentweave-spec+json"' in block


def test_a_document_with_no_payload_returns_none_rather_than_guessing():
    """Hand-written, or written before the payload block existed. What that
    means is the caller's decision."""
    assert extract_payload("<html><body>written by hand</body></html>") is None


def test_an_unparseable_payload_block_returns_none():
    document = '<html><script id="aw-spec-payload">{not json</script></html>'
    assert extract_payload(document) is None
