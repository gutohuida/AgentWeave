"""Identifier minting and document rendering.

The properties under test are the ones that used to be a self-check the model
ran on itself and reported: no dangling anchor, no duplicate identifier, no
external resource. They are now structural — the renderer emits the anchor and
the link from the same minted value, so the failure has nowhere to occur.
"""

import hashlib
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
from hub.spec_render import _STYLE, CorpusChild, CorpusContext, render_document

# The neutral custom properties SpecFrame.tsx's HUB_NEUTRALS override sets on every
# mode (`themeOverride()` in SpecFrame.tsx) — spec_render.py must define each one under
# this exact name or the override has nothing to land on. --aw-accent is deliberately
# excluded: SpecFrame.tsx does not override it, and spec_render.py is not meant to rename it.
_HUB_OVERRIDDEN_NEUTRALS = ("--bg", "--surface", "--surface-2", "--border", "--fg", "--muted")


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


def test_the_neutral_variables_match_the_hub_shells_override_names():
    """SpecFrame.tsx's themeOverride() sets --bg/--surface/--surface-2/--border/--fg/--muted
    on the frame. If spec_render.py's _STYLE stops defining one of those names, the override
    has nothing to affect and the document silently stops following the shell's theme — this
    is what happened before the --aw-* names were renamed to match."""
    for name in _HUB_OVERRIDDEN_NEUTRALS:
        assert f"{name}:" in _STYLE, f"{name} is not defined in spec_render.py's _STYLE"


def test_each_modal_value_renders_with_its_own_distinct_class():
    """F1: colour carries meaning. MUST/SHOULD/MAY must be visually distinct without reading
    the word — the machine-checkable half of that is three distinct classes, one per value,
    on both the modal span and the requirement's left border."""
    payload = _payload(
        requirements=[
            _requirement("alpha", modal="MUST"),
            _requirement("beta", modal="SHOULD"),
            _requirement("gamma", modal="MAY"),
        ]
    )
    identifiers, _ = mint(["alpha", "beta", "gamma"])

    html = _render(payload, identifiers)

    modal_classes = set(re.findall(r'class="aw-modal (aw-modal-\w+)"', html))
    requirement_classes = set(re.findall(r'class="aw-requirement (aw-requirement-\w+)"', html))
    assert modal_classes == {"aw-modal-must", "aw-modal-should", "aw-modal-may"}
    assert requirement_classes == {
        "aw-requirement-must",
        "aw-requirement-should",
        "aw-requirement-may",
    }


def test_shall_takes_the_same_tone_as_must():
    """MUST and SHALL are the same obligation in RFC2119 language; a document written with
    SHALL should not silently lose the colour a MUST would have gotten."""
    payload = _payload(requirements=[_requirement("alpha", modal="SHALL")])
    html = _render(payload, {"alpha": "FR-1"})
    assert 'class="aw-modal aw-modal-must"' in html


def test_the_rigor_chip_takes_a_tone_for_contract_and_gate_but_not_sketch():
    """sketch is the default and blocks nothing, so it stays the plain neutral chip; contract
    and gate mean something happens, so each gets its own tone."""
    for rigor, expected_class in (
        ("contract", "aw-chip-rigor-contract"),
        ("gate", "aw-chip-rigor-gate"),
    ):
        html = render_document(
            _payload(),
            {},
            phase="exploring",
            stored_payload=payload_to_dict(_payload()),
            rigor=rigor,
        )
        assert f'class="aw-chip {expected_class}">{rigor}' in html

    sketch_html = render_document(
        _payload(),
        {},
        phase="exploring",
        stored_payload=payload_to_dict(_payload()),
        rigor="sketch",
    )
    assert 'class="aw-chip">sketch' in sketch_html
    assert "aw-chip-rigor-sketch" not in sketch_html


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


# ---------------------------------------------------------------------------
# Colour that carries information
# ---------------------------------------------------------------------------


