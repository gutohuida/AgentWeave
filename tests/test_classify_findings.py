"""The gate for `scripts/classify_findings.py`.

That script decides how many findings in `scripts/drive/FINDINGS.md` are still open, which
makes it load-bearing for the backlog number in `spec-queue/ROADMAP.md`. It had **no test of
any kind** until 2026-09-09, and by then it had been wrong six separate ways -- five recorded
in its own header, the sixth found by writing this file.

Two rules govern everything below.

**The fixtures are synthetic.** Not one assertion reads the real ledger's content. That file
grows every night, so a test written against it would fail for the ordinary reason that
somebody appended a finding, and the only way to keep it green would be to edit the expected
numbers until they stopped meaning anything. It is also the exact disease the script's own
header warns about: a census written into the file it measures changes that census.

**Every case here is a defect that actually happened.** Each names the finding numbers it cost
in the real ledger, so a future reader can tell a regression guard from a preference.

The one thing that does read the real file is `test_every_line_belongs_to_exactly_one_section`
-- a structural invariant with no dependence on content. Both of the segmentation defects
(blind spots 5b and 6) violated it, and neither was caught by any vocabulary test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "classify_findings.py"


def _load():
    """Import `scripts/classify_findings.py` by path -- `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("classify_findings", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cf = _load()


def verdicts(text: str) -> dict[int, str]:
    return {r["num"]: r["verdict"] for r in cf.classify(text.strip("\n").split("\n"))}


def sections(text: str):
    return cf.classify(text.strip("\n").split("\n"))


# --- segmentation -----------------------------------------------------------------------


def test_heading_without_a_parenthetical_is_still_a_finding():
    """Blind spot 5a: `HEAD` demanded `(A)`..`(D)`, so 26 findings had no section at all.

    One of them, F77, was open and had never been counted by any census.
    """
    got = verdicts("""
## F1 (B) — a titled finding
**Status:** fixed abc1234

## F77 — an agent has no way to address the operator
**Status:** open
""")
    assert set(got) == {1, 77}
    assert got[77] == "OPEN"


def test_an_unparenthesised_heading_ends_the_previous_section():
    """Blind spot 5b, the expensive half: a heading the scanner could not see did not END
    the previous section, so F71's section absorbed F72-F86 -- 1,223 lines -- and seven
    verdicts were computed from a marker belonging to a different finding.
    """
    got = verdicts("""
## F71 (B) — the finding that absorbed its neighbours
Not queued.

## F72 — the neighbour
**Status:** fixed deadbee
""")
    assert got[71] == "OPEN", "F71's own 'Not queued' must survive its neighbour's marker"
    assert got[72] == "RESOLVED"


def test_a_continuation_block_belongs_to_its_parent():
    """Blind spot 6, found 2026-09-09 by writing this file.

    A continuation heading was correctly skipped as a section and then dropped on the floor:
    its lines belonged to no section at all -- 2,030 of them in the real ledger, including
    `### F45 — fixed 2026-08-25`, a finding's own resolution sitting outside the finding.
    """
    got = verdicts("""
## F45 (B) — the review turn named a transition the task could not make
It reproduces every time.

### F45 — a later block that carries the resolution
**Status:** fixed fec52d1
""")
    assert got[45] == "RESOLVED"


def test_a_continuation_block_does_not_double_count():
    """The rule blind spot 6's fix must not break: `### F63 — Resolution` is a continuation
    of F63, not a second finding.
    """
    secs = sections("""
## F63 (C) — a finding
Body.

### F63 — Resolution, 2026-08-26
**Status:** fixed abc1234
""")
    assert [s["num"] for s in secs] == [63]


def test_severity_comes_from_the_parenthetical_not_the_continuation():
    secs = sections("""
## F115 (B) — a finding
Body.

## F115, reproduced independently — RETIRED IN PART
More.
""")
    assert [s["sev"] for s in secs] == ["B"]


# --- what may count as a verdict --------------------------------------------------------


def test_quoted_history_is_not_current_status():
    """Blind spot 3, found by a mutation test failing. A section that withdraws its own
    banner *quotes* it, and `stays open` inside the quotation was read as an assertion.

    The fixture carries NO resolution marker on purpose. An earlier draft of this test put a
    `**Status:** fixed` line under the quotation and asserted RESOLVED -- which passes whether
    or not the quotation is stripped, because `RESOLVED` is decided before `OPEN`. Mutation M7
    survived against it. A test for a guard must fail when the guard is removed.
    """
    got = verdicts("""
## F140 (A) — a finding that narrates its own correction
The 2026-09-03 banner said *"so this entry stays open until somebody re-drives it."*
That banner was wrong, and the drive it asked for had already happened.
""")
    assert got[140] != "OPEN", "a quoted banner is a claim being withdrawn, not one being made"


def test_struck_through_text_is_withdrawn_not_asserted():
    """Same shape, same reason for carrying no competing marker."""
    got = verdicts("""
