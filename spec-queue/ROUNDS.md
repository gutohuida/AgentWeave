# Rounds — a plan for every open B, C and D finding

**Written 2026-09-22 by an interactive session, at the operator's request:** *"Do a scan on all the B,
C and D task and come up with a plan to solve them by round. Group the ones that can be solved
together and create the plan with the round on how to tackle them and priority."*

**Inventory:** 191 open findings, every one placed below (checked by script; a few appear twice as deliberate cross-references) (85 B, 86 C, 20 D) at `1c42253`. Six read-only scanners (Sonnet)
read every entry and spot-checked the cited code. Their verdicts are the scanners' word. Each fix
re-verifies its finding before touching code, as today's sweep did.

This file is a **plan, not an authority** (same standing as `ROADMAP.md`). `APPROVALS.md` and
`DECISIONS.md` stay the only authority.

## Read this first: scope and timing

1. **Scope.** `DECISIONS.md` *"The scope of the drain"* (2026-09-10) drains A and B and did not
   propose against C and D. **Footnoted 2026-09-22 by the operator:** *"the draining of the others
   is manual execution guided by me."* So C and D are in this plan, but they are worked **only in
   interactive sessions the operator directs**. The unattended FILL window still proposes from A and
   B alone, and FIX builds only what `APPROVALS.md` names. A C/D spec track starts when the operator
   says so, not when a window finds room.
2. **This week.** The Merge Week scorecard's O5 opens no new `openspec/changes/` directory before
   2026-09-28. So the no-spec rounds run this week, and the spec tracks start on 2026-09-28.
   **Relaxed by the operator on 2026-09-23:** the day window's own specs may open this week (it opened
   `an-at-mention-an-agent-wrote-reads-no-file` and `pressing-run-names-the-reason-that-held` that
   day). These rounds' spec tracks still start on 2026-09-28.
3. **Answered 2026-09-23 (carried since handoff 0144).** `archive_job` does **not** refuse a running
   loop: the job's archive keeps ending the loop itself (F224). A refusal was chosen, then withdrawn
   once the operator was shown that no screen can stop a loop (F225/D6), which would strand the app
   as `agent-loops` records for 2026-08-21. Revisit only if a stop control ships. Recorded in
   `archive_job`'s docstring.
4. **Answered 2026-09-23 (D10, F193 only).** An archived agent's open conversation is *shown,
   marked, with Unarchive*: both rail views list it, and opening it offers to unarchive the agent.
   UI-only; archiving an agent still leaves its conversations open. Built in UI-1.
5. **Answered 2026-09-23 evening (carried since handoff 0144).** The merge gate gets **no re-run
   allowance** for F292/F314: both are closed (2026-09-22, by measurement), so condition 3 stays
   strict. A new intermittent is filed as a new finding, not absorbed by a re-run.
6. **Answered 2026-09-23 evening.** D13 goes **through `daily-review`**: the next review page puts
   each item with a recommended answer. It is no longer carried as a handoff question.

## How a round runs

- **No-spec rounds (0–5)** follow the F117/F196/F222/F227 pattern of 2026-09-22:
  1. Re-verify the finding against the code, and check `git log -S` for the cited snippet.
  2. Write a regression test that fails before the fix.
  3. Fix, then run the affected files **with `claude` stripped from PATH**, as CI runs (DEAD-ENDS).
  4. Run the full CLAUDE.md lint block *after* writing.
  5. Commit per finding, add a foot to the finding, regenerate the backlog.
- **UI rounds ship one bundle per round** (`make ui`; commit `hub/ui/src` and `hub/hub/static/ui`
  together). A committed bundle reaches the operator's live `:8000` on their next reload. So a UI
  round ends with a browser check, not only `npm run lint`.
- **Spec tracks** get R1 / R2 / R3 / IMPL (the round discipline in CLAUDE.md), one change at a time.
  Each change stays small enough that stopping anywhere leaves complete changes.
- **Decision rounds** are `daily-review` material: each question gets a recommended answer, and
  the verdict goes to `DECISIONS.md`. Nothing in them is built until it is answered.

## Priority, in one line

**Round 0 → 1 → 2 → 3 → 4 → 5 this week**, with **D** put to the operator alongside, then the
**spec tracks from 2026-09-28 in the order listed**. Round 1 comes early because every later round
depends on a CI that tells the truth. Round 5 was waiting on F352, which landed and was driven on
the 2026-09-23 night window, so it is unblocked. Within a round, work B before C before D.

Counts place each finding in the **first round that names it without striking it**. A hand-off
is written by striking the id where the finding left (`| ~~F167~~ |` in a table, `~~F62~~ (D7)` in
prose): the page shows it under that round as *moved →* and counts it where it went. A finding
struck everywhere has left the plan (F373 and F400, to a proposed change) and is counted in no
total. Other later mentions are cross-references. These are the same numbers `ROUNDS.html` shows
(recounted 2026-09-23). **Track progress there:** `py -3.11 scripts/rounds_page.py` regenerates it
from this file and `FINDINGS.md`.

