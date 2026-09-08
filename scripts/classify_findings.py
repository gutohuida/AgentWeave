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
SEV_IN = re.compile(r"\b([ABCD])\b")

RESOLVED_PAT = [
    (re.compile(r"\bRETIRED\b"), "RETIRED"),
    (re.compile(r"\bRETRACTED\b"), "RETRACTED"),
    (re.compile(r"\bStatus\**:\**\s*\**\s*FIXED\b", re.I), "Status: FIXED"),
    (re.compile(r"\bSUPERSEDED\b"), "SUPERSEDED"),
    (re.compile(r"\bWITHDRAWN\b"), "WITHDRAWN"),
    (re.compile(r"\bNOT A DEFECT\b", re.I), "NOT A DEFECT"),
    (re.compile(r"\bis not a defect\b", re.I), "not a defect"),
    (re.compile(r"\bno longer reproduces\b", re.I), "no longer reproduces"),
]
EXT_WORD = re.compile(r"\b(RETIRED|RETRACTED|FIXED|SUPERSEDED|WITHDRAWN|closed|resolved)\b", re.I)
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
NEG_BEFORE = re.compile(r"\b(not|never|isn'?t|aren'?t|no|without|un)\W{0,12}$", re.I)

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
    heads = []
    for i, ln in enumerate(lines):
        m = HEAD.match(ln)
        if m:
            sm = SEV_IN.search(m.group(2))
            heads.append((i, int(m.group(1)), sm.group(1) if sm else "?", m.group(2)))
    sections = []
    for n, (i, num, sev, inner) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        sections.append({"num": num, "sev": sev, "inner": inner, "start": i, "end": end})
    span = {s["num"]: (s["start"], s["end"]) for s in sections}

    def hits(text, pats):
        out = []
        for pat, label in pats:
            for m in pat.finditer(text):
                if NEG_BEFORE.search(text[max(0, m.start() - 40) : m.start()]):
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
        raw = "\n".join(lines[s["start"] : s["end"]])
        body = dequote(raw)
        in_res, in_open = hits(body, RESOLVED_PAT), hits(body, OPEN_PAT)

        ext = []
        npat = re.compile(rf"\bF{num}\b")
        lo, hi = span[num]
        for i, ln in enumerate(lines):
            if lo <= i < hi or not npat.search(ln):
                continue
            cln = dequote(ln)
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
    print(f"RESOLVED on a STRONG marker : {strong}   (trustworthy)")
    print(f"RESOLVED on 'NOT A DEFECT'  : {len(weak)}   (weak -- >=1 known wrong, F187)")
    print("RESOLVED_ELSEWHERE          : lead only -- 3 of 5 hand-checked FALSE\n")
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
