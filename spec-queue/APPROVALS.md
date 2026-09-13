# Approvals

The only file the FIX window (23:00-07:00) reads to learn what the operator said. Written by the
DECIDE session, not by hand and not by either scheduled window. Format and semantics: `README.md`
in this directory.

```
- APPROVED  <change-name>   optional note
- REVISING  <change-name>   what needs to change
- REJECTED  <change-name>   why
ORDER: <change-name>, <change-name>, F156      (optional, that night only)
NOTHING TONIGHT                                 (optional, stops the window)
```

Newest day first. Days below the newest are history and are not read.

---

## 2026-09-12

Written by the FILL window, 2026-09-12, from `review/review-2026-09-12.html`. **No status token is
supplied below — that is the operator's to write.** A row with no token is not an approval and the
FIX window builds nothing from it.

**Note for whoever reads this at 23:00:** this section is now the newest, so the 2026-09-11 section
below is history. Its approved change is built and archived
(`openspec/changes/archive/2026-09-12-an-agent-that-recorded-the-evidence-is-the-author`), and its
token is not an instruction. There is deliberately **no `ORDER:` line** — absent an operator
decision the default queue applies, and section 5 of today's page walks what that produces.
Measured: **it produces no feature.** `openspec/changes/` holds one non-archive directory, the
change below, at 0 of 46 tasks. Nothing is waiting to be archived. Of the seven open severity-A
findings the classifier reads, four belong to that change and three (`F299`, `F301`, `F319`) have no
proposal.

