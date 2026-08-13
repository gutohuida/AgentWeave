"""Identifier minting and document rendering.

The properties under test are the ones that used to be a self-check the model
ran on itself and reported: no dangling anchor, no duplicate identifier, no
external resource. They are now structural — the renderer emits the anchor and
the link from the same minted value, so the failure has nowhere to occur.
"""

import re

from hub.spec_identity import (
    IDENTITY_FIELD,
    identity_block,
    mint,
    read_identity,
    read_retired,
    retained,
)
from hub.spec_payload import SCHEMA_VERSION, extract_payload, payload_to_dict, validate_payload
from hub.spec_render import render_document


def _payload(**overrides):
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "A change",
    }
    base.update(overrides)
    return validate_payload(base)


def _requirement(key, statement="It does the thing", modal="MUST", **kw):
    return {"key": key, "statement": statement, "modal": modal, **kw}


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------


def test_identifiers_are_minted_in_order_for_new_keys():
    mapping, high_water = mint(["alpha", "beta"])
    assert mapping == {"alpha": "FR-1", "beta": "FR-2"}
    assert high_water == 2


def test_an_existing_key_keeps_its_identifier_when_reworded():
    previous, high_water = mint(["alpha", "beta"])
    mapping, _ = mint(["alpha", "beta"], previous, high_water)
    assert mapping["alpha"] == "FR-1"


def test_inserting_a_requirement_does_not_renumber_the_others():
    """The defect that position-based correlation would have shipped: a new
    requirement at the top would have taken FR-1 and moved everything down,
    silently re-targeting every task and evidence link pointing at them."""
    previous, high_water = mint(["alpha", "beta"])

    mapping, _ = mint(["inserted", "alpha", "beta"], previous, high_water)

    assert mapping["alpha"] == "FR-1"
    assert mapping["beta"] == "FR-2"
    assert mapping["inserted"] == "FR-3"


def test_reordering_requirements_preserves_identifiers():
    previous, high_water = mint(["alpha", "beta", "gamma"])
    mapping, _ = mint(["gamma", "alpha", "beta"], previous, high_water)
    assert mapping == previous


def test_a_removed_identifier_is_never_reissued():
    previous, high_water = mint(["alpha", "beta"])
    # beta is dropped; a new requirement arrives.
    mapping, new_high_water = mint(["alpha", "later"], previous, high_water)

    assert mapping["later"] == "FR-3"
    assert "FR-2" not in mapping.values()
    assert new_high_water == 3


def test_the_high_water_mark_survives_a_document_round_trip():
    previous, high_water = mint(["alpha", "beta"])
    dropped = retained(previous, ["alpha"])
    stored = {"aw_identity": identity_block({"alpha": "FR-1"}, high_water, dropped)}

    recovered_map, recovered_mark = read_identity(stored)

    assert recovered_map == {"alpha": "FR-1"}
    assert recovered_mark == 2
    mapping, _ = mint(["alpha", "fresh"], recovered_map, recovered_mark)
    assert mapping["fresh"] == "FR-3"


def test_a_corrupt_high_water_mark_cannot_mint_a_duplicate():
    """A mark below an identifier already in use would hand out FR-2 twice."""
    stored = {"aw_identity": {"requirements": {"alpha": "FR-7"}, "high_water": 0}}
    mapping, mark = read_identity(stored)
    assert mark == 7
    minted, _ = mint(["alpha", "beta"], mapping, mark)
    assert minted["beta"] == "FR-8"


def test_identity_of_a_document_with_no_block_is_empty_rather_than_an_error():
    assert read_identity(None) == ({}, 0)
    assert read_identity({"title": "x"}) == ({}, 0)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render(payload, identifiers=None, phase="exploring"):
    identifiers = identifiers or {}
    return render_document(
        payload,
        identifiers,
        phase=phase,
        stored_payload=payload_to_dict(payload),
    )


def test_the_document_references_no_external_resource():
    """Inline style only. A document that fetched a font or a stylesheet would
    render differently — or not at all — depending on the network."""
    html = _render(_payload(summary="A summary."))

    assert "<style>" in html
    assert not re.search(r"<link\b", html)
    assert not re.search(r'src\s*=\s*"https?://', html)
    assert not re.search(r"@import", html)
    assert "cdn" not in html.lower()