| Round | What | Findings | Size | Needs |
|---|---|---|---|---|
| 0 | Ledger hygiene and harness one-liners | 8 (+3 moved: F395 → 3, F167 → 5, F382 → D) | ~1 h | nothing |
| 1 | Make CI tell the truth | 4 | ~1 day | nothing |
| 2 | Decided, unbuilt | 6 (+1 moved: F349 → D) | ~1 day | nothing (verdicts exist) |
| 3 | Hub routes that act wrongly (B-led) | 27 (+2 moved: F275, F156 → UI-1) | ~2–3 days | nothing |
| 4 | Hub routes that answer wrongly (C/D sweep) | 27 (+3 moved: F62, F149, F322 → D) | ~2 days | nothing |
| UI-1 | One bundle: controls that lie or do nothing | 22 (incl. F275, F156 from Round 3) | ~2 days | ui-bundle, browser check, `:8000` restarted past `c18a87b` |
| 5 | Scheduler residuals | 2 (incl. F167 from Round 0; +3 moved: F327 → S13, F373 and F400 out of the plan) | ~1 day | nothing (F352 landed 2026-09-23) |
| D | Operator decisions (13 questions) | 59 | ~2 DECIDE sessions | operator |
| S1–S13 | Spec tracks, from 2026-09-28 | 34 + those D releases | ~1 change / 2–3 days | C/D tracks: the operator starts them |

---

## Round 0 — ledger hygiene and harness one-liners (do first, ~1 h)

Cheap, and it makes the open count honest before any real work starts.

**Status:** done 2026-09-22 (commits `9e3f9cb`..`77d39f9`, Opus-reviewed). 8 of 11 closed: F399 (retired into F234), F381, F311, F296, F138, F346, F170, F160. Three handed on, all still open: **F395** closes with F258 in Round 3; **F167** has its heading and is fixed in Round 5; **F382** was narrowed to `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped` but not diagnosed, and is back to watch-only in D13. The review's residuals are recorded on the entries (F381: Overview card and Questions panel, with F146; F170: projects in a repository subdirectory). **Next: Round 1.**

| Finding | Action |
|---|---|
| ~~F395~~ (B) | **Moved to Round 3** (closed there with F258). Same root cause as F258 (confirmed: `messages.py` `hop_depth = hop_budget + 1` without a run). Fix it under F258 in Round 3, then close both. Keep F395's `origin_type` detail. |
| F399 (D) | Literal duplicate of F234 (same line, same defect). Mark it a duplicate of F234 and fix it in Round 4. |
| F381 (C) | Probably fixed by `24f3655` (`pendingQuestions.ts` filter). Verify with a test and close. |
| F311 (C) | Bookkeeping only: F307's table omits `TaskDetailDrawer`. Correct the table and close. |
| F296 (C) | Harness: `t_d4_instructions_failed_load.py` uses `role="button"` where `"combobox"` is right. One word. |
| F138 (B) | Harness residual: `scripts/drive/aw.py` `HUB` defaults to `:8010`. Make it required, like `AW_KEY`. |
| F346 (C) | Harness: `n10_route_reachability.py` `segment_match` lets a literal satisfy `{param}`, so the count reads 35 where the truth is 36. |
| F170 (C) | `repo_hygiene.py` `EXCLUDE_PATTERNS` lacks `.agentweave/project.json`. |
| ~~F167~~ (B) | **Moved to Round 5** (fixed there). Has **no `## F167 ` heading**, so every tool that greps the ledger misses it. Give it one. Its fix is in Round 5. |
| ~~F382~~ (C) | **Moved to D** (D13, watch-only). A one-off overnight stall that never reproduced (a rerun gave 4440 passed). Propose **watch-only**, closed unless it recurs. The operator confirms in D. |
| F160 (C) | `test_tool_surface_matches_server.py` doesn't assert that optional arguments are described. Add the assertion. |

## Round 1 — make CI tell the truth (~1 day, highest leverage)

Every later round's "green" means only what these let it mean.

**Status:** done 2026-09-22 (commits `329c911`..HEAD, Opus-reviewed and the review applied). All 5
closed, none handed on. **F383** was not a defect of its own: symptom B is F292's failure under a
second number, and `b630252` fixed it (0 lock errors in the 59 hub-test runs that completed after
it, against 28 before). **F408** was found while closing it — a Windows CI flake in
`tests/test_locking.py` — and is fixed. **F396** re-keyed the MISREPORT table on (file, hook,
occurrence); the count is 55, and decay now fails a test. **F392** became one rule with a check.
**F308** was put to the operator, who chose the weekly unpinned CI job; it arms when `master` takes
it. **Next: Round 2.**

