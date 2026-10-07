# Approvals

The only file the FIX window (23:00-07:00) reads to learn what the operator said. Written by the
DECIDE session, not by hand and not by either scheduled window. Format and semantics: `README.md`
in this directory.

```
- APPROVED  <change-name>   optional note
- REVISING  <change-name>   what needs to change
- REJECTED  <change-name>   why
ORDER: <change-name>, <change-name>, F156      (optional, that night only)
APPROVED-FIXES: F489, F492                      (optional, Tier-0 findings built with no spec)
NOTHING TONIGHT                                 (optional, stops the window)
```

Newest day first. Days below the newest are history and are not read.

---

## 2026-10-07

Written in an interactive session with the operator present. The spec-flow plan (operator-approved
2026-10-07) is being built interactively in the repository root, change by change, so the root is
not free for a cycle branch tonight.

NOTHING TONIGHT

---

## 2026-10-06

Written ~22:58 in an interactive session with the operator present (operator: "Run, but fence F510").
No new APPROVED rows: the window works the backlog as normal, with these fences.

- **F510 is the trial's, not tonight's.** It was built on the trial Hub `:8010` (document
  `spec/changes/a-review-turn-reviews-the-branch-tip-where-evidence-does-not-govern-the-merge/`); its
  work is already on master (`3bae149`, `4f2face`). Do not build, re-spec or archive it.
- **F520 and F521 are in-session work, not tonight's.** Filed tonight from the trial; their fixes are
  the interactive session's. Do not build them.
- `hub/tests/test_a_review_turn_reviews_the_branch_tip.py` is the trial's file. If it is red, record it in
  the log and leave it; do not edit it.
- Do not start, stop, restart or call the trial Hub `:8010` (as always), and do not touch
  `.agentweave/checks/` or `.agentweave/tasks/` worktrees.

## 2026-10-05

There is no review page. This was written in an interactive session with the operator present (operator: "Credits change +
F489"). F492 stays out: its fix weakens secret redaction (a 40-character lowercase-hex key would
survive), so it is the operator's call, awake.

- APPROVED  a-copilot-one-shot-records-its-credits   carried from 10-04, as R3 and the Opus review's seven fixes left it; its drive spends at most two Copilot Free calls on `:8010`
APPROVED-FIXES: F489

**Added ~22:10 in an interactive session (`/autonomous-prep`, operator present).** The 10-04 night
never ran: its arm cut `autonomous/2026-10-04-daily` and exited 1. That branch was deleted with
the operator's OK ("Delete it"), so tonight cuts a fresh branch from master. Operator: "C1b first".

- APPROVED  a-task-may-serve-a-whole-slice   (C1b, Tier 1) as committed in `0fcdce7`. D1–D5 are the
  operator's choices from handoffs 0166–0168: "Block at every rigor", "Remove the cap", no override.
  Build order is its `tasks.md`:
  - 0.1: one **grounded** review round, every claim cited at `file:line`, recorded as a short
    "Review round" section in `design.md`.
  - 1.1: a `mode=ro` count on `:8000`'s DB only.
  - 1.2: drive D (`testbed/drive-slices/drive_d.py`, built from `drive_c.py` and
    `stub_provider.py`), run and FAILING on `:8010` before the build.
  - 2–5: the build, test-first.
  - 6.1–6.3: suites, drive D passing, the METRICS row.
  - Then archive and sync.

  Pre-authorised: if the review round finds a defect a design decision does not already settle,
  fix the spec when the fix is one sentence. Otherwise file an OPEN `DECISIONS.md` row, stop C1b,
  and move to the next ORDER item.

  Environment for C1b:
  - `:8010` is still up from the interactive session: PID 13972, on `f17c8e0`-equivalent code,
    using the trial-profile DB and a fake `MY_F490_KEY`.
  - Restart it from `hub/` on tonight's branch before drive D; `.claude/reference/hubs.md` has the
    runbook.
  - The drive's stub is `py -3.11 testbed/drive-slices/stub_provider.py`. It is gitignored but
    present in this working tree.

ORDER: a-task-may-serve-a-whole-slice, a-copilot-one-shot-records-its-credits, F489

When the ORDER is exhausted, the window does **not** stop. It continues with the playbook default:
other unarchived changes, then open findings by severity.

## 2026-10-04

No review page. **Written in an interactive session with the operator present**, after the morning
briefing. The operator answered all five open `DECISIONS.md` rows; each is recorded there as DECIDED
with its evidence. What tonight needs from them:

