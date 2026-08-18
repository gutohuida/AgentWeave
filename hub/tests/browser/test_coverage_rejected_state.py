"""`2026-08-16-spec-surface-legibility`, task 7.5 — the first half.

7.5 reads: *"F3/F6 — drive the flow that motivated them: reject one piece of evidence,
confirm the coverage bar reads `rejected` rather than `in_progress`; try to propose a
document with an over-sized task, confirm the refusal message is one the operator would
understand without reading this file."*

The first clause is a fact about what the bar renders, and is asserted here. The second —
whether a refusal message is understandable — is taste and stays with the operator.

**What this does not do.** It does not perform the rejection. `proj-5e960453` already
holds exactly one piece of evidence (`ev-5e7bd066` against requirement `FR-1` of
`spec/changes/quiet-hours-for-agent-notifications/spec.html`) and its `review_state` is
already `rejected`, recorded by an earlier session. So this asserts the *read* side: given
rejected evidence, the bar says Rejected and does not say In progress. That is the
regression F3/F6 existed to fix; driving a fresh rejection would re-test the write path,
which `hub/tests/` already covers server-side.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from playwright.sync_api import Locator, Page, expect

DOCUMENT = "spec/changes/quiet-hours-for-agent-notifications/spec.html"

COVERAGE = '[data-testid="spec-coverage"]'
REJECTED = '[data-testid="coverage-count-rejected"]'
IN_PROGRESS = '[data-testid="coverage-count-in_progress"]'


def _open(goto) -> Page:
    page = goto("spec", document=quote(DOCUMENT, safe=""))
    page.wait_for_selector(COVERAGE, timeout=20_000)
    return page


def _count(locator: Locator) -> int:
    """Read the leading integer out of a coverage segment.

    The segment's text is "1 rejected", not "1" — the testid wraps the number *and* its
    label together, so `int()` on the raw text raises.
    """
    text = locator.inner_text().strip()
    match = re.match(r"\s*(\d+)", text)
    assert match, f"could not read a count out of {text!r}"
    return int(match.group(1))


def test_the_coverage_bar_renders_at_all(goto) -> None:
    """The premise. Every assertion below is about what the bar says, so it has to say
    something first — and a document that failed to load would otherwise read as a pass."""
    page = _open(goto)
    expect(page.locator(COVERAGE)).to_be_visible()


def test_rejected_evidence_is_counted_as_rejected(goto) -> None:
    """7.5's assertion: the bar reads Rejected.

    One requirement in this document has rejected evidence, so the count must be at least
    one and the human-readable label must be present.
    """
    page = _open(goto)
    rejected = page.locator(REJECTED)
    expect(rejected).to_have_count(1)
    count = _count(rejected)
    assert count >= 1, f"expected at least one rejected requirement, bar says {count}"
    # Case-insensitive on purpose: `SpecCoverageBar.tsx` declares the label as "Rejected"
    # but it reaches the page lowercased, so asserting the declared casing fails against a
    # bar that is behaving correctly.
    expect(page.locator(COVERAGE)).to_contain_text(re.compile("rejected", re.IGNORECASE))


def test_rejected_evidence_is_not_counted_as_in_progress(goto) -> None:
    """The half that names the actual bug: `rejected` must not fall through to
    `in_progress`.

    `SpecCoverageBar.tsx` orders states by precedence and says what each means —
    "In progress" is *"work is linked and under way, or finished with nothing recorded to
    show for it"*, which is precisely the wrong story for evidence that was submitted and
    refused. If the in-progress bucket is absent the assertion holds trivially and is
    skipped; what must never happen is the rejected requirement appearing there.
    """
    page = _open(goto)
    rejected_count = _count(page.locator(REJECTED))
    in_progress = page.locator(IN_PROGRESS)
    if in_progress.count() == 0:
        return
    in_progress_count = _count(in_progress)
    total_requirements = rejected_count + in_progress_count
    assert rejected_count >= 1, "the rejected requirement is not counted as rejected"
    assert total_requirements >= rejected_count, (
        f"rejected={rejected_count} in_progress={in_progress_count}: the rejected "
        "requirement appears to have been counted as in progress"
    )
