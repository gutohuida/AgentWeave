---
name: backlog
description: Regenerate spec-queue/BACKLOG.html — the standing, interactive orientation page merging open findings and operator requests, each tagged with where it came from (found by driving, found by reading code, or asked for by the operator), whether it is ready to work, and its theme. Reports what moved since the last generation and triages the ledger's own inconsistencies. Use when the user says "update the backlog", "refresh the backlog page", "regenerate BACKLOG.html", "what's open", "how many findings are open", "what is the backlog", "add this to the backlog", or after anything that changes the ledger — filing a finding, closing one, proposing a change, archiving a change, or a loop window finishing. Callable by the FILL and FIX windows as step 0.
---

Regenerate the backlog page and say what changed. The page is derived, never authored.

## The one rule

**Never edit `spec-queue/BACKLOG.html` by hand.** It is generated from `scripts/drive/FINDINGS.md`,
`spec-queue/REQUESTS.md`, `openspec/changes/`, `spec-queue/` and the two `STATE-*.json`. A hand edit
is lost on the next generation and, worse, makes the page disagree with the ledgers it claims to
summarise — which is the exact failure `night-window.md` names: *"a backlog that cannot say what is
done is read as a backlog of everything."* If the page is wrong, the fix is in
`scripts/backlog_page.py` or in the source ledger, never in the HTML.

## The two ledgers it merges

| | |
|---|---|
| `scripts/drive/FINDINGS.md` | **defects.** Something the product does wrong, with a reproduction. Severity A/B/C/D. |
| `spec-queue/REQUESTS.md` | **what the operator asked for.** Not a defect — work wanted because they want it. `R<n>` ids. |

They are separate files on purpose: filing a request as a finding makes it pretend to be a defect,
and filing a defect as a request hides it from the night window's severity queue.

**A request that names a `Finding:` does not become its own row.** It re-sources that finding as
operator-originated and lends it the operator's own words. That is what stops an ask which has
already been measured into a finding from being counted twice. When the operator asks for something
new, add a request section — `REQUESTS.md` documents the format, and nothing else is required.

## The three columns the page adds

Neither ledger states these; the generator derives them, and each has an escape hatch.

- **Source** — `operator` · `drive` · `audit` · `review` · `unknown`. Inferred by scoring the
  Status line *and the body*, because for most of the corpus the Status line records fix state
  ("open (no fix commit references it)") and says nothing about how the finding was found. A
  `**Source:** <value>` line in the body overrides it.
- **Ready** — `proposed` · `ready` · `parked` · `triage` · `thinking`. **`proposed` is computed,
  never claimed**: a live change directory naming the F-number is the only thing that sets it, and
  it is the column that says whether the night window could actually build the item. A
  `**Ready:**` line overrides.
- **Theme** — keyword-scored into twelve groups. A `**Theme:**` line overrides. A wrong guess costs
  a reader one glance, which is why this is a reading aid and not a taxonomy.

When you file a finding whose provenance you know, **write the `**Source:**` and `**Theme:**` lines
in** rather than leaving them to inference. Inference is for the 373 findings that predate them.

---

## Putting something ON the backlog

Three different things, three different files. Nothing goes into `BACKLOG.html` directly.

### The operator asked for something → `spec-queue/REQUESTS.md`

Append a section. Nothing else is required, and no field is mandatory except the heading.

```markdown
## R<n> — <one line, in their words>
**Asked:** YYYY-MM-DD
**Theme:** Flows & loops
**Ready:** thinking
**Finding:** F377

<Quote them. Their phrasing is the point — it is what the page shows.>
```

- **Next `R<n>`:**
  ```bash
  py -3.11 -c "import re;t=open('spec-queue/REQUESTS.md',encoding='utf-8').read();print(max(int(n) for n in re.findall(r'^##\s*R(\d+)',t,re.M))+1)"
  ```
  Take the **maximum + 1**, never a count — `grep -c '^## R'` also matches the `## R<n>` line in
  this file's own format example and hands you a number that is already taken.
- **`Finding:` whenever the ask is already measured into a finding.** That re-sources the finding
  as operator-originated instead of creating a duplicate row. Getting this wrong is the one way to
  double-count the backlog.
- **`Ready:`** — `thinking` (default, no criticism), `ready` (a spec loop could take it),
  `proposed` (a change directory exists).
- Quote the operator rather than paraphrasing. A request is *theirs*; the page shows the quote.

### You found a defect → `scripts/drive/FINDINGS.md`

Append a section. The heading form is load-bearing — the generator parses it.

```markdown
## F<n> (A) — <one line saying what is wrong, not what to do about it>

**Status:** open. Filed YYYY-MM-DD by <who>, from <where>.
**Source:** drive
**Theme:** Task ledger

**What happened.** …
**Where.** file:line for each claim.
**Related:** F<n>, F<n>
```

- **Next `F<n>`:**
  ```bash
  py -3.11 -c "import re;print(max(int(n) for n in re.findall(r'^##\s*F(\d+)',open('scripts/drive/FINDINGS.md',encoding='utf-8').read(),re.M))+1)"
  ```
- **Severity** in the parenthetical: `A` wrong behaviour an operator will act on · `B` wrong or
  misleading surface · `C` friction or vestige · `D` minor. Omit it and the finding lands in the
  page's `?` group and the night window's severity queue can never reach it.
- **A `**Status:**` line is not optional.** Without one the generator counts the finding as open
  forever and warns about it, which is how the open number drifts upward.