- APPROVED  a-copilot-one-shot-records-its-credits   as R3 and the Opus review's seven fixes left it (`copilot-oneshot-credits-approve`). Its drive spends at most two Copilot Free calls on `:8010`.
- APPROVED  a-copilot-agent-uses-hooks-and-its-own-agents   amendment D8a (F484) and D9a (F485) only, added 2026-10-04 ~18:00 in an interactive session (operator: "APPROVED"), as the verification round and the pre-approval Opus review left it (`8c3cde9`); write-tool flags stay stripped outside Full access. Built in the same session; tonight does not touch it (see the withdrawn F488 bullet below).
- APPROVED  a-secret-split-across-two-events-is-still-scrubbed   (F488) added 2026-10-04 ~18:40 in an interactive session (operator: "APPROVED, fold the log in"), as R3 and the pre-approval Opus review left it (`cdb4a1d`). Operator questions decided: no hold, m = min(8, len//2) with no floor; join across tool and other cards; D6 (scrub the session.error log line) folded in. Built in the same session; tonight does not touch it.
- APPROVED  a-file-path-is-not-redacted-as-a-credential   added 2026-10-04 in an interactive session (operator: "APPROVED"), as R4 left it after the pre-approval Opus review; option (a), the 16-character letter-and-digit segment rule. Being built in the same session; if `openspec/changes/archive/` holds it, there is nothing to do.
- **`worker-spend-counts-against-the-budget`'s next round gains a real task** for the per-`workers`-line
  credit sums, with a test and a spec-delta line (`copilot-oneshot-credits-oq1`).
- **Slice 5 group A is unblocked, subagent scenarios included** (`ghcp-s5-subagent-capture`). The 10-04
  re-capture delivered `subagent.started`/`completed`, and `hub/tests/fixtures/copilot/subagent.jsonl`
  is now that capture. A real dispatch needs the built-in's exact lowercase id and a model the plan
  offers (`claude-haiku-4.5` on Free). Group A's own drive (7.1) must prompt that way. The D8 follow-up
  and F484 are recorded on the row.
- **`the-shell-judge-reads-a-word-whole`**: task 1.7c's two escape bullets become `(POSIX CI)`, and
  design D7's "harmless readings" claim is corrected to name F487's drive-letter-host case
  (`shell-judge-escape-scope-1-7c`, (b)). Task 2.3 is rewritten to compare the whole `hub/tests/`
  suite before and after the change: every moved outcome must be one of task 1.8's rows or a new row
  (`shell-judge-2-3-eight-files`, (c)). That unblocks 1.7c, 2.2a, 2.3 and then 4.1.
- ~~**F488 first**~~ **Withdrawn from tonight, 2026-10-04 ~15:30** (operator, interactive: "Let's
  finish it right now", then "Yes, do it now" for F488). The interactive session owns, today, all of
  the Copilot work: **F488** (its own change, `a-secret-split-across-two-events-is-still-scrubbed`),
  **slice 5 `a-copilot-agent-uses-hooks-and-its-own-agents` entire** (group A build and drives, the
  F484 amendment to group B, the F485 investigation for group D), and **F484/F485**. **Tonight does
  not touch any of them**, whatever their state, and does not compose them from the playbook default
  either. Tonight takes the playbook default **minus** those: other unarchived changes (the APPROVED
  `a-copilot-one-shot-records-its-credits` first), then open findings by severity, then APPROVED rows.

## 2026-10-03

No review page today. **Written in an interactive session with the operator present.** The operator
asked for a build window today, 13:00-22:00, run exactly like the night window (night-window.md, FIX),
*"focus on the ghcp implementation"*, and asked that the queue be decided now. It was armed by hand
(`arm-cycle.ps1 -Window night -StartAt 13:00 -Until 22:00`) on `autonomous/2026-10-03-daily`, and its
STATE was seeded with the queue below, so it skips compose. **Tonight's 22:55 arm continues the same
branch and reads this same section**: tonight follows this ORDER from wherever the day stopped.

Copilot slices 1-4 are archived (`each-runner-cli-is-one-adapter` 10-01, `a-copilot-agent-runs-over-acp`
09-30, `a-run-reaches-the-hub-without-mcp` and `a-copilot-run-shows-its-credits` 10-02), so slice 5's
gate (`ghcp-d5-order`: "not before slice 4 is archived") is met. Slice 5 is the only ghcp work left.

- **Slice 5, `a-copilot-agent-uses-hooks-and-its-own-agents`, one queue item per group**, in the
  change's own value order A, C, B, D, so that stopping anywhere leaves whole groups. Each group item
  takes its own tests-first tasks (group 1) with its build tasks; the untagged task 2.8 rides with A;
  the UI tests in 1.14 ride with the group whose UI they test; 6.1 closes the last group built. First,
  inside A: re-read design.md's *Required of slices 1-4* against the slices as built and fix every
  "(rebase at IMPL)" site. **Task 1.1 is real Copilot calls** (Free plan, ~5 calls); if a type is not
  delivered, stop group A as the task says and go on to C.
- **Group C is the security-sensitive one** (a provider key in a run's environment; the exact-value
  scrub, the whole-prefix strip, the `urlsplit` check). It runs on Opus.
- **Drive (7.x) on `:8010` only, with a Copilot agent on the Free plan's Auto model, inside the task's
  own 12-call budget.** That is the exception to the "every drive binds claude-haiku-4-5" limit, for
  Copilot agents in this change only. **Task 7.6 stays unchecked**: it needs the operator's dedicated
  capped Anthropic key. Record "not driven: no key".
- **No archive.** Task 8.1 needs every kept group's tasks checked, which includes 7.6. The change
  waits for the operator at that point; do not tick, waive or archive it.
- **Then the Copilot follow-up the operator decided on 10-02** (`DECISIONS.md` `copilot-oneshot-credits`:
  a Copilot one-shot records its credits from `session.usage_checkpoint`, "a follow-up change, not this
  one"): R1-R3 and the Opus review, as the operator's explicit exception to "this window writes no
  proposals" (as with F478 on 10-01). **No `-impl`**: the operator approves it first.
- **Then the remainder of the 10-02 night's work**: `the-shell-judge-reads-a-word-whole` (20/41), then
  `a-drive-or-a-home-variable-names-a-directory-by-itself` (12/31), both approved (`B4-approve`).

Merge note for the operator, not for the window: slice 5 adds a migration (`runners.provider_config`)
and UI. Once merged, `:8000` runs the migration on its next restart, and the rebuilt bundle reaches the
live app on its next reload.

### Tonight (the 22:55 arm, 23:00-07:00) — decided now, because the operator is away all day

The operator will not be back before tonight's arm, so nothing below waits for them.

- **Compose keeps the afternoon's queue rather than rebuilding it from `ORDER:`.** The arm resets
  `STATE-night.json` to compose, but the afternoon's last state is one commit back. Read it with
  `git show <the arm commit>^:.claude/autonomous/STATE-night.json` (the arm commit is the newest
  `arm(night): 2026-10-03` in `git log`). Carry every item that is not `done` into tonight's queue
  **verbatim and in order**: same ids, same `model` overrides (group C stays on Opus), same detail.
  Then append any `ORDER:` entry the carried queue does not already cover. Read the afternoon's last
  log entry for where it stopped mid-item. The `ORDER:` line below is the fallback only if that
  state cannot be read.
- **Step 3's suite gate is satisfied by CI.** The branch was built all afternoon under the driver's
  CI check, so if the CI verdict for the inherited tip is `success`, record that and skip the local
  full Hub suite run. Last night that run cost 9 firings and 46 minutes. If CI is `failure`, fixing
  it is the first item, as the playbook says. If it is unfinished, read the newest finished run.
- **When the queue empties, take the backlog default** (unarchived changes, then open findings by
  severity), not a null `next_action`. A night that finishes early should keep working.
- **The weekly limit resets 2026-10-04 15:00.** A usage-limit pause is acceptable tonight: the driver
  waits it out, and there is no need to slow down to avoid one.
- **Decisions still go to `DECISIONS.md` as `OPEN` rows**, and the window moves on to the next item.
  Nobody will answer before morning.
- **No merge.** Leave the branch for the operator. The day arm is disabled, so nothing else will
  merge it either.

ORDER: a-copilot-agent-uses-hooks-and-its-own-agents, copilot-oneshot-credits-r1, copilot-oneshot-credits-r2, copilot-oneshot-credits-r3, copilot-oneshot-credits-rev, the-shell-judge-reads-a-word-whole, a-drive-or-a-home-variable-names-a-directory-by-itself


## 2026-10-01

No review page today. **Written in an interactive session with the operator present**, before the
22:55 arm. The operator asked to prepare tonight's run and answered three questions (AskUserQuestion,
verbatim choices quoted). This restates the 2026-09-30 `ORDER:` for tonight, with what finished
today taken out and three changes to it:

- **Done since 09-30, not queued:** `each-runner-cli-is-one-adapter` (slice 1, archived `eec4085`).
  `a-run-reaches-the-hub-without-mcp` (slice 3) is built, driven and CI-green (`db1a331`) but **not
  in the queue**: its open tasks are 10.1 (the operator's work-PC checks), 10.2 (archive, after 10.1)
  and 9.10 (blocked by F478). Do not tick, waive or archive any of them.
- **`ghcp-d5-order` is relaxed for tonight only** — *"Build on unarchived slice 3 (Recommended)"*:
  slice 4 (`a-copilot-run-shows-its-credits`) may start on slice 3 as it stands in the tree, built
  but unarchived. Slice 5 still comes only after slice 4 is **archived** (a slice left unfinished
  stops the ghcp run; go on to the 09-27 remainder). Slice 4's and 5's archives sync their deltas
  on top of `openspec/specs/` as it stands; where a delta touches a requirement slice 3's
  unsynced delta also changes, stop that archive and say so in the log rather than merge by hand.
  Slice 5's task 7.6 is still skipped (spends real money; needs the operator's capped key).
- **F479 first** — *"Yes, first item (Recommended)"*: the one-line fix (drop `str_replace` from
  slice 2's Copilot spec-turn `--excluded-tools`, with a test), footed in `scripts/drive/FINDINGS.md`.
- **F478's design rounds next** — *"Queue R1–R3, first (Recommended)"*: R1 explores and writes a
  proposal under `openspec/changes/` (it is the URL reader of the archived `a-url-is-not-a-path`; check
  whether `the-shell-judge-reads-a-word-whole`, also queued below, already owns that code and say how
  the two order); R2 and R3 each independently re-derive it against the code; `-rev` is the
  adversarial Opus review. The night window normally writes no proposals; these four items are the
  operator's explicit exception for tonight (as `who-owns-a-loops-queue-R1..R3` were on 09-14).
  **No `-impl` tonight**: the operator approves it first. It unblocks slice
  3's task 9.10.

`an-agent-can-be-paused-and-keeps-its-input` is still `REVISING` and not in the queue.

- APPROVED  an-arguments-file-written-from-powershell-is-the-hubs-own   added 2026-10-02 in an interactive session
  (operator: *"Option A. Approve."*), with Open questions 1 and 2 as recommended (no bash form; the location
  residual accepted). **Built interactively on `master`, not by the night window**; it is not in tonight's ORDER.

ORDER: F479, F478-r1, F478-r2, F478-r3, F478-rev, a-copilot-run-shows-its-credits, a-copilot-agent-uses-hooks-and-its-own-agents, the-corpus-is-indexed-arranged-and-adopted-from-the-app, a-specification-is-read-in-results-that-fit, input-the-hub-accepted-is-answered-as-accepted, charters-are-named-once-and-an-empty-one-says-so, a-dialog-takes-the-keyboard-when-it-opens, the-app-window-keeps-the-operators-preferences, a-run-records-that-its-calls-were-allowed, drift-is-scanned-and-answered-on-the-document, a-retried-firing-records-how-its-work-ended, a-task-checkout-catches-up-with-its-approved-prerequisites, stop-clears-a-run-an-earlier-hub-left-running, worker-spend-counts-against-the-budget, every-event-the-hub-sends-reaches-the-app, a-flow-stages-its-review-in-the-dispatch, the-shell-judge-reads-a-word-whole, a-drive-or-a-home-variable-names-a-directory-by-itself, drift-watches-the-files-its-evidence-is-about, a-name-a-caller-chooses-reaches-its-own-resource, a-file-path-is-not-redacted-as-a-credential, a-refused-first-send-leaves-no-exploration-behind


## 2026-09-30

No review page today. **Written in an interactive session with the operator present**, at 22:30.
Asked what tonight would build, the operator answered *"Add the things from ghcp into the queue and
then the rest"*. So tonight's `ORDER:` is the four Copilot (ghcp) slices still unbuilt, in slice
order, then the seven changes still open from the 2026-09-27 `ORDER:`, then the other unarchived,
approved changes in the backlog's severity order (last night's queue order).

**This overrides two gates written on 2026-09-28**, by the operator's instruction above:

- Slice 1's row said *"Not before every change still open from the 2026-09-27 `ORDER:` is
  archived"*. Of the changes its proposal's *Depends on* names, only
  `a-run-records-that-its-calls-were-allowed` is still unbuilt (the others are archived). Slice 1
  goes first anyway; **`a-run-records-that-its-calls-were-allowed` then rebases onto the adapter
  slice 1 leaves**, instead of slice 1 rebasing onto it. Do slice 1's rebase-at-IMPL lines against
  the tree as it stands tonight.
- `ghcp-d5-order` (slices in order 1→3→4→5, each after the one before it is archived) **still
  holds**: slice 2 (`a-copilot-agent-runs-over-acp`) is archived. A slice left unfinished stops the
  ghcp run; go on to the seven, not to the next slice.

Not unattended work, skip it: slice 5's task 7.6 (spends real money; needs the operator's capped
key). `an-agent-can-be-paused-and-keeps-its-input` is `REVISING` and is not in the queue.

ORDER: each-runner-cli-is-one-adapter, a-run-reaches-the-hub-without-mcp, a-copilot-run-shows-its-credits, a-copilot-agent-uses-hooks-and-its-own-agents, the-corpus-is-indexed-arranged-and-adopted-from-the-app, a-specification-is-read-in-results-that-fit, input-the-hub-accepted-is-answered-as-accepted, charters-are-named-once-and-an-empty-one-says-so, a-dialog-takes-the-keyboard-when-it-opens, the-app-window-keeps-the-operators-preferences, a-run-records-that-its-calls-were-allowed, drift-is-scanned-and-answered-on-the-document, a-retried-firing-records-how-its-work-ended, a-task-checkout-catches-up-with-its-approved-prerequisites, stop-clears-a-run-an-earlier-hub-left-running, worker-spend-counts-against-the-budget, every-event-the-hub-sends-reaches-the-app, a-flow-stages-its-review-in-the-dispatch, the-shell-judge-reads-a-word-whole, a-drive-or-a-home-variable-names-a-directory-by-itself, drift-watches-the-files-its-evidence-is-about, a-name-a-caller-chooses-reaches-its-own-resource, a-file-path-is-not-redacted-as-a-credential, a-refused-first-send-leaves-no-exploration-behind


## 2026-09-28

No review page today. **Written in an interactive session with the operator present.** The
operator asked to *"approve the ones we can"* after the Copilot (ghcp) slices had R2, R3 and the
Opus adversarial review (`spec-queue/tracks/reviews/ghcp-s1..s5-2026-09-28.md`). Only slice 1 has
no question left for the operator; slices 2–5 wait on the questions listed in their designs.

**Tonight continues the 2026-09-27 `ORDER:`.** Asked at 20:15 whether tonight should build the
23 changes of that `ORDER:` still unbuilt, the operator answered *"yes"*. The line below is those
23, in their 09-27 order (the first five were built and archived by the 09-27 night). Each carries
its 09-27 approval (restated there from 2026-09-24); none has changed since. Slice 1's prerequisites
are exactly these 23 (its proposal's *Depends on*), and DECISIONS `ghcp-d5-order` puts every ghcp
slice after them, so **no ghcp slice is in tonight's `ORDER:`**, even if the 23 finish early.

ORDER: an-undelivered-message-says-how-its-last-attempt-ended, the-checkpoint-grant-says-it-reaches-every-checkpoint, the-operator-can-rename-a-task, a-message-to-the-operator-is-told-where-the-operator-reads, an-agent-updates-a-task-with-what-its-tool-carries, a-claude-run-is-told-its-agentweave-tools-by-their-full-names, request-agent-models-the-new-agent-on-one-the-operator-made, a-runner-that-cannot-collaborate-says-so-where-it-is-bound, agents-no-longer-register-themselves, a-loops-outstanding-mail-is-mail-not-yet-delivered, the-permissions-pill-shows-the-posture-the-run-gets, an-ask-me-card-says-what-workspace-only-would-decide, the-approval-preview-asks-the-gates-merge-question, isolation-does-not-change-under-held-work, a-documents-rigor-history-and-retired-requirements-are-on-screen, a-pending-proposal-can-be-withdrawn, the-corpus-is-indexed-arranged-and-adopted-from-the-app, a-specification-is-read-in-results-that-fit, input-the-hub-accepted-is-answered-as-accepted, charters-are-named-once-and-an-empty-one-says-so, a-dialog-takes-the-keyboard-when-it-opens, the-app-window-keeps-the-operators-preferences, a-run-records-that-its-calls-were-allowed

- APPROVED  each-runner-cli-is-one-adapter   ghcp slice 1. R1 09-27; R2, R3, Opus review (REVISE,
  11 findings) and its fixes 09-28; an independent Opus verification of the fixes found it
  approvable (finding 7's worker-spend note has since landed). **Not before every change still
  open from the 2026-09-27 `ORDER:` is archived**: a night that finds any of them unarchived skips
  this row. Carries F461 and F462 (its task 6.2). Before building: the rebase-at-IMPL lines in its
  design, and the verifier's two notes on task 1.4 (seed Run/Conversation rows for the executor
  test; vary `AW_DECISION_TIMEOUT` as an input, not by mutating `env`).

Slices 2–5 below were approved once the operator answered their questions (*"yes"* to every
recommendation, DECISIONS `### 2026-09-28 — ghcp slices 2–5`). Each design's Round log carries an
"Operator decisions, 2026-09-28" entry, and all five slices pass `openspec validate --strict`.
**Every row is gated like slice 1's, and also on the slice before it (`ghcp-d5-order`, 1→2→3→4→5):
a night that finds the gate unmet skips the row.** None is in tonight's `ORDER:`.

- APPROVED  a-copilot-agent-runs-over-acp   ghcp slice 2. Opus review REVISE, fixes applied 09-28;
  Q13 decided (c): a spec turn under Full access is judged as Workspace. **Not before
  `each-runner-cli-is-one-adapter` is archived.**
- APPROVED  a-run-reaches-the-hub-without-mcp   ghcp slice 3. Opus review APPROVE WITH FIXES,
  applied; Q11 decided (c), Q7 decided (a) with detect-and-degrade as a follow-up change triggered
  by the work-PC drive (its test-guide human-only 8). **Not before `a-copilot-agent-runs-over-acp`
  is archived.**
- APPROVED  a-copilot-run-shows-its-credits   ghcp slice 4. Opus review APPROVE WITH FIXES,
  applied; Q7 decided (b), Q6 decided (keep the hold; the notice names the reset date and the
  remedy, new tasks 1.19 and 5.5). **Not before `a-run-reaches-the-hub-without-mcp` is archived.**
- APPROVED  a-copilot-agent-uses-hooks-and-its-own-agents   ghcp slice 5. Opus review APPROVE WITH
  FIXES (group C REVISE), applied; open question 8 decided item by item (no hooks; Azure/OpenAI
  deferred). Task 7.6 spends real money and is **not unattended work**: it needs the operator's
  dedicated capped key and runs only after findings 2, 3 and 10 are built. **Not before
  `a-copilot-run-shows-its-credits` is archived.**

## 2026-09-27

No review page today. **Written in an interactive session with the operator present** (DECIDE).
The operator asked for an aggressive night: *"build a queue for tonight of the approved changes. Be
agressive."* The rows below restate the approvals of 2026-09-24 so that tonight's window, which
reads only today's section, builds every approved change that nothing outside the window gates.
Each row's notes and constraints are the original row's, unchanged. The 2026-09-26 night and the
session after it built and archived that night's whole ORDER (master fast-forwarded to `e60dcdf`).

Each change is still built, driven and archived before the next one starts. Being aggressive means
a long ORDER, not skipped steps. The ORDER is arranged so that stopping anywhere leaves only
complete changes behind: small, independent changes first, the migration-bearing and larger ones
later, and the lowest priority last. Migrations take numbers in build order from `0111`.

- APPROVED  a-runner-choice-names-its-model   B7 (F268), 09-24 row.
- APPROVED  an-estimate-that-misses-turns-says-so   B7 (F62), 09-24 row.
- APPROVED  a-model-alias-is-a-model-choice   B7 (F221), 09-24 row.
- APPROVED  the-codex-models-offered-are-the-ones-its-cli-lists   B7 (F267, F174), 09-24 row. Codex is undrivable (plan cancelled 2026-08-29): drive the UI and the cache read with a fixture CLI cache, and never start a Codex run.
- APPROVED  a-firing-is-counted-once-however-many-agents-it-starts   B2 (F121), 09-24 row.
- APPROVED  an-undelivered-message-says-how-its-last-attempt-ended   B2 (F291, F273), 09-24 row.
- APPROVED  the-checkpoint-grant-says-it-reaches-every-checkpoint   B2 (F235), 09-24 row. Table rebuild; migration renumbers in build order.
- APPROVED  the-operator-can-rename-a-task   B3 (F125), 09-24 row. UI bundle together with its backend.
- APPROVED  a-message-to-the-operator-is-told-where-the-operator-reads   B3 (F77), 09-24 row. A refusal only; the retired backstop stays retired.
- APPROVED  an-agent-updates-a-task-with-what-its-tool-carries   B3 (F366), 09-24 row. Edits MCP `update_task` in `mcp_server.py`.
- APPROVED  a-claude-run-is-told-its-agentweave-tools-by-their-full-names   B3 (F139), 09-24 row.
- APPROVED  request-agent-models-the-new-agent-on-one-the-operator-made   B3 (F378), 09-24 row.
- APPROVED  a-runner-that-cannot-collaborate-says-so-where-it-is-bound   B10 (F178), 09-24 row. **Before `agents-no-longer-register-themselves`**: both edit `AgentCard`, and this one deletes it.
- APPROVED  agents-no-longer-register-themselves   B3 (F111, F136, F3), 09-24 row. After the runner change above. Its own migration, seeded from `:8000`'s real `agents` DDL through a `mode=ro` read only.
- APPROVED  a-loops-outstanding-mail-is-mail-not-yet-delivered   B10 (F259), 09-24 row. No migration.
- APPROVED  the-permissions-pill-shows-the-posture-the-run-gets   B4 (F283), 09-24 row. UI bundle.
- APPROVED  an-ask-me-card-says-what-workspace-only-would-decide   B4 (F230, F284), 09-24 row. Migration. Its `mcp_server.py` half: **the operator was told on 2026-09-27** that `:8000`, when it is next started, serves this checkout's tool server.
- APPROVED  the-approval-preview-asks-the-gates-merge-question   B5 (F141), 09-24 row.
- APPROVED  isolation-does-not-change-under-held-work   B5 (F242), 09-24 row.
- APPROVED  a-documents-rigor-history-and-retired-requirements-are-on-screen   B6 (F211, F429), 09-24 row.
- APPROVED  a-pending-proposal-can-be-withdrawn   B6 (F213, F428, F431), 09-24 row.
- APPROVED  the-corpus-is-indexed-arranged-and-adopted-from-the-app   B6 (F206), 09-24 row. Carries F434.
- APPROVED  a-specification-is-read-in-results-that-fit   B12 (F363), 09-24 row. Its preferred predecessor `an-agents-tool-server-is-the-one-its-hub-loaded` is archived.
- APPROVED  input-the-hub-accepted-is-answered-as-accepted   B11 (F349), 09-24 row.
- APPROVED  charters-are-named-once-and-an-empty-one-says-so   B11 (F134, F183), 09-24 row. One migration, no table rebuild.
- APPROVED  a-dialog-takes-the-keyboard-when-it-opens   B11 (F307), 09-24 row. UI bundle.
- APPROVED  the-app-window-keeps-the-operators-preferences   B11 (F385), 09-24 row.
- APPROVED  a-run-records-that-its-calls-were-allowed   B11 (F389), 09-24 row. Lowest priority, so last. Migration.

Not tonight, deliberately. Each is held by something the window cannot do:
- `every-event-the-hub-sends-reaches-the-app` and `a-refused-first-send-leaves-no-exploration-behind`: their UI commits wait for an operator restart of `:8000`.
- `drift-is-scanned-and-answered-on-the-document`: it waits for `drift-watches-the-files-its-evidence-is-about`, which is REVISING.
- B4's `the-shell-judge-reads-a-word-whole` and `a-drive-or-a-home-variable-names-a-directory-by-itself`: they must be built in one window together, and at 72 tasks they would take the whole night.

ORDER: a-runner-choice-names-its-model, an-estimate-that-misses-turns-says-so, a-model-alias-is-a-model-choice, the-codex-models-offered-are-the-ones-its-cli-lists, a-firing-is-counted-once-however-many-agents-it-starts, an-undelivered-message-says-how-its-last-attempt-ended, the-checkpoint-grant-says-it-reaches-every-checkpoint, the-operator-can-rename-a-task, a-message-to-the-operator-is-told-where-the-operator-reads, an-agent-updates-a-task-with-what-its-tool-carries, a-claude-run-is-told-its-agentweave-tools-by-their-full-names, request-agent-models-the-new-agent-on-one-the-operator-made, a-runner-that-cannot-collaborate-says-so-where-it-is-bound, agents-no-longer-register-themselves, a-loops-outstanding-mail-is-mail-not-yet-delivered, the-permissions-pill-shows-the-posture-the-run-gets, an-ask-me-card-says-what-workspace-only-would-decide, the-approval-preview-asks-the-gates-merge-question, isolation-does-not-change-under-held-work, a-documents-rigor-history-and-retired-requirements-are-on-screen, a-pending-proposal-can-be-withdrawn, the-corpus-is-indexed-arranged-and-adopted-from-the-app, a-specification-is-read-in-results-that-fit, input-the-hub-accepted-is-answered-as-accepted, charters-are-named-once-and-an-empty-one-says-so, a-dialog-takes-the-keyboard-when-it-opens, the-app-window-keeps-the-operators-preferences, a-run-records-that-its-calls-were-allowed

## 2026-09-26

No review page today. **Written in an interactive session with the operator present** (DECIDE).
The six rows below restate earlier approvals (09-23, 09-24, 09-25) so that tonight's window, which
reads only today's section, builds R1's flow changes and the three changes they build after. Each
row's notes and constraints are the original row's, unchanged. The 2026-09-25 night built and
archived its whole ORDER (`9fbfb96`..`f2c970e`, merged to master fast-forward).

- APPROVED  an-at-mention-an-agent-wrote-reads-no-file   09-23 (F409, severity A), 09-24 row. First: the one severity-A item.
- APPROVED  a-loop-is-stopped-archived-and-delegated-from-its-own-tab   B10 (F225), 09-24 row. `a-flow-is-configured-from-its-own-tab` builds after it. UI bundle.
- APPROVED  a-flow-is-configured-from-its-own-tab   R1 (F377), 09-25 row. Carries the operator's **Start a flow…** button. Its tasks.md names migration `0108`: HEAD is now `0109`, so it takes `0110`. UI bundle.
- APPROVED  a-document-moves-forward-only-through-its-checks   B5 (F207, F113), 09-24 row. A prerequisite of R1's second change.
- APPROVED  a-loop-that-is-gone-lets-go-of-its-document   B11 (F53, F157), 09-24 row. A prerequisite of R1's second change; shares the staffing walk with the archived attended change (textual overlap only).
- APPROVED  a-document-says-how-it-will-be-built-and-approval-starts-it   R1 (F377), 09-25 row. Last: builds after the three above. Edits `mcp_server.py` (`submit_spec_document` gains `delivery`): **the operator was told on 2026-09-26** that until `:8000` restarts onto F354's pin, `:8000`'s live agents run the checked-out tool server. UI bundle.

Not tonight, deliberately: B4's `the-shell-judge-reads-a-word-whole` and
`a-drive-or-a-home-variable-names-a-directory-by-itself` (one window of their own, also
`mcp_server.py`), and B10's `a-loops-outstanding-mail-is-mail-not-yet-delivered` (size). F336 (no
control dispatches a review), listed with F377 in `ROUNDS.md`, is covered by neither R1 change and
needs its own round.

ORDER: an-at-mention-an-agent-wrote-reads-no-file, a-loop-is-stopped-archived-and-delegated-from-its-own-tab, a-flow-is-configured-from-its-own-tab, a-document-moves-forward-only-through-its-checks, a-loop-that-is-gone-lets-go-of-its-document, a-document-says-how-it-will-be-built-and-approval-starts-it

## 2026-09-25

No review page today (the day window is disabled; the newest page, `review/review-2026-09-23.html`,
was fully decided on 09-24). **Written in an interactive session with the operator present**
(DECIDE). The first seven rows below are 09-24 approvals, restated so that tonight's
window, which reads only today's section, builds the next link of each chain whose prerequisite
landed last night (`c9873c4`). Each row's notes and constraints are the 09-24 row's, unchanged. Each
re-validated `--strict` today. The other 09-24 APPROVED rows stay approved and are not tonight's. The last two rows are new approvals from the afternoon session (request R1) and are not tonight's either.

- APPROVED  a-task-is-attended-only-by-a-turn-that-will-reach-it   B1, 09-24 row. Its prerequisites (pressing-run, F133, flows-own-moves) are built and archived.
- APPROVED  a-review-no-reviewer-can-approve-goes-to-the-operator   B1, 09-24 row. After the attended change. Check the gate-code overlap with B5's approval-preview change.
- APPROVED  why-queued-input-waits-is-told-truthfully   B1, 09-24 row. F133 is in.
- APPROVED  a-live-view-that-fell-behind-is-told-and-catches-up   B9 (F253), 09-24 row. F335 is in. UI bundle (task 2.6): it reaches `:8000`'s live app on the operator's next reload, and an old Hub never sends `stream_gap`. `every-event-the-hub-sends-reaches-the-app` is NOT tonight's: its bundle still waits for the `:8000` restart onto F335.
- APPROVED  evidence-is-decided-after-the-run-that-recorded-it   B5 (F358, F426), 09-24 row. Before the coverage-bar change. Mind the F409 cross-change note.
- APPROVED  the-coverage-bar-takes-the-evidence-decision-it-asks-for   B5 (F215), 09-24 row. After the evidence change.
- APPROVED  a-footprint-names-the-line-of-work-its-commit-is-on   B5 (F165, F166), 09-24 row. Before B6's drift change (still REVISING).

- APPROVED  a-flow-is-configured-from-its-own-tab   Request R1 (F377), approved in the afternoon session after R1 (an interactive explore), R2, R3 and an Opus review, APPROVE WITH FIXES (`tracks/reviews/R1-2026-09-25.md`), all fixes applied and re-validated `--strict`. Decisions: `DECISIONS.md` 2026-09-25 R1-*. **Not in tonight's ORDER.** Builds after B10's `a-loop-is-stopped-archived-and-delegated-from-its-own-tab`. Migration (next free number); UI bundle reaches `:8000` on reload.
- APPROVED  a-document-says-how-it-will-be-built-and-approval-starts-it   Request R1 (F377), same rounds and review. **Not in tonight's ORDER.** Builds after `a-flow-is-configured-from-its-own-tab`, B5's `a-document-moves-forward-only-through-its-checks` and B11's `a-loop-that-is-gone-lets-go-of-its-document`. No migration; UI bundle.

ORDER: a-task-is-attended-only-by-a-turn-that-will-reach-it, a-review-no-reviewer-can-approve-goes-to-the-operator, why-queued-input-waits-is-told-truthfully, a-live-view-that-fell-behind-is-told-and-catches-up, evidence-is-decided-after-the-run-that-recorded-it, the-coverage-bar-takes-the-evidence-decision-it-asks-for, a-footprint-names-the-line-of-work-its-commit-is-on

## 2026-09-24

Review page: the bundle pages (`tracks/B1.html` … `B12.html`, published as one artifact with
`ROUNDS.html`); the day window did not run (disabled by the operator). **Written in an interactive
session with the operator present** (DECIDE). Each APPROVED row had the Opus adversarial pass, and its
fixes were applied and re-validated `--strict` before the row was written (each design.md opens
with `## Operator review, 2026-09-24`). The 2026-09-23 rows below remain undecided.

- APPROVED  a-checkpoint-is-handed-over-once-and-says-where-it-went   B8 (F293, F294). D2 per conversation; D6 amended by the operator: a reopened, handed-over conversation declines only the billed steps (notes turn, `due` warning, generation), and the free final compaction warning still fires (MODIFIED delta on `conversation-checkpoint`). Migration: takes `0106` if built first, otherwise renumbers in build order.
- APPROVED  a-specification-is-read-in-results-that-fit   B12 (F363). Hub-enforced 40,000-character budget; continuation by `identifiers` leaves out the preamble (operator); MODIFIED delta on `agent-capability-plane`. Preferably after B11's `an-agents-tool-server-is-the-one-its-hub-loaded`, but not blocked by it (its D5).
- APPROVED  a-refused-first-send-leaves-no-exploration-behind   B12 (F330). A post-commit refusal archives the document and never deletes it; a creation failure refuses the send. **Two commits: the UI commit waits for the operator's `:8000` restart past the Python commit.**
- REVISING  a-file-path-is-not-redacted-as-a-credential   B12 (F278). The Opus review found (a) a base64/uppercase-hex key segment still redacts the whole path, so the scenario overpromises, and (b) a 16-31-character token used as a path segment, redacted today, would survive. Re-derive the rule and re-measure both residuals (URLs carrying tokens, not only random base64).
- APPROVED  a-loop-is-stopped-archived-and-delegated-from-its-own-tab   B10 (F225). Build Stop, Archive and delegation in the loop tab; `archive_job` still does not refuse a running loop (operator confirmed). Operator, after the Opus review: a stop on a loop that has already ended is **refused 409** and its record is left untouched (`end_loop` becomes write-once). Collides with B9's F335 guard; either order, per both designs.
- APPROVED  a-runner-that-cannot-collaborate-says-so-where-it-is-bound   B10 (F178). The collaboration line under the runner picker, `AgentCard` deleted; runner update/delete now also refresh launchability (review fix). Overlaps `agents-no-longer-register-themselves` 2.9 (edits `AgentCard`), which is not yet approved.
- APPROVED  a-loops-outstanding-mail-is-mail-not-yet-delivered   B10 (F259). Derived from inbound-queue delivery state, no migration.
- APPROVED  an-event-is-announced-only-once-its-write-is-committed   B9 (F335). First of B9's three: F335, then F253, then F251. The AST guard's rule 1 now catches wrapper helpers (review fix). Collides with B10's loop change through the guard; either order, per both designs.
- APPROVED  a-live-view-that-fell-behind-is-told-and-catches-up   B9 (F253). After F335. Needs no restart gate: an old Hub never sends `stream_gap`.
- APPROVED  every-event-the-hub-sends-reaches-the-app   B9 (F251). After F335 is in the tree (task 0.4). **Its UI bundle waits for the operator's `:8000` restart onto F335 (task 0.5).** B9-Q1: no runtime allowlist, generated type.
- APPROVED  run-id-in-an-event-always-names-a-run   B2 (F149). The Opus review approved it as it stands: `run_id` becomes `job_run_id` outright, and no reader breaks.
- APPROVED  an-estimate-that-misses-turns-says-so   B7 (F62). The Opus review approved it as it stands. On `:8000` the label will read "excludes 3 turns" (operator: fine). Whichever of this change and `worker-spend-counts-against-the-budget` lands second adds `unpriced_calls` (review, B7 §2).
- REVISING  a-retried-firing-records-how-its-work-ended   B2 (F123, F147). Opus review, `tracks/reviews/B2-2026-09-24.md` §3: two MODIFIED deltas are missing (`agent-loops` "A firing in progress is distinguishable", `loop-firing-accountability` "A firing that does start is unaffected"); the Core `UPDATE` bypasses the `error_summary` fitter; the "still 200" claim fails at a real flush/commit (session needs a rollback); conclusion-vs-broadcast ordering is unspecified; `reconcile_run` must conclude too (a gap with the Stop change). Open Questions 1/3 stay deferred to `REQUESTS.md` R7.
- REVISING  stop-clears-a-run-an-earlier-hub-left-running   B2 (F168). Opus review §5: on Windows `taskkill` never raises, so the 409 path cannot fire (poll `pid_alive`); POSIX `killpg` can hit the Hub's own process group (require `pgid == pid != getpgrp()`); Windows pid reuse (compare process creation time with `run.started_at`). The operator keeps "end it by pid", narrowed to a process identifiable as the run's own. Fold in the retried-firing conclusion.
- APPROVED  the-shell-judge-reads-a-word-whole   B4 (F362, F403). **Approved 2026-09-24 evening** (`DECISIONS.md` `B4-approve`) after R6 (`6c2c7bf`), R7 (`1aaa9a7`), a third Opus review, APPROVE WITH FIXES (`tracks/reviews/B4-2026-09-24-third.md`), and R8 (`aaba6ab`), which applied its fixes with three measured departures (colon-split whole-value judgement on drive-letter hosts; unreadable bracket expressions loosened to `?`; `_glob_links` does not re-judge its base). Residual accepted: a colon-named directory (Git Bash only) with a link behind it. Change 2 builds after change 1, in one window. **Not in tonight's ORDER.** Adds D2 step 6 (a word's value is judged as the path it spells). Was REVISING:
  REVISING  the-shell-judge-reads-a-word-whole   B4 (F362, F403). **Security regression found by the Opus review** (`tracks/reviews/B4-2026-09-24.md`): a glob reaches through a link inside the workspace (`cp n u*/x` with `up` pointing outside), plus an extglob `@(..)` escape. Operator: expand glob matches against the filesystem and judge each one. Also the `user@host:` spec/design mismatch, a MODIFIED network-address requirement for the approved `host:x/y`, and Windows rules untested on Linux CI. **Afternoon:** R4 (`a1f03ec`) and R5 (`d0311a0`) ran; the operator's answers were applied (`DECISIONS.md` `B4-drive-exists`, `B4-dep-links`, `B4-residuals`); a second Opus review (`tracks/reviews/B4-2026-09-24-second.md`) says **REVISE** again: a bracket at a word's edge hides the glob from the link check, and a `..` after a link is resolved physically (`B4-link-dotdot`: fixed in change 1). **Still REVISING; R6 owed**, run by the operator after a handoff.