## F2 (C) — a finding
~~Status: open — nobody has driven this.~~
The strike-through is how this ledger withdraws a line without deleting the history.
""")
    assert got[2] != "OPEN"


def test_weak_prose_may_not_resolve_a_finding_from_a_continuation_block():
    """Split 2026-09-09. Blind spot 6's fix fed more prose to the `NOT A DEFECT` arm that
    the script's header already calls unreliable, and it misfired immediately: F197 on
    "A declaration is not a defect" and F164 on "One new observation, not a defect" --
    neither a statement about the finding it would have resolved.
    """
    got = verdicts("""
## F197 (B) — the settings page has no error state
It renders a loading skeleton forever.

### F197 sized, 2026-09-02 — it is 57 sites, not 133 declarations
A declaration is not a defect: three components calling one hook are three chances to fail.
""")
    assert got[197] != "RESOLVED"


def test_a_strong_marker_in_a_continuation_block_does_resolve():
    """The other half of the same split: a declaration still counts wherever it appears in
    the finding's own text. Only prose is confined to the primary block.
    """
    got = verdicts("""
## F3 (B) — a finding
Body.

### F3 — the drive
**Status:** fixed abc1234
""")
    assert got[3] == "RESOLVED"


def test_a_finding_may_be_resolved_by_its_own_heading():
    """Structural evidence, added 2026-09-09. `### F162 is closed` is a heading `ANY_HEAD`
    already matched to F162, so the words in it are about F162 -- unlike the same words in
    a sentence. Without this, blind spot 6's fix would have dropped F161 and F162 from a
    verdict to no signal at all, and those two are the only true positives the script's
    header credits to the cross-section arm.
    """
    got = verdicts("""
## F162 (D) — a task reads `completed` before its work is committed
Body with no marker of any kind.

### F162 is closed, measured inside the window at 1-second granularity
The drive ran.
""")
    assert got[162] == "RESOLVED"


def test_a_prose_verb_in_a_heading_is_not_a_verdict():
    """Blind spot 9, F317, found 2026-09-11 while computing the open severity-A count for the
    review page. The own-heading arm searched the whole heading for the cross-section
    vocabulary, and a heading is a SENTENCE ABOUT THE DEFECT, so ordinary English verbs read
    as verdicts. It cost F316 -- a severity-A finding whose title carries the domain verb
    `scheduler.resolve_reviewer` is named for -- which classified RESOLVED over its own
    `**Status:** open`, and did not even raise CONFLICT, because the verdict block takes
    `in_res` unconditionally. The census is what both scheduled windows queue from, so the
    finding was queued by neither.
    """
    got = verdicts("""
## F316 (A) — the reviewer resolved after a silent review excludes only the completer

**Status:** open — filed 2026-09-11.
""")
    assert got[316] == "OPEN"


def test_a_trailing_status_token_in_a_heading_is_still_a_verdict():
    """The other half of blind spot 9's repair, and the reason it is a narrowing rather than a
    deletion. F151 and F152 declare their close by ending the title in a status token, and
    neither has a `**Status:**` line to fall back on -- so a narrowing that dropped this shape
    would trade one false negative for two. Guards against over-correction, not under.
    """
    got = verdicts("""
## F151 — running migrations at startup silences the Hub's logging for the life of the process — FIXED
The repair shipped.
""")
    assert got[151] == "RESOLVED"


# --- negation ---------------------------------------------------------------------------


def test_a_negation_does_not_reach_across_a_line_break():
    """Regression guard, 2026-09-09. A finding's TITLE routinely negates while its verdict
    is a `**Status:**` declaration lines below. Widening the guard to tolerate intervening
    words let the title reach the marker, and six canonical Status-line verdicts silently
    became UNCLASSIFIED: F16, F27, F46, F58, F95, F100.
    """
    got = verdicts("""
## F16 (C) — `loop_id` is accepted on task creation but never echoed back

**Status:** fixed 3b4efd6
""")
    assert got[16] == "RESOLVED"


def test_a_negation_on_the_marker_s_own_line_does_suppress_it():
    """The reason the guard exists at all. F213's own heading says the twin "can never be
    resolved" -- the defect being stated, not a resolution. One intervening word ("be")
    defeated the original guard.
    """
    got = verdicts("""
## F213 (D) — a resubmitted edit stacks a duplicate proposal, and the twin can never be resolved
Filed, not fixed.
""")
    assert got[213] != "RESOLVED"


# --- conflict and the unknown -----------------------------------------------------------


def test_open_and_external_resolution_is_a_conflict_for_a_human():
    got = verdicts("""
## F5 (B) — a finding
**Status:** open