`a-url-is-not-a-path` — F300 (A), F312 (A), F321 (A) and F323 (A). Under the default posture the
workspace approver reads a shell command with one regex that does not know where a word starts. It
refuses the request the Hub's own notice instructs, every URL for a filesystem reason, and the
workspace's own subdirectories. And on Windows it lets a quoted traversal out: `F323`,
`echo hi > "..\stray.txt"` in the Bash tool, **measured live writing outside the workspace today**.
46 tasks, 0 ticked. **Python only** — `hub/hub/mcp_server.py` plus its tests and one docs paragraph;
no migration, no API or schema change, **no UI bundle**, so the Python lint set is required (§8) and
`make ui` is not. It includes a live drive on a pre-fix worktree and the fixed tree, and 16 mutation
checks. `openspec validate --strict` passes, re-run 2026-09-12 11:17. All three rounds changed it:
R2 replaced R1's word split with a shell lexer after measuring sixteen escapes in it (five live), and
R3 found a live glued-backslash escape R2's reader passed (`sort -o"..\stray.txt"`) and made the
backstop `\`-aware on Windows. The argument is section 4 of the review page.

**Eight decisions on the page**, in one box near the top. Two change what tonight builds:

- **Decision 2** — `F321` is folded in without a verdict of its own. Splitting it out shrinks the
  change to `design.md` D8(a), and leaves `F300` unable to fire. **No answer means it stays folded
  in.**
- **Decision 3** — the one widening beyond the verdict (`curl example.com/x` becomes allowed, D3),
  and whether `/dev/null` should pass (D10). Task 7.3 takes both into `DECISIONS.md`, after the build
  if you prefer. **No answer means the night builds D3 as written.**

Decision 1 is the row above. The other five are not work for tonight and want no row here: `F319`'s place in the order now that
it is an A; `DECISIONS.md` 1c/1d resting on a false `python -c` measurement (re-derive `F301`'s
notice before proposing it); `CLAUDE.md`'s migration head (`0101` → `0102`); the merge-gate note
("compose waits for the arming commit's CI"); and the correction that the 2026-09-11 research was
late, not skipped.

**The merge gate opened this morning.** `master` is `eac213c`: `6f7e486..eac213c`, 21 commits,
landed. Nothing from the 2026-09-08 branch is unmerged.

If you approve nothing, the FIX window falls to the default queue, and both Windows escapes stay
open. `ORDER:` and `NOTHING TONIGHT` are both available.

**Correction by the DECIDE session:** the page carries eight decisions, and `STATE-day.json` carries
ten. Two were added after the page was written. Item 9 is R3's live `sort -o"..\stray.txt"` escape,
which the change already closes. Item 10 is **`F325` (A)**: Codex's default app-server transport
sends a run no canonical context at all. It was filed at D-7 and is not on the page. It is not work
for tonight.

**DECIDED by the operator, in session, 2026-09-12 afternoon**, after an adversarial Opus review run
before approving, as on 2026-09-11. The review's verdict was **approve**. It measured both live
Windows escapes (F323, and R3's Z1) writing outside today and refused by the design. It measured
F300's instructed request, header included, going from denied to allowed. It found **no escape the
design allows that today refuses.** It found one residual class the design did not name: PowerShell
runtime path builders (`Set-Content (Join-Path .. x)`, measured writing outside). Those are allowed
today and after. The class is now named in `design.md` D9 and the proposal's non-goals. Nothing
executable changed, and `openspec validate --strict` was re-run after the edit.

- APPROVED  a-url-is-not-a-path   F300 (A) + F312 (A) + F321 (A) + F323 (A), **46 tasks**, 0 ticked. Python only: `hub/hub/mcp_server.py`, its tests, one docs paragraph. No migration, no schema, no API shape, **no UI bundle**, so the Python lint set *is* required (§8) and `make ui` is not. **Verify it as four findings.** §9.1 sets four `Status:` lines, and a run that closes fewer has closed part of a change. **§6.2 must record the actual `tool_name` of every `permission_denied` row.** D1 picks the lexing dialect by that name, and nobody has verified it; the review could not, because it ran no agent turn. **Both Windows escapes must be driven pre-fix and fixed** (§6.2 asks 4 and 5). A table row is not a substitute.

Decisions 2 and 3 on the page were not answered separately, so their stated defaults apply. **`F321` stays folded in**, and the review agreed, because splitting it leaves F300 unable to fire. **D3 is built as written**, which means `curl example.com/x` becomes allowed. `/dev/null` stays refused. §7.1–§7.3 are human-only verification and stay open for the operator. §9.3 still holds: the night does not edit `DECISIONS.md`.

**A second change, specced and decided the same evening.** The operator judged one change too
little for an 8-hour night. So a session ran the full spec loop on F319 + F320 in the afternoon:
R1 `75b11ac`, R2 `895aad9`, R3 `32df122`. The operator answered R2's question with option (a)
(`DECISIONS.md` `F327-scope`, `0e41a15`). An adversarial Opus review then ran before approval, and
its doc-only repairs landed at `992eab9`. **All three rounds and the review each found a real
defect.** The one the review found is that R3's `queued`-only re-read narrows F328 and does not
close it.

- APPROVED  a-refused-review-leaves-nothing-behind   F319 (A) + F320 (B), **52 tasks**, 0 ticked. Code is `hub/hub/turn_scheduler.py` plus one comment in `hub/hub/api/v1/agent_trigger.py`. No migration, no schema, no API shape, **no UI bundle**, so the Python lint set *is* required (§7) and `make ui` is not. It shares no code file with `a-url-is-not-a-path`; the only shared file is `FINDINGS.md`, in separate sections. `openspec validate --strict` passes, re-run 19:30. **Verify it as two findings:** §8.1 and §8.2 each set their own `Status:` line. **F326, F327 and F328 stay open** (§8.3, §8.4, §8.5a). Never set F328 `fixed`.

ORDER: a-url-is-not-a-path, a-refused-review-leaves-nothing-behind

**How the night runs the second change.** This is the pre-approval review's sizing: 98 tasks is
about 5.7 of 8 hours at last night's pace, and only if both drives go cleanly.
1. Build `a-url-is-not-a-path` first and finish it. Start `a-refused-review-leaves-nothing-behind`
   only if **at least 3 hours** remain.
2. Commit per section, in this order: §1, §2, mutations 4.1–4.4c, §3, the remaining mutations, §7,
   §5, §8. **§2 alone is a green, coherent stopping point**, and it fixes F319 at unit level.
3. Do not start the live drive (§5) with less than **75 minutes** left.
4. **Never close out (§8) without the drive.** No `fixed` status for F319 or F320 without §5.
5. Give each change's drive its own fresh profile, for example `drive0913u` and `drive0913r`, and
   its own free port.

If the window ends mid-change, the next night resumes it, and the day window's drain count sees
it and runs one spec loop instead of two.

**BUILT — `a-url-is-not-a-path`, written by the FIX window at close-out, 2026-09-13, not by the
operator.** **44 of 47 tasks are ticked** with actuals. That is the 46 approved plus 5.17, which
S2 added for D11a's sentinel. The three left open are §7.1–7.3, which are human-only (see below).
- **Commits.** Fix `612b9c9`. Pin `00a5569`: D2's table ran against the unmodified `_decide` with
  strict xfails, so the fix is seen to flip them.
- **Mutations.** Seventeen, each killed by the row its task names.
- **Gate.** The whole Hub suite gave 4194 passed, 0 failed. CI's lint set is clean.
- **Four findings, verified as four, plus a fifth.** `F300`, `F312`, `F321` and `F323` each carry
  their own `fixed 612b9c9` line and their own quoted §6.2 evidence. `F331` (A, POSIX) was filed
  by this window at §1. It is closed by the same fix and **tested, not driven**: CI's Linux job
  turned its rows from XFAIL at `00a5569` to PASSED at `612b9c9`. `F322`, `F299`, `F301` and `F332`
  stay open.
- **`tool_name`, as the row demanded.** All six `permission_denied` rows across both drives are
  `tool_name='Bash'`. The PowerShell name was never exercised.
- **Both Windows escapes, driven on both trees.** Asks 4 and 5 were allowed pre-fix (`00a5569` in a
  worktree), and `stray.txt` and `out.txt` were written into `.agentweave\worktrees\`. On the fixed
  tree (`39b6be3`) both were refused, and nothing was written.

The deltas were synced into `agent-capability-plane` (1 MODIFIED, whose scenarios and F301 clause
are byte-identical) and `agent-run-sandboxing` (3 ADDED). Each block is verbatim against the delta,
by script, and `validate --specs --strict` passes 43/43. The change is archived as
`2026-09-13-a-url-is-not-a-path`.

**Still yours:** §7.1, whether the refusal reads in the served UI. §7.2, whether D5's wording is the
lever it needs to be. The one Haiku turn stopped and asked in prose, not through `ask_user`, and
named `WebFetch` without calling it. §7.3, N3 and `/dev/null`, to decide in `DECISIONS.md`. And D11a's four
departures from R2's reader.

---

## 2026-09-11

Written by the FILL window, 2026-09-11, from `review/review-2026-09-11.html`. **No status token is
supplied below — that is the operator's to write.** A row with no token is not an approval and the
FIX window builds nothing from it.

**Note for whoever reads this at 23:00:** this section is now the newest, so the 2026-09-10 section
below is out of scope and the token on its row is history, not an instruction. There is deliberately
**no `ORDER:` line here** — absent an operator decision the default queue applies, and section 5 of
today's review page walks what that produces. Measured: **it produces no substantial build.**
`openspec/changes/` holds one non-archive directory, the change below, at 0 of 39 tasks; nothing is
waiting to be archived; and of the six open severity-A findings exactly one has a proposal, which is
that same change.

`an-agent-that-recorded-the-evidence-is-the-author` — F306 (A) and F316 (A), retired together. An
agent that recorded the evidence for a task was staffed to review, and approved, its own work,
because the exclusion set reads three record sources and the evidence table is a fourth it does not
read. 39 tasks across the union function, four call sites, the approval guard, six MODIFIED
requirements in `agent-flows` and `task-lifecycle-governance`, and new coverage including a mutation
table. **No migration, no new column, no API shape change, and it does not touch the UI bundle.**
`openspec validate --strict` passes, re-run 2026-09-11 10:52. All three rounds changed it — the
argument is section 4 of the review page, and R3's finding is that R2's own repair would have shown
the operator a sentence that is untrue of the task in front of them.

**Six decisions on the page**, all of them in one box near the top so none is buried. Two want an
answer before tonight and four are about how the loop works:

- **Decision 6 on the page** — should `F316` be split out into its own change? It is folded in as
  task 2.4, which lifts out cleanly. **No answer means it stays folded in**, which is the only one
  of the six that changes what tonight builds.
- **Decision 1 on the page** — the research task did not run this morning and there is no file for
  2026-09-11. The scheduler skipped the occurrence; cause unverified and no log exists to read.
  Nothing was blocked today, but this is the loop's only input from outside itself.
- The other four: whether `F292` should displace something in the spec-loop order now that its
  mitigation is measured and refuted; the merge-gate rule change, which is a `day-window.md` edit
  and so the operator's; whether the ledger's "shape of a fix" lists should be labelled unverified
  after two of `F306`'s three were measured wrong; and what "blast radius" should mean in a
  proposal, after three rounds measured it three different ways and the widest one found the defect.

**The merge gate did not open today** and `master` is still `5d928f5`, 26 commits behind. Three of
today's four checks failed on timing — that diagnosis is now complete — and the fourth failed
because CI went red on a **documentation-only** commit, which is `F292`. **No `HEAD`-shaped gate rule
can work while `F292` stands**, so the rule change proposed yesterday is necessary and not
sufficient. Section 1 of the page has the four checks side by side.

If you approve nothing, the FIX window falls to the default queue, which tonight is thin enough to
be worth naming: the `F292` concurrent sampler (`conftest.py`-only, no spec) and the `F317`
classifier repair. Neither lands a feature. `ORDER:` and `NOTHING TONIGHT` are both available.

Two things on the page are **not** work and want no row here: the research-task question, and the
merge-gate rule change — both are the operator's to act on outside this file.

**DECIDED by the operator, in session, 2026-09-11 evening**, after an adversarial Opus review
commissioned specifically before approving — *"Before approving ask a opus model to review
everything."* That review is recorded as **R4** and it found a defect all three rounds missed. The
change was repaired at `67bebb6` before this row was written; **the row approves the repaired
change, not the one the review page describes.**

- APPROVED  an-agent-that-recorded-the-evidence-is-the-author   F306 (A) + F316 (A), **42 tasks**, 0 ticked. Python only — no migration, no schema, no API shape, **no UI bundle**, so the Python lint set *is* required (§6) and `make ui` is not. `openspec validate --strict` passes, re-run 2026-09-11 19:55. **Verify it as two findings** — §7.0 and §7.1 each set their own `Status:` line; a run that closes one and reports the change done has closed half a change. **And verify it as five call sites, not four**: the R4 repair added a fifth defence (§3.4) and a run that stops at §3.3 ships the wedge described below.

**What R4 changed, and why the night must not treat §3.4 as optional.** Sections 1–3.3 teach
`_guard_author_is_not_reviewer` that an evidence author is an author. `_guard_reviewer_is_not_the_author`
sits fifteen lines below it on the same edge of the same review, and §3.4 previously said to leave it
alone — every round checked whether that guard was *in scope* and none asked what §3.1 did *to* it.
It refuses only when a completer is recorded; an operator completion records none, so an operator
`PATCH` carrying `{assignee: <evidence author>, status: under_review}` is permitted, and §3.1 then
refuses that agent every review outcome. Entry permitted plus every exit refused is a task no actor
can move, held by an agent no transition names, which the flow reports as a review genuinely in
progress and never restaffs. **That is the F45/F70/F161 shape, manufactured by the change whose
subject is removing it.** §3.4 is reversed and carries a fourth MODIFIED requirement, because the
base spec's *"a task whose completer is unknown may enter review"* scenario is exactly what breaks.

**§5 is kept — the three live drives are in scope.** Rejected: the smaller cut (§1–§4 plus §6). The
change's own history is the argument: R2 and R3 each found what a green suite hid, and §5.1's
misread-a-green trap is now closed — it names a `git worktree`, **forbids `git stash`**, and requires
the approving transition row as the only acceptable proof of the reproduction. A drive that cannot
show that row leaves §5.2 unticked and says so, rather than reporting a pair.

**`DAY-1`-equivalent, decision 6 — answered: NO, `F316` is not split out.** It stays folded in as
task 2.4, which is where R2 filed it and where §7.0 closes it. Splitting it would put a second
change in a night already carrying 42 tasks, and F316 is a one-term edit to the same function.

**Read the mutation-hygiene block at the top of §4 before starting §4.7.** Nine tasks require a tree
with the fix deliberately removed, and this window commits and pushes every firing. Commit the
implementation first; keep each mutation and its restore inside one firing; require
`git status --short` empty after every restore; stop *before* a mutation rather than partway through
one. A boundary landing mid-cycle pushes the hole reopened under a message saying it is closed.

**No `ORDER:` line.** This is the only approved change, so the order is not in question, and an
`ORDER:` line is read verbatim with no date check — a liability the moment it outlives its day.

**BUILT — written by the FIX window at close-out, 2026-09-12, not by the operator.** The approved
row above is complete: **43 of 43 tasks ticked** with actuals. That is the 42 approved plus 4.11a,
which iteration 2 added because R4's §3.4 moved a second existing test; that fixture was repaired to
operator evidence, and the guard was left as it was. Fix `4929ea0`, tests `40bd429`. **All five
call sites are in**, §3.4 included, as the row demanded. There are ten mutations and each one
killed its target leg. The whole Hub suite gave **4057 passed, 0 failed**, and CI's lint set is
clean.

**Driven live on both trees, and proven from the tables, not the harness.** The drive harness
prints green on either tree.

- **Pre-fix** (`37b8226` in a worktree): the evidence author approved its own work at seq 8 on
  `proj-34d006e2f3e5`.
- **Fixed**: the flow's only staffing was the other agent, and it approved at seq 4 on
  `proj-192ee0e59efb`. The author was refused through its own MCP approval (403), a flow firing
  (409, *"could not staff this step"*), hand dispatch (403, before any run), and the operator's
  §3.4 `PATCH` (403, with the assignee rolled back).

Deltas were synced into `openspec/specs/agent-flows` and `task-lifecycle-governance`, 7 blocks
verbatim, and the change is archived as
`openspec/changes/archive/2026-09-12-an-agent-that-recorded-the-evidence-is-the-author`.

**Verified as two findings, as the row demanded.** `F306` and `F316` each carry their own
`**Status:** fixed 4929ea0` line. `F306`'s two statements that R1 refuted are corrected in place.
`F316`'s entry says plainly that its restaff route is proven at unit level and not on a live Hub.
The census moved exactly those two verdicts. One new finding came out of the mutation run:
`F319 (B)`, a scheduler-path refusal that leaves the refused reviewer holding the task. It is filed
and has no proposal.

---

## 2026-09-10

Written by the FILL window, 2026-09-10, from `review/review-2026-09-10.html`. **No status token is
supplied below — that is the operator's to write.** A row with no token is not an approval and the
FIX window builds nothing from it.

**Note for whoever reads this at 23:00:** this section is now the newest, so the 2026-09-09
`ORDER:` line below is out of scope and no longer read. There is deliberately **no `ORDER:` line
here** — absent an operator decision the default queue applies, and section 5 of today's review page
walks what that produces (measured: thin, because only one open severity-A finding has a proposal
and it is the one below).

`2026-09-10-the-control-that-asks-holds-the-keyboard` — F309 (A) and F310 (B), retired together.
A ticket cannot be blocked from the keyboard, and one Escape dismisses two things; both are the same
failure of arbitration, where two mechanisms act on one keystroke and the one further from the
operator wins. 40 tasks across the hook, the two nested owners, the menu, the reason panel, the
bundle, unit coverage and two browser drives. UI only — no route, schema, migration or API shape.
**Touches the committed bundle**, so it is the one bundle-touching change if it is taken. All three
rounds changed it; R3 found that the third instance R1 and R2 both called "repaired for free" cannot
be repaired that way at all — the argument is section 4 of the review page.

**One question on the page**, `DAY-1`: should this change be widened to swallow F307? It deliberately
does not, for three stated reasons, and the reversal is yours. No answer means the split stands.

If you approve nothing, the FIX window falls to the default queue. `ORDER:` and `NOTHING TONIGHT`
are both available.

**DECIDED by the operator, in session, 2026-09-10 18:30**, on the review page published at
`https://claude.ai/code/artifact/a762970b-f7a4-4919-bdcf-263abaa54554`. Both answers below are the
operator's; the notes are the reading they were given.