- APPROVED  a-drive-or-a-home-variable-names-a-directory-by-itself   B4 (F402, F401). **Approved 2026-09-24 evening** (`DECISIONS.md` `B4-approve`) after R6 (`6c2c7bf`), R7 (`1aaa9a7`), a third Opus review, APPROVE WITH FIXES (`tracks/reviews/B4-2026-09-24-third.md`), and R8 (`aaba6ab`), which applied its fixes with three measured departures (colon-split whole-value judgement on drive-letter hosts; unreadable bracket expressions loosened to `?`; `_glob_links` does not re-judge its base). Residual accepted: a colon-named directory (Git Bash only) with a link behind it. Change 2 builds after change 1, in one window. **Not in tonight's ORDER.** Was REVISING:
  REVISING  a-drive-or-a-home-variable-names-a-directory-by-itself   B4 (F402, F401). Opus review: `bash -c 'cp n $HOME'` bypasses it one quote level down, and the spec requires the bypass. Operator: refuse it (accepting that `echo '$HOME'` and `grep '$HOME'` get refused), extend the list (`$HOMEPATH`, `$HOMEDRIVE`, `$PUBLIC`, `$OneDrive` and the others the review names), and the PowerShell spellings `${env:N}`/`$variable:N`/`$global:N`. `$(dirname $PWD)` is now refused (operator accepts this). **Afternoon:** R4 (`a1f03ec`) and R5 (`d0311a0`) ran; the operator's answers were applied (`DECISIONS.md` `B4-drive-exists`, `B4-dep-links`, `B4-residuals`); a second Opus review (`tracks/reviews/B4-2026-09-24-second.md`) says **REVISE** again: a bracket at a word's edge hides the glob from the link check, and a `..` after a link is resolved physically (`B4-link-dotdot`: fixed in change 1). **Still REVISING; R6 owed**, run by the operator after a handoff.
