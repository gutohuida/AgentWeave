"""Classify every finding in FINDINGS.md -- third instrument.

Blind spots corrected, each one found by measurement rather than review:

  1 (found by count mismatch, 271 vs 258) -- the heading regex demanded exactly
    `(A)`..`(D)`, hiding 13 sections: `F9 (A-)`, `F123 (C, open)`,
    `F165 (new, severity **B**)`, `F266 (C, was B)`, `F296 (C, harness)` ...

  2 (found by a zero that looked like a result) -- the cross-section search
    reused `Status:`-anchored patterns, so a drive record saying
    "F154 stays **FIXED**" could never match. The arm built for the
    F140/F154/F155 failure was structurally incapable of firing and reported 0.

  3 (found by MUTATION 1 failing) -- QUOTED HISTORY READ AS CURRENT STATUS.
    A section that withdraws its own banner quotes it:
      *"...so this entry stays open until somebody re-drives it."*
    The classifier matched "stays open" inside that quotation. Every section
    that narrates its own correction was at risk of reading OPEN. This is the
    same disease as the banners themselves -- believing a sentence without
    asking whether it is a claim being made or a claim being withdrawn.
    Fix: strip blockquotes, quoted spans and struck-through spans before
    matching STATUS vocabulary. Prose still counts; quotation does not.

  4 -- a section carrying BOTH an open marker and an external resolution is no
    longer silently forced either way. It is reported as CONFLICT, for a human.

  5 (found by an adversarial review, 2026-09-08) -- `HEAD` demanded a
    parenthetical, so 46 headings were invisible: 26 findings had no section at
    all, and 20 sections silently swallowed the next finding's text. Detail and
    the seven verdicts it corrupted are in classify().

  6 (found 2026-09-09 by writing this file's FIRST TEST) -- a continuation
    heading was skipped as a section and then dropped: 2,030 lines belonged to
    NO section, including `### F45 -- fixed 2026-08-25`, a finding's own
    resolution sitting outside the finding. Detail in classify().

  7 (found while fixing 6) -- the negation guard was line-local BY ACCIDENT and
    the accident was load-bearing. Blind spot 6's fix widened it, and a
    finding's TITLE promptly reached across a blank line to negate its own
    `**Status:** fixed` -- six canonical verdicts silently became UNCLASSIFIED.
    The line bound is now explicit; see NEG_BEFORE and `hits`.

**This file now has a test: `tests/test_classify_findings.py`.** Every case in it
is a defect that actually happened, its fixtures are synthetic so they do not
move when the ledger grows, and all seven guards above were mutation-checked on
2026-09-09 -- each mutation killed. Two of the tests were decorative when first
written and only the mutation run said so.
"""

import collections
import re
from pathlib import Path

PATH = str(Path(__file__).resolve().parent / "drive" / "FINDINGS.md")

# Verdict reliability, measured 2026-09-08 by hand-checking samples. Read this
# before believing any number this script prints.
#
#   STRONG markers (Status: FIXED / RETIRED / RETRACTED / SUPERSEDED /
#   WITHDRAWN) -- 9 sampled, 9 correct. These are `**Status:** fixed <sha>`
#   lines directly under the heading and can be trusted.
#
#   WEAK marker (NOT A DEFECT) -- 17 verdicts rest on this phrase and at least
#   one is WRONG: F187 matched "(F185 is the archived case of the same refusal,
#   not a defect in this one.)" -- a sentence about a DIFFERENT finding.
#
#   RESOLVED_ELSEWHERE -- 5 verdicts, and **3 of the 5 are false positives**,
#   hand-checked: F32 ("rather than fixed alongside F32" -- a negation this
#   script's guard does not catch), F108 ("the drive that closed this also
#   OPENED one"), F272 (a *note* was superseded, not the finding). Only F161 and
#   F162 are real. **Treat this arm as a lead for a human, never as a verdict.**
#
# The single failure mode behind every error above is the same: a sentence that
# mentions finding X while resolving finding Y. Prose is not a status field.
STRONG_MARKERS = {"Status: FIXED", "RETIRED", "RETRACTED", "SUPERSEDED", "WITHDRAWN"}