- APPROVED  2026-09-10-the-control-that-asks-holds-the-keyboard   F309 (A) + F310 (B), 40 tasks, 0 ticked. **UI only** — no route, schema, migration or API shape — and **touches the committed bundle**, so §5 (`npm run build` then `make ui`) is not optional and the Python lint set is not required (say so in the log rather than passing over it). `openspec validate --strict` passes, re-run 2026-09-10 18:20. **Verify it as two findings**: a run that closes one and reports the change done has closed half a change. Note the dependency R3 established — **the F310 half depends on the F309 half**, because arbitration by `defaultPrevented` presumes the nested owner actually holds the keyboard, and `DirectoryPicker`'s handler is bound where focus never goes (`design.md` D9, `tasks.md` §2.2).

**`DAY-1` — answered: NO, the split stands.** The change is **not** widened to swallow `F307`. The
operator's reason is the proposal's second: `F307`'s fix requires deciding where focus lands in a
*destructive* confirmation — its first focusable is Cancel, its last is the destructive button — and
`F307` declines to guess. **That decision is a review page's, not a window's**, and widening would
put a severity-A keyboard repair on a path the Hub makes mandatory behind a design question about
five dialogs that are not broken in this way. `F307` stays open and is not queued tonight.

**No `ORDER:` line.** The default queue applies and this is the only approved change, so the order
is not in question. Deliberately not added: an `ORDER:` line is read **verbatim and with no date
check**, which is what made the 2026-09-09 section necessary, and one is a liability the moment it
outlives its day.

**BUILT — written by the FIX window at close-out, 2026-09-11, not by the operator.** The approved
row above is complete: 41 tasks ticked with actuals, `F309` and `F310` both driven green in a real
browser against the served bundle (`t_d1_0910_escape_across_the_dialogs.py` 48/0,
`t_d1_0910_rowmenu_leaves_the_page_inert.py` 37/0), delta specs synced into
`openspec/specs/hub-interaction-feedback` and `openspec/specs/task-lifecycle-governance`, and the
change archived. **Verified as two findings, as the row demanded** — each carries its own
`**Status:**` line in `FINDINGS.md` naming the two commits it took. `DAY-1`'s answer was honoured:
`F307` is untouched, still reproduces at `HEAD`, and now carries a dated note in its own section
saying why this change left it standing. One new finding came out of the drive, `F315 (C)`, filed
and deliberately not repaired — it is a whole-menu gap, not one button's.

---

## 2026-09-09

**Why this section exists: the 2026-09-08 `ORDER:` line below is now a trap.** The night window
reads *the newest day section only* and takes an `ORDER:` line **verbatim, ignoring the default
queue** (`.claude/loops/night-window.md`, iteration 1 step 2) — and it applies **no date check**,
unlike `DIRECTION.md`. Three of the four changes that line names were built, driven and **archived
by the night of 2026-09-08**. Left alone, tonight's window would queue three archived changes.

**No new approval is granted here.** The row below is the operator's 2026-09-08 verdict carried
forward, restated because only the newest section is read. Written 2026-09-09 morning by a RESUME
session; the `ORDER:` line is the operator's, given in session.

- APPROVED  2026-09-07-clearing-instructions-asks-first   DAY-3. 25 tasks, 1 ticked (5.2, the pre-change drive, closed on real evidence committed at `3078843`). **Touches the bundle.** Unchanged from 2026-09-08 — it is the one change on that night's `ORDER:` line the window did not reach, because it is bundle-touching and iteration 16 had already spent that slot.

ORDER: F142, 2026-09-07-clearing-instructions-asks-first, R1-ratchets, R2-archive-collision, R34-model-catalog, DAY1-constraints

**Why the drive leads.** `F142` is the **last open severity-A finding**, and it is not a build: the
fix shipped at `f3a778f` on 2026-08-31 and the single unmet condition is that **nobody has driven
it**. Its own change document says so — task group 7 is headed *"Written, compiled, and not
driven"*, and 7.1/7.2 are ticked as *written*, which is the ordinary reading of a task list and not
evidence of a run. A few hours against a live Hub takes the open severity-A list to **zero**, which
is the milestone `ROADMAP.md` names; the 25-task bundle change would very likely consume the whole
night and leave the A-list at one.

**What the drive has to cover** (both from the change's own 7.1/7.2, restated here so the window
does not have to find them):

- `AW_COMPLETE_BY=operator` on `scripts/drive/t_row12_review_leg.py` must reach a **staffed
  review** — or, in a project with no second agent, a `409` whose reason names *the task* rather
  than the queue histogram. **Assert specific strings**: an earlier version of that file passed its
  checks against content that said the opposite.
- **Row four, which has no coverage at all**: the operator completes a task **no agent ever
  touched**, and a review is staffed with nobody excluded. That is the widest-exclusion arm.
- **Do not be surprised by `F167` (B)**, a known residual on the adjacent path: an all-operator
  history defeats `wedged_review`'s recovery and takes the `in_flight` arm. It is scoped to F167 and
  does not reopen F142.

**On the change, if the night reaches it.** It touches `hub/hub/static/ui`; nothing else tonight
does, so the one-bundle-change-per-night constraint is satisfied. Rebuild the bundle through
`make ui` / `scripts/refresh_ui_bundle.py` so the stamp is written — only that script writes it.

### The last four ORDER items — decided work that needs no proposal

**Added 2026-09-09 ~18:50 on the operator's instruction**, whose stated preference is *finishing the
roadmap*. These are **not changes** and have no directory under `openspec/changes/`; they are the
four decided-but-unbuilt items that touch only `scripts/`, `tests/` and packaging config, so the
round discipline does not gate them — there is no product behaviour to spec. Each closes a
`ROADMAP.md` row outright.

**They are last for a reason.** F142 and the approved change come first and neither may be shortened
to reach these. **If the window ends with any of the four untouched, that is the correct outcome**,
not a miss — each is sized to finish inside one firing, so stopping between them leaves nothing
half-built. Take them in ORDER sequence.

**`R1-ratchets`** — three checks, from `DECISIONS.md` `### R-1 — Enforce, as a ratchet`. The
contract is quoted, not paraphrased: *"the repo writes a check, and the check freezes today's count
as a ceiling that may shrink and may never grow."* And, load-bearing: ***"Existing instances are not
repaired before the check may pass."*** Do not fix the 35 routes or the 51 surfaces. All three
promote scripts that already exist and were re-verified 2026-09-08:

| Check | Script | Ceiling to freeze |
|---|---|---|
| route reachability | `scripts/drive/n10_route_reachability.py` | **35** clientless of 187 declared route+method pairs |
| query error surface | `scripts/drive/n11_query_error_surface.py` | **51** operator-reachable MISREPORTs of 54 |
| dependency ceilings | — | exactly **three** `fastmcp>=2.0,<4` declarations (`pyproject.toml:47`, `:71`, `hub/pyproject.toml:24`) and `starlette<2.0` (`hub/pyproject.toml:32`) |

**Both scripts are static** — no Hub, no database, no network; verified today. **But `n10` imports
`hub.main:app`**, so its check must live where that import resolves: `hub/tests/`, not `tests/`.
Confirm that before placing it — a ratchet that cannot import is a ratchet that never runs.
`tests/test_skill_sync.py` is the model for a check that must skip rather than fail when its subject
is absent.

**`R2-archive-collision`** — a script under `scripts/`, run before archiving, from `DECISIONS.md`
`### R-2`. It warns when two changes both carry a `## MODIFIED` block for the **same requirement**.
The motivating incident is in that verdict: archiving the second **reverted the first**, dropping a
qualification that had just landed — one collision in a batch of seven. Its recorded weakness is
known and accepted: *it only fires if whoever archives remembers to run it.* Build the script; do
not redesign it into a hook without a decision.

**`R34-model-catalog`** — a `scripts/` tool, from `DECISIONS.md` R-3.4. `model_catalog.py` names
`~/.codex/models_cache.json` as its source of truth and **nothing re-reads it**: the only mention is
the module docstring at `:34`, describing how the literal was *derived*. The cache is per-machine
and absent in CI, so this can only be a `scripts/` tool or a skip-if-missing check — that was the
verdict, and it is why this is not a CI gate. *"Doing nothing is defensible; doing nothing silently
is what let a phantom default model sit in the catalog for four weeks."*

**`DAY1-constraints`** — from tonight's `DECISIONS.md` verdict, `DAY-1`. Add a development
constraints file pinned to CI's resolution — **starlette 1.6.0, fastapi 0.141.1** — and leave
`hub/pyproject.toml`'s published range (`starlette<2.0`, `fastapi>=0.110`) untouched. Two conditions
from the verdict, both binding: it is **development-only and not a second source of truth** for what
the Hub supports, and **both the CI job and `CLAUDE.md`'s documented local commands must install
through it** — a constraints file nothing installs through is decoration, and the drift it exists to
stop returns silently. This is what would have caught today's starlette defect before a push instead
of thirteen commits later.

**Out of scope tonight, deliberately:** the missing guard against a fourth `app.routes` occurrence.
The review page records why a naive grep fails — it false-positives on the three files whose
comments document the trap, `hub/tests/_routing.py` included. Unowned, and not this window's to
invent.


### Addendum from the FILL window, 2026-09-09 ~10:55 — no rows, because nothing was specced

**This is not an approval and grants none.** It adds no change, no order and no status token; the
section above is unchanged and remains the authority for tonight. Written by the day window at the
end of its queue, per `.claude/loops/day-window.md` D-5.