def test_the_phase_chip_takes_a_tone_per_lifecycle_state():
    """Phase answers "can I rely on this?", so each state reads differently. `approved` and a
    capability's `current` are settled, `proposed` waits on an operator, `exploring` has not
    arrived and `archived` has been superseded."""
    for phase, expected_class in (
        ("approved", "aw-chip-phase-done"),
        ("current", "aw-chip-phase-done"),
        ("proposed", "aw-chip-phase-waiting"),
        ("exploring", "aw-chip-phase-quiet"),
        ("archived", "aw-chip-phase-archived"),
    ):
        html = _render(_payload(), phase=phase)
        assert f'class="aw-chip {expected_class}">{phase}' in html


def test_an_unknown_phase_falls_back_to_the_plain_chip():
    """A phase this mapping does not know renders neutral rather than raising, the same way an
    unknown rigor does."""
    html = _render(_payload(), phase="something-new")
    assert 'class="aw-chip">something-new' in html


def test_the_kind_chip_is_never_toned():
    """kind is a category, not a state. Hue there would rank things that have no ranking."""
    html = _render(_payload(), phase="approved")
    assert 'class="aw-chip">change-spec' in html


def test_the_phase_tone_is_never_the_accent():
    """The document already spends the accent on links and on MUST. A third meaning would empty
    it of any, so the phase scheme uses the done/warn tones instead."""
    for phase in ("approved", "current", "proposed", "exploring", "archived"):
        html = _render(_payload(), phase=phase)
        chip = re.search(r'class="aw-chip aw-chip-phase-[a-z]+"', html)
        assert chip is not None
        assert "accent" not in chip.group(0)


def test_an_unresolved_question_is_toned_and_a_resolved_one_is_not():
    """An unresolved question blocks propose, so it is a state and not a label."""
    payload = _payload(
        open_questions=[
            {"question": "Still deciding?", "resolved": False},
            {"question": "Settled.", "resolved": True},
        ]
    )
    html = _render(payload)
    assert 'class="aw-chip aw-chip-open">open' in html
    assert 'class="aw-chip">resolved' in html


def test_limits_is_toned_and_checked_is_not():
    """Limits is where a reader is most likely to be misled; it read identically to Checked."""
    payload = _payload(evidence={"checked": ["Read the code"], "limits": ["Not run live"]})
    html = _render(payload)
    assert '<h3 class="aw-limits">Limits</h3>' in html
    assert "<h3>Checked</h3>" in html


def test_the_summary_counts_requirements_by_modal_in_the_modal_scheme():
    """The first screenful was monochrome however the requirements below were coloured."""
    payload = _payload(
        requirements=[
            _requirement("a", modal="MUST"),
            _requirement("b", modal="SHALL"),
            _requirement("c", modal="SHOULD"),
            _requirement("d", modal="MAY"),
        ]
    )
    html = _render(payload, {"a": "FR-1", "b": "FR-2", "c": "FR-3", "d": "FR-4"})
    summary = html.split('<p class="aw-summary">')[1].split("</p>")[0]
    # SHALL folds into MUST, exactly as the requirement list itself tones it.
    assert '<span class="aw-count">2</span> MUST' in summary
    assert '<span class="aw-count">1</span> SHOULD' in summary
    assert '<span class="aw-count">1</span> MAY' in summary
    assert '<span class="aw-count">4</span> requirements' in summary


def test_the_summary_reports_unresolved_questions_and_stays_silent_when_there_are_none():
    with_open = _render(
        _payload(
            requirements=[_requirement("a")],
            open_questions=[{"question": "Undecided?", "resolved": False}],
        ),
        {"a": "FR-1"},
    )
    assert "1</span> open question" in with_open

    resolved_only = _render(
        _payload(
            requirements=[_requirement("a")],
            open_questions=[{"question": "Decided.", "resolved": True}],
        ),
        {"a": "FR-1"},
    )
    assert "open question" not in resolved_only.split('<p class="aw-summary">')[1].split("</p>")[0]


