---
name: backlog
description: Regenerate spec-queue/BACKLOG.html — the standing orientation page showing open findings by severity, the drain, what each loop window is holding, and which file is the authority for what. Reports what moved since the last generation and triages the ledger's own inconsistencies. Use when the user says "update the backlog", "refresh the backlog page", "regenerate BACKLOG.html", "what's open", "how many findings are open", "what is the backlog", or after anything that changes the ledger — filing a finding, closing one, proposing a change, archiving a change, or a loop window finishing. Callable by the FILL and FIX windows at close.
---

Regenerate the backlog page and say what changed. The page is derived, never authored.

## The one rule

**Never edit `spec-queue/BACKLOG.html` by hand.** It is generated from `scripts/drive/FINDINGS.md`,
`openspec/changes/`, `spec-queue/` and the two `STATE-*.json`. A hand edit is lost on the next
generation and, worse, makes the page disagree with the ledgers it claims to summarise — which is
the exact failure `night-window.md` names: *"a backlog that cannot say what is done is read as a
backlog of everything."* If the page is wrong, the fix is in `scripts/backlog_page.py` or in the
source ledger, never in the HTML.

---

## Step 1 — Regenerate

```bash
py -3.11 scripts/backlog_page.py
```

`py -3.11`, never bare `python` — the bare interpreter here is a venv that behaves differently
(`CLAUDE.md`, Testing).

It prints three blocks: the file it wrote, `SINCE LAST GENERATION`, and `LEDGER WARNINGS`.

Two other modes:

| | |
|---|---|
| `--check` | reports without writing; **exit 1** if the ledger has moved since the page was built. Compares the data, not the rendered bytes — the timestamp changes every run, so a byte comparison would always say stale. |
| `--quiet` | writes and prints only the path. For a caller that wants the side effect, not the report. |

---

## Step 2 — Read the delta out loud

`SINCE LAST GENERATION` is the part the operator actually wants. Report it in your own words, and
**say plainly when nothing moved** — "nothing moved since the last generation" is a real answer and
a useful one, not a failure to find something.

Two lines deserve comment rather than restatement:

- **`newly filed: F…`** — name what they are, not just their numbers. The operator asked for a
  backlog, not a diff.
- **`unbuilt changes` changed** — this is the throttle. Say what it means for tomorrow: **2 or more
  → no spec loop runs at all**, **1 → one loop**, **0 → two loops**. A drain that just went from 1
  to 2 silently cancels tomorrow's proposing, and nothing else announces that.

---

## Step 3 — Triage the warnings; do not just repeat them

`LEDGER WARNINGS` is the script noticing things it cannot resolve. None is conclusive alone. Decide
which, if any, is worth the operator's attention now:

| Warning | What it usually means | Act on it when |
|---|---|---|
| *N findings have no `**Status:**` line* | Old entries predating the convention. They are **counted as open**, so they inflate the open number. | The count grew — a window filed something and forgot the Status line. |
| *N findings declare no severity anywhere* | Same vintage. The night window orders by severity, so an unrated finding is never reached by the A-before-B-before-C queue. | One of them is recent, or the operator is asking why something is never picked up. |
| *N findings read 'open' but name a commit sha* | The classic stale row: fixed, and the Status line never updated. **This is the single most likely reason the open count is too high.** | Always worth mentioning. Never "fix" it by editing the Status line on a hunch — verify against the code first, the way the night playbook's status sweep does. |
| *unbuilt change carries a STOPPED note and still counts toward the drain* | A change was abandoned mid-flight but its unticked tasks still throttle the spec loop. | Always mention — it is suppressing proposing for a change nobody intends to build. |

**Do not repair the ledger from inside this skill unless the user asks.** Reporting that 24 rows may
be stale is useful; rewriting 24 Status lines without verifying each against the code is how the
ledger became untrustworthy in the first place. If they want the sweep, that is real work with a
verification step per row, not a side effect of refreshing a page.

---

## Step 4 — Commit, if the page changed

The page is tracked, so a regeneration is a real diff. Commit it with whatever prompted the refresh
rather than on its own where possible — a commit that only bumps a timestamp is noise.

```bash
git add spec-queue/BACKLOG.html
```

Stage explicitly. **Never `git add -A`** in this repo (`CLAUDE.md`, Critical rules).

If the only difference is the `generated` stamp and the HEAD sha — which `--check` will have
reported as `current` — there is nothing worth committing. Say so and leave the tree alone.

---

## Callable interface

Other skills and the loop windows may invoke this:

```
skill: "backlog"              regenerate, report, offer to commit
skill: "backlog", args: "--check"   report only; non-zero exit means the ledger moved
```

**For the FILL and FIX windows:** call this at close, after the last queue item and before the
final log entry. The window has just changed the ledger — filed findings, ticked tasks, maybe
archived a change — and the page is the cheapest place the next reader learns that. Use the plain
form so the delta lands in the log.

**Before proposing anything:** run `--check` and read the page first. It is the cheapest way to
find out that what you are about to file is already F-something. Two of the four findings filed on
2026-09-17 turned out to be re-discoveries of F361 and F363, found only because the ledger was
searched first — and they were three days old.

---

## Where the page lives

```
spec-queue/BACKLOG.html          the page — open it in a browser
scripts/backlog_page.py          the generator — edit this, not the page
spec-queue/README.md             the spec-queue contract, including this file's row
```

The page embeds its own counts as JSON in `<script type="application/json" id="backlog-data">`.
That is what the next run compares against, and what any other tool should read rather than
scraping the rendered numbers.