| Finding | Sev | Fix |
|---|---|---|
| F383 | C | **Symptom B**: a leaked write transaction in `hub/tests/conftest.py` teardown fails the next test's `BEGIN IMMEDIATE`. Symptom A (the lock) was fixed 09-18. This is the costliest open flake. Consider raising it to B. |
| F408 | C | Added 2026-09-22. `test_locking.py`'s thread-race tests joined for 3 s, so a slow Windows runner read as a wrong lock result (`77d39f9`). Joins now bounded at 30 s, with an `is_alive` check before any result is read. |
| F396 | B | `test_surface_ceilings.py` keys MISREPORT sites by file:line, so line drift reads as improvement. Re-key on (file, hook), the pattern `UNHANDLED_SITE_CEILING` already uses. |
| F392 | B | Process: a "full suite must not move" tick was taken without its evidence being written. Rule: the tick carries its inline count, and the regression set includes tests parametrised over files a sibling change adds. |
| F308 | B | Pinning CI's resolution silenced the drift alarm. **Decision**, see D13; nothing is built here until then. |

## Round 2 — decided, unbuilt (~1 day)

**Status:** done 2026-09-22 (commits `cd2157a`..HEAD, Opus-reviewed). Six of seven built; **F349**
was never this round's to build — its remainder is a design question in D13, and it is listed here
only so the round is complete. **F347** refuses an unborn `HEAD` with the repair rather than git's
plumbing error, on both the agent and the task checkout. **F202** made `GET /tasks` answer
`{tasks, total, has_more}`, gave `list_tasks` paging, and stopped the Overview counting the page
instead of the ledger. **F203** put a task's transition history on both planes, in an MCP tool, and
on the operator's own screen. **F209** keeps an accept's reason as a reject already did. **F212**
projects `unserved` as objects carrying `document_id`. **F201** moved R5's block rule behind the
transition machine, so an illegal block is refused as illegal. **Next: Round 3.**

The operator has already answered these, so none needs a question or a spec.

| Finding | Sev | Verdict | Fix |
|---|---|---|---|
| F347 | B | 2026-09-13, option (a) | An unborn HEAD refuses with a sentence naming "make a first commit" instead of git's plumbing error (`worktrees.py` `ensure_worktree`). |
| F202 | B | DECISIONS, additive | `GET /tasks` returns `total` / `has_more`, `list_tasks` (MCP) gets `limit` / `offset`, and the Overview stops truncating silently. |
| F203 | C | DECISIONS, additive | A route (plus an MCP read) for a task's transition history (`history_for`). |
| F212 | C | DECISIONS, additive | Coverage `unserved` carries `document_id` alongside the identifier. |
| F209 | C | 2026-09-08 R-3 | `accept_proposal` stores `reason`, as `reject` does. |
| F201 | C | 2026-09-08 | Illegal `blocked` names the illegal transition (409) before the Pydantic validator asks for a reason. Nine validators share the ordering hazard. Fix the one measured, and list the others. |
| ~~F349~~ | B | half-fixed 09-22 | The remainder is a design question (a post-commit failure leaves the entry queued with nothing to drain it). **Moved to D13**, and listed here only so the round is complete. |

## Round 3 — Hub routes that act wrongly (B-led, ~2–3 days)

**Status:** done 2026-09-23 (commits `779820e`..`3cd9db1`, branch `round/3d` for 3d–3f, Opus-reviewed
and the review applied). 27 of 28 built. **F275** needs a UI bundle, which cannot ship until `:8000`
restarts past `c18a87b`, so it moved to **UI-1** with **F156**'s UI half. The review found no blocker
and six residuals, all applied (`3cd9db1`); its two separate defects are filed and queued as **F414** and
**F415** in Round 4 (4e). Everything was checked against the old code: each new test fails there for the
reason its finding states. **F338** had never been measured; it reached. **F360** was reproduced live
on Haiku (old rule 0/32, new rule 32/32, `scripts/drive/t_f360_probe_task_rule.py`). **F297**'s graceful
stop was measured with a probe launched exactly as `cmd_hub_start` launches the Hub. Full Hub suite,
run alone at `3cd9db1`: **4675 passed, 86 skipped, 0 failed (25:01)**. CLI suite: **549 passed, 4
skipped**. Merged into `autonomous/2026-09-21-daily` at `4724e64` (the daily branch had changed no
product code since the fork; CLI suite on the merge 550 passed). Not driven live: F288, F359, F245, F246, F189, F326 (unit and route level only). **Next:
Round 4.**

Grouped by file, so each group is one context load.

**3a · `messages.py` — the operator's own messages**

| Finding | Sev | Fix |
|---|---|---|
| F258 + F395 | B | An operator `POST /messages` is born at `hop_budget + 1` and labelled `origin_type="agent"`. Give it depth 0 and `"operator"`. |
| F261 | C | The sender is never checked against the roster, and an unregistered name becomes a listed agent. |
| F262 | C | `?conversation=conv-…` is split as `agent:agent` and silently dropped. |
| F263 | D | `sort` means ascending unless it is exactly `"desc"`. Latent: no UI calls it (F260). |

**3b · jobs and loops**