**There is nothing to approve today.** Per `DIRECTION.md`'s `2026-09-09` section — the operator's
*"nothing new but finish everything that we have open"* — **no spec loop ran**, so no change was
proposed and this section has no row per change. The day's slots went to the red CI, a drive of the
three changes the night built, the whole unclassified half of `FINDINGS.md`, and key hygiene.

The page is `spec-queue/review/review-2026-09-09.html`. It carries **three decisions** —
`DAY-1` pin `starlette` or keep resolving newest; `DAY-2` whether the no-grounds notice should stop
asserting `no MCP tools this turn` (new, `F302`); `DAY-3` the posture question on a harness without
MCP (`F299`, carried and enlarged by `F300`/`F301`).

**One correction to the section above, and it changes a count rather than the plan.** That section
calls `F142` *"the last open severity-A finding"*. After today's classification the instrument reads
open severity-A as **three** — `F299`, `F300`, `F301`, all filed by the night of 2026-09-08 — and
`F142` itself sits in `CONFLICT`, not `OPEN`. The practical meaning survives: those three are the
`DAY-3` decision and are not buildable unattended, so `F142` is still the only severity-A a night
window can act on, and the order above stands as written.

**Merge-gate state at the time of writing**, since it is what the morning firing will read: the
`hub-test` job that concluded `failure` on thirteen consecutive completions was repaired at
`630473f`, which then concluded `success`. Of the five commits that have completed since, **four are
green**; the one exception, `2b33a6e`, failed on `F292`'s intermittent `database is locked`,
occurrence #12. `master` has not moved, so a fast-forward is still available.

---

## 2026-09-08

## ALL FOUR APPROVED — the operator, in session, 2026-09-08

**Verdict given after three review rounds**, the third of which measured the F295 arrangement rather
than reading it. The four rows below are the authority; everything after them on this page is the
reasoning.

- APPROVED  2026-09-07-a-dead-connection-is-never-handed-back-out   F295 (A). 25 tasks, 1 ticked (2.4, a question not a step). Python only — no migration, no UI, no bundle. **Task 1.6 carries an open choice**: the delta says the neutralisation SHALL cover *"every path"* and tasks 1.1-1.5 build four of five; the fifth (`close_detached`, via `_finalize_fairy`) is measured unreachable today. Write the two lines or narrow the requirement — the task states both and either satisfies the approval.
- APPROVED  2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing   sidequest, no finding number. 35 tasks. Python and docs only — no UI, no bundle. **Task 2.2 was rewritten by the third review** after it was found unfollowable (the ordering was backwards); build from the rewritten text, not from any earlier copy.
- APPROVED  2026-09-05-the-conversation-carries-its-own-run-facts   F274 (A). 44 tasks. **Touches the bundle.** Phase 0 is a hard gate — *"if phase 0 has not been recorded, do phase 0 and stop"* — and its port instruction was reworded on 2026-09-08 after the clean slate invalidated the old one. Likely two nights.
- APPROVED  2026-09-07-clearing-instructions-asks-first   DAY-3. 25 tasks, 1 ticked (5.2, the pre-change drive, closed on real evidence committed at `3078843`). **Touches the bundle.**

ORDER: 2026-09-07-a-dead-connection-is-never-handed-back-out, 2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing, 2026-09-05-the-conversation-carries-its-own-run-facts, 2026-09-07-clearing-instructions-asks-first

**Why an `ORDER:` line at all, and why this one.** Without it the default queue is **backlog first**
(`README.md`, decided 2026-09-01) — unarchived changes, then findings, and `APPROVED` rows only
third. Four freshly approved changes would sit behind that. The sequence is the two **bundle-free**
changes first, because they can land beside anything and cannot conflict, highest severity leading;
then the two that rebuild `hub/hub/static/ui`, **strictly one per night**. Those two share no source
file — their only collision is the generated artefact — so the constraint is on the bundle, not on
the code.

**One change per night. `ORDER` is that night's only**, so it needs rewriting each evening with what
remains.

---

### The row that made this section necessary

**Written by a second review session, not by a window.** This section originally existed for one
reason: to give `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` a row it never had. It
came off the sidequest branch and merged straight to `master` at `2b4dce4`, so it never entered the
DECIDE flow and **appears on no review page.** Without a row it could not take a verdict, and
approving it would have meant approving something the operator had never been shown.

The other three changes have descriptive rows under `## 2026-09-07`, `## 2026-09-06` and
`## 2026-09-05`. Those sections are **history and are not read** by the FIX window, which is why all
four verdict rows are restated above rather than left in place.

- 2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing   sidequest, no finding number. 35 tasks in 6 phases. **No migration, no UI, no bundle rebuild** — `tasks.md:7` says so itself; Python and docs only. A run whose harness cannot use MCP is handed a working credential (`AW_RUN_TOKEN`) and the Hub's own address (`HUB_URL`) in its environment, and is then told in the first line of its prompt that it has no way to reach AgentWeave at all (`launchability.py:325-330`, prepended at `agent_trigger.py:1006-1007`). Both halves verified against the code. The branch was emptied rather than repointed when `2026-08-03-single-runtime` cut the CLI to five commands; the HTTP plane those commands wrapped did not go anywhere. Four parts: the notice tells the truth; a discovery surface describes the operations as requests rather than tool calls; the two adapter-only rules (`archive_job`'s confirmation, `ask_user`'s wait) move into the contract; and a run is told the access path it actually has instead of having the tool-protocol path asserted for it. Two ADDED requirements plus one MODIFIED in `agent-capability-plane` — the MODIFIED is *HTTP and MCP access have equal capability* (shipped at `:107`), which **already names this exact deployment**: *"some environments forbid MCP servers while still allowing ordinary local API calls."* `openspec validate --strict` passes.

**Read this before approving it.** The change is not filed against a numbered finding — it is filed
against a shipped requirement whose agent-facing half was never built, which is a weaker trigger
than F274's or F295's and a stronger one than a preference. It also found, and deliberately did
**not** fix, that `openspec/specs/agent-capability-plane/spec.md:140-185` still states two
requirements for the unasked-question backstop **retired on 2026-08-20 at the operator's request**
and dropped by migration `0082`. Confirmed present in the shipped spec by this review. That is a
false current-behaviour requirement sitting thirty lines from the one this change edits, and it
belongs to retiring `openspec/changes/2026-08-07-unasked-question-backstop`, not here — but it is
how a later round inherits a retired feature as evidence, so it is put to the operator now.

**A third review ran after this section was written** —
`review/third-review-2026-09-08.md`, an Opus subagent briefed to work blind and reconcile only at
the end. **It agrees none of the four needs another round**, and it is the first round to *measure*
the F295 arrangement rather than read it (raise-only checkout plus the `close` listener recovers in
0.00s; without the listener the same checkout survived a 20-second timeout and ran seven minutes to
a manual kill). It found **one thing that blocked implementation**: change 4's task 2.2 had its
ordering backwards — the context materialisation at `agent_trigger.py:960` happens 46 lines *before*
`resolve_access_path` at `:1006`, so the value it told the implementer to pass through does not
exist yet. Repaired, along with six editorial findings. Two are left for you: **F295's new task 1.6**
(the delta says "every path" and the tasks build four of five; the fifth, `close_detached`, is
measured unreachable today — write the two lines or narrow the requirement) and **R-7**, an
unmeasured widening of the working indicator that task 6.7's drive should watch for.

**One correction to `ROADMAP.md`, which bears on the `ORDER:` line.** Stage 0.3 says *"Three of the
four touch `hub/ui` and the committed bundle... Only one is bundle-free."* That is wrong: **two are
bundle-free.** This change names no `hub/ui` file anywhere and declares its own bundle exemption at
`tasks.md:7`, and `a-dead-connection` is Python-only. Only `the-conversation-carries-its-own-run-facts`
and `clearing-instructions-asks-first` touch the bundle, and those two share **no source file** —
their only collision is the generated `hub/hub/static/ui`. So the ordering constraint is narrower
than the roadmap states.

---

### The day window's section — 2026-09-08, and it has no rows

Review page: `review/review-2026-09-08.html`. **No change was proposed today, so there is nothing
here to take a verdict.** `DIRECTION.md`'s `2026-09-08` section forbade the spec loop outright — no
R1/R2/R3, no approval token, no decision marked, and nothing found today specced. The window held to
all four. This subsection exists so a reader does not mistake the absence of rows for an omission.

**The four `APPROVED` rows above are still the night's authority and were not touched.** They were
written by you at 01:24 today (`0d82d6d`); the day window may not add to them, reorder them, or write
a token of its own. `ORDER:` stands exactly as it was. **Tonight at 22:55 is the first build night
those four approvals have ever had** — `AgentWeaveArmNight` measured `Ready`, `LastTaskResult=0`,
next run 2026-09-08 22:55.