## F6 (C) — another finding
F5 was RETIRED by this change.
""")
    assert got[5] == "CONFLICT"


def test_a_line_naming_several_findings_is_bookkeeping_not_a_verdict():
    """Blind spot 8: six of the ledger's eight CONFLICTs, and four of them self-inflicted.

    The corrections table blind spot 5 wrote to record its own wrong verdicts is the exact
    shape below. `| **F65** | RESOLVED | **OPEN** | F67's resolution |` says F65 was WRONGLY
    read as resolved, and the cross-section arm read it as F65 being resolved -- so F65, F68,
    F149 and F168 were flagged CONFLICT by the one table that says they are open. A
    heading-format list did it to F296 and F266, and a sentence about how the word
    "superseded" had been used did it to F185 and F272.

    The rule is about a line naming two findings, not about tables: the sentence form
    ("markers -- F65, F68, F149 -- were being counted as resolved") did the same damage.
    """
    got = verdicts("""
## F65 (C) — a finding
**Status:** open

## F90 (C) — the census corrections, 2026-09-08
| | Was | Now | It had been reading |
|---|---|---|---|
| **F65** | RESOLVED | **OPEN** | F67's resolution |

Three findings with explicit open markers — F65, F68, F149 — were counted as resolved.
""")
    assert got[65] == "OPEN", "the table that records the wrong verdict must not restate it"


def test_a_single_finding_line_still_carries_its_verdict():
    """The guard above must stay narrow. F52 and F292 are the two conflicts that really are
    about their own finding, and both hang on a one-number line -- the summary row at the top
    of the ledger, and a sentence contrasting F292 with an unrelated fix.
    """
    got = verdicts("""
## F52 (A) — a finding
**Status:** open

## F91 (B) — the summary table
| **F52** — the posture never sees a git command | **fixed** `68459ea` |
""")
    assert got[52] == "CONFLICT", "a one-number line is still evidence a human must reconcile"


def test_a_quotation_that_wraps_is_still_quotation_in_another_section():
    """Blind spot 10 (F318). The cross-section arm dequoted one line at a time, so a quotation
    that wraps had its two marks on different lines and nothing paired them. F317's body quotes
    F316's title across a line break, and the quoted participle `resolved` flagged F316 --
    `**Status:** open`, severity A -- as CONFLICT, which the consumer reading only OPEN missed.
    """
    got = verdicts("""
## F316 (A) — a finding
**Status:** open

## F317 (B) — the classifier reads a verb in a title as a verdict
The own-heading arm searches the first line of every range. `F316`'s title is "the reviewer resolved
after a silent review excludes only the completer" -- there the participle is a domain verb.
""")
    assert got[316] == "OPEN", "a wrapped quotation of F316's title is not a verdict about it"


@pytest.mark.parametrize("boundary", ["", "## F92 (B) — the next finding"])
def test_a_stray_quote_mark_does_not_reach_past_its_paragraph(boundary):
    """Why blind spot 10 dequotes paragraphs and not the document, which F318 measured giving
    the right census on the day and rejected: the third QUOTED pattern pairs any two quote
    marks within 600 characters, so at document scope a stray mark -- an inch sign, a quote
    in a code span -- pairs with the next one ACROSS a paragraph or a section and blanks a
    real verdict between them. Both boundaries markdown gives a block must stop it.
    """
    got = verdicts(f"""
## F52 (A) — a finding
**Status:** open

## F91 (B) — a note
The old screen was 12" wide.
{boundary}
F52 is **fixed** in `68459ea`, see "the summary table".
""")
    assert got[52] == "CONFLICT", "a quote mark in another paragraph must not hide this line"


def test_a_finding_with_no_resolution_language_is_unclassified_not_resolved():
    """The 119. `UNCLASSIFIED` must mean "nobody has read this", never "probably fine" --
    four of the six ever sampled were real and unfixed.
    """
    got = verdicts("""
## F7 (C) — a finding nobody has ever triaged
It does a thing, and the thing is wrong.
""")
    assert got[7] == "UNCLASSIFIED"


# --- the structural invariant, against the real ledger -----------------------------------


def test_every_line_belongs_to_exactly_one_section():
    """The ratchet for the next segmentation defect.

    Content-free, so it does not move when the ledger grows. Both blind spot 5b (a heading
    that did not end its predecessor) and blind spot 6 (a block that ended one and joined
    nothing) violated it, and no vocabulary test could see either.
    """
    findings = Path(cf.PATH)
    if not findings.exists():  # pragma: no cover - the ledger is tracked, but do not assume
        pytest.skip(f"{findings} is absent")
    lines = cf.load()
    secs = cf.classify(lines)
    assert secs, "the ledger parsed to no sections at all"

    owner: dict[int, int] = {}
    for s in secs:
        for lo, hi in s["ranges"]:
            for i in range(lo, hi):
                assert (
                    i not in owner
                ), f"line {i + 1} claimed by both F{owner.get(i)} and F{s['num']}"
                owner[i] = s["num"]

    first = min(lo for s in secs for lo, _hi in s["ranges"])
    orphans = [i for i in range(first, len(lines)) if i not in owner]
    assert not orphans, (
        f"{len(orphans)} lines after the first finding belong to no section "
        f"(first at line {orphans[0] + 1 if orphans else '-'}) -- "
        "a heading is cutting a section without joining one"
    )