| Finding | Sev | Fix |
|---|---|---|
| F265 | B | A refused `create_loop` + `initial_tasks` leaves the loop and job committed and enabled. Refuse before committing, as F54 does. |
| F264 | B | `_pending_loop_request`'s Message query has no project filter. Add it. The dead `read` predicate is F259's (D6). |
| F224 | C | A loop archived through its job trips "still running" forever (`loops.py` checks `ending_state` before `archived_at`). |
| F226 | D | `GET /jobs/{id}` embedded history drops `error_summary` / `tick_count`. |

**3c · checkpoints**

| Finding | Sev | Fix |
|---|---|---|
| F130 | B | An empty-span checkpoint stores NULL `covers_through`, which means "cover everything", so the next one re-summarises the whole conversation at full price. Check the checkpoint spec first; if it names the boundary, this is a repair, otherwise it moves to a spec track. |
| F333 | B | `continue`'s give-up pass reads the queue after withdrawing it, then says "had nothing queued". |
| F234 + F399 | D | Taking a checkpoint doesn't clear `dismissed`. |
| F398 | C | `dismiss` accepts a never-warned conversation and pre-silences its first warning. Guard: require `due`. |
| F233 | D | The same hole from the NULL-state side, fixed with the same guard. |
| F236 | D | A passed-over note resurfaces later as fresh. Retire older unconsumed notes. |
| F364 | C | `submit_checkpoint_notes` refusals say neither which entry was refused nor by how much it overshot. |

**3d · runs, reconciliation, queue delivery**

| Finding | Sev | Fix |
|---|---|---|
| F288 | B | Reconciliation after a restart re-schedules only the interrupted runs' own agents. It breaches a **shipped requirement** (F286): call `redrain_queued_agents(project_id)`. |
| F359 | B | A run killed by the Hub's own "database is locked" write skips the worktree snapshot and the footprint re-point. |
| F338 | D | Delivery selects, then updates by key, so a withdrawal in between is overwritten to "delivered". Use the conditional-UPDATE claim (the F227 pattern). |
| ~~F275~~ | C | **Moved to UI-1** (needs the bundle). An abandoned operator message renders after the failures it caused (appended after the sort). |
| F195 | C | The titler inherits the Hub's cwd, not the project's, and leaks another project's CLAUDE.md into titles. Do the ~8-site cwd sweep DECISIONS bundles with it. |
| F297 | B | `agentweave stop` on Windows force-kills (`taskkill /F`), so lifespan shutdown never runs. Try a graceful stop first. |

**3e · worktrees and merge visibility (backend half)**

| Finding | Sev | Fix |
|---|---|---|
| F245 | B | Conflict detection never compares a task branch with the branch it will merge into. |
| F246 | C | Releasing a task drops its branch from the conflict report while unmerged commits remain. |
| F189 | B | The Workspace section shows `.agentweave/agents/<a>-session.json`, which nothing writes. The real path is already computed. |
| F326 | D | A review refused after its checkout was provisioned leaves the checkout registered. |

**3f · smaller B's that fit nowhere above**

| Finding | Sev | Fix |
|---|---|---|
| F360 | B | The checkpoint probe asks about "tasks assigned to this agent" while a loop checkpoint lists the whole queue. |
| ~~F156~~ | B | **Moved to UI-1** (its UI half). `integration-preview` says `will_merge: true` for a task the gate refuses. The wording repair; the F154 residual. |
| F277 | C | `restrict_spec_writes` omits `MultiEdit` from `--disallowedTools`. |

## Round 4 — Hub routes that answer wrongly (the C/D sweep, ~2 days)

**Status:** done 2026-09-23 on `round/4`; adversarial Opus review applied (`90ffd53`: one
blocker — `POST /agents` still accepted `operator` — two should-fixes, six nits); full Hub suite
CI-style 4741 passed / 0 failed, CLI 550 passed. 4e, 4a, 4b, 4c done: 27
closed (F414, F415; F192, F194, F199, F239, F247, F254; F175, F182, F191, F200, F180, F208; F176,
F184, F243, F244, F397, F204, F210, F214, F216, F232, F238, F255, F257, F282). **F249** moved to
UI-1 beside F250: its fix changes the list routes' response shape, which the bundled panel reads.
~~F62~~ (D7) and ~~F149~~ (D1) stay with their decisions; 4d stays parked.

Mostly S, mostly one guard or one sentence each. Batch them by the shared helper.

**4a · the unknown entity is not a 200 or a vague 404.** Write one `require_known_agent` helper and
apply it everywhere, since the trigger route already does this right.
F192 (stop on an unknown agent), F194 (chat routes), F199 (queue routes), F247 (`GET
/worktrees/{agent}`), F254 (an SSE ticket outlives its project), F239 (usage for an unknown or
foreign conversation).

**4b · refusals that say what is true and what would work.**
F175 + F182 (model refusal enumerates what is declared: one helper, two sites), F191 (four states
share "Conversation is unavailable"), F200 (four states share "already delivered/withdrawn"), F180
(the archive refusal omits "bind a runner"), F208 (`arrange` 409 names `POST /spec/reindex`).