def test_every_anchor_resolves_and_no_identifier_is_duplicated():
    payload = _payload(
        requirements=[_requirement("alpha"), _requirement("beta")],
        tasks=[{"key": "t1", "description": "Do it", "requirements": ["alpha", "beta"]}],
        acceptance_criteria=[
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
    )
    identifiers, _ = mint(["alpha", "beta"])

    html = _render(payload, identifiers)

    ids = re.findall(r'id="([^"]+)"', html)
    assert len(ids) == len(set(ids)), f"duplicate id: {ids}"
    for target in re.findall(r'href="#([^"]+)"', html):
        assert f'id="{target}"' in html, f"dangling anchor #{target}"


def test_requirement_text_is_escaped_not_interpreted():
    payload = _payload(requirements=[_requirement("alpha", statement="<img src=x onerror=1>")])
    html = _render(payload, {"alpha": "FR-1"})

    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_a_title_that_looks_like_markup_cannot_escape_the_head():
    html = _render(_payload(title="</title><script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html


def test_the_phase_is_rendered_from_the_hub_not_from_the_payload():
    """A payload claiming a phase changes nothing — the caller passes the phase
    the Hub's transition log says the document is in."""
    html = _render(_payload(), phase="approved")
    assert 'name="aw-spec-status" content="approved"' in html


def test_the_rendered_document_carries_its_payload_for_round_tripping():
    payload = _payload(requirements=[_requirement("alpha")], gate_policy={"rigor": "gate"})
    html = _render(payload, {"alpha": "FR-1"})

    recovered = extract_payload(html)
    assert recovered["gate_policy"] == {"rigor": "gate"}
    assert recovered["requirements"][0]["key"] == "alpha"


def test_an_empty_document_still_renders():
    """Explore starts from an empty document, so this is the first thing an
    operator ever sees rendered."""
    html = _render(_payload())
    assert "A change" in html
    assert "No requirements yet." in html


def test_stated_scope_with_no_non_goals_says_so_rather_than_omitting_the_heading():
    payload = _payload(scope={"in_scope": ["the thing"], "non_goals": []})
    html = _render(payload)
    assert "Non-goals" in html
    assert "Omission is not a" in html


def test_the_three_theme_layers_are_present():
    html = _render(_payload())
    assert ":root {" in html
    assert "@media (prefers-color-scheme: dark)" in html
    assert ':root[data-theme="dark"]' in html


def test_the_document_carries_no_navigation_script_of_its_own():
    """The shell injects the bridge into the frame. A second copy here would
    diverge from the one that is actually used."""
    html = _render(_payload())
    assert "postMessage" not in html
    assert "addEventListener" not in html


# ---------------------------------------------------------------------------
# Reading the document, rather than parsing it
#
# Both of the following were found by reading the first agent-authored document
# end to end. Nothing in the suite could have caught either: the output was
# well-formed, every anchor resolved, and it was simply harder to read than it
# needed to be.
# ---------------------------------------------------------------------------


def _criterion(key, requirement, then="t"):
    return {"key": key, "requirement": requirement, "given": "g", "when": "w", "then": then}


def _requirement_column(html):
    table = html.split('id="acceptance"', 1)[1]
    return re.findall(r'<td><a href="#(FR-\d+)">', table)


def test_acceptance_criteria_are_grouped_by_requirement_order():
    """The live document ran FR-8, FR-8, FR-7 — submission order, not
    requirement order — and a reader scanning the column lost their place."""
    payload = _payload(
        requirements=[_requirement("alpha"), _requirement("beta"), _requirement("gamma")],
        acceptance_criteria=[
            _criterion("c3", "gamma"),
            _criterion("c1", "alpha"),
            _criterion("c2", "beta"),
        ],
    )
    identifiers, _ = mint(["alpha", "beta", "gamma"])

    assert _requirement_column(_render(payload, identifiers)) == ["FR-1", "FR-2", "FR-3"]


def test_criteria_for_one_requirement_keep_the_order_they_were_written_in():
    """Within a requirement the author's order carries their emphasis, so the
    sort has to be stable rather than merely correct."""
    payload = _payload(
        requirements=[_requirement("alpha"), _requirement("beta")],
        acceptance_criteria=[
            _criterion("c1", "beta", then="beta first"),
            _criterion("c2", "alpha", then="alpha first"),
            _criterion("c3", "beta", then="beta second"),
            _criterion("c4", "alpha", then="alpha second"),
        ],
    )
    identifiers, _ = mint(["alpha", "beta"])

    html = _render(payload, identifiers)
    assert _requirement_column(html) == ["FR-1", "FR-1", "FR-2", "FR-2"]
    assert html.index("alpha first") < html.index("alpha second")
    assert html.index("beta first") < html.index("beta second")


def test_no_outstanding_questions_is_stated_rather_than_left_blank():
    """An absent section cannot be told apart from questions never asked."""
    html = _render(_payload(open_questions=[]))
    assert "Open questions" in html
    assert "None outstanding" in html


def test_outstanding_questions_are_still_listed():
    payload = _payload(open_questions=[{"key": "q1", "question": "Which one?"}])
    html = _render(payload)
    assert "Which one?" in html
    assert "None outstanding" not in html


# ---------------------------------------------------------------------------
# Retirement, across more than one save
# ---------------------------------------------------------------------------


def test_a_retirement_survives_a_later_unrelated_save():
    """Found by running the loop: a v1 document retired FR-5 and FR-7, and the
    next save — which only *added* a requirement — reported `retired: {}`.

    `previous` is the live map alone, so computing retirement from it describes
    one submission and forgets everything older."""
    first = retained({"alpha": "FR-1", "beta": "FR-2"}, ["alpha"])
    assert first == {"beta": "FR-2"}

    # The next save adds a requirement and touches nothing else.
    second = retained({"alpha": "FR-1"}, ["alpha", "gamma"], first)
    assert second == {"beta": "FR-2"}, "the retirement was forgotten one save later"


def test_retirements_accumulate_across_saves():
    first = retained({"alpha": "FR-1", "beta": "FR-2"}, ["alpha"])
    second = retained({"alpha": "FR-1", "delta": "FR-3"}, ["alpha"], first)
    assert second == {"beta": "FR-2", "delta": "FR-3"}


def test_a_key_that_comes_back_is_no_longer_retired():
    """A key in both maps under two identifiers would say two different things
    about one requirement."""
    first = retained({"alpha": "FR-1", "beta": "FR-2"}, ["alpha"])
    second = retained({"alpha": "FR-1"}, ["alpha", "beta"], first)
    assert "beta" not in second


def test_retirement_is_read_back_from_a_stored_document():
    stored = {IDENTITY_FIELD: {"requirements": {"alpha": "FR-1"}, "retired": {"beta": "FR-2"}}}
    assert read_retired(stored) == {"beta": "FR-2"}


def test_a_document_with_no_identity_block_has_no_retirements():
    assert read_retired(None) == {}
    assert read_retired({}) == {}
    assert read_retired({IDENTITY_FIELD: {"requirements": {}}}) == {}