def test_a_document_with_no_requirements_has_no_summary():
    """Nothing to count is not the same as counting zero, and a bar of zeroes is noise."""
    assert 'class="aw-summary"' not in _render(_payload())


def test_the_summary_claims_no_coverage_it_cannot_see():
    """Whether a requirement has work linked is the Hub's knowledge, not the renderer's."""
    payload = _payload(requirements=[_requirement("a")])
    summary = _render(payload, {"a": "FR-1"}).split('<p class="aw-summary">')[1].split("</p>")[0]
    assert "linked" not in summary
    assert "coverage" not in summary.lower()


def test_the_done_tone_is_defined_in_every_theme_block():
    """--aw-ok is read by the phase chip, so a block that omits it would render an unstyled chip
    in that mode. Mirrors the neutral pinning test above."""
    assert _STYLE.count("--aw-ok:") == 4


# ---------------------------------------------------------------------------
# corpus-aware-documents §1: the renderer accepts a corpus context and, until
# groups 2-3 land, ignores it. This is the regression net that lets those groups
# add navigation and a map without re-reviewing every document rendered before
# they existed: every caller that omits `corpus` — which today is every caller —
# must keep getting exactly this output, byte for byte.
# ---------------------------------------------------------------------------


def _rich_payload():
    return _payload(
        kind="capability",
        title="A rich document",
        summary="What this changes and why.",
        problem="The problem.",
        scope={"in_scope": ["thing one"], "non_goals": ["not this"]},
        requirements=[_requirement("alpha")],
        acceptance_criteria=[_criterion("c1", "alpha")],
        tasks=[{"key": "t1", "title": "Do it", "description": "desc", "requirements": ["alpha"]}],
        open_questions=[{"key": "q1", "question": "Still open?", "resolved": False}],
        evidence={"checked": ["Read the code"], "limits": ["Not run live"]},
    )


# Captured from render_document's own output. Recaptured twice: in §2, when `.aw-nav` joined the
# shared stylesheet, and again in §3, when `.aw-map*` did the same (_STYLE is embedded in every
# document regardless of whether this document's own `corpus` uses it — the existing pattern for
# every other CSS rule here, e.g. `.aw-chip-rigor-contract` is present even in documents whose
# rigor is not `contract`). §1.3's guarantee is that the `corpus is None` branch renders no
# *region*, not that the shared stylesheet is frozen — a change to this digest with no `corpus`
# argument passed and no stylesheet edit means the None-branch stopped being a no-op.
_BASELINE_DIGEST = "7596614bf74c4b2b1129c95973e4fd42599f94d3ca0a673ae29f33c2d2d3be83"


def test_omitting_corpus_reproduces_the_pre_change_output_byte_for_byte():
    payload = _rich_payload()
    identifiers, _ = mint(["alpha"])
    html = render_document(
        payload, identifiers, phase="current", stored_payload=payload_to_dict(payload), rigor="gate"
    )
    assert hashlib.sha256(html.encode("utf-8")).hexdigest() == _BASELINE_DIGEST


def test_explicit_corpus_none_is_identical_to_omitting_it():
    payload = _rich_payload()
    identifiers, _ = mint(["alpha"])
    kwargs = {"phase": "current", "stored_payload": payload_to_dict(payload), "rigor": "gate"}
    omitted = render_document(payload, identifiers, **kwargs)
    explicit = render_document(payload, identifiers, corpus=None, **kwargs)
    assert omitted == explicit


# ---------------------------------------------------------------------------
# corpus-aware-documents §2: the navigation region — home and parent links,
# below the meta chips (decision D-S2-navstrip), computed relative to the
# document's own path on disk.
# ---------------------------------------------------------------------------


def _render_with_corpus(corpus):
    payload = _rich_payload()
    identifiers, _ = mint(["alpha"])
    return render_document(
        payload,
        identifiers,
        phase="current",
        stored_payload=payload_to_dict(payload),
        rigor="gate",
        corpus=corpus,
    )