**One fact the night needs, and it is the reason this subsection is not empty.** F292's CI failure
rate is now measured rather than estimated: **11 failures in 54 runs (20.4 %) across all branches
2026-09-07T00:00Z → 2026-09-08T08:26Z, and all 11 are F292.** CI redness on this project currently
has exactly one cause. So a red CI on tonight's build is more likely F292 than a regression from the
change, and the window **must classify with `gh run view <id> --log-failed` before diagnosing a
regression**. Two further occurrences (#10 `34205968391`, #11 `34206652706`) were read while writing
the review page; see F292's last section for what they add and what they correct.

**Three things on the review page are questions, not work, and want no row here:** DAY-1, whether the
loop may rotate a trial-profile Hub key itself (the specific instance is closed — you rotated it —
but the policy is open); DAY-2, whether the residual `aw_live_` literals sweep should be queued (the
page recommends leaving it); and DAY-3, whether building Stage 2 tonight through a 20.4 %-wrong suite
is accepted, or `ORDER:` should be held until F292 has a named holder. Answer any of them in
`DIRECTION.md`.


## 2026-09-07

Review page: `review/review-2026-09-07.html`. **Two changes proposed, each taken through all three
rounds. Not one of the six rounds was a no-op** — the seventh and eighth consecutive outings. The
second change is at the bottom of this section, with its own verdict row. Round 3 is the one to read: it did not
merely confirm the change, it **moved the fix**, on a measurement neither earlier round made.
`await engine.dispose()` -- task 2.3, the last thing the change's own new shutdown does -- was
measured to **hang forever** on the very connection the change is about (40-second external kill;
the same dispose returns in **0.00s** once the neutralisation moves to the `close` pool event). As
rounds 1 and 2 wrote it, this change could have turned *a traceback on a process that is leaving
anyway* into *a Hub that will not exit* -- strictly worse than the defect. The neutralisation is now
sited on `close`, which every close of a pooled connection passes through, so one listener covers
four paths with no ordering hazard.

**The merge gate opened this morning.** `master` fast-forwarded `ab60cf3..9fd9853`, 26 files; the
2026-09-04 cycle is fully landed and the cycle branch is now `autonomous/2026-09-07-daily`. It
deferred twice first, on a different failed condition each time, and **DAY-1** on the page asks
whether the gate needs rewording -- CI takes 10-16 minutes on this branch, so a firing that commits
before checking fails the CI condition and one that checks late fails the tree-clean condition. The
two chase each other, and today it opened only because a manoeuvre was improvised on the spot.

**Written by the day window, which does not fill in its own verdict.** The row below carries no
status token. Write `APPROVED`, `REVISING` or `REJECTED` in front of the change name.

- 2026-09-07-a-dead-connection-is-never-handed-back-out   F295 (A). 23 tasks in 4 phases. No migration, no API shape change, no UI. A pooled database connection can outlive the event loop that last queued work on it; the aiosqlite worker thread dies trying to report a result to a closed loop, the connection stays in the pool looking healthy, and any later use of it hangs forever with no timeout that can rescue it. Two ADDED requirements in `app-lifecycle`: shutting the instance down settles its background runs and disposes its engine *while the loop still runs*, and a connection whose driver worker is gone is replaced rather than reused or disposed of. Touches `hub/hub/db/engine.py`, `lifespan` in `hub/hub/main.py`, `hub/tests/conftest.py`, plus tests. `openspec validate --strict` passes.

**Read DAY-2 before approving this one.** The change is filed against a severity-A finding whose
**production blast radius no round could establish by measurement**, and all three rounds narrowed
it further rather than widening it. R1 found the Hub's only in-process loop closure is process exit.
R2 re-derived that negative independently -- it held -- and established that the worker threads are
daemon *because SQLAlchemy makes them so*, so the process really does leave. R3 measured that
`agentweave stop` on Windows force-kills and runs no shutdown sequence at all, so the production
occurrence is narrower again, and it measured one of R2's two test-suite paths **false** (a disposed
engine calls `pool.recreate()`, so the connection belongs to a pool the engine no longer references
-- a file-handle leak, F292's subject, not a reusable dead connection). The test-suite half is now
**one** unrun path, not two. So the questions are: does F295 keep its **A**, and is the change worth
a night slot on shutdown-hygiene and test-harness value alone? The proposal argues yes, and R3 gave
it a second reason: the reading was worth doing whatever the severity turns out to be, because the
fix as originally specced would itself have hung the shutdown.

**Two new findings, and one of them is a candidate for tomorrow's spec loop.**

- **F296 (C, harness)** -- `scripts/drive/t_d4_instructions_failed_load.py:316` asks for role `button` on a control that is a `<select>`, so its `0` could never have been anything else, and two windows quoted that `0` as evidence about the product. Column C of F271 is now closed **by measurement** (20/0, mutation-checked at 17/3) rather than by construction, and the real reason is navigation: the switcher sends you to `tab=overview` and the page unmounts. **A change that made the switcher preserve the current tab would put column C back in play.** The fix is one word plus deleting a now-false print -- harness-only, no product code, available to a night window under the no-spec carve-out without any approval.
- **F297 (B)** -- `src/agentweave/cli.py:528-545`. `agentweave stop` on Windows runs `taskkill /PID <pid> /F` with no signal first, so the Hub's ASGI lifespan shutdown never runs and `terminate_all_active_runs()` is skipped, against the shipped `app-lifecycle` scenario's own clause *"active runs across projects are terminated through normal shutdown"*. Measured, not reasoned. It was deliberately kept **out** of the F295 change -- it is CLI work against a different shipped requirement. **DAY-3** asks whether it gets its own spec loop and in what order. They interact: a graceful Windows stop would start *running* the shutdown sequence F295's change is adding, so landing F295 first is the safer order.

**Still unanswered from earlier pages, and each is one line.**
`2026-09-05-the-conversation-carries-its-own-run-facts` (F274) sits at line 203 of this file **with no
verdict token** -- 44 tasks, fully specced, and the one change in the repository that is ready to
build; no night window may touch it until it reads `APPROVED`, `REVISING` or `REJECTED`. And
2026-09-06's DAY-2 -- spend a night slot on F292, or let the CI gate tolerate a re-run -- is still
open; today's spec loop deliberately does **not** claim to resolve F292.

**If you approve nothing**, tonight falls to the backlog and has one real item: the re-drive banners
on F140/F142/F154/F155, which each have an archived, never-driven change. Step 1 (archiving) is
empty -- both open changes are unimplemented, 0/44 and 0/23 -- and the B-severity findings have no
proposals, so the backlog rule sends them back to tomorrow's day window rather than tonight.
`NOTHING TONIGHT` is a valid answer and cheaper than silence.

**A second change was specced after the section above was first written, and it too had all three
rounds plus a drive.** It is the confirmation you asked for in `DIRECTION.md`'s 2026-09-07 section,
answering 2026-09-06's DAY-3. It carries **no question** -- only a verdict token.

- 2026-09-07-clearing-instructions-asks-first   Your own queued scope, no finding behind it. 24 tasks in 6 phases. No migration, no server code, no change to what the route accepts. An operator who has the project's instructions on screen, selects all, deletes and clicks Save loses them: **measured in a browser**, not read out of the source -- exactly one PUT carrying `{"content": ""}`, **zero dialogs** at any point, the row read back as `''`, the ordinary green success badge, and nothing anywhere on the rendered page saying undo, restore, revert, recover or history (`/project/instructions/history` is 404). The store is one row upserted in place with no revision column and no second table, so the loss is unrecoverable. One `ADDED` requirement with six scenarios plus **two** `MODIFIED` requirements in `project-instructions`. Adds `hub/ui/src/components/instructions/ClearInstructionsDialog.tsx` (the `ArchiveConfirmDialog` shape, reusing `hooks/useDialogFocus.ts`) and a gate in `InstructionsPage.tsx`; the committed bundle must be rebuilt, so `make ui` is part of the work. `openspec validate --strict` passes.

**Each round found something, and the third one drove it.**

- **R1** found the change contradicted *Hub UI provides instructions editor* -- archived **the day
  before** -- whose save scenario requires the click to persist. The delta `MODIFIED`s it rather than
  shipping the contradiction. R1 also answered the question DIRECTION.md set it: the confirmation
  **cannot** fire over a state that was never loaded, because F271's `actions={data ? … : undefined}`
  gate means there is no Save control at all in the error and in-flight states. Four confirmation
  primitives already ship and none was invented.
- **R2** found the delta's own two requirements contradicting each other **over a single newline**.
  `design.md` D1's predicate trims both sides and always did; the requirement text did not carry it,
  so a save leaving one newline behind was required to persist by one requirement and to be confirmed
  by the other, and a save blanking whitespace-only stored content was required by neither. Both now
  say "containing more than whitespace" / "empty or only whitespace". **Nothing about the design
  changed** -- the conclusion was right while the argument stating it was not. R2 also found two of
  R1's citations wrong (the `models.py` grep returns two lines not three, and could not establish its
  negative anyway; `instructions.py:66-67` contained neither statement quoted from it) and *measured*
  R1's one unmeasured belief, which held.
- **R3 drove the pre-change product**: `scripts/drive/t_d8_clearing_instructions_prechange.py`,
  Chromium against the served bundle on a throwaway Hub, **27 passed / 0 failed**. That is the table
  above, and it discharges `tasks.md` 5.2 in advance -- the one task ticked before implementation,
  because it measures behaviour that stops being observable once the fix lands. R3 then found a
  **second** shipped requirement in tension, one `proposal.md` had cleared **by name** and R2 had not
  re-checked: *Save cannot write instructions that were never read*, whose fourth scenario is the
  positive complement and requires an unqualified write once the read succeeds. On
  `read -> clear -> Save -> decline` the two requirements contradict. Fixed with a second `MODIFIED`
  entry using the same words, header and `SHALL` byte-identical.

**Two things about this change are labelled rather than claimed.** Whether a bare `openspec archive`
overwrites the hand-merged sync in its own task 6.2 is **unverified** -- measuring it would have meant
archiving a live change -- so 6.2 names the skill path or `--skip-specs` instead. And whether
blanking whitespace-only stored content deserves no interruption is a **judgement**, not a
measurement; three rounds left it standing, and reversing it is a one-line edit to the predicate and
two scenarios.

**The night's picture changes if you approve either change**, and the paragraph above about "one real
item" was written when only the first existed. There are now **three** open changes, all
unimplemented -- 0/44, 0/23 and 0/24 -- and any one verdict token gives the night real work.

---

## 2026-09-06

Review page: `review/review-2026-09-06.html`. **One change proposed, taken through all three
rounds.** Neither review round changed nothing, for the **sixth consecutive outing**. Round 2 found
that the change's own gate could not reach the button it needed to gate -- `Save` is rendered in
`SettingsSection`'s heading, a sibling of the `{children}` the rewritten branch lives in -- which
made task 1.4 unimplementable as written and exposed the **loading** state as a second live
one-click blanking path, unbounded against a request that hangs. Round 3 found the delta required
the session disclaimer in the very state the change removes it from, so a conforming implementation
had to both show and not show it; that is the 2026-08-28 shape, a wrong *argument* rather than a
wrong outcome, and round 2 had re-derived the whole delta without catching it.