**4c · request contracts.**
F176 (empty runner name), F184 (whitespace-only charter name), F243 (`config: {}` / `null` cannot
clear, with F219's shape), F244 (the roster omits `config`), F397 (a re-archive re-stamps
`archived_at`), F204 + F210 (bodyless calls to routes whose every field is optional), F214 (a retired
requirement's coverage reads `unserved`), F216 (drift rows name only database ids), F232 (dismiss
accepts an answered permission card), F238 (`PUT /settings` writes no activity row), F255 (a
malformed `since` is ignored), F257 (an unknown severity filter answers 200), F249 (worktree lists
can't say "not a repository"), F282 (junction refusal prints the declared path, not the resolved
one), F62 → D7, F149 → D1.

**4e · carried from Round 3's review (2026-09-23).** **F414** (B, first in this round): `create_loop`
with `initial_tasks` still commits the job and loop before a per-task refusal (entry status, an unknown
requirement id) can land -- F265's half-created loop through a second door; validate every initial task
before the first commit. **F415** (C): reserve `operator` as an agent name, since Round 3a made it the
runless sender (the CLI and Hub name rules change together).

**4d · the Codex caveat.** ~~F322~~ (Codex network by cwd) cannot be driven: Codex has been undrivable
since 2026-08-29. It is parked with F325, pending D13.

## UI-1 — one bundle: controls that lie or do nothing (~2 days, B first)

**Status:** done 2026-09-23 (commits `12db377`..`fa3f812` on `round/ui-1`, fast-forwarded into the
2026-09-24 daily branch; Opus-reviewed and the review applied; full Hub suite 4753 passed, vitest
1620 passed, browser check 13/13 on `:8010`; bundle rebuilt and `:8000` restarted at the operator's
instruction). 22 of 23 closed: F186 F187 F179 F241 F237 F348 F171 F61 F307 F249 F250 F252 F315 F337
F205 F229 F169 F275 F193 F256 F231, and F156's UI half (F255 was already closed in Round 4c).
**F350 carried** (the row says why). Not driven live: F348 (needs a running turn). **Next: Round 5.**

One bundle and one browser check, and it reaches `:8000` on reload.