def test_the_home_document_gets_no_home_link():
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=()
    )
    html = _render_with_corpus(corpus)
    assert 'class="aw-nav"' not in html


def test_a_non_home_document_with_no_parent_gets_only_a_home_link():
    corpus = CorpusContext(
        path="spec/capabilities/x/spec.html", home="spec/agentweave.html", parent=None, children=()
    )
    html = _render_with_corpus(corpus)
    nav = re.search(r'<p class="aw-nav">(.*?)</p>', html).group(1)
    assert '<a href="../../agentweave.html">Home</a>' in nav
    assert "aw-map" not in nav


def test_a_document_with_a_parent_gets_both_links_home_first():
    corpus = CorpusContext(
        path="spec/areas/agents.html",
        home="spec/agentweave.html",
        parent=("spec/agentweave.html", "AgentWeave"),
        children=(),
    )
    html = _render_with_corpus(corpus)
    nav = re.search(r'<p class="aw-nav">(.*?)</p>', html).group(1)
    home_pos = nav.index(">Home<")
    parent_pos = nav.index(">AgentWeave<")
    assert home_pos < parent_pos
    assert '<a href="../agentweave.html">Home</a>' in nav
    assert '<a href="../agentweave.html">AgentWeave</a>' in nav


def test_relative_links_climb_out_of_nested_directories():
    corpus = CorpusContext(
        path="spec/capabilities/deep/nested/spec.html",
        home="spec/agentweave.html",
        parent=("spec/areas/agents.html", "Agents and execution"),
        children=(),
    )
    html = _render_with_corpus(corpus)
    assert '<a href="../../../agentweave.html">Home</a>' in html
    assert '<a href="../../../areas/agents.html">Agents and execution</a>' in html


def test_the_navigation_region_carries_no_external_resource():
    corpus = CorpusContext(
        path="spec/capabilities/x/spec.html",
        home="spec/agentweave.html",
        parent=("spec/agentweave.html", "AgentWeave"),
        children=(),
    )
    html = _render_with_corpus(corpus)
    assert "http://" not in html
    assert "https://" not in html


def test_a_rendered_file_opened_from_disk_resolves_both_links_with_no_hub_running(tmp_path):
    """Task 2.5: the links are computed relative to the document's own location on disk, so
    writing the home and a nested document to their real relative locations and following the
    href from the nested one, with no HTTP server involved, must land on the file that exists."""
    home_dir = tmp_path / "spec"
    home_dir.mkdir()
    (home_dir / "agentweave.html").write_text("<html>home</html>", encoding="utf-8")

    corpus = CorpusContext(
        path="spec/capabilities/x/spec.html", home="spec/agentweave.html", parent=None, children=()
    )
    html = _render_with_corpus(corpus)
    href = re.search(r'<a href="([^"]+)">Home</a>', html).group(1)

    own_dir = tmp_path / "spec" / "capabilities" / "x"
    own_dir.mkdir(parents=True)
    doc_path = own_dir / "spec.html"
    doc_path.write_text(html, encoding="utf-8")

    resolved = (doc_path.parent / href).resolve()
    assert resolved == (home_dir / "agentweave.html").resolve()
    assert resolved.read_text(encoding="utf-8") == "<html>home</html>"


# ---------------------------------------------------------------------------
# corpus-aware-documents §3: the generated map — every child of the document
# being rendered, listed with kind, phase, summary, and a relative link.
# ---------------------------------------------------------------------------


def test_a_document_with_no_children_gets_no_map_section():
    corpus = CorpusContext(
        path="spec/capabilities/x/spec.html", home="spec/agentweave.html", parent=None, children=()
    )
    html = _render_with_corpus(corpus)
    assert 'class="aw-map"' not in html


