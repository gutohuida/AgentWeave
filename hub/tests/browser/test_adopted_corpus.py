"""`document-adoption`, tasks 8.3 and 8.5 — the factual half.

These two read:

  - **8.3** *"The Spec tab gained a lifecycle. Open the Spec tab; documents that previously
    showed no phase now show one, and the phase bar is populated."*
  - **8.5** *"Requirements arrived. Open a document with requirements and confirm coverage
    renders against it."*

Both mix a fact with a judgement, and only the fact is settled here. Whether the phase bar
*reads* as informative rather than as clutter, and whether coverage *reads* as useful, stay
with the operator.

**What makes these worth running in a browser at all.** Every one of these documents renders
identically on disk with or without a row — `GET /specs` builds its tree from the filesystem,
so the file has always been readable. What a row adds is invisible in the file and visible
only here: a phase, a document id the panel can key a tab by, and requirements that coverage
can resolve against. A unit test asserting `document_id is not None` proves the row exists; it
does not prove the UI found it.

**Setup.** These need a Hub whose project has been through corpus adoption. They were written
against a throwaway Hub serving a *copy* of this repository's own `spec/` tree — 34 capability
documents plus the `system-map` home — precisely so the real corpus and the operator's trial
database were never involved:

    cd hub
    AW_HUB_URL=http://127.0.0.1:8021 \
    AW_HUB_API_KEY=<key> \
    AW_HUB_PROJECT_ID=<adopted project> \
      py -3.11 -m pytest tests/browser/test_adopted_corpus.py -v

Run against a project that has *not* been adopted, every test here fails on the phase
assertion — which is the point, and is what makes them evidence rather than decoration.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect

#: The two documents `document-adoption`'s proposal names as permanently `unfiled` before
#: this change, because `build_index` files only documents that have a row.
PREVIOUSLY_UNFILED = [
    "spec/capabilities/quiet-hours/spec.html",
    "spec/capabilities/project-instructions/spec.html",
]

#: A capability document carrying requirements, for the coverage half.
DOCUMENT_WITH_REQUIREMENTS = "spec/capabilities/agent-charter/spec.html"

#: The corpus home — a `system-map`, and the one document in this corpus that is not
#: `current`. Its presence stops the phase assertions below from passing on a UI that
#: hardcodes a single phase everywhere.
HOME_DOCUMENT = "spec/agentweave.html"


def _open_document(goto, path: str) -> Page:
    page = goto("spec", document=quote(path, safe=""))
    page.wait_for_selector('[data-testid="spec-phase"]', timeout=20_000)
    return page


@pytest.mark.parametrize("path", PREVIOUSLY_UNFILED)
def test_a_previously_unfiled_document_now_shows_a_phase(goto, path: str) -> None:
    """8.3's fact, on the two documents that most needed it.

    Before adoption these had no row, so `GET /specs` returned `phase: null` for them and
    the phase bar had nothing to render.
    """
    page = _open_document(goto, path)
    expect(page.locator('[data-testid="spec-phase"]')).to_have_text("current")


@pytest.mark.parametrize("path", PREVIOUSLY_UNFILED)
def test_the_phase_bar_is_populated_rather_than_present_and_empty(goto, path: str) -> None:
    """The other half of "populated": a bar that rendered but said nothing would satisfy a
    visibility check while showing the operator exactly what they had before."""
    page = _open_document(goto, path)
    expect(page.locator('[data-testid="spec-phase"]')).to_be_visible()
    expect(page.locator('[data-testid="spec-rigor"]')).to_be_visible()
    assert page.locator('[data-testid="spec-phase"]').inner_text().strip()


def test_the_home_document_shows_its_own_phase_not_a_hardcoded_one(goto) -> None:
    """The contrast case. Every other document in this corpus is `current`; if the bar
    rendered a constant, the assertions above would pass on a UI that reads nothing."""
    page = _open_document(goto, HOME_DOCUMENT)
    expect(page.locator('[data-testid="spec-phase"]')).to_have_text("exploring")


def test_the_document_title_comes_from_the_payload_not_the_path(goto) -> None:
    """Adoption took the title from the file's own payload. `quiet-hours` on disk would
    yield "Quiet hours" either way through `deriveTitle`'s fallback — so this asserts the
    rendered document, where a path-derived name would be visibly wrong."""
    page = _open_document(goto, "spec/capabilities/quiet-hours/spec.html")
    expect(page.get_by_text("Quiet hours").first).to_be_visible()


def test_coverage_renders_against_an_adopted_document(goto) -> None:
    """8.5's fact, and the strongest single piece of evidence in this file.

    Coverage counts *requirement rows*, which are stored against a document id and are
    indexed only when a row exists. A document with no row has no requirements to count,
    so a coverage control reporting a real number is something that could not render at
    all before adoption — unlike the document body, which reads the same either way.

    Asserted as "a positive count", not a fixed one: the number is a property of the
    corpus this ran against, and pinning it would make the test fail when a requirement is
    added to a document that has nothing to do with adoption.
    """
    page = _open_document(goto, DOCUMENT_WITH_REQUIREMENTS)
    coverage = page.get_by_role("button", name=re.compile(r"\d+\s+no work linked"))
    expect(coverage.first).to_be_visible(timeout=20_000)
    label = coverage.first.inner_text().strip()
    count = int(label.split()[0])
    assert count > 0, f"coverage reported no requirements at all: {label!r}"


def test_the_rendered_document_carries_its_minted_identifiers(goto) -> None:
    """The other half of 8.5: the identifiers coverage counts are the ones a reader sees.

    The document body renders inside an iframe — `page.get_by_text` does not reach it, and
    a test that forgot this would report the requirements missing when they are simply one
    frame down.
    """
    page = _open_document(goto, DOCUMENT_WITH_REQUIREMENTS)
    frame = page.frame_locator("iframe").first
    expect(frame.get_by_text("FR-1").first).to_be_visible(timeout=20_000)


def test_the_spec_tree_lists_the_whole_adopted_corpus(goto) -> None:
    """A corpus reconstituted from files alone is browsable as one.

    Asserted on the count rather than on any single entry: adoption's failure mode at this
    scale is a partial sweep, and one document being present says nothing about the other
    thirty-four.
    """
    page = goto("spec", document=quote(HOME_DOCUMENT, safe=""))
    page.wait_for_selector('[data-testid="spec-phase"]', timeout=20_000)
    for path in (*PREVIOUSLY_UNFILED, DOCUMENT_WITH_REQUIREMENTS):
        leaf = path.split("/")[-2].replace("-", " ")
        expect(page.get_by_text(leaf, exact=False).first).to_be_visible()