HEAD = re.compile(r"^#{1,4}\s+F(\d+)\s+\(([^)]*)\)")
# Every F-heading, parenthetical or not. Used for SECTION BOUNDARIES -- see classify().
ANY_HEAD = re.compile(r"^#{1,4}\s+F(\d+)\b")
SEV_IN = re.compile(r"\b([ABCD])\b")

# Split 2026-09-09. The two halves are not equally trustworthy and, since blind spot 6's
# fix, they no longer see the same text. STRONG markers are declarations; WEAK ones are
# prose that happens to contain a phrase. Only STRONG runs over merged continuation
# blocks -- see classify(). Measured reason: letting WEAK run there imported two false
# positives immediately (F197 "A declaration is not a defect", F164 "One new observation,
# not a defect"), neither a statement about the finding it would have resolved.
STRONG_PAT = [
    (re.compile(r"\bRETIRED\b"), "RETIRED"),
    (re.compile(r"\bRETRACTED\b"), "RETRACTED"),
    (re.compile(r"\bStatus\**:\**\s*\**\s*FIXED\b", re.I), "Status: FIXED"),
    (re.compile(r"\bSUPERSEDED\b"), "SUPERSEDED"),
    (re.compile(r"\bWITHDRAWN\b"), "WITHDRAWN"),
]
WEAK_PAT = [
    (re.compile(r"\bNOT A DEFECT\b", re.I), "NOT A DEFECT"),
    (re.compile(r"\bis not a defect\b", re.I), "not a defect"),
    (re.compile(r"\bno longer reproduces\b", re.I), "no longer reproduces"),
]
RESOLVED_PAT = STRONG_PAT + WEAK_PAT
EXT_WORD = re.compile(r"\b(RETIRED|RETRACTED|FIXED|SUPERSEDED|WITHDRAWN|closed|resolved)\b", re.I)
# BLIND SPOT 8, found 2026-09-10 by reading the EVIDENCE behind every CONFLICT rather than the
# count of them. Seven of the ledger's eight conflicts were false, and six had one cause: a line
# that names SEVERAL finding numbers is bookkeeping ABOUT the ledger, not a verdict about any one
# finding in it. The cross-section arm read such a line as evidence for every number on it.
#
# The worst case is self-inflicted. The corrections table that blind spot 5 produced,
#     | **F65** | RESOLVED | **OPEN** | F67's resolution |
# is a record that F65 was WRONGLY read as resolved -- and the scanner read it as F65 being
# resolved. Four sections (F65, F68, F149, F168) were flagged CONFLICT by the very table that
# says they are open; a heading-format list did it to F296, and one line of a severity note to
# F273. A verdict word on such a line belongs to at most one of the numbers and the scanner
# cannot tell which, so it must attribute it to none.
#
# Single-number lines are untouched, which is why F52 and F292 -- the two conflicts that really
# are about their own finding -- still flag. The direction of the error is also the safe one:
# suppressing a lead can only move a section toward OPEN or UNCLASSIFIED, never toward resolved.
MULTI_F = re.compile(r"\bF\d+\b")
OPEN_PAT = [
    (re.compile(r"Status[^\n]{0,80}\bopen\b", re.I), "Status: open"),
    (re.compile(r"\bfiled,? not fixed\b", re.I), "filed not fixed"),
    (re.compile(r"\bnot specced\b", re.I), "not specced"),
    (re.compile(r"\bUnverified, not retired\b", re.I), "unverified not retired"),
    (re.compile(r"\bstays open\b", re.I), "stays open"),
    (re.compile(r"\bstill open\b", re.I), "still open"),
    (re.compile(r"\bunqueued\b", re.I), "unqueued"),
    (re.compile(r"\bnot queued\b", re.I), "not queued"),
]
# Widened 2026-09-09. The old form required the negation to sit within 12 NON-WORD
# characters of the marker, so it caught "not resolved" and missed "can never be
# resolved" -- one intervening word defeated it. That exact sentence is F213's own
# heading ("the twin can never be resolved") and it read as a resolution. Now up to two
# short intervening words are tolerated; more than that and the negation is too far away
# to be reliably about this marker.
#
# Callers must pass ONLY the text from the start of the marker's own line -- see `hits`.
# The old `\W{0,12}` form was line-local by accident (12 non-word characters cannot span a
# word), and widening it exposed that the constraint had been doing real work: a finding's
# TITLE routinely negates, while its verdict is a `**Status:**` declaration lines below.
# `## F16 (C) — ... but never echoed back` / `**Status:** fixed 3b4efd6` then reads as a
# negated "fixed". Six canonical Status-line verdicts went UNCLASSIFIED that way (F16, F27,
# F46, F58, F95, F100) before the line bound was made explicit rather than incidental.
NEG_BEFORE = re.compile(
    r"\b(not|never|cannot|can'?t|isn'?t|aren'?t|no|without|un)\b(?:\W+\w{1,6}){0,2}\W*$", re.I
)