- REVISING  worker-spend-counts-against-the-budget   B7 (F240). Opus review, `tracks/reviews/B7-2026-09-24.md` §3: the final warning at exhaustion cannot fire (`needs_final_warning` returns False for automatic; use an `effective` policy); three MODIFIED deltas are missing (`conversation-checkpoint`, `agent-flows`, `conversation-lifecycle`); the B8 interaction text is stale; test 10e cannot catch a read that is not lazy. Operator: a dismissal made at exhaustion **persists** until the operator acts, and **F422 is fixed first**.
- REVISING  drift-watches-the-files-its-evidence-is-about   B6 (F217, F427, F432). Opus review, `tracks/reviews/B6-2026-09-24.md` §1: the three rules are a union, so agent evidence always watches its whole task diff (on `:8000` one commit to `src/engine.js` still raises about 22 candidates); the main production path (restamp at run end) has no test, and a NULL `watched_from` silently makes a row legacy; a MODIFIED delta on `requirement-traceability` is missing. Operator inputs: **apply the rules in order** (locator, then named commit, then branch diff), **match locator tokens against the tree**, and **backfill** legacy footprints from the stored commit plus the first-parent merge diff (42 of 46 rebuildable). Still lands after B5's footprint change.
- APPROVED  a-firing-is-counted-once-however-many-agents-it-starts   B2 (F121). The Opus review approved it; new task 2.7 re-points `t_row11_loop.py`'s count checks at distinct `fired_at`.
- APPROVED  an-undelivered-message-says-how-its-last-attempt-ended   B2 (F291, F273). Review fixes applied: "Last attempt was interrupted", and the `RUN_TERMINAL_EVENT_TYPES` comment is corrected.
- APPROVED  the-checkpoint-grant-says-it-reaches-every-checkpoint   B2 (F235). Drops the `visibility` column: a table rebuild that preserves every partial index, including B8's, in either landing order (the review probed it). The downgrade restores server default `'project'` (stated). Migration renumbers in build order.
- APPROVED  the-permissions-pill-shows-the-posture-the-run-gets   B4 (F283). D4a: `workspace` for Claude, through `posture_at_rest`. Review fixes: a MODIFIED delta on `agent-run-sandboxing` and a `permission_mode_built_in` field for the settings label. The UI bundle follows the refresh rule.
- APPROVED  an-ask-me-card-says-what-workspace-only-would-decide   B4 (F230, F284). D4b: advice on the card, with the reason also shown on an allow; Codex says "checked by working directory only". Has a migration (renumbers). Its `mcp_server.py` half reaches `:8000`'s next run from the working tree (tell-first).
- APPROVED  a-runner-choice-names-its-model   B7 (F268). Label pinned to `{name} — {model part} ({cli})`, without doubling for Hub-created runners; the checkpoint select names `checkpoint_model`.
- APPROVED  a-model-alias-is-a-model-choice   B7 (F221). D2.2: aliases are stored as written; a runner-registry MODIFIED delta was added. The Add-agent default stays `claude-sonnet-5`.
- APPROVED  the-codex-models-offered-are-the-ones-its-cli-lists   B7 (F267, F174). D2.1: the CLI cache is read at runtime (`json.loads(read_bytes())`, memoised only on success on `(mtime_ns, size)`); the literal is the fallback, and window lookups also fall back to it.
- APPROVED  a-document-moves-forward-only-through-its-checks   B5 (F207, F113). Operator after the review: the checks run **inside `transition()`**; F113 goes in the 200 `blocking` list; Q0: no refusal of a stale import.
- APPROVED  evidence-is-decided-after-the-run-that-recorded-it   B5 (F358, F426). Operator after the review: an agent refused `recording_run_live` is **re-queued when the recording run ends** (new D7, a queue origin with a migration); a revision bumps `produced_at`. **Before** `the-coverage-bar-takes-the-evidence-decision-it-asks-for`.
- APPROVED  the-coverage-bar-takes-the-evidence-decision-it-asks-for   B5 (F215). After the evidence change above. Operator: Accept **says on the row** that it may merge into main; a run that recorded evidence broadcasts on exit.
- APPROVED  a-footprint-names-the-line-of-work-its-commit-is-on   B5 (F165, F166). D12-3: one spelling `""`; the data migration is a no-op on `:8000` (0 `HEAD` rows). Review fix: the `""` bucket drops only proper ancestors; a MODIFIED delta on `task-lifecycle-governance`. **Before** B6's `drift-watches-the-files-its-evidence-is-about`.
- APPROVED  isolation-does-not-change-under-held-work   B5 (F242). D12-1: refused under held work. Review fix: compares the merged (effective) config. Operator: **`/session/sync` is guarded too**.
- APPROVED  the-approval-preview-asks-the-gates-merge-question   B5 (F141). D12-2: a live probe, nothing stored. Review fix: the fallback is wrapped too (a git failure gives a sentence, never a 500), and the real commit count is used. Does not fix F424.
- APPROVED  drift-is-scanned-and-answered-on-the-document   B6 (F129, F132, F430). **Must not ship without `drift-watches-the-files-its-evidence-is-about` (REVISING), so it waits for it.** Operator: carries F436 (*Code corrected* stores no silencing fingerprint, D8); order ties broken by `id`.
- APPROVED  the-corpus-is-indexed-arranged-and-adopted-from-the-app   B6 (F206). M1: merge stays API-only (R9 queues M3). Operator: carries F434 (a failed index write still commits the requirement index, answering 200 `written: null`; arrange refuses with a sentence).
- APPROVED  a-documents-rigor-history-and-retired-requirements-are-on-screen   B6 (F211, F429). Lowering rigor needs a reason; the history refreshes on success.
- APPROVED  a-pending-proposal-can-be-withdrawn   B6 (F213, F428, F431). W3. Review fixes: a MODIFIED delta on the gating requirement; a retraction supersedes; a row-count-checked `UPDATE … WHERE status='pending'` for every status change.
- REVISING  a-flow-stages-its-review-in-the-dispatch   B1 (F327). Opus review, `tracks/reviews/B1-2026-09-24.md` §3: the author exemption can replace a live reviewer mid-review (two live reviews). Operator: the holder check exempts an author only where it is **not attending**. The MODIFIED delta for governance requirement 476 (F167's evidence term) is missing; operator: write it here. Still after the attended change, the gate change and B3's flow-moves change.
- REVISING  a-task-checkout-catches-up-with-its-approved-prerequisites   B1 (F158). Opus review §5: the `workspace-isolation` "merged only at branch creation" SHALL is contradicted with no delta; the refusal cannot name the prerequisite (carry `(prerequisite_id, sha)`); a git timeout can leave a checkout mid-merge. Operator: **keep D2** (refuse on conflict), with the attended change surfacing the refused work head as `unstaffed`, naming the prerequisite, the checkout and the merge command, so it stalls visibly instead of churning.
- REVISING  an-agent-can-be-paused-and-keeps-its-input   B3 (F15). Opus review, `tracks/reviews/B3-2026-09-24.md` §3: a paused agent would be told it is waiting on a usage limit (name-only `agents_held`; rung-3 and hold sentences); six shipped SHALLs across agent-flows, agent-loops, agent-capability-plane and run-task-binding are contradicted. Operator: **a pause takes precedence** over anything that starts or wakes a turn (reviews, divergence retry and escalate wait), and **archiving a paused agent withdraws its queue**.
- REVISING  a-name-a-caller-chooses-reaches-its-own-resource   B11 (F248). Opus review, `tracks/reviews/B11-2026-09-24.md` §7: reserving the route words in `validate_agent_name` bricks any existing agent with such a name (the validator runs at every turn, the worktree paths, a whole-project session sync and the CLI config load). Operator: a **Hub-only create-time check** (`validate_new_agent_name`) at the create doors only; the use-site validator and the CLI set stay `{user, operator}`. The route-table walk must allowlist the SPA catch-all, and fail by default on an unmapped parameter.
- APPROVED  a-task-is-attended-only-by-a-turn-that-will-reach-it   B1 (F370, F371, F368). **Build after** `pressing-run-names-the-reason-that-held`, B11's F133 no-spec fix (its task 2.0 stops without `select_turn`) and B3's `a-flows-own-moves-are-recorded-as-the-flows`. D3: refused input is not attendance. Operator after the review: a refused **work** head is surfaced as `unstaffed` with its refusal's words, and the firing no longer re-briefs it (closes the held/paused pile-up).
- APPROVED  a-review-no-reviewer-can-approve-goes-to-the-operator   B1 (F374, D9 = `F374-fix`). After the attended change. Operator after the review: "could not ask git" (F424's category) counts as **held for the operator**. Git on `evaluate`'s path runs off the event loop with a 5 s diagnostic timeout. It touches shared gate code, so check its overlap with B5's `the-approval-preview-asks-the-gates-merge-question`.
- APPROVED  why-queued-input-waits-is-told-truthfully   B1 (F361, F289). After F133. Review fix: D3 uses `takes_own_checkout` (no git on the polled route) and is wrapped to fall through to D4. Collision with B3's F77 change is named.
- APPROVED  an-at-mention-an-agent-wrote-reads-no-file   09-23 (F409, severity A). **Approved 2026-09-24 afternoon** (`DECISIONS.md` `F409-approve`) after R4 (`fb4c8f5`), R5 (`8786289`), the operator's Q4 answer (D10 stays) and a second Opus review, APPROVE WITH FIXES (`tracks/reviews/F409-2026-09-24-second.md`), whose seven fixes are applied: task 1.0 gate first; cross-change notes in B5's `evidence-is-decided-after-the-run-that-recorded-it` and B7's `worker-spend-counts-against-the-budget`; the in-workspace-link residual named (F445) and the requirement narrowed to "no second mention of its own". UI bundle (D8, D10). **Not in tonight's ORDER**; a later night. Was REVISING this morning:
  REVISING  an-at-mention-an-agent-wrote-reads-no-file   09-23 (F409, severity A). Opus review, `tracks/reviews/2026-09-23-changes-2026-09-24.md` §1, measured on CLI 2.1.280: `\@` blocks expansion and the choke point holds, **but a clicked `ask_user` option echoes agent text unescaped** (bypass: an option "Use @~/.ssh/id_rsa", clicked, attaches the file). Also: `agent-flows` "delivered unchanged" needs a MODIFIED delta; the ADDED requirement contradicts Q1 (a job message is neutralised); `spec_turn_notice` `path`; line citations have drifted. Q1-Q3 stand as answered (defaults).
- APPROVED  an-agents-tool-server-is-the-one-its-hub-loaded   B11 (F354). The pin goes under `~/.agentweave/hub/tool-server/<digest>/` (0700); old digests are pruned after 7 idle days. **Build early**: after it lands and `:8000` restarts, `mcp_server.py` edits stop reaching live agents from the working tree (task 4.1 rewrites `.claude/rules/mcp-server.md`).
- APPROVED  the-app-window-keeps-the-operators-preferences   B11 (F385). A window folder per `--profile`; reset clears it and warns if the folder is held open; the pywebview floor is raised to `>=5.3` (no `icon=` below it).
- APPROVED  a-dialog-takes-the-keyboard-when-it-opens   B11 (F307). Confirmations open on Cancel; the four dialogs missing from the hook join it. UI bundle.
- APPROVED  input-the-hub-accepted-is-answered-as-accepted   B11 (F349). Also covers the job/loop/flow firing path (a firing that is still waiting stays in progress) and `_stage_selection`; only transient errors are retried. MODIFIED deltas on `loop-firing-accountability` and `runtime-diagnostics`.
- APPROVED  a-loop-that-is-gone-lets-go-of-its-document   B11 (F53, F157). Three MODIFIED agent-loops deltas; `loop_tasks_adopted` is written against both loops. Shares the staffing walk with `a-task-is-attended-only-by-a-turn-that-will-reach-it` (textual overlap only).
- APPROVED  charters-are-named-once-and-an-empty-one-says-so   B11 (F134, F183). Runners are included (a new `runner-registry` requirement; three doors; exact match). One migration, no table rebuild (F177 reads `rowid`).
- APPROVED  a-run-records-that-its-calls-were-allowed   B11 (F389). Lowest priority. The write happens in the background after the 202; writes are monotonic. Migration.
- APPROVED  agents-no-longer-register-themselves   B3 (F111, F136, F3). Carries out `D3-self-registration`. Migration follows `0013` (`recreate="never"`; on `:8000`, `self_registered` is NOT NULL with no default), with a test seeded from `:8000`'s real `agents` DDL. Separate migration from any other `agents` alter. L: 19+ test files re-fixtured; `e2e.py` switches to `POST /agents`.
- APPROVED  request-agent-models-the-new-agent-on-one-the-operator-made   B3 (F378). Copies runner, charter and config, minus `principal`, `yolo`, `hub_client` and the question-wait env; no grants or posture. A raise from the scheduler after the commit answers 201.
- APPROVED  a-flows-own-moves-are-recorded-as-the-flows   B3 (F47, F120; D8). Migration. `enter_selected_task(..., origin, job_id)` is the signature S13 rebases onto. **Before** B1's attended change.
- APPROVED  a-message-to-the-operator-is-told-where-the-operator-reads   B3 (F77). A refusal only; removes the retired backstop requirements, including the `agent-conversation-workspace` attention-state clause.
- APPROVED  a-claude-run-is-told-its-agentweave-tools-by-their-full-names   B3 (F139). Full names for runs described with the injected surface; the host-`SendMessage` sentence for every Claude-family run.
- APPROVED  an-agent-updates-a-task-with-what-its-tool-carries   B3 (F366). Review fixes: a MODIFIED governance delta; MCP `update_task`'s `status` becomes optional. F443 (create-time fields) is separate.
- APPROVED  the-operator-can-rename-a-task   B3 (F125). Its own `useRenameTask` (renaming a blocked task works); `title: null` is refused. UI bundle together with its backend.
- APPROVED  pressing-run-names-the-reason-that-held   09-23 (F400, F373). **B1's prerequisite: build first among B1's chain.** Review fix: the busy re-ask is unconditional below the skipped/failed arms; the stale-409-to-500 race is named in Risks. F411, F412 and F413 stay separate.

ORDER: F133, an-agents-tool-server-is-the-one-its-hub-loaded, pressing-run-names-the-reason-that-held, a-checkpoint-is-handed-over-once-and-says-where-it-went, an-event-is-announced-only-once-its-write-is-committed, run-id-in-an-event-always-names-a-run, a-flows-own-moves-are-recorded-as-the-flows

## 2026-09-23

Review page: `review/review-2026-09-23.html`. **Written by the day window, not the DECIDE session —
no status token on either row below.** Two changes went through the full three-round spec loop
today; both are new proposals, neither built or archived.

- `an-at-mention-an-agent-wrote-reads-no-file`   F409 (A); R1/R2/R3 done; three open design
  questions (Q1: accept that an operator-typed `@path` in a scheduled job's prompt no longer
  expands, since job entries are not operator-origin; Q2: accept `a\@b.com` in what agents read, in
  exchange for a rule that need not mirror the CLI's own tokeniser; Q3, added in R3: escape the
  board's Start-work task title, or drop the title from the message instead); touches the UI and
  needs a bundle refresh (design D8); shares no file with the change below.
- `pressing-run-names-the-reason-that-held`   F400 + F373 (B); R1/R2/R3 done; four open design
  questions (Q1 fold F411 in — the Run button shows none of this today; Q2 the scope-clause
  wording; Q3 fold F412 in — a `terminal_failure` firing still answers `200 {"success": true}`; Q4
  fold F413 in — a crash that leaves no row cannot be told from a decline that left none); route and
  scheduler only, no UI, no migration; shares no file with the change above.

## 2026-09-22

Review page: `review/review-2026-09-22.html`. **Written in an interactive session with the operator
present** (DECIDE). Decisions behind it: `DECISIONS.md` `### 2026-09-22` and
`### 2026-09-21 night`.

ORDER: a-hub-that-was-not-told-which-database-refuses-to-open-one all groups, then an-unstaffed-review-names-its-holders groups 2, 5, 6

**1. `a-hub-that-was-not-told-which-database-refuses-to-open-one` (F388, A).** Approved 2026-09-21
~21:30 for tonight. The row is copied from `## 2026-09-21`, where the build rules are written out
in full, and they bind tonight unchanged: groups 1 and 3 land in one commit or neither; for 3.7,
edit the `.claude/skills/` sources and then run `scripts/sync_skills.py`; tasks 2.7 and 2.8 follow
their implementation notes, with both mutation checks; run the group 6 drive in the 8090s on a
throwaway profile, and set F388 `fixed` only after 6.1-6.3 are observed; stop and log if a task
disagrees with the code; write both suite counts into `tasks.md`. `config.py`/`main.py` reach
`:8000` on its next restart. Never restart it or call it.

- APPROVED  a-hub-that-was-not-told-which-database-refuses-to-open-one   all groups; F388; groups 1+3 in one commit; drive in the 8090s

**2. `an-unstaffed-review-names-its-holders` (F352's visibility half), groups 2, 5 and 6.** Group 1
is built. Round 9 (this morning's day window) found R8-1..R8-5 holding against the tree. **R9-5 is
dropped: build the fit as the tasks say, and apply neither cure (a) nor (b).** Group 5 edits
`hub/ui/` and ships a bundle. Commit it only if 5.3's served-bundle drive passed (task 5.4); the
operator accepts that it reaches `:8000`'s live app on their next reload (`unstaffed-bundle`). In
group 6.3, drive R8's replacement bullets, not the stale ones struck through above them. Drive Hub
on a free port with a fresh profile, Haiku on every real turn, never `:8000` or `:8010`, and no job
left enabled. Second in the ORDER. If F388 takes the night, this carries to the next.

- APPROVED  an-unstaffed-review-names-its-holders   groups 2, 5, 6; group 1 built; R9-5 dropped (accepted as is); second in tonight's ORDER

**Not tonight:** `a-refused-capability-reaches-the-operator`. §1 is still gated on F386, which is
open.

---

## 2026-09-21

Review page: `review/review-2026-09-21.html`. **No change proposed; no spec loop ran** (drain count 4).
The four gated changes below carry no row from the day window; the operator may act on any of them.

- `a-hub-that-was-not-told-which-database-refuses-to-open-one` -- REVISING by the night; Opus DO NOT APPROVE, four blocking items for R4.
- `a-loop-staffs-the-agent-it-names`
- `a-refused-capability-reaches-the-operator`
- `an-unstaffed-review-names-its-holders`

### Operator, 2026-09-21 evening — tonight's queue

**Written in an interactive session with the operator present, after the review page above.** This
section is the authority for tonight. Decisions behind it: `DECISIONS.md` `### 2026-09-21 evening`.
Aimed at the week scorecard: O5 (close changes), O4 (severity A), O2 (CI green rate).

ORDER: archive a-first-turn-is-not-told-it-has-nothing, then F380 as a no-spec repair, then F292 fix-or-quarantine, then a-loop-staffs-the-agent-it-names group 7 then archive it -- NOT group 5, then a-word-without-a-separator-can-still-leave (only if the four above are done)

**1. Archive `a-first-turn-is-not-told-it-has-nothing`.** Every task is ticked (7.5/7.5b tidied this
evening; 7.4 carries counts, so D2's archive bar is met). Sync specs, archive, and in the same commit
confirm F302's Status line — it is already `fixed 802a8c7` for the text; do not claim more than its
own entry does.

- APPROVED  a-first-turn-is-not-told-it-has-nothing   archive only; nothing left to build

**2. F380 (A), no-spec repair — part (a) at minimum.** `arm-cycle.ps1:167` refuses to arm on
`git status --short`, which counts **untracked** files; any stray file disarms the next window with
nothing to read. Make the dirty check ignore untracked files (`--untracked-files=no`) or refuse only
on tracked modifications, and make every refusal **write a line somewhere a morning reader looks**
(the day/night log, not only stdout). Read F380's (b) and take it too if it is small. **Constraints:**
do not re-register or trigger any scheduled task; do not run the arm for real — test it by running
the dirty-check logic alone, against a scratch untracked file, and remove the file after. Lint any
PowerShell by running it with `-WhatIf`-style dry paths only. Set F380's Status to `fixed <sha>` only
for the part that landed.

**3. F292 (B), fix-or-quarantine — timeboxed to two firings.** The CI flake (`database is locked` at
setup) took 3 of 16 runs this week and blocks O2 (≥ 90%). Read the **foot** of F292 first, not all
1,400 lines. Prefer the cheap shape: stop the two known files racing (serialise them, or give them
their own database). **Measure it on CI, not locally** — F292 does not reproduce locally (entry
line ~201). Record the CI green rate across the night's pushes in the log. If neither shape lands in
two firings, write down what was learned and move on.

**4. `a-loop-staffs-the-agent-it-names` — group 7 (the drive), then archive.** Group 7 was approved on
2026-09-19 and never run. **§5 is moved out by operator decision → F400**, and its delta was trimmed
this evening to what the built groups do. Do not build §5. Drive per group 7 — **never `:8000`, never
`:8010`**, fresh Hub on a free port with an explicit `DATABASE_URL` (a `C:/...` path, not `/c/...`),
Haiku on every real turn, never leave a job enabled. Task 7.4's "read-only against the operator's
database" means `mode=ro` SQLite only. Then archive; F128/F161/F70 statuses per the playbook.

- APPROVED  a-loop-staffs-the-agent-it-names   group 7 and archive; §5 moved out to F400, NOT built

**5. `a-word-without-a-separator-can-still-leave` (F375, A) — added ~19:50 by the operator ("approve"),
last in the ORDER.** Three rounds (R1-R3), decisions in `DECISIONS.md` `### 2026-09-21 late evening`.
Tasks 0.3 and 0.4 are satisfied by that entry; tick them citing it. Build groups 1-3 in order: tests
first, each recorded failing today; then the rule; then task 2.3's exact-diff check (only P7, R8, R9,
H10 change -- anything else is a defect, stop and log it). Group 3's real-shell rows run in a scratch
directory, never the repo root. **Editing `mcp_server.py` reaches `:8000`'s next run at once** --
the operator knows; do not restart anything. If group 1 or 2.3 disagrees with the design, stop and
log rather than adjusting the design unattended. Archive (4.2) only with every task ticked with counts.

- APPROVED  a-word-without-a-separator-can-still-leave   groups 1-4; F375; last in tonight's ORDER

**Not tonight:** `a-hub-that-was-not-told-which-database-refuses-to-open-one` (F388, A).
**Approved by the operator at ~21:30 for the night of 2026-09-22, not tonight** (`DECISIONS.md`
`### 2026-09-21 night`). R4 (`da19eb5`) fixed the four blockers, and a second Opus pass returned
APPROVE WITH FIXES, applied in `b14342b`. There is deliberately no `APPROVED` token for it in this
section. **Tomorrow's DECIDE session copies this row into `## 2026-09-22`**, with the build rules
below:
`- APPROVED  a-hub-that-was-not-told-which-database-refuses-to-open-one   all groups; F388; groups 1+3 in one commit; drive in the 8090s`.
The build rules:
- groups 1 and 3 land in one commit, or neither;
- for task 3.7, edit the two `.claude/skills/` sources, then run `scripts/sync_skills.py`, never
  `.agents/` by hand;
- `config.py`/`main.py` reach `:8000` on its next restart (a told launch, measured safe); never
  restart it or call it;
- tasks 2.7 and 2.8 follow their implementation notes (a stderr reader thread, a `wait()` timeout,
  pop `DATABASE_URL`), with both mutation checks in the commit;
- run the group 6 drive in the 8090s on a throwaway profile, and set F388 `fixed` only after 6.1-6.3
  are observed;
- stop and log if a task disagrees with the code;
- write both suite counts into `tasks.md`.

Also not tonight:
`a-refused-capability-reaches-the-operator` (§1 gated on F386); `an-unstaffed-review-names-its-holders`
(a verification round is running now — if it returns clean, a row will be added below this line).

---

## 2026-09-20

Written in session with the operator present, not by the day window — the day window hit the weekly
usage limit at 14:15 with `f388-r1` still `in_progress`, so it may not reach `d5` (the review page)
before 17:00. This section is the authority for tonight regardless of whether it does.

**Read this before building: the tree was red when this section was written, and is not any more.**
`a-loop-staffs-the-agent-it-names` task 3.3 (`831ac16`) repointed `_loop_flow_busy_reason` at
`_agents_a_loop_may_staff`, whose pool is empty for a documentless loop, and that broke three group-3
cases in `hub/tests/test_a_task_nothing_will_move_holds_nobody.py` — a file no artifact of that
change names anywhere. Repaired in `aa9983f` by restaging `_guard_case` on a spec-linked loop, with
the mutation re-checked. Filed as **F392 (B)**, because the *process* hole is open: group 6.2
(`pytest hub/tests/ -q` in full) is ticked `[x]` citing a log entry that was never written. **Step 3
of `night-window.md` still applies — run the suite yourself before adding to it, and do not trust
6.2's tick.**

### APPROVED — `an-archived-agent-holds-nothing-and-is-offered-nowhere`

**F185 (B) + F181 (C) + F390 (C).** R1, R2 and R3 all ran on 2026-09-20 as three independent day-window
processes; R2 corrected four of R1's claims and R3 corrected four more and filed F391.
`openspec validate --strict` passes after the amendment below.

**The one decision this change carried is now made** (`design.md` D10, *Decided by the operator*):
of the three shapes offered — API only, API plus a persisted archival event, API plus a `hub/ui/src`
bundle refresh — the operator chose **the middle one**. So:

- **Group 2b is new and is approved with the rest.** `archive_agent` and `unarchive_agent` each
  `persist_event` **and** `sse_manager.broadcast`, matching `agent_created` (`agents.py:689-690`).
  `agent_archived` carries `released_charter_id` from task 2.1's pre-release capture.
- **Both calls are server-side.** The change still commits nothing under `hub/ui/src`, still needs no
  `make ui`, and still reaches nothing in the operator's live `:8000` app on its next reload. **Task
  2b.7 is the check; if this group acquires a bundle refresh, stop and leave it for the operator.**
- **It closes the recording gap, not the display gap.** Do not set `**Status:** fixed` on **F391**
  unless both the persist and the broadcast landed, and say in the same edit that display is
  untouched (task 2b.6).
- **Group 5 was offered as a cut and the operator declined it.** Build it.
- **Migration `0105` rewrites rows in the operator's live database** on their next `:8000` restart
  (`.claude/rules/db-migrations.md`). It is required — D5 — but read group 3's banner first.

**The standing adversarial-Opus pass was deliberately skipped**, at the operator's explicit
instruction, on the grounds that the three rounds were independent processes that each corrected the
last. Recorded so its absence does not read as an oversight. **The consequence to carry while
building: D10 and group 2b are R3-and-later work that nothing has re-derived** — if a task in 2b
disagrees with the code, the task is the thing more likely to be wrong.

- APPROVED  an-archived-agent-holds-nothing-and-is-offered-nowhere   all groups, including the new 2b and group 5; no UI, no bundle refresh

### APPROVED — `a-first-turn-is-not-told-it-has-nothing`, **group 7 only**

**Added 2026-09-20 22:3x, in session with the operator present**, after the operator asked for more
than one change and an e2e run on the same night. Groups 1-6 were implemented, quality-gated and
**merged to `master` at `802a8c7`** earlier this evening; CI run `35536597112` is green on all nine
jobs. Group 7 is the only thing left, and it is a drive, not a build.

**What it is.** The measurement the operator's **D2** decision turns on: *"ship this shape, then
measure"*. Three fresh agents, a throwaway Hub, **Haiku bound** (standing directive), **first turn
only**. It answers whether removing the two false sentences actually moves behaviour, or whether the
Architect's ten post-fix `curl` runs mean the steer was never the cause.

- **Read task 7.1b before 7.1.** It names three preconditions 7.1 does not, each of which *silently
  voids the experiment while looking identical in the transcript*: `hub_client` must resolve to
  `None` (not `"cli"`, not `"mcp"`), the bound runner must be in `MCP_INJECTABLE_RUNNERS`, and the
  agent must have **no prior run** carrying `mcp_adapter_online_at`. All three are trivially true of
  a brand-new agent on a fresh Hub — which is why 7.1's wording is safe *only* if the agent really
  is new. **Verify them before the turn, not after.**
- **The baseline in 7.5 is n=1, not "4 of 4".** R3 corrected this and it was the most load-bearing
  error in the group. Four agents were *told* the sentence; one agent's behaviour was read. Do not
  restore the larger number.
- **7.4 must carry counts inline.** Per **F392** and the operator's own bar, a tick citing a log
  entry that was never written is not done. **The change stays barred from archive until it does.**
- **Whatever it finds, append it to F302 in `scripts/drive/FINDINGS.md`** (task 7.6) — including a
  result that says the change did not help. F302 is already `fixed 802a8c7` for the *text*; the
  behavioural claim is deliberately left open, and 7.7 corrects the exploration's own overreach.

- APPROVED  a-first-turn-is-not-told-it-has-nothing   group 7 ONLY (7.1-7.7); groups 1-6 are built, merged and green

### APPROVED — one full-surface e2e sweep, **last**, and only if the queue above is finished

The operator asked for this explicitly. Per-change drives are scoped to the change; a full-surface
sweep is the only thing that finds defects living *between* two features. Use the `e2e-loop` skill.
**It is last on purpose: it must not consume the window before the builds land.**

**Four constraints, because the skill's own "Reference — this machine" section conflicts with
`night-window.md` and following it literally would be a CLAUDE.md violation:**

1. **NOT port 8010.** `.claude/skills/e2e-loop/SKILL.md:144` hands you a launch on **8010**. That is
   the *trial Hub*, and **this repository is registered in it as `proj-d85a82bf4216`**. Driving it
   points the Hub you are editing at the tree you are editing — the exact thing CLAUDE.md prohibits,
   because a restart kills the runs orchestrating the work. `night-window.md` already says never
   8010 and never 8000. **Pick a free port** (`netstat -ano | grep LISTENING` first) and record it.
2. **Set `DATABASE_URL` explicitly** to a per-night drive profile, `profiles/drive0920/agentweave.db`.
   That same skill line carries **no `DATABASE_URL`**, so it resolves through the gitignored
   `hub/.env` — measured today as the *relative* `data/agentweave.db`, i.e. whatever is under the
   launch directory. It does **not** reach the operator's live database (checked), but it is not a
   fresh profile either, and a sweep that inherits another run's rows is not a sweep. **This is
   F388's mechanism and it is still unfixed** — see the REVISING row below.
3. **Fresh project every drive; never `proj-5e960453` or `proj-18e5d4e0`**, and never this
   repository's own working directory as the project path.
4. **Haiku on every real agent turn**, and **never leave a job enabled**. File what it finds in
   `scripts/drive/FINDINGS.md` with the usual `Source: found by driving`.

### REVISING — `a-hub-that-was-not-told-which-database-refuses-to-open-one` (**F388, severity A**)

**The operator's standing adversarial-Opus pass ran on 2026-09-20 22:2x and returned DO NOT APPROVE.**
This change was a candidate for tonight and is **held out of the queue**. R1, R2 and R3 all ran today
and all concluded "every decision survives"; the core mechanism *is* sound — the reviewer probed the
raising `default_factory` directly and could not break D2 or D3. The blockers are in the task list
and the delta, which is exactly what a fourth independent pass is for.

**Four blocking findings, for tomorrow's R4 — do not build any of this tonight:**

1. **A second spec-vs-tasks contradiction, the same class R3 caught once.**
   `specs/app-lifecycle/spec.md:9-13` still requires launch-directory independence for *"a direct
   `uvicorn hub.main:app` invocation"*, while **task 4.7 mandates the opposite** and says so in its
   own words. No task touches those lines.
2. **Task 2.7 is a test that cannot fail — measured, not argued.** The reviewer ran it: pytest's
   logging plugin pins the root logger at WARNING, so
   `logging.getLogger("hub.main").isEnabledFor(logging.INFO) is False` holds with `alembic.ini`
   deleted. It ticks green proving nothing. **F190's shape.**
3. **Group 3's sweep is labelled *"settled by R3"* and is incomplete.** Three more
   `uvicorn hub.main:app` launches with no `DATABASE_URL` exist and were never opened:
   `.claude/skills/e2e-loop/SKILL.md:144`, `.claude/skills/autonomous-session/SKILL.md:265` (and
   both `.agents/` mirrors), and **`hub/Makefile:25`** (`make dev`). All survive today only on the
   gitignored `hub/.env`. `tasks.md:9-11` tells a fresh process to treat group 3 as complete.
4. **Remedy (d) leaves a live copy of the false sentence it exists to delete.**
   `hub/tests/test_config.py:3-7` restates the same guarantee; task 1.9 fixes a *different*
   docstring and task 4.1 fixes `config.py`. And 4.1's own replacement text is unqualified in the
   same way, because `src/agentweave/cli.py:617-621` returns a pre-existing `DATABASE_URL`.

**The one thing every round got right for the wrong reason, worth carrying into R4:** all three
asserted the operator's `:8000` is a native `agentweave` start and therefore unaffected — while the
only document they had, **`.claude/reference/hubs.md:37`, says it is a bare
`pythonw -m uvicorn hub.main:app --port 8000` with no `DATABASE_URL`**, i.e. says the change would
brick it. None of them reconciled that. The reviewer measured it from the PID file
(`~/.agentweave/hub/hub.pid` = 9940/8000, mtime exactly matching the process, written only at
`cli.py:1108` inside the detach branch that sets `DATABASE_URL` at `:1038`) and **refutes** the
brick — but on inference from a PID file, not from the process's environment block. **`hubs.md:37`
is false and is still in the file task 4.5 edits.**

- REVISING  a-hub-that-was-not-told-which-database-refuses-to-open-one   adversarial Opus returned DO NOT APPROVE 2026-09-20; four blocking items above; needs R4, not a build

```
ORDER: an-archived-agent-holds-nothing-and-is-offered-nowhere all groups, then a-first-turn-is-not-told-it-has-nothing group 7 ONLY, then one full-surface e2e sweep under the four constraints above
```

**Why group 7 is second and not last.** It is a drive on a throwaway Hub and it is the only thing
standing between `a-first-turn-is-not-told-it-has-nothing` and the archive, which serves the week's
**O5**. It is cheap — one drive iteration — and putting it behind a 38-task build risks losing it to
the clock for no gain.

**If all three finish and the window still has time**, the backlog-first default applies — and the
honest next item is `a-loop-staffs-the-agent-it-names` **group 6.2-REDO**: run
`py -3.11 -m pytest hub/tests/ -q` in full and write the count into the task. **§5 of that change is
still NOT approved** and was held deliberately on 2026-09-19.

**Inherited state, measured at 22:3x so the compose iteration does not have to.** `master` is
`802a8c7` and **CI is green on it** (run `35536597112`, all nine jobs). The branch HEAD `28ed8f1` is
**red on F292 alone** — `4452 passed, 20 skipped, 0 failed, 1 error`, `database is locked`, on a
commit whose entire diff is one `.md` file. Per step 3 that is the gate's business, not the night's:
name it and carry on. Tonight's green rate is **6 of 9**. The full local Hub suite is green twice
over at `802a8c7` (`4460 passed, 86 skipped`, in 33m27s and 26m46s). **Also new tonight: F394 (A)** —
`hub-test` sometimes does not error on `master`, it *hangs*, and three runs were killed or stranded
at the 6-hour mark. A run with no conclusion is neither green nor red; do not read one as either.

---

Sections dated 2026-09-19 and earlier are in `archive/APPROVALS-to-2026-09-19.md` (moved 2026-10-04 to keep the windows' reads small; history, never read by the FIX window).