def test_a_document_with_children_gets_a_map_section():
    child = CorpusChild(
        path="spec/capabilities/a/spec.html",
        title="A",
        kind="capability",
        phase="current",
        summary="What A does.",
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=(child,)
    )
    html = _render_with_corpus(corpus)
    section = re.search(r'<section class="aw-map">(.*?)</section>', html).group(1)
    assert '<a href="capabilities/a/spec.html">A</a>' in section
    assert '<span class="aw-chip">capability</span>' in section
    assert '<span class="aw-chip aw-chip-phase-done">current</span>' in section
    assert "<p>What A does.</p>" in section


def test_children_in_the_map_are_ordered_as_given_not_alphabetically():
    """build_corpus_context already orders by the manifest's `order` (task 1.4); the map must not
    re-sort what it is handed."""
    children = tuple(
        CorpusChild(
            path=f"spec/{name}.html", title=name, kind="capability", phase="current", summary="s"
        )
        for name in ["z", "a", "m"]
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=children
    )
    html = _render_with_corpus(corpus)
    section = re.search(r'<section class="aw-map">(.*?)</section>', html).group(1)
    positions = {name: section.index(f">{name}<") for name in ["z", "a", "m"]}
    assert positions["z"] < positions["a"] < positions["m"]


def test_an_empty_summary_renders_as_no_summary_yet_in_the_empty_style():
    child = CorpusChild(
        path="spec/capabilities/a/spec.html",
        title="A",
        kind="capability",
        phase="current",
        summary="",
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=(child,)
    )
    html = _render_with_corpus(corpus)
    assert '<p class="aw-empty">no summary yet</p>' in html


def test_a_placeholder_summary_renders_as_no_summary_yet():
    """design D8: the sync-created placeholder ('TBD - created by syncing change ...') is
    indistinguishable from a real summary unless named, so it is treated the same as empty."""
    child = CorpusChild(
        path="spec/capabilities/a/spec.html",
        title="A",
        kind="capability",
        phase="current",
        summary="TBD - created by syncing change 2026-08-04-x. Update Purpose after archive.",
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=(child,)
    )
    html = _render_with_corpus(corpus)
    assert '<p class="aw-empty">no summary yet</p>' in html
    assert "TBD - created by syncing change" not in html


def test_the_map_region_is_labelled_as_generated():
    child = CorpusChild(
        path="spec/capabilities/a/spec.html",
        title="A",
        kind="capability",
        phase="current",
        summary="s",
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=(child,)
    )
    html = _render_with_corpus(corpus)
    section = re.search(r'<section class="aw-map">(.*?)</section>', html).group(1)
    assert "generated" in section.lower()


def test_a_grandchild_present_in_the_context_renders_nested_and_links_relative_to_the_document():
    """Decision D-S2-recursive: whether a grandchild shows up at all is
    `spec_documents.build_corpus_context`'s call, not the renderer's — this only proves that once
    handed a nested tree (as the home's context is), the renderer walks it and computes every link
    relative to the document actually being rendered, not to the immediate parent in the tree."""
    grandchild = CorpusChild(
        path="spec/capabilities/leaf/spec.html",
        title="Leaf",
        kind="capability",
        phase="current",
        summary="A leaf.",
    )
    child = CorpusChild(
        path="spec/areas/agents.html",
        title="Agents and execution",
        kind="system-map",
        phase="current",
        summary="An area.",
        children=(grandchild,),
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=(child,)
    )
    html = _render_with_corpus(corpus)
    section = re.search(r'<section class="aw-map">(.*?)</section>', html).group(1)
    assert '<a href="areas/agents.html">Agents and execution</a>' in section
    assert '<a href="capabilities/leaf/spec.html">Leaf</a>' in section


def test_the_map_carries_no_external_resource():
    child = CorpusChild(
        path="spec/capabilities/a/spec.html",
        title="A",
        kind="capability",
        phase="current",
        summary="s",
    )
    corpus = CorpusContext(
        path="spec/agentweave.html", home="spec/agentweave.html", parent=None, children=(child,)
    )
    html = _render_with_corpus(corpus)
    assert "http://" not in html
    assert "https://" not in html
    assert "<script src" not in html
    assert "<link" not in html