**Written by the day window, which does not fill in its own verdict.** The row below carries no
status token. Write `APPROVED`, `REVISING` or `REJECTED` in front of the change name.

- APPROVED  2026-09-06-an-unread-editor-cannot-overwrite   F271 (A). 24 tasks. UI-only, no migration. A failed instructions GET renders the same empty textarea and enabled Save as a project with no instructions, so one click blanks the row -- and both consumers gate on non-empty, so it removes the section from every turn's context and un-prepends every charter. The gate is `data` present rather than `isError`, checked *before* the error state so a background refetch failure cannot take a loaded editor from you mid-edit. Round 3 found `WorktreesPanel` already ships this exact three-branch shape one page over, which makes it the codebase's convention rather than this change's taste. UI change means the committed bundle must be rebuilt and `make ui` run.

**Two things round 3 folded in that are worth knowing before you decide.** The change now also fixes
a **shipped requirement the component breaches today**: `project-environment-settings`' *Saving
reports its outcome* requires a failed save to state why in the section, and `InstructionsPage` never
reads `saveMutation.isError` -- a rejected PUT re-enables the button and renders nothing. No delta
needed, since the requirement already binds. And the scope was **narrowed against the proposal's own
interest**: of the three states that render an empty editor over unread content, only two can
actually destroy -- the disabled-query row sends its PUT to a path the route 404s or 401s on, so it
is misinformation, not data loss. The gate is unchanged; the claim is smaller.

**Read section 1 of the page before deciding anything.** The branch is 36 commits deep, spans three
days, and is unmerged. The merge gate did not open: dormant under this window's seeded limit
(`limits[0]`, re-seeded every cycle from `arm-cycle.ps1`), and it would have failed condition 3
regardless. **DAY-1** asks whether you want that seeded line relaxed.

**F292 is the reason condition 3 keeps failing, and today added a measurement in both directions.**
CI run `34021133812` (`8902e53`) is the **sixth** occurrence and the first inside a day window --
same signature, `hub-test` on Linux, sole error in the run. But the three completed runs immediately
after it were all green, so condition 3 is *satisfiable*, just not reliable: one failure in six
completed runs today. The N-1 diagnostic printed a **third character-identical negative**, which
falsifies the standing mechanism at n=3 rather than n=2; D-1 additionally killed APScheduler's sync
engine by measurement, leaving alembic's worker-thread engine as the one surviving lead. **DAY-2**
asks whether chasing it is worth a night slot or whether the gate should tolerate a re-run. The
night's own **DEC-1** -- may the window take a second guess at `hub/tests/conftest.py` -- is still
open and is the adjacent question.

**The strongest candidates for the next spec loop are today's two drive findings, and one change
answers both.** D-2 re-drove the night's F126 guard independently on a fresh Hub and found **F293**
(following the refusal's own *"unarchive it first"* mints the duplicate successor the guard exists to
prevent, because `unarchive` is documented as never refused) and **F294** (two simultaneous presses
both return 200, because the guard reads the lifecycle at `:97` and writes it at `:144` with nothing
serialising the window -- exactly the retry/second-tab case F126 named). Each reproduced twice on two
separate fresh databases. Both are answered by F126's deferred shape-(2) column **plus a claim or a
uniqueness constraint**; the column alone races identically. Neither is specced, so the night window
cannot pick either up on its own.

**DAY-3 is the one product question this change deliberately did not answer.** Should a PUT that
would replace non-empty stored instructions with the empty string confirm first? The empty string is
a value the route accepts on purpose, and *"clear my instructions"* is a legitimate ask. Recorded in
`design.md` as an explicitly rejected alternative, with the note that it would not be sufficient
alone -- a client that cannot tell "not loaded" from "empty" is still lying to you with the dialog on
screen. Nothing in the change depends on the answer.

**If you approve nothing, tonight is probably quiet, and that is a real outcome rather than a
failure.** The night playbook's backlog is: unarchived-but-implemented changes (none -- both open
changes are at 0/44 and 0/24), then open findings severity A first (but *"a finding with no proposal
needs the day window first"*, and the four remaining open As are the needs-a-re-drive state), then
`APPROVED` rows (none). An `APPROVED` row above, or a `DIRECTION.md` line answering DAY-2, is a
single line either way. `NOTHING TONIGHT` is also valid and cheaper than silence.

---

## 2026-09-05

Review page: `review/review-2026-09-05.html`. **One change proposed, taken through all three
rounds.** Neither review round changed nothing, and round 3 did something new: it overturned round
2's own finding. Round 2 showed that a design decision could not deliver the case it was chosen for
and filed F290 (B) underneath it; round 3 showed that round 2's replacement mechanism **already
ships app-wide with a test on it**, retracted F290, and filed F291 (C) in the place it was pointing
at.

**Written by the day window, which does not fill in its own verdict.** The row below carries no
status token. Write `APPROVED`, `REVISING` or `REJECTED` in front of the change name.

-           2026-09-05-the-conversation-carries-its-own-run-facts   F274 (A), the last open severity A with no proposal. 44 tasks, 8 phases. Two Pydantic responses gain a `runs` map, two chat routes gain a primary-key lookup over the run ids their own returned entries name, one React prop changes source, one SSE predicate gains four events — plus a `MODIFIED` requirement that repoints a cross-reference which sent three earlier rounds to a rule that could not forbid this. No migration. UI change means the committed bundle must be rebuilt and `make ui` run.

**Before you decide, read section 1 of the page.** The branch is 17 commits deep, spans two days,
and is unmerged. The merge gate was evaluated at 09:02 and did not open — dormant under this
window's seeded limit, and it would have failed condition 3 regardless.

**The thing that changed after that check, and it is new since yesterday.** `0b8aaf5`'s CI run has
since concluded `failure`, and it is the **third** failure on this branch with exactly one cause:
`sqlalchemy.exc.OperationalError: database is locked`, always at the *setup* of some test, always
the `hub-test` job on Linux with every other job green, always the only error in the run. Three of
sixteen runs; green runs bracket each one. Filed today as **F292 (B)**.

This is the residue of the F285 fix you made on 2026-09-04 — which was right, and is not in
question. Moving the suite off `:memory:` removed a deterministic corruption and bought file
locking in its place. **It was already mitigated once and the mitigation did not hold:** `be6a70d`
adds `await _REAL_ENGINE.dispose()` before the schema reset, that dispose is present in the tree at
all three failures (measured with `git show <sha>:hub/tests/conftest.py`), and the first failure
*is* the test its comment names. The mechanism is **not established** — the comment blames a live
`JobScheduler`, but both failing files await `_fire_job_internal` directly and `dispose()` cannot
reclaim a connection a running task has checked out.

**That is a decision, not a repair, and it is why the day window did not touch it.** If the night
window's green-tree check lands on a red chunk, its playbook makes the inherited breakage tonight's
first item — so it would make the *second* guess at this file from the same evidence, unattended. A
`DIRECTION.md` line saying whether it may is the cheapest way to steer that.

**Narrowed after the page was written, by D-6's control run — read this with the paragraph above.**
The evidence is no longer "the same evidence". Rebuilding the `app` fixture's exact conditions
(file-backed `sqlite+aiosqlite`, WAL, `busy_timeout=30000`, `expire_on_commit=False`, a session
leaked across the boundary, then `dispose()`, then `drop_all`) and varying only what the leaked
session did last gives: a session that **committed** — with or without a following `refresh` — lets
the DDL through in **0.0s**, and a session holding an **uncommitted write** fails it with
`database is locked` after the busy timeout, **byte for byte the error CI reports, at the same
statement**. So F292's leaker wrote and did not commit, a leaked reader is ruled out, and
`be6a70d`'s `dispose()` provably could not have helped — it closes *idle* pooled connections and
cannot reclaim one a running task holds mid-transaction. It is still **not reproduced from the suite
itself**, so this narrows the guess rather than removing the need for your line.

**F287 is fixed — `890cf40` — and yesterday's section forbade exactly that, so here is why.** The
2026-09-04 note said deleting `output_recording.py`'s `db.refresh` "would very likely turn CI green
on its own … That is masking, not fixing." Its premise was the shared connection, which is gone. The
day window did not treat the expiry as a licence: it took F292 as a live reason to re-ask the
question, and answered it with the control above — the refresh holds a SQLAlchemy transaction and a
checked-out connection, and **no SQLite lock at all**, because pysqlite issues no `BEGIN` for a
`SELECT`. Removing it cannot make F292 stop reproducing. Taken under the playbook's no-spec repair
carve-out, with all three conditions verified, both tests mutation-checked, and a real
`claude-haiku-4-5` turn driven against a Hub restarted from the edited source. **If you disagree
with the override, this is the line to say so on** — the change is one commit and reverts cleanly.

**A second decision the page argues both sides of.** Today's drive filed **F288 (B)**: a Hub restart
ends every orphaned run but re-evaluates only those runs' own agents, stranding an agent parked on
the crashed run's task checkout — driven, a 6m15s strand with the checkout free. That **breaches the
requirement last night's change synced** (`agent-conversation-workspace/spec.md:2217`, quantified
over every agent holding queued input in the project). The day specced F274 instead because severity
decides and F274 is the only open A, while F288 needs three consecutive interruptions to become
observable and self-heals under one. If you would rather tonight closed a nine-hour-old spec breach
than the oldest A, say so and F288 takes the slot.

If you approve nothing, the night falls to the backlog and stalls quickly — there is nothing to
archive (`openspec/changes/` holds only this unimplemented change), the one remaining open
severity-A row (F271) has no proposal, which the playbook makes a note to tomorrow rather than
tonight's work, and an unapproved proposal is not in the default either. It would land on B rows:
F288 and F292, filed today. An `ORDER:` line and the stop-the-window token are both available and
both override the default; both are spelled out in the format block at the top of this file.

---


## 2026-09-04