**Blocked until `:8000` is restarted past `c18a87b`** (the operator's call). Any rebuild now carries
that commit's `{tasks, total, has_more}` envelope (F202), and `:8000`'s backend, unrestarted since
2026-09-19, still answers the bare array -- the night window's group 5.4 gate found this on
2026-09-23 and held that bundle back for the same reason.

| Finding | Sev | Fix |
|---|---|---|
| F186 | B | Charter delete gets a confirmation. The delete is hard and cannot be undone. |
| F187 | B | The charter form renders its own 422. Re-locate the component first, because `ChartersPage.tsx` moved. |
| F179 | B | "No runner" shows the Hub's reason instead of reading as a neutral value. |
| F241 | B | Wire `GET /worktrees/conflicts`, which now includes Round 3e's base-branch check, into the Worktrees panel. |
| F237 | B | `project_settings_updated` also invalidates the accounting keys, so budget displays stop going stale. |
| F348 | B | Autoscroll counts the streaming indicator, so following stays on. |
| F171 | B | Identity-conflict dialog copy: its fixed explanation is false in 3 of 4 cases. |
| F61 | B | Flow conversations stop all being titled "Ledger flow". This needs `review_task_id` on the queue response (a backend line), plus the rail. |
| F250 | D | The Worktrees panel refetches on SSE, together with F249's "not a repository". |
| F337 | C | The permission-refusal activity line shows `detail` and attributes the refusal to the Hub. |
| F256 | D | The Logs agent filter marks roster names apart from ghost strings. |
| F229 | D | Decline is available on the Questions page, not only in the run card. |
| F231 | C | Approved permission decisions can be listed (`pending_only=false`). F389's event half is D. |
| F205 | C | The two `→ archived` edges get a button. |
| F169 | C | Render the approval advisory. |
| F315 | C | "Mark waiting" shows it is pending and refuses a second press. |
| F350 | C | The composer send button stays on-panel below ~560 px. **Carried out of UI-1 (2026-09-23):** the repair is the narrow layout (the rail as a drawer or header control below 760px), a design change that has to be measured in a browser, not a CSS cap set blind. |
| F252 + F255 | B | Logs show newest-first, with paging. The route and the view change together. F255's malformed `since` is the same query. |
| F307 | B | The first Tab in a confirm-only dialog stays in the dialog. The operator named which control gets focus as a separate question, so it is in D13. |
| F193 | B | An archived agent's open conversation shows one state in both rail views, with a remedy. Its product answer is in D10. |
| F275 | C | *Carried from Round 3d.* `groupIntoTurns` puts an abandoned entry among the turns by its timestamp, not in the trailing `pending` group; the chat routes sort it in instead of appending it. |
| F156 (UI half) | B | *Carried from Round 3f.* The approval drawer reads `will_attempt_merge`, `will_merge` is retired from `integration-preview`, and the drawer's "cherry-picks" becomes "merges" (integration runs `merge --no-ff`). |

## Round 5 — scheduler residuals (~1 day)

**Status:** done 2026-09-23 (interactive session, worktree `round/5`, Opus-reviewed). **F357** and
**F167** closed (see their FIXED paragraphs and the review follow-ups). **F327 left the round**, by
the operator's answer of 2026-09-23 evening: `DECISIONS.md` `F327-scope` (2026-09-12) had already
said it waits for its own spec loop, since every repair changes a main spec, and this table's
"no-spec, F319/F328 pattern" row disagreed with it. It is spec track **S13**, option (b).

**Status:** unblocked 2026-09-23. F352's build (`an-unstaffed-review-names-its-holders`) landed and
was driven on the 2026-09-23 night window and is archived, so `decide_firing` / `run_job` are no
longer being rewritten underneath this round. **F373 and F400 have left it:** the day window's
`pressing-run-names-the-reason-that-held` (proposed 2026-09-23, with F411-F413, F23, F300, F312)
names both, and a finding is carried in one change only. If that change is rejected they come
back here. Three remain.

*(Written before F352 landed:* F352 and `an-unstaffed-review…` rewrite the same `decide_firing` /
`run_job` functions. A fix landed first would conflict, and a naive one regresses the others: F392
is that failure.*)*

| Finding | Sev | Fix |
|---|---|---|
| ~~F373~~ | B | **Moved to `pressing-run-names-the-reason-that-held`.** Pressing Run answers with an earlier firing's stall reason. |
| ~~F400~~ | B | **Moved to `pressing-run-names-the-reason-that-held`.** "No other agent is free" while one is. |
| F357 | B | The review briefing names the evidence gate. This is copy, so no design is needed. |
| F167 | B | `agents_that_worked` cannot see an author whose history is all the operator's, so F70/F142 recovery never fires. |
| ~~F327~~ | B | **Moved to spec track S13** (operator, 2026-09-23). A flow-staffed review whose dispatch is refused leaves the reviewer holding the task. Every repair modifies a main spec (`DECISIONS.md` `F327-scope`), so it is not a no-spec row. |

---

## D — operator decisions (13 questions; put them through `daily-review`)

Each question below unblocks the findings in its row. They are grouped so that one answer closes
several findings. **Recommended first**, because they unblock the most or the largest: **D1, D3, D6,
D4.**

| # | Question | Unblocks |
|---|---|---|
| D1 | What is a JobRun row: a firing, a turn, or an attempt? And does `run_id` in job events get renamed? | F121, F123, F147, F149 (all four become mechanical, S7) |
| D2 | Model catalog: read the CLI's cache at runtime, or regenerate the literal at release? Are aliases accepted? | F174, F267, F268, F221 (S8) |
| D3 | What does an unbound self-registered agent get told, keyed on `contact_mode`? Does `contact_mode="watchdog-spawn"` go? | F111, F136, F3 (S9) |
| D4 | Permission posture: one built-in default (`acceptEdits` vs `workspace`). Does the manual card show the workspace verdict? | F283, F230, F284 (S10) |
| D5 | How strict should the shell judge be about bare `$VAR` / `$(…)`? | F401 (the rest of S3 needs no answer) |
| D6 | Dead surfaces: build the mount point, or delete the code? Per surface. | F178 (launchability card), F225 (loop controls), F260 + F263 (Messages screen), F259 (the message-read flag) |
| D7 | Does the budget cover worker spend (checkpoint, probe, titler)? Is Codex priced from tokens, or are totals marked partial? | F240, F62 (S11) |
| D8 | Who is the actor when a loop or flow moves a task (a new `actor_kind`)? | F47, F120 |
| D9 | Is a gate-refused approval "no verdict", and what does the divergence reason say? | F374 (F357 is in Round 5) |
| D10 | Agent control and addressing. "Pause this agent" (F15). Addressing the operator without a question (F77). Collision with host `SendMessage` (F139). `agent_wide` for "no such agent" (F276). Is the assignee settable by agents over HTTP but not MCP (F366)? Are titles editable (F125)? What does an archived agent's conversation show (F193)? | F15, F77, F139, F276, F366, F125, F193 |
| D11 | Run and turn presentation: where a pre-spawn failure shows (F291). Binding without completion evidence (F42). A stale-run sweep trigger (F168). Checkpoint visibility, which is really all-or-nothing (F235). What a run says when its own terminal-status write fails (F273). | F291, F42, F168, F235, F273 |
| D12 | Isolation and merge truth: may `read_only` flip mid-task (F242)? Is the approval gate's conflict result persisted (F141)? Unknown-branch spelling (F165)? | F242, F141, F165 |
| D13 | The remainder, one line each | F308 (CI drift alarm), F305 (windows re-ask decided questions), F354 (live agents run MCP from the working tree), F385 (pywebview private mode), F20 (deep-link fallback), F307 (dialog initial focus), F349 remainder, F53 (a loop's archive releases adopted tasks?), F217 (drift branch basis), F281 (shell writes recorded how?), F389 (event per allow?), F146 (an operator-posted blocking question), F157 (`spec_document_id` on non-loop jobs), F134 (an empty charter), F183 (charter name uniqueness), F177 (a runner sequence column, needs a migration), F248 (`/worktrees/conflicts` shadows an agent named "conflicts"), F133 (queue status recomputes the reason), F21 (**retire**: not fixable inside AgentWeave), F382 (**watch-only**; narrowed 2026-09-22 to `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped`, not diagnosed), F322 (**park with F325**), F339 and F340 (**stay parked**, confirmed 09-21) |

## Spec tracks — from 2026-09-28, one at a time, R1 / R2 / R3 / IMPL

In priority order. Tracks marked *(after Dn)* start only once that decision is recorded.

| # | Change | Findings | Why this order |
|---|---|---|---|
| S1 | **What counts as attending a task.** One helper replaces `on_it` / `tasks_with_a_turn_pending_or_running`: keyed by pair, excluding suspended entries, with a written `waiting_reason`. | F370, F371, F368, F361, F289, F158 | B-heavy, and it follows directly from F352. Starts once Round 5 is in. |
| S2 | **Checkpoint cutover identity.** A `cut_over_to_conversation_id` column plus a row claim. It is the third time the ledger has asked for this column. | F293, F294 | Two B's, one migration, well understood. |
| S3 | **Shell judge word shapes.** | F362, F403, F402, F401 *(after D5 for F401)* | F362 has the largest live reach (262 refusals on a real project). Follows the F375 precedent. |
| S4 | **SSE tells the client what it lost.** A generated allowlist, a gap marker, and broadcast after commit. | F251, F253, F335 | Silent data loss under load. F335 must land with or before F251. |
| S5 | **Spec flow operator surface.** An epic, split into slices, each its own change: (a) evidence decision + coverage bar (F215); (b) drift (F129, F132, F216, then F217 after D13); (c) corpus writes (F206, F208, F205); (d) audit reads (F211, F169). | F215, F129, F132, F206, F211 | The product asks the operator for judgements no screen can take. It is the largest track. |
| S6 | **Propose gates agree.** `/documents/phase` enforces completeness, and `propose` lists every blocker. | F207, F113 | Small, and closes a back door to `approved`. |
| S7 | **JobRun semantics** *(after D1)* | F121, F123, F147, F149 | |
| S8 | **Model catalog** *(after D2)* | F174, F267, F268, F221 | |
| S9 | **Agent identity and runners** *(after D3)*, plus `request_agent` templates from a table nothing writes | F111, F136, F3, F378 | F378 is B: every `request_agent` call 400s today. |
| S10 | **Permission posture and the manual card** *(after D4)* | F283, F230, F284 | |
| S11 | **Budget covers worker spend** *(after D7)* | F240, F62 | |
| S12 | **Evidence footprint and timing** | F166, F358, F165 *(after D12)* | |
| — | **Query errors are shown, not skeletoned** | F197 (57 hooks, 101 sites) | L. Best done as a ratchet (R-1 model) rather than one change. Schedule after S5, because S5 adds hooks. |
| — | **Settings that gate collaboration are distinct** | F379 | UI redesign. After UI-1's F237. |
| — | **Flows get an operator surface** | F377, F336 | After S5, since flow creation names a spec document. |
| S13 | **A flow stages its review in the dispatch** (option (b) of `DECISIONS.md` `F327-scope`). The flow stops staging `under_review` before the dispatch; the dispatch stages it, and the reviewable pool excludes the task by its pending entry. Modifies `agent-flows`; the divergence restaff's D9 collision needs its own answer. | F327 | Decided by the operator 2026-09-23. After S1, which rewrites the "attending" helper this reads. |
| — | **Remaining single-finding specs** | F65 (queued as Q4-SPEC), F130 (if Round 3c finds no contract), F330 (orphan document on a refused send), F363 (after F354, D13), F278 (redaction false positives), F213 (a pending proposal can be withdrawn) | One each, in severity order. |

## Bundles — R1 / R2 / R3 reached, parked for the operator

Opened 2026-09-23 night: every spec track and operator decision above was grouped into twelve
bundles (`spec-queue/tracks/README.md`) and taken through R1, R2 and R3 by separate rounds. Each
bundle's full record and its **Final** section are in `spec-queue/tracks/Bn.md` (page:
`tracks/Bn.html`). **Every answer below is a recommendation** until it is recorded in
`DECISIONS.md`; nothing is built until `APPROVALS.md` names it.

| Bundle | Status | Recommended decisions (the Final section has the why) | Changes |
|---|---|---|---|
| B8 Checkpoint cutover (S2: F293, F294) | R3 done, parked | Handed over at most once **per conversation** (partial unique index), recorded as `Checkpoint.cut_over_to_conversation_id`; a DB compare-and-set serialises two presses (measured, WAL and rollback journal); exact backfill (0 rows on `:8000`); the automatic trigger declines a reopened, handed-over conversation (D6) | `a-checkpoint-is-handed-over-once-and-says-where-it-went` (M) |
| B9 SSE tells the client what it lost (S4: F335, F253, F251) | R3 done, parked | An event is announced only after its write commits (publish-on-commit, a guard test with a rule for whoever lands second); a lagging subscriber gets a `stream_gap` frame and catches up as after a reconnect; **B9-Q1:** drop the app's allowlist and keep event kinds as one server-side list with a generated TypeScript type (yes); **B9-Q2:** hold F251's UI bundle until `:8000` is restarted (yes). Candidate finding: the Overview strip shows every project's events and checks `warning` where the Hub writes `warn` | `an-event-is-announced-only-once-its-write-is-committed`, `a-live-view-that-fell-behind-is-told-and-catches-up`, `every-event-the-hub-sends-reaches-the-app` — build in that order |
| B10 Dead surfaces (D6: F178, F225, F260, F263, F259) | R3 done, parked | **F225: build** Stop, Archive and delegation in the loop's tab (an operator stop always records `stopped`; every loop event row inside the transaction); `archive_job` still does not refuse a running loop. **F178: build** a collaboration line under the runner picker and delete `AgentCard`. **F260: delete** the Messages screen as a no-spec round (lower `MISREPORT_CEILING` and `UNHANDLED_SITE_CEILING`). F263 already fixed (`779820e`). **F259:** outstanding mail is mail not yet delivered, no migration. Candidate findings: `/compact` and `/new-session` messages never delivered; `LoopTab` fetches events it never renders | `a-loop-is-stopped-archived-and-delegated-from-its-own-tab`, `a-runner-that-cannot-collaborate-says-so-where-it-is-bound`, `a-loops-outstanding-mail-is-mail-not-yet-delivered` |
| B12 Single-finding specs (F65, F130, F330, F363, F278) | R3 done, parked | **F363:** the Hub caps a spec read at 40,000 characters (under Claude Code's measured 50,000 spill limit) and the agent continues by requirement id or key; file-read errors answer 409 (after B11's F354 pin). **F330:** the document is created inside the trigger route, a failed commit removes its file, and a post-commit refusal *archives* it as the operator's act — never deleted, since recorded events are never removed (R2 reversed R1). **F278:** deep POSIX paths are not redacted as credentials. **Close without change:** F130 (fixed 2026-09-22), F65 (its state can no longer arise). Candidate finding: `list_evidence` ignores `document` when no identifier is given | `a-specification-is-read-in-results-that-fit`, `a-refused-first-send-leaves-no-exploration-behind`, `a-file-path-is-not-redacted-as-a-credential` |
| B7 Models and budget (D2/S8: F174, F267, F268, F221; D7/S11: F240, F62) | R3 done, parked | **D2:** read the Codex CLI's model cache at runtime, the literal kept as fallback (Docker has no Codex CLI, so it falls back); **aliases are accepted** and stored as written, and every model screen resolves them. **D7:** worker spend (checkpoint, probe, titler) **counts in the budget** and is gated like turns — automatic checkpoints decline before generating rather than writing an empty one; **Codex is not priced**, its estimate is marked partial. The runner choice names its model (F268). Backfill on `:8000`: 962,599 tokens ($1.17), nothing pauses. Candidate findings: checkpoint worker runs `claude -p` without `--tools ""` (F195 gap); an `unwritten` checkpoint becomes the next base; the titler re-pays each turn; a declined handover's note never reaches its reviewer | `a-runner-choice-names-its-model`, `an-estimate-that-misses-turns-says-so`, `worker-spend-counts-against-the-budget` (migration), `a-model-alias-is-a-model-choice`, `the-codex-models-offered-are-the-ones-its-cli-lists` |

**Migration numbering:** four unarchived changes name `0106` (B8's, B3's
`agents-no-longer-register-themselves`, B7's `worker-spend-counts-against-the-budget`, B5's
`a-footprint-names-the-line-of-work-its-commit-is-on`). The first built keeps it; the rest renumber
in build order.

## Honest arithmetic

- **No-spec (Rounds 0–5 + UI-1): ~100 findings** if every re-verification agrees. By
  today's pace (6 fixes in one afternoon, with tests), that is **~2 weeks of interactive sessions**,
  or fewer if the night window takes the S-sized rows.
- **Decisions: 60 findings behind 13 questions.** Answering D1, D3, D6 and D4 alone releases 17.
- **Spec tracks: ~30 findings direct, plus those the decisions release**, at one change per 2–3
  days under the round discipline. That is **~6–8 weeks**.
- **Inflow:** drives file ~3–5 findings a week, and none of this counts them. The ledger converges
  only if the no-spec rounds keep outrunning the drives.