- **Search before filing.** `--check` first, then grep the ledger for the symptom. Two of the four
  findings filed on 2026-09-17 were re-discoveries of three-day-old rows.

### Something got fixed or decided → edit the row in place

Set `**Status:** fixed <sha>` on the finding, or `**Ready:**` on the request. Do not delete rows —
a retired finding stays, marked `RETIRED <date>` in its title, and the page excludes it from the
counts while keeping it findable.

---

## Changing what the page SHOWS → `scripts/backlog_page.py`

Different job from putting something on the backlog. The page's columns, themes, grouping, filters
and warnings all live in the generator:

| Want | Edit |
|---|---|
| a new theme, or a theme that classifies badly | `THEMES` — keyword tuples, scored against title (×3) and body (×1) |
| provenance guessed wrong across many rows | `_DRIVE_WORDS` / `_AUDIT_WORDS` / `_REVIEW_WORDS`, or add a `**Source:**` line to the one row |
| a new readiness state | `READY`, and `classify_ready` |
| a new ledger warning | `consistency_warnings` |
| layout, filters, interaction | `TEMPLATE` — one f-string; **CSS and JS braces must be doubled** (`{{`/`}}`) |
| a new figure or snapshot field | `build()`'s `snapshot` dict and the `TEMPLATE.format(...)` call, together |

After any edit: `py -3.11 scripts/backlog_page.py` and check the printed report still makes sense.
The page is ~300 KB, so validate structure with a parser rather than by reading it.

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

## When the windows run

The backlog is read and written by two unattended windows and one person. Knowing the clock matters
here, because *"call it at close"* and *"step 0"* mean nothing without it, and because a refresh at
the wrong moment reports a ledger someone else is mid-way through changing.

```
07:10  AgentWeaveResearch    reads the web, outside the repo
08:55  AgentWeaveArmDay      arms the day — settles the branch, writes STATE-day.json, registers DayLoop
09:00  ├─ FILL   ──────────┐ AgentWeaveDayLoop, every 5 min, PROPOSES (never implements)
17:00  ┘                   │ unregisters itself
17:00  ├─ DECIDE ──────────┐ the operator. Writes APPROVALS.md, the only file FIX reads
23:00  ┘                   │
22:55  AgentWeaveArmNight    arms the night, same shape
23:00  ├─ FIX    ──────────┐ AgentWeaveNightLoop, every 5 min, BUILDS (never proposes)
07:00  ┘                   │ unregisters itself
07:00–09:00  margin
```

- **The two working loops are transient by design.** Each driver unregisters itself at its stop
  time; that is what stops a dead loop firing forever. Only the three arming tasks are permanent.
- **Each arm fires five minutes before its window.** `install-tasks.ps1` is the authority for those
  times, not this file and not the live Task Scheduler — the live ArmDay trigger had drifted to
  10:15 and silently cost three days of FILL windows (F380).
- **Nothing fires while the operator is logged out.** All tasks run as an interactive logon,
  because `gh`'s keyring and the Claude credentials only resolve there.
- **Both windows run `--check` as step 0 of iteration 1** — the first firing only — and again at
  close, before the final log entry.

Practical consequences for this skill:

- **During FILL or FIX, a window may be committing while you read.** Check
  `git status --porcelain` before committing a regenerated page; if a window is mid-iteration, say
  what the page shows and let the window commit its own refresh.
- **The best moment to refresh is DECIDE** (17:00–23:00): both loops are stopped, the night's work
  is in, and the operator is deciding from exactly this page.
- Run `Get-ScheduledTask -TaskName "AgentWeave*" | Get-ScheduledTaskInfo` to see what is armed and
  what fired last. A `State` of `Running` on a `*Loop` task means a window is live right now.

---

## Callable interface

Other skills and the loop windows may invoke this:

```
skill: "backlog"                    regenerate, report, offer to commit
skill: "backlog", args: "--check"   report only; non-zero exit means the ledger moved
```

**Both windows run `--check` as step 0 of iteration 1** (`day-window.md`, `night-window.md`). It is
one tool call and it stops the two failures this loop keeps having: filing something already filed,
and queueing a finding that has no proposal and therefore cannot be built.

**Never `cat` the HTML.** It is ~300 KB and reading it burns the context the iteration needs. The
printed report is the interface; the page is for the operator's browser.

**Call it again at close**, after the last queue item and before the final log entry — the window
has just changed the ledger, and the delta belongs in the log.

**Before proposing anything:** run `--check` and read the report. Two of the four findings filed on
2026-09-17 turned out to be re-discoveries of F361 and F363, caught only because the ledger was
searched first — and they were three days old.

## What the operator gets in the browser

Worth knowing, because it changes what is worth saying in chat. The page is interactive: filter
chips for source / ready / severity, a text filter over id, title and theme, a group-by toggle
between theme and severity, and collapsible groups. **Groups are closed at rest** and open
automatically while a filter is live — a 217-row page that opened flat was 17,000px of wall.

So do not read long lists out loud. Give them the delta, the warnings that matter, and let the page
carry the enumeration.

---

## Where the page lives

```
spec-queue/BACKLOG.html          the page — open it in a browser
spec-queue/REQUESTS.md           what the operator asked for; add asks here
scripts/drive/FINDINGS.md        defects; add findings here
scripts/backlog_page.py          the generator — edit this, not the page
spec-queue/README.md             the spec-queue contract, including this file's row
```

The page embeds its own counts as JSON in `<script type="application/json" id="backlog-data">`.
That is what the next run compares against, and what any other tool should read rather than
scraping the rendered numbers.