# --- blind spot 3: quotation is not assertion -------------------------------
QUOTED = [
    re.compile(r"\*\"[^\"]{0,600}\"\*", re.S),  # *"..."*  italic quotation
    re.compile(r"\*\*\"[^\"]{0,600}\"\*\*", re.S),
    re.compile(r"[\u201c\u201d\"][^\"\u201c\u201d]{8,600}[\u201c\u201d\"]", re.S),
    re.compile(r"~~[^~]{0,600}~~", re.S),  # struck-through = withdrawn
]


def dequote(text):
    """Blank out quoted and struck-through spans, preserving line structure."""
    out = text
    for pat in QUOTED:
        out = pat.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), out)
    # blockquote lines
    out = "\n".join(" " * len(ln) if ln.lstrip().startswith(">") else ln for ln in out.split("\n"))
    return out


def load(path=PATH):
    return open(path, encoding="utf-8", errors="replace").read().splitlines()


def classify(lines):
    # Two passes, because a heading does two jobs and they are not the same job.
    #
    # BLIND SPOT 5, found 2026-09-08 by an adversarial review of this script:
    # `HEAD` requires a parenthetical, and **46 headings in this ledger do not have
    # one** -- `## F77 — an agent has no way to address the operator`. Consequences,
    # both measured:
    #   (a) 26 finding numbers had NO section at all and were invisible to every
    #       census ever run here. One of them, F77, is `**Status:** open`.
    #       The real census is 297, not 271.
    #   (b) far worse: a heading the scanner cannot see does not END the previous
    #       section, so an em-dash finding's whole body was appended to whichever
    #       paren-headed finding preceded it. F71's "section" absorbed F72-F86 --
    #       1,223 lines. Seven verdicts were computed from a marker belonging to a
    #       different finding, four of them on the STRONG arm this file's header
    #       calls trustworthy: F65, F68, F135, F149, F152, F164, F168. F168 read
    #       RESOLVED off `## F154 — Status: **FIXED**`, two clauses after stating
    #       its own "Not queued."
    #
    # So: ANY `F<n>` heading is a boundary, but only a number with no parenthetical
    # heading anywhere becomes a section of its own. That distinction matters because
    # `### F63 — Resolution, 2026-08-26` is a continuation of F63, not a new finding.
    #
    # BLIND SPOT 6, found 2026-09-09 by writing this file's first test. The rule above
    # stops a continuation DOUBLE-COUNTING and then drops it on the floor: a heading
    # skipped as a section still cut the previous one, so its lines belonged to **no
    # section at all**. Measured on this ledger: 30 continuation headings, **2,030
    # orphaned lines**, including `### F45 — fixed 2026-08-25` and `### F162 is closed`
    # -- a finding's own resolution, sitting outside the finding. Reachable only by the
    # cross-section arm this file's header calls a lead and never a verdict.
    # Blast radius when merged back: 3 verdicts move (F164, F168, F197). Smaller than
    # blind spot 5's seven, and measured rather than asserted.
    #
    # The fix generalises past the case that was found: **every heading block for a
    # number belongs to that number.** That also absorbs a second *parenthetical*
    # heading for one finding, which the old `seen` guard orphaned the same way.
    bounds = []  # every heading -- these cut sections
    for i, ln in enumerate(lines):
        m = ANY_HEAD.match(ln)
        if m:
            pm = HEAD.match(ln)
            bounds.append((i, int(m.group(1)), pm.group(2) if pm else None))

    ranges = collections.defaultdict(list)  # num -> every block of lines that is its text
    first_paren = {}  # num -> (line, inner) of its first parenthetical heading
    anchor = {}  # num -> line of its first heading of any kind
    for n, (i, num, inner) in enumerate(bounds):
        end = bounds[n + 1][0] if n + 1 < len(bounds) else len(lines)
        ranges[num].append((i, end))
        if inner is not None and num not in first_paren:
            first_paren[num] = (i, inner)
        anchor.setdefault(num, i)

    sections = []
    for num in sorted(ranges, key=lambda k: anchor[k]):
        # The parenthetical heading is the finding's own; an em-dash-only finding
        # anchors on its first heading. Either way the TEXT is every block above.
        i, inner = first_paren.get(num, (anchor[num], None))
        sev = "?"
        if inner:
            sm = SEV_IN.search(inner)
            sev = sm.group(1) if sm else "?"
        else:
            # No parenthetical: many of these state severity in the body instead.
            end = next(hi for lo, hi in ranges[num] if lo == i)
            body_head = "\n".join(lines[i : min(i + 8, end)])
            bm = re.search(r"\*\*Severity:?\*?\*?\s*([ABCD])\b", body_head)
            sev = bm.group(1) if bm else "?"
        sections.append(
            {"num": num, "sev": sev, "inner": inner or "", "start": i, "ranges": ranges[num]}
        )
    span = {s["num"]: s["ranges"] for s in sections}

    def hits(text, pats):
        out = []
        for pat, label in pats:
            for m in pat.finditer(text):
                # Only the marker's own line may negate it -- a title that says "never"
                # has no authority over a `**Status:**` line two lines below it.
                if NEG_BEFORE.search(text[text.rfind("\n", 0, m.start()) + 1 : m.start()]):
                    continue
                out.append(
                    (
                        label,
                        text[: m.start()].count("\n") + 1,
                        re.sub(r"\s+", " ", text[max(0, m.start() - 70) : m.end() + 70]),
                    )
                )
        return out

    results = []
    for s in sections:
        num = s["num"]
        # The primary block is the finding's own statement; continuation blocks are drive
        # narratives, where "not a defect" is far more often about something the drive met
        # along the way. So WEAK prose fires only on the primary block -- exactly the text
        # it was calibrated against -- while STRONG declarations and OPEN markers read the
        # whole finding. OPEN reads everything deliberately: it is the conservative
        # direction, and a wrongly-open finding costs a read, not a missed defect.
        primary = next(rng for rng in s["ranges"] if rng[0] == s["start"])
        body_primary = dequote("\n".join(lines[primary[0] : primary[1]]))
        body_all = dequote("\n".join("\n".join(lines[lo:hi]) for lo, hi in s["ranges"]))
        in_res = hits(body_all, STRONG_PAT) + hits(body_primary, WEAK_PAT)
        in_open = hits(body_all, OPEN_PAT)

        # A heading of the finding's OWN blocks that carries resolution vocabulary --
        # `### F162 is closed, measured inside the window`, `### F45 — fixed 2026-08-25`.
        # Needed because blind spot 6's fix moves these lines INSIDE the section, and the
        # in-section vocabulary is narrower than `EXT_WORD`: without this, merging the
        # block correctly would drop F161 and F162 from a verdict to no signal at all --
        # and those two are the only true positives this file's header credits to the
        # cross-section arm. This is structural evidence, not prose: it fires on a
        # heading line that ANY_HEAD already matched to THIS finding's number, which is
        # why it may be trusted where the same words in a sentence may not.
        for lo, _hi in s["ranges"]:
            head_line = dequote(lines[lo])
            m = EXT_WORD.search(head_line)
            if m and not NEG_BEFORE.search(head_line[max(0, m.start() - 40) : m.start()]):
                in_res.append(
                    ("own heading: " + m.group(1).upper(), lo + 1, lines[lo].strip()[:200])
                )

        ext = []
        npat = re.compile(rf"\bF{num}\b")
        own = span[num]
        for i, ln in enumerate(lines):
            if any(lo <= i < hi for lo, hi in own) or not npat.search(ln):
                continue
            cln = dequote(ln)
            # blind spot 8: a line naming more than one finding is bookkeeping, not a verdict.
            if len(set(MULTI_F.findall(cln))) > 1:
                continue
            m = EXT_WORD.search(cln)
            if not m or NEG_BEFORE.search(cln[max(0, m.start() - 40) : m.start()]):
                continue
            ext.append((m.group(1).upper(), i + 1, ln.strip()[:200]))

        if in_res:
            v, why = "RESOLVED", in_res[0]
        elif in_open and ext:
            v, why = "CONFLICT", (in_open[0], ext[0])
        elif in_open:
            v, why = "OPEN", in_open[0]
        elif ext:
            v, why = "RESOLVED_ELSEWHERE", ext[0]
        else:
            v, why = "UNCLASSIFIED", None
        results.append(
            {
                "num": num,
                "sev": s["sev"],
                "inner": s["inner"],
                "line": s["start"] + 1,
                # Exposed so a caller can check the segmentation itself. Both blind spots
                # 5b and 6 were segmentation defects that every vocabulary check passed.
                "ranges": s["ranges"],
                "verdict": v,
                "evidence": why,
                "n_ext": len(ext),
                "ext": ext[:4],
            }
        )
    return results


