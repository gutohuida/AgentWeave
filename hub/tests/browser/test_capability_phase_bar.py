"""`2026-08-16-the-corpus-keeps-what-shipped`, task 10.2 — the factual half.

10.2 reads: *"Is a capability document's phase bar quiet enough? With no controls
rendering for `current`, confirm the bar does not look broken or empty."*

Two claims, and only the first is checkable here:

  - **fact** — no phase control renders for a `current` document, while the phase chip and
    the enforcement control still do. `SpecPhaseBar.tsx` gates Propose on `exploring`,
    Approve on `proposed`, Archive on `approved`, and Reopen on `proposed || approved`, so
    `current` falls through all four. This asserts that the *rendered* bar agrees.
  - **taste** — whether the result reads as "nothing to decide here" rather than "something
    failed to load". That is 10.2's actual question and it stays open.

Task 10.1 — "does Archive read as final?" — is taste only, and absent.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from playwright.sync_api import Page, expect

CAPABILITY_DOCS = [
    "spec/capabilities/quiet-hours/spec.html",
    "spec/capabilities/project-instructions/spec.html",
]
ARCHIVED_CHANGE_DOC = "spec/changes/quiet-hours-for-agent-notifications/spec.html"

PHASE_CONTROLS = ("Propose", "Approve", "Archive", "Reopen")


def _open_document(goto, path: str) -> Page:
    page = goto("spec", document=quote(path, safe=""))
    page.wait_for_selector('[data-testid="spec-phase"]', timeout=20_000)
    return page


@pytest.mark.parametrize("path", CAPABILITY_DOCS)
def test_capability_document_reads_as_current(goto, path: str) -> None:
    """The premise: these documents really are in the `current` phase.

    Without this, the absence assertions below would pass just as happily on a document
    that failed to load at all.
    """
    page = _open_document(goto, path)
    expect(page.locator('[data-testid="spec-phase"]')).to_have_text("current")


@pytest.mark.parametrize("path", CAPABILITY_DOCS)
def test_no_phase_control_renders_for_a_capability_document(goto, path: str) -> None:
    """10.2's assertion: none of the four phase controls appear."""
    page = _open_document(goto, path)
    bar = page.locator('[data-testid="spec-phase"]').locator("xpath=..")
    for label in PHASE_CONTROLS:
        expect(bar.get_by_role("button", name=label, exact=True)).to_have_count(
            0
        ), f"{label} should not render for a current capability document"


@pytest.mark.parametrize("path", CAPABILITY_DOCS)
def test_the_bar_is_quiet_but_not_empty(goto, path: str) -> None:
    """The other half of "quiet enough": something is still there.

    An empty bar and a correctly-quiet bar are indistinguishable to the absence
    assertions above — this is what separates them. The enforcement control is deliberately
    *not* a phase control (`SpecPhaseBar.tsx`'s own comment: the two answer different
    questions), so it must survive.
    """
    page = _open_document(goto, path)
    expect(page.locator('[data-testid="spec-phase"]')).to_be_visible()
    expect(page.locator('[data-testid="spec-rigor"]')).to_be_visible()


def test_an_archived_change_document_also_offers_no_phase_control(goto) -> None:
    """The contrast case, and the reason the parametrised tests are not vacuous.

    `archived` is a different terminal phase reached a different way, and it too falls
    through all four gates. If a control ever renders here, the assertions above are
    testing a bar that renders nothing for anyone.
    """
    page = _open_document(goto, ARCHIVED_CHANGE_DOC)
    expect(page.locator('[data-testid="spec-phase"]')).to_have_text("archived")
    bar = page.locator('[data-testid="spec-phase"]').locator("xpath=..")
    for label in PHASE_CONTROLS:
        expect(bar.get_by_role("button", name=label, exact=True)).to_have_count(0)


def test_archived_document_shows_its_archived_marker(goto) -> None:
    """`spec-archived-marker` is what tells the operator why the bar is quiet here."""
    page = _open_document(goto, ARCHIVED_CHANGE_DOC)
    expect(page.locator('[data-testid="spec-archived-marker"]')).to_be_visible()