Review page: `review/review-2026-09-04.html`, published as an Artifact and walked through with the
operator in the DECIDE session at 19:00–19:40. **One change proposed, taken through all three
rounds; approved.** Neither review round changed nothing: round 2 found the code in breach of a
requirement that already shipped, and round 3 overturned design decision D3 by measurement and
found that *both* earlier rounds had specified a regression test that would have passed without the
fix.

- APPROVED  a-terminal-run-releases-the-queue-behind-it   F286 (B). 24 tasks, 5 phases. Python only in `hub/hub/api/v1/agent_trigger.py` — no migration, no API shape change, no UI, no bundle. **It is now first**: F285 was fixed and pushed by the DECIDE session (`d9ad1e0`), so the test isolation its regression test runs against is already settled and green.

ORDER: a-terminal-run-releases-the-queue-behind-it

**F285 is DONE — do not start it.** Fixed by the DECIDE session in `d9ad1e0` and pushed, with
the file-backed fix named below. The full Hub suite is 3961 passed / 0 failed / 0 errors on this
machine. Its `ORDER:` entry is removed above so tonight starts on the approved change; the
section below is kept because it records why that fix and not the other two.

### F285 — DONE (`d9ad1e0`). Kept as the record of which fix and why.

**A file-backed temporary database per test** — implemented, not merely chosen. Not an unshared
pool, and not per-test engine disposal. Decided by measurement in the DECIDE session rather than
by preference, because the other two options on the review page do not work:

| Option | Measured result |
|---|---|
| Unshared pool (`NullPool` on `:memory:`) | Every session gets its own **empty** database — `OperationalError: no such table` |
| Shared-cache memory URI + `NullPool` | The last connection closing destroys the database — same error |
| Per-test engine disposal | Does not address the mechanism: the race is *within* one test (the background run task against an HTTP request), not between tests |
| **File-backed temp DB per test** | **Works.** `AsyncAdaptedQueuePool` — the pool production already uses |

The day window's reproduction was re-run at HEAD in the DECIDE session and holds:
`sqlite+aiosqlite:///:memory:` → `InvalidRequestError: Could not refresh instance`, file-backed →
clean. Cost is disk I/O across a 15–25 minute suite and is **unmeasured** — time the suite before
and after, and record the figure rather than asserting one.

**F287 is NOT ordered and must not be bundled into this.** Deleting
`output_recording.py:94`'s redundant `db.refresh` would very likely turn CI green on its own, by
removing the one operation that makes the shared-connection rollback loud. That is masking, not
fixing. It stays an open `C` for a later window, on its own merits as one extra `SELECT` per
streamed output line.

### Why the order is F285 first

Getting `hub-test` green is the point of tonight. The branch is 34 commits ahead of `master`, 0
behind — a clean fast-forward — and the operator has decided **not to merge until CI is genuinely
green**, rather than merge over a red run known to be a harness artefact. So F285 is what unblocks
the merge, and it is also what the approved change's regression test has to run on.

The night window does not merge, and that limit is unchanged. The merge stays the operator's, awake.

### Two corrections to the review page

1. **The page's own steering advice was wrong about which file.** It said *"a `DIRECTION.md` line
   naming the fix is the cheapest way to steer it"*. `README.md` in this directory says
   `DIRECTION.md` is read by the **FILL window and nothing else**; the FIX window reads
   `APPROVALS.md` and nothing else. A steer for tonight placed in `DIRECTION.md` would never have
   been read. That is why the F285 instruction is here.
2. **The page's `<title>` element still read `2026-09-03`** — the stylesheet was reused verbatim
   from yesterday and carried the title tag with it. Corrected in the published Artifact; the
   window that writes tomorrow's page should set the title from the same date as the `<h1>`.

---

## 2026-09-03

Review page: `review/review-2026-09-03.html`. **One change proposed, taken through all three rounds.**
Rounds 2 and 3 each broke the round before them, and round 3's defect was measured rather than argued.

**Written by the DECIDE session of 2026-09-03, not by the day window.** The day window proposed
`a-blocked` and left both lines as blanks to fill, precisely so it could not appear to approve its own
work. The operator filled them, and approved both:

- APPROVED  a-blocked-agent-workspace-holds-its-input   F188 (A). First: Python only, no migration, no API shape change, no UI, no bundle.
- APPROVED  a-write-outside-the-workspace-is-recorded   F115. Second: touches `AgentTimeline.tsx` and the committed bundle, so it must not run beside `a-blocked`.
ORDER: a-blocked-agent-workspace-holds-its-input, a-write-outside-the-workspace-is-recorded

> **Status note appended by the night window, 2026-09-04 (not an operator decision).** The first row
> is **built, driven and archived** — `openspec/changes/archive/2026-09-04-a-blocked-agent-workspace-holds-its-input`,
> all 6 phases, F188 retired in the ledger. The gate two paragraphs down is therefore open:
> `a-write` may now start. Its task 4.2 migration number was re-checked on 2026-09-03 and `0101` is
> correct as written.

> **Second status note, night window 2026-09-04 iteration 24 (not an operator decision).** The second
> row is now **built, driven and archived** too —
> `openspec/changes/archive/2026-09-04-a-write-outside-the-workspace-is-recorded`, all 9 phases,
> driven live at N-23 (29/29, two real Haiku turns, on a Hub serving this checkout's own migration
> `0101`), five deltas synced into `openspec/specs/` and verified header by header, and **F115
> retired** in both of its ledger sections. Both approved rows for 2026-09-03 are closed, in the
> `ORDER` given and without the two ever overlapping on `agent_trigger.py` or the bundle.
>
> Three things the change deliberately did **not** fix are carried forward as their own ledger rows
> rather than closed with it: **F281 (B)** (a shell command's writes are never recorded, in any
> posture), **F282 (C)** (a junction is classified and refused correctly but both the refusal and
> the record print the declared path), and **F284 (C)** (the `manual` permission card gives the
> operator no marker that the path leaves the run's workspace — lifted out of F115's reproduction so
> retiring that section would not bury it). None has a proposal, so by the night window's own rule
> they are the day window's to take up, and F284 should be decided together with **F283 (B)**.

`ORDER` is not decoration here. The two changes collide on `agent_trigger.py` and `worktrees.py`, and
`a-write` moves `hub/hub/static/ui` on top of that — the one combination this repo cannot build
concurrently. Sequential, severity-A first, is what makes approving both safe. 86 tasks will not fit in
one window; **stopping part-way through `a-blocked` is the expected outcome and is fine.** What is not
fine is starting `a-write` before `a-blocked` is finished and archived.

`a-blocked-agent-workspace-holds-its-input` — **F188 (A)**. Two refusals stop an agent from running.
One holds the operator's message until they perform the repair; the other destroys it on the third
schedule. They are eleven lines apart in the same function and the difference is a keyword argument —
and the Continue button the conversation view offers for exactly this situation *is itself a schedule*,
so the operator's attempts to find out why nothing is happening are what consume the allowance. **F114
reproduced verbatim at a site the F114 fix did not reach.**

The obvious repair — flag the site — **breaches a requirement that shipped 2026-08-28**, because one
`except` covers two workspaces: the task checkout (where other input really could have run, and
counting is right) and the agent's own worktree (which blocks the agent's whole ordinary population).
So the site states *which* workspace it could not prepare and the scheduler answers the starvation
question, being the only party holding the queue. Read against the archived change's own task 1.2a,
this **completes** a decision deferred six days ago rather than reversing one.

- **Round 2** found R1's design D3 rested on `takes_task_workspace` reducing to "the entry names a
  task". It does not — **naming a task is not taking a task's checkout**. Grandfathered tasks, refused
  ids, and deleted or decided tasks all run in the blocked directory while naming a task, so R1's
  helper would have counted the attempt and destroyed the head having released nothing: **F188
  surviving its own fix on every project old enough to have grandfathered tasks.** Measured under
  `py -3.11` at HEAD. Four smaller corrections; tasks 24 → 28.
- **Round 3** measured R2's task 3.0 and it is false: extracting the predicate the obvious way turns
  `test_task_workspace_scheme.py` red, because its source scan looks for the substring
  `.workspace_scheme =`, which is a prefix of `.workspace_scheme ==`. Today's resolver survives only
  because it happens to be written `!=`. Four more corrections — a decided task can still inherit its
  thread's live binding (so the code was right and only the argument was wrong), the `selected`
  exclusion needed a fact rather than an enumeration, a review with no commit is a false yes (new D3b),
  and `D3a` collided with a shipped `D3a` cited by both files this change edits (renamed D8). Plus the
  thing no round had looked at: `turn_scheduler.py:225-233`, a shipped comment **inside the branch being
  edited**, asserts the exact claim this change falsifies, and task 5.2's grep could never reach it.
  Tasks 28 → 32.

Cost if approved: **32 tasks** across 6 phases — phase 1 is a reproduction gate, phase 6 is three drive
legs. Four files, all Python: `agent_trigger.py`, `turn_scheduler.py`, `worktrees.py`,
`task_workspace.py`. **No migration, no API shape change, no UI.** `openspec validate --strict` passes.
Nothing under `hub/hub/`, `hub/ui/` or `src/` is committed from today.

`a-write-outside-the-workspace-is-recorded` — carried forward unchanged from 2026-08-30, and
**approved today after three days undecided**. It is R3-complete at 54 tasks. It collides with
`a-blocked` on `agent_trigger.py` and `worktrees.py`, and touches `AgentTimeline.tsx` on top, so
approving both means ordering them — which is what the `ORDER:` line above does. Its task 4.2 migration
number **is already correct** — fixed to `0101` on 2026-09-02 and still right, since head is still
`0100_loop_work_needs_evidence.py`.

**A correction to the 2026-09-02 carry-forward, measured this morning.**
`runner-model-is-chosen-from-the-catalog` is **done, not pending**. It was built and archived on
2026-09-02 by the night window (`7df21ea`, 29 of 29 tasks closed), and nothing by that name remains in
`openspec/changes/`. Both items approved on 2026-09-01 have now shipped. Do not re-approve it.