if __name__ == "__main__":
    res = classify(load())
    strong = sum(
        1 for x in res if x["verdict"] == "RESOLVED" and x["evidence"][0] in STRONG_MARKERS
    )
    weak = [x for x in res if x["verdict"] == "RESOLVED" and x["evidence"][0] not in STRONG_MARKERS]
    elsewhere = [x for x in res if x["verdict"] == "RESOLVED_ELSEWHERE"]
    print(f"RESOLVED on a STRONG marker : {strong}   (see header -- NOT fully trustworthy)")
    print(f"RESOLVED on 'NOT A DEFECT'  : {len(weak)}   (weak -- >=1 known wrong, F187)")
    print(f"RESOLVED_ELSEWHERE          : {len(elsewhere)}   lead only, hand-check each")
    print("  " + ", ".join(f"F{x['num']}" for x in elsewhere))
    print(
        "\nNumbers are COMPUTED. Do not copy them into a document that this file\n"
        "then reads back -- writing the census into FINDINGS.md changes the census.\n"
    )
    tally = collections.defaultdict(collections.Counter)
    for r in res:
        tally[r["sev"]][r["verdict"]] += 1
    print(f"{len(res)} finding sections\n")
    for sev in ["A", "B", "C", "D", "?"]:
        if tally[sev]:
            t = tally[sev]
            print(
                f"  severity {sev}: total {sum(t.values()):3d}   "
                + "  ".join(f"{k}={v}" for k, v in sorted(t.items()))
            )
    for want in ["CONFLICT", "OPEN", "RESOLVED_ELSEWHERE", "UNCLASSIFIED"]:
        print(f"\n--- {want} ---")
        for sev in ["A", "B", "C", "D", "?"]:
            rows = [r for r in res if r["verdict"] == want and r["sev"] == sev]
            if rows:
                print(
                    f"  {sev} ({len(rows)}): " + ", ".join(f"F{r['num']}@{r['line']}" for r in rows)
                )