**The day window warned that approving nothing would leave the FIX window with nothing it is allowed
to build, and that is why both rows are approved.** Source 1 (implemented changes needing only
archiving) is **empty**: both open changes sit at zero completed tasks. Source 2 lands on **F271**,
then **F188**, then **F274**, but the playbook's own rule is that a finding with no proposal is a note
to tomorrow rather than work — F271 and F274 have no proposal. `ORDER:` above therefore carries the
whole night: source 3, in the stated order, and nothing else. **`NOTHING TONIGHT` was considered and
rejected** — the branch growing unmerged for a fourth day is a real cost, but it is the operator's to
weigh against a severity-A defect that destroys operator messages, and tonight it lost.

Today's drive filed **F274 (A)** — a turn's terminal label and its "Worked for Ns" line vanish once the
agent-scoped 50-event timeline window moves past that run, which four ordinary triggers in the agent's
*other* conversations achieve. That is **F190's own symptom, live, against the change that closed
F190**, found by driving the served bundle rather than the Python transcription phases 6 and 7 used.
The route is **not in breach** — `agent-stream-events/spec.md:363-366` blesses it — the gap is that no
requirement says the events must cover the turns the client renders. It has no proposal and wants no
row here; it is tomorrow's spec loop. Also **F275 (C)**: an abandoned operator message renders after the
failures it caused.

Four things on the review page are **not** work and want no row: whether the three-day, 167-commit
branch merges; F271's blank-a-non-empty-PUT question; `f272-harness-guard`, still the only open decision
that blocks work; and `findings-ledger-retirement`, new — nothing in the cycle retires a ledger row when
the change that fixes it is archived, which is how the open severity-A count read "one" for a week while
F188 sat in it.

---

## 2026-09-02

Review page: `review/review-2026-09-02.html`. **No new change was proposed today.** The spec-loop
slot went to repairing an already-approved one, because last night's phase-0 gate falsified the
premise of its design D6 (task 0.3) and `DIRECTION.md`'s governing sentence is that a broken
approved design outranks a new proposal. Two rounds ran; the row below is what came out.

The day window wrote this section with **blanks** rather than tokens, because it did the work and
must not appear to have approved it. **The operator filled them in on 2026-09-02 at 20:40, in a
DECIDE session.** The row below is a real row. Leaving a change out entirely is undecided, not
rejection — but note that only the newest section is read, so an omitted row here means the FIX
window sees no approval for it tonight, whatever last night's section says.

- APPROVED  a-turn-says-how-it-ended   operator, 2026-09-02 20:40, in session -- the phase 0 condition is satisfied; rounds RA and RB repaired D6; phases 1-7 unblocked

ORDER: a-turn-says-how-it-ended

`a-write-outside-the-workspace-is-recorded` has **no row**, which is undecided rather than
rejected. It is deliberate: it collides with `a-turn` on three files, one of them the committed
UI bundle, so approving both for one night means ordering them and eating a bundle conflict every
iteration. It reappears on tomorrow's review page unchanged.

The `ORDER:` line is load-bearing, not decoration. Without it the default queue applies, and its
source 2 -- open findings, A before B before C -- reaches **F271** before it ever reaches this
approved row. F271's repair is half a plain fix and half a product decision the window may not
make, so the night would spend itself on the half it is not allowed to finish. `ORDER:` sends it
straight to the 41 open tasks of the change that has been through eight rounds of review.

`a-turn-says-how-it-ended` -- F190 (A). You approved this on 2026-09-01 **conditionally**: observed
first. Phase 0 ran last night against a live Hub and the gate did its job -- **task 0.3 falsified
round 3b's premise**, and task 0.7 returned the change to a round rather than letting it proceed.
Phases 1-7 were blocked in the tasks file itself. Two rounds ran today:

- **Round RA** re-derived design D6 against nine files and found that signal 1 *does* fire, for the
  run that finished, written by a producer round 3b never looked for (`runner_parsing.py:346-356`,
  persisted at `agent_trigger.py:1925-1938`). D6's purpose survives on a narrower argument -- it
  extends signal 1 to runs that did **not** complete, plus a durable exit code -- and loses two
  attributions. **Scope not narrowed; phases 1-7 unblocked.** Three tasks added, five rewritten.
- **Round RB** re-derived RA's argument independently, confirmed every fact by a stronger route, and
  corrected its **scope**: `status_event("completed")` occurs exactly once in the whole Hub, inside
  the Claude-only parser, so signal 1 has never fired for a Codex run of either transport. RA's
  headline retraction is right for Claude and wrong for Codex. Four tasks corrected, one added, and
  **one task withdrawn** -- 4.5a offered two fixes as equivalents and RB ran both; one fails in
  exactly F269's case. RB changed **nothing** about designs D1-D5, D7, D6's purpose/writer/exit-code
  argument, or F190's headline, and that is stated on the review page rather than left implicit.

Cost if approved: **41 open tasks** across phases 1-7, including phase 7's separate verifying round.
Both rounds implemented and ran code to test their own claims and reverted all of it; nothing under
`hub/hub/`, `hub/ui/` or `src/` is committed from today. `openspec validate --strict`: valid.

`a-write-outside-the-workspace-is-recorded` -- carried forward unchanged and still undecided rather
than rejected. It collides with `a-turn` on three files, so approving both for one night means
ordering them. Its task 4.2 migration number was corrected to `0101` and must be re-derived if
another migration lands first.

**If you approve nothing**, the FIX window falls to the default queue: source 1 (implemented changes
needing only archiving) is **empty**, source 2 lands on **F271 (A)** -- today's drive finding, whose
repair is half a plain fix and half a product decision the window may not make -- and source 3 is
`a-turn`, approved last night and unblocked today. `ORDER:` and `NOTHING TONIGHT` are both available.

Three things on the review page are **not** work and want no row here: whether the two-day branch
should merge, F271's blank-a-non-empty-PUT question, and whether the FIX window may write a proposal
when its queue empties five hours early -- which is what happened last night.

---

## 2026-09-01

Review page: `review/review-2026-09-01.html`. One change proposed, taken through all three rounds.
Write its row below in the contract's form — the status token goes between the `-` and the change
name. Leaving the row out entirely is undecided, not rejection. **No real token is written here:**
the day window proposed this change and must not appear to have approved its own work, so the line
below is a blank to fill, not a row.

- APPROVED  runner-model-is-chosen-from-the-catalog   operator, 2026-09-01 17:40, in session
- APPROVED  a-turn-says-how-it-ended   operator, 2026-09-01 20:15, in session -- CONDITIONAL, see below

`a-turn-says-how-it-ended` -- F190 (A). Approved with a condition the operator stated when
approving: **observed first, and tested after implementation by a new round.** The contract here has
only three tokens and no way to say "approved with a precondition", so the condition is encoded as
blocking structure inside the change instead:

- **Phase 0 is a gate.** It says, in the tasks file itself: if phase 0 has not been completed and
  recorded, do phase 0 and stop. A window reaching this change with no observation record performs
  the six observations, writes them up, and ends its turn. Nothing is implemented.
- **Phase 7 is a separate round.** Implementation does not close the change and task 6.7 no longer
  retires F190; a sitting that did not write the code re-runs phase 0's observations against the
  built product and closes it.
- **Phase 0 can falsify the design.** Task 0.3 in particular: rounds 2 and 3 disagree about whether
  a single-run conversation is affected, and if the indicator releases cleanly there, the round 3b
  finding is wrong and the change returns to a round rather than proceeding.

Why the condition is right, in one line: four rounds of review each found the defect nearest the
code that sitting happened to read, three of them read the same gate expression, and none of them
checked where its inputs come from. Every claim in the change is derivation; none is observation.

Note also that `DECISIONS.md` **D-7 is OPEN** and groups response-shape changes as ones "no window
took unattended". This change is a BREAKING envelope. The phase 0 gate is what makes an unattended
window safe to let near it; D-7 itself is still undecided.

`runner-model-is-chosen-from-the-catalog` — F173 (A). The runner screen free-types the model against
a shipped requirement that says it must offer the catalog's, and swallows the backend's refusal
entirely. 29 tasks across the API, the picker, the error surface, tests and a drive; retires F173
(A), F219 (C) and F220 (C). Round 2 and round 3 each changed it — the argument in section 4 of the
review page.

If you approve nothing, the FIX window falls to the default queue and lands on open findings, A
first — which is F173 again, by the finding route and without this design. `ORDER:` and
`NOTHING TONIGHT` are both available.

Two decisions on the page are **not** work and want no row here: ratifying the `fastmcp<4` ceiling,
and leaving F188/F190 unproposed as direct repairs.

---

ORDER: a-turn-says-how-it-ended, runner-model-is-chosen-from-the-catalog

**Why this order.** `a-turn`'s phase 0 is a gate: it observes and stops, touching no product code,
so it cannot collide with anything and cannot run long. Putting it first spends perhaps an hour to
learn whether the design is *right* — task 0.3 can falsify it outright, since rounds 2 and 3
disagree about whether a single-run conversation is affected. Learning that tonight is worth more
than learning it after the change is built. `runner-model` then gets the rest of the window; it is
approved unconditionally, disjoint from everything else in flight, and is the item that actually
ships.

**Both touch `hub/ui/src`, and that is safe only because of the order.** `hub/hub/static/ui` is a
committed build artefact and two UI changes in flight conflict on it every time. Phase 0 writes no
UI, so there is exactly one UI change tonight.

`a-write-outside-the-workspace-is-recorded` has **no row** and is therefore undecided, not rejected
— it is R3-complete but never approved, and it collides with `a-turn` on three files. Do not build
it tonight. Before anyone does, fix its task 4.2: it names migration `0100`, and
`hub/hub/migrations/versions/0100_loop_work_needs_evidence.py` already exists, so it must be `0101`.

If the window finishes both, the next most valuable thing is **F188** — the last severity-A finding
with no change and no design (see `DECISIONS.md`, *Not decisions*). Spec it; do not repair it
directly.
