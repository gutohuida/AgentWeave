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

## 2026-09-19

Written by the day window, iteration 5, from `review/review-2026-09-19.html`. No change was
specced today — the drain count at compose time was 2 (both `a-refused-capability-reaches-the-operator`
and `an-unstaffed-review-names-its-holders` still unbuilt), so per the playbook's own rule every
slot went to the draining column instead of a spec round. There is no row to give a status token to.

The two carried decisions from `## 2026-09-18` are unchanged and still open: an explicit
`APPROVED`/`REVISING`/`REJECTED` token for `a-refused-capability-reaches-the-operator`, and the
re-derivation round `an-unstaffed-review-names-its-holders` needs before it can build. Also open:
the merge gate's cadence, now a three-day-old pattern (§1 of the page).

Today's work was a full-surface sweep (one new finding, F384, filed and fixed same day) and a
`FINDINGS.md` status sweep (29 entries normalized, 14 of them already fixed but miscounted as
open). Neither needed a spec. If you approve nothing, the FIX window falls to the same
decision-gated default the last two nights already surveyed and closed with an empty queue (§5 of
the page). There is deliberately no `ORDER:` line here.

### APPROVED — `a-refused-capability-reaches-the-operator`

**The operator approved this on 2026-09-19**, after the adversarial Opus review their standing
process requires (`feedback_opus_review_before_approval`) returned **DO NOT APPROVE**, and after
**R4** applied every finding from it. R4 is commit `6954a17`; `openspec validate --strict` passes.
Read design.md's **Rounds** section before building — R4 changed four things beneath the decision,
and two of them are defects R1-R3 would have shipped.

**This supersedes the "no row to give a status token to" line above**, which was written before the
review ran.

- APPROVED  a-refused-capability-reaches-the-operator   tasks 0.3, 0.4, 0.5 and 4.12 only; §1 is gated on F386

```
ORDER: a-refused-capability-reaches-the-operator tasks 0.3, 0.4, 0.5 and 4.12 ONLY, then an-unstaffed-review-names-its-holders tasks 1.1-1.4 ONLY, then a-loop-staffs-the-agent-it-names groups 0, 1, 2, 3, 4, 6, 7, 8 -- NOT group 5
```

**The `- APPROVED` row above was missing until 2026-09-19 16:0x** — the approval was written only
as this heading and the `ORDER:` line. `README.md`'s contract is *"One line per change. The status
token is the authority"*, and every machine reader looks for that row: `backlog_page.py`'s
`approvals_rows()` found none and rendered this change as still **waiting on the operator**, which
is how the omission was caught. A prose heading is for the human; the row is the contract. **Write
both.**

**Why the order is partial, and this is the part a window must not skip.** R4 added task **0.1**:
`F386` must be fixed and merged before anything in §1 is built. The record this change opens is
deliberately **non-blocking**, and the card that is its only route to a human
(`QuestionInterruptCard.tsx:35`, `:24`) says `{from_agent} is waiting` for every question it
renders — which this change's **own ADDED requirement** forbids
(*"SHALL NOT cause any surface to report that the refused run, its conversation or its loop is
waiting on the operator"*). Building §1 before `F386` makes the change violate its own spec in the
same motion that satisfies the rest of it. **Do not build §1, §2, §3 or §5 tonight.**

**What is in scope tonight**, and it is real, self-contained work that no prerequisite gates:

- **0.3** — migration `0104` (head is `0103`): `questions.subject_key`, `String(200)`, nullable,
  plus a **partial unique index** on `(project_id, subject_key)` where
  `answered = 0 AND declined = 0 AND subject_key IS NOT NULL`. Backfills nothing. `downgrade` drops
  both.
- **0.4** — the column on `Question` in `hub/hub/db/models.py`, with the comment saying the key is
  a structural identifier and **not prose** (design **D15** — this is the whole point of it).
- **0.5** — `ask_question_for_actor` (`questions.py:235`) takes `subject_key: Optional[str] = None`.
- **4.12** — the test that every existing caller is unaffected: an operator-posted question still
  writes `subject_key IS NULL`, and two NULL-keyed open questions on one project coexist.

Additive, nullable, with no consumer yet — so it cannot change behaviour, and it de-risks the
larger build. **`0104` runs against the operator's live database on their next restart.** That is
the one thing here they should know happened; it adds a column and an index and touches no existing
row.

### APPROVED — `an-unstaffed-review-names-its-holders`, group 1 only

**The operator approved this on 2026-09-19 afternoon**, in an interactive session, after the
adversarial Opus review their standing process requires returned **DO NOT APPROVE** and **R6**
applied every finding from it. R6 is commit `7d805df`; the measurements are `48215cb`;
`openspec validate --strict` passes.

- APPROVED  an-unstaffed-review-names-its-holders   group 1 ONLY (tasks 1.1-1.4); groups 2, 5, 6 are not approved

**Why group 1 only, and this is the part a window must not exceed.** Three consecutive passes over
this change each found something the previous one missed, and all three were the same shape — a
decision that read correctly while reverting shipped behaviour. R5 found that D1 would revert
`4b59ee0`. R6 found it would *also* revert `a-spent-allowance-holds-the-queue`, via `agents_held`
ORed into the running set in the very expression R5 quoted. Measuring the budget then found a third
defect (`R6-8`, a `.;` in the operator's own sentence) that five rounds had specified past. That
pattern has not broken yet, so the night builds the part whose correctness its own tests can prove
and stops.

**What is in scope tonight:**

- **1.1** — `AgentAvailability` and `Holding` in `hub/hub/scheduler.py`, one record per
  non-archived agent in name order, carrying `has_runner`, `running`, **`held`**, and holdings as
  `Holding(task_id, status, loop_id, reachable)`. `LIVE_STATUSES` is the **band**, not the test;
  `reachable` is `loop_id in live or (task_id, assignee) in queued`; `held` is `agents_held(...)`.
- **1.2** — re-express `_agents_that_are_free` as the projection
  `has_runner and not running and not held and not any(h.reachable for h in holdings)`, keeping its
  docstring's reachability **and** D6 paragraphs. Correct the three caller citations
  (`:348`, `:1262`, `:1444` — `:298`/`:1137`/`:1298` are stale).
- **1.3 / 1.4** — the record test with its **three** mutations (drop `Task.status`; force
  `reachable` true; drop `held`), and the one-read test.

**This group changes no text the operator ever sees.** It is a refactor whose whole content is
*"compute the same answer, in a shape rung 3 can also read"* — so its correctness is entirely a
question of whether the pool's membership is unchanged, which is what its mutations test.

**The regression guard is the point of the night, not a formality.** Run
`py -3.11 -m pytest hub/tests/test_a_held_agent_is_busy.py hub/tests/test_a_task_nothing_will_move_holds_nobody.py -q`
before starting and again at the end. **Measured green today at `7d805df`: 55 passed, 36.21s.** If
`test_the_loopengine_shape_staffs_its_review` or `test_a_held_agent_is_not_free` goes red, the
projection has reverted a shipped change — **fix the projection, never the test.**

**Do not build group 2 tonight.** It carries the five-clause sentence, the fit algorithm (still
unwritten, and the only remaining unmeasured piece), and updates to three shipped tests including
an exact string equality. It also carries an ordering constraint — 2.14 before 2.3 — whose
violation produces an `AssertionError` inside the scheduler. None of that is night work while the
find-rate on this change is still one defect per pass.

**`F386` goes to the day window of 2026-09-20 as a no-spec carve-out repair**, the same shape as
F384 on 2026-09-19. It is a finding with no proposal, which this playbook's own source-2 rule says
is the day window's work and not a FIX window's. Both halves read fields the card already receives:
`blocking` (so a non-blocking question stops claiming someone is waiting) and `declined` (which
fires **today**, with no new code — `list_questions` filters on `answered` only, `questions.py:318`,
so a question the operator explicitly closed renders as an agent waiting on them forever).
`F387` — one question, oldest-first, so this record would hide a genuine blocker behind it — is
**not** a prerequisite but should be taken in the same sitting; the deterministic floor is
blocking-first-then-newest and both fields are already on the wire type.

**Then §1 onward, on the first night after `F386` lands.**

**Still open, and not changed by this approval:** `an-unstaffed-review-names-its-holders` needs its
re-derivation round against `F352-free`'s decided option (f) before it can build — spec work, not
FIX work. The merge gate's cadence is undecided for a fourth day.

---

### APPROVED — `a-loop-staffs-the-agent-it-names`, all groups except §5

**The operator approved this on 2026-09-19 evening**, in an interactive session, after a **second**
adversarial Opus review — run because R1 and R3 were written by the same session, and
`DEAD-ENDS.md` records that *"a round you wrote yourself is not a check"*. It returned
**DO NOT APPROVE** with eight blocking findings; six were re-verified at the source before being
accepted and all six held. **R4** (`96fed13`) applied every one. `openspec validate --strict`
passes.

- APPROVED  a-loop-staffs-the-agent-it-names   groups 0, 1, 2, 3, 4, 6, 7 and 8; §5 is NOT approved

**It is third in tonight's `ORDER:`, deliberately.** The two changes ahead of it are small, scoped
partials. Take this one only after both are done and green; if the night runs short, this is the one
to leave.

**Why §5 is held, and a window must not take it anyway.** §5 changes the two sentences the operator
actually reads — `run_job`'s 409 and the loop board's stall reason. Two things about it are hours
old and unreviewed:

- **Task 5.3 is now tied to a MODIFIED requirement written this evening.** R4-2 found that
  `agent-loops:1471` (*"Pressing Run on a loop that declines names why it declined"*) requires the
  answer to say *"which of those **two** held"*, while 5.3 mandates a third clause. The delta gained
  that requirement in R4 and **no round has yet re-derived it**.
- **Design Open Question 2 is open by R4's own admission**: `_stall_reason_from_walk`'s exact
  current sentence has never been read, and D4 asserts which string `jobs.py:355` replaces. Task 5.4
  asserts a sentence nobody has verified is the one there today.

So §5 is one short follow-up once that function has been read — not night work while its own
requirement is unrounded.

**What is in scope tonight.**

- **§1** — `_agents_a_loop_may_staff(session, loop)` in `hub/hub/scheduler.py`: call the existing
  availability read and **filter its result**. For a documentless loop the pool is **empty**, not
  `{job.agent}` (D2 — the job's own agent reaches work through `decide_firing`'s own branch at
  `:1601-1618`, which is deliberately not tested against the pool). No `default_agent` parameter
  (R2-8). **Locate the call sites by `grep -n "await _agents_that_are_free("`, never by line
  number** — they are `:348`, `:1263`, `:1444`, and the numbers in these documents have been wrong
  three times.
- **§2, §3** — staffing is not resumption (D6); `_loop_flow_busy_reason` collapses to
  `_loop_agent_busy_reason` for a documentless loop (D3).
- **§4** — the reviewer-recovery guards. **Read task 4.1's R4-6 note first:** its *"No existing test
  covers this"* was false. `test_a_loops_wedged_review_still_recovers`
  (`hub/tests/test_a_loop_does_not_staff_its_own_review.py:328`, `declares_document=False`) already
  covers it and is **green today**. Run the mutation against that test; write a new one only if it
  does not already fail.
- **§6, §7, §8** — the regression set, the drive, and closing F128 out.

**The baseline is the point of the night, not a formality.** Measured at `96fed13` with no product
code changed:
`py -3.11 -m pytest hub/tests/test_a_loop_does_not_staff_its_own_review.py hub/tests/test_loop_busy_guard.py hub/tests/test_flow_width.py hub/tests/test_actor_aware_claimability.py -q`
→ **54 passed, 20.83s.** Run it before starting and again at the end.

**Triage a new red by the fixture, never by the filename** (R4-7). A failing test whose loop sets
`spec_document_id` is a **flow** regression and is this change's fault by default — flows do not
change. R3's list of "documentless" files was wrong for four of nine, and omitted
`test_loop_busy_guard.py`, which is the dedicated regression file for the function §3 changes.

**One thing to tell the operator in the morning, because it will look like a regression.**
`hub/ui/src/components/spec/loopCounts.ts:23` buckets any loop carrying a `stall_reason` as
`'stalled'`. After this, every documentless loop pinned to a busy agent gains one, so the running
count falls and the stalled count rises on the board. **No UI code changes and every sentence shown
is true** — the loop genuinely is not proceeding. That is the fix working.

**Do not build §5.** Do not edit `hub/hub/api/v1/jobs.py`'s 409 `why` clause and do not touch the
board's stall sentence. If §1-§4 land early, spend the remainder on §6's full suite and §7's drive,
which are the two things four rounds of reading cannot substitute for.

## 2026-09-18

Written by the day window, iteration 5, from `review/review-2026-09-18.html`. **No status token is
supplied below. That is the operator's to write.**

`a-refused-capability-reaches-the-operator` — F376 (A) / F378 (B). Three independent spec rounds
(R1, R2, R3) all done today; `openspec validate --strict` passes; `0/24` tasks; nothing implemented.
R2 changed the record's shape (D10: it carries no run and therefore no `conversation_id`, or a
working run reports as stuck forever to two of three readers). R3 found two defects in the tasks
beneath the surviving decision: a dedupe branch that could not fire on a typed answer (D13, keyed on
a field both answering surfaces leave empty when the operator types instead of clicking), and a tool
list naming `update_job`, which does not exist, while omitting `create_job`, the one agents are
likeliest to reach for (D7). Two costs recorded rather than repaired inside the change: D13's
unindexed dedupe scan (bounded, no migration proposed) and D14, a fourth reader (the conversation
tray) that can still rank this change's own non-blocking record ahead of a real blocker in the same
agent's tray — filed separately as `F381` (C) so it outlives this change's archive. No migration, no
`mcp_server.py` edit, no UI.

Also open: the merge gate's cadence (§1 of the review page) — three of four conditions have now held
at two consecutive firings, failing only because each firing's own commit restarts a 13+ minute CI
clock faster than firings arrive. Three options are on the page; none has been picked.

If you approve nothing, the FIX window falls to the same decision-gated default the 2026-09-17 night
already surveyed and closed with an empty queue (§5 of the page). There is deliberately no `ORDER:`
line here.

---

## 2026-09-16

Written 2026-09-16 ~22:20 by an interactive session, **on the operator's explicit instruction in
session** ("apply the fixes and approve. I want the night window to build this tonight"). No FILL
window ran today — `AgentWeaveArmDay` fired at 10:15 and `install-driver.ps1` self-cancelled, so
`STATE-day.json` still reads `iteration: 0` and there is no review page behind this row. The
approval is the operator's own, given after reading the fourth adversarial review's verdict.

- APPROVED  a-materialised-task-carries-its-criteria   build §2-§5 tonight; §6-§7 only if they fit

ORDER: a-materialised-task-carries-its-criteria

**This is the whole queue for tonight.** The default backlog shape is ignored.

### What was approved, and at which commit

`a-materialised-task-carries-its-criteria` as of **`2de0233`** — R1-R4 plus **four** independent
adversarial Opus reviews. The fourth returned *approve with fixes*; its three blocking findings were
each verified against the code and applied in `2de0233`. `openspec validate --strict` passes.

The change: `spec_tasks.materialise()` builds its `Task(...)` at `:205-217` with nine fields and
never `acceptance_criteria`, while `scheduler.py:2456-2460` renders that field to the implementer
**and** the reviewer, introducing it to a reviewer as *"the standard you check their work against"* —
then shows nothing. Measured: 18 of 18 hand-made tasks carry criteria, **0 of 32** spec-materialised
ones do, all 32 NULL.

**Its home is openspec, and that is now decided** — the operator confirmed it in the same session.
Earlier handoffs carried it as an open question inferred from "do R1->R2->R3 ourselves". It is not
open any more; do not re-raise it, and do not re-author this change in the trial Hub.

### The tree was green at 22:46, so step 3 is already done

`py -3.11 -m pytest tests/ -q` from `hub/`, run by the interactive session that wrote this section:
**4415 passed, 86 skipped, 0 failed, 27:46**, pytest exit 0. Measured at commit **`6d70710`**, which
is this branch's tip and carries **no product code** — everything since `2a9d536` is
`openspec/` and `spec-queue/` prose. So it is a true baseline for tonight's build.

**Skip `night-window.md` step 3's own green-tree run and spend the 15-47 minutes on the change
instead** — but only if `git log` still shows `6d70710` as the last commit touching `hub/` or `src/`
when you compose. If anything else has landed, the measurement is stale: run the gate yourself and
say so in the log. The suite emits a `RuntimeError: Event loop is closed` warning during teardown;
that is pre-existing noise on a green run, not a failure, and it is not yours.

### Read this before writing a line of it

**`design.md`'s Round log, all of it, first.** Eight passes have argued about this one function, and
each of the last four found that the previous pass's *fix* introduced a new defect. The log is the
only record of which arguments are already refuted. Re-proposing one costs the night.

Three things the log will tell you that are easy to get backwards:

- **Match on what the entry `names`, never on the resolved row's `.key`** (design D3). The delta
  spec was reworded from *resolves* to *names* in `2de0233` precisely because they diverge.
- **`dict.fromkeys`, not a `set`** (task 2.2). A `set` makes the stored order vary between
  processes.
- **The guards go INSIDE `spec_reading.py`'s helpers** (`:72` and `:98`), not at this change's call
  site (design D7). `requirement_view` reaches `statements_by_key` with no `try`/`except`, so a
  call-site guard leaves a 500 standing on the `read_spec_document` path.

### Shape of the work, ordered so stopping anywhere leaves something complete

1. **§2 — implementation.** One function in `hub/hub/spec_tasks.py` plus two `isinstance` guards in
   `hub/hub/spec_reading.py`. Note §2's task numbers run `2.1, 2.2, 2.7, 2.3, 2.6, 2.5, 2.4` —
   that is accretion order, not dependency order. **2.7 builds the `position` map that 2.2
   consumes**; read both before starting either.
2. **§3 — about 22 tests.** Several carry an explicit `MUST` clause on the fixture. Those clauses
   are the difference between a test that discriminates and one that passes under the naive
   implementation too — honour them literally.
3. **§4 — 17 mutations.** Apply, run, record, `git checkout` to revert. A mutation that flips no
   test means §3 does not pin what it claims. **Expect at least one to fail to flip** and treat that
   as a finding about the tests, not a reason to weaken the mutation.
4. **§5 — gates.** Full suite from `hub/`, `ruff`/`black`/`mypy`, `openspec validate --strict`, and
   5.4's measurement. **Background the suite** — it is 15-47 minutes and exceeds the 600s cap.
5. **§6-§7 — drive and close-out, only if they genuinely fit.** If they do not, stop after §5, say
   so in the log, and leave the change unarchived for a later window. A half-driven change is worse
   than an undriven one.

### Two hazards specific to this build

- **`py -3.11`, never bare `python`.** Bare `python` is a venv that produces three phantom
  `pty_runner` failures on a green tree and will send you hunting a breakage you did not cause.
- **Task 6.5 edits `hub/hub/mcp_server.py`** (one docstring sentence). F354 (B, open) records that
  the operator's live `:8000` Hub spawns that file fresh — **uncommitted mid-edit included** — on
  every real turn. If you reach 6.5, make the edit and commit it in one pass; never leave it
  uncommitted between iterations. If the night ends before 6.5, leave the file untouched.

**No migration. No UI bundle.** `models.py:684` is already `JSON, nullable=True` and
`hub/ui/src/api/tasks.ts:18` already types the field `string[]` — which is exactly why D1 chose
rendered strings. If you find yourself editing `hub/ui/` or writing a migration, you have
misread the change; stop and log it.

---

## 2026-09-14

Written by the FILL window, 2026-09-14, from `review/review-2026-09-14.html`. **No status token is
supplied below. That is the operator's to write.** A row with no token is not an approval, and the
FIX window builds nothing from it.

**Built and archived today, so no row:** `a-spent-allowance-holds-the-queue` (F355, B). The build
day's authority is `DECISIONS.md` `### 2026-09-14 — a day that reads LoopEngine and builds what it
finds`. Built `98385cd`/`e1eca5b`/`c8e3bbd`, gated `b5b6baf`, driven `ac6bff6` + `87b8d6a` with a
stub `claude` standing in for the provider's refusal, archived `4b362f3`. F355, F127 and F369 are
retired. **It adds migration `0103_allowance_refusals`.** Because `:8000` runs this checkout, the
operator's next restart of it applies `0103` to their real database, merged or not. There is no UI
bundle and no `mcp_server.py` edit.

**Note for whoever reads this at 23:00:** this section is now the newest, so the 2026-09-13 section
below is history. Its `APPROVED a-quote-can-spell-a-slash` and its `ORDER:` are no longer
instructions. That change is stopped on `OPEN F332-rule` in any case (3 of 30 tasks ticked). If the
operator wants it built after deciding the rule, the token has to be written again here. There is
deliberately **no `ORDER:` line**. Section 5 of the page walks the default queue: nothing to archive,
and none of the five open A findings is buildable (F299 rejected, F301 no proposal, F325 Codex, F332
rule open, F352 stopped on an operator question). **An unapproved night lands no feature.**

`a-late-answer-is-delivered` — F356 (B). An answer to `ask_user` that arrives after the tool's wait
ended, while the asking run lives, is delivered as a queued turn. *Still waiting* reads
`wait_ended_at`, the tool's own report. The expiry report delivers an answer that landed after the
tool's last poll, and both writers decide after commit, so the worst case is a duplicate, never a
loss. Specced R1 `3fb17ad`, R2 `9240fde`, R3 `9e78e9c`, and the Opus review `b01d3ca` (**no stop**).
Every round changed it:
- R2 found a mid-report loss and a pre-existing decline race (tasks 2.8, 2.9).
- R3 measured the guarded `UPDATE` on aiosqlite (it needs `synchronize_session=False` and
  `populate_existing`), and put both writers through one helper (2.10).
- The review found a fourth loss, a sibling declined mid-report (2.11), and corrected comments that
  are false in shipped code (1.6).

**31 tasks, 0 ticked. No migration, no `mcp_server.py` edit, no UI.** It was not built only because
time ran out. The measured ledger correction: only 1 of F356's 3 batches was lost (09-13 14:38). D5
leaves a named residual of three routes. Whether a follow-on closes it without a migration (routes 1
and 2, with a ~2 s grace-window duplicate) or with a receipt stamp (all three) is the operator's
later choice, and does not block this row.

`an-unstaffed-review-names-its-holders` — F352 (A) + F353 + F334 + F365. **Stopped at its review
and unbuilt, under `DIRECTION.md`'s stop clause.** R1 wrote an OPERATOR QUESTION at the top of
`proposal.md`: which holdings make an agent unavailable to a flow. There are five options, and it
recommends (d). R1 `e8ea490`, R2 `fb469e2`, R3 `82b58df`, review `e9f4cea`. 40 tasks, 0 ticked, no
migration, no UI, no `mcp_server.py`. **An `APPROVED` token here does not build it as it stands.**
It needs one of two answers first, both carried in `STATE-day.json` `decisions_for_user`:
- **F352-free**, the operator question itself. Its answer needs its own spec loop.
- **F352-split**, the review's recommendation. Move the F353 half (D4 + D5: the refusals' remedies,
  F334's wording, F365's once-per-task record, and the `error_summary` fit F367 needs) into its own
  change, give it one verification round, and build it. That is day-window work before any night
  can take it. The rung-3 naming waits for F352-free.

The stopped change's rung-3 rewrite must also carry `a-spent-allowance-holds-the-queue`'s hold
clause, which is +49 characters (250 with it, 201 without).

**Also on the page, and wanting no row:** the eleven improvement briefs
(`openspec/explorations/2026-09-14-*.md`), each ending in its own decision line; research candidate
3 (whether WAL plus a busy timeout becomes an `OPEN` row in `DECISIONS.md`); and the eleven fixes
not reached today (F357–F364, F347, F302, F47), which have no change directories. **Two evening
reminders:** `DIRECTION.md` has no `## 2026-09-15` section yet, and the *Carried* plan needs one;
`F332-rule` is still OPEN.

---

### The operator sat down at 23:30, after the window had already composed

**This section was written by the FILL window with no tokens, and the night composed its default
queue at 23:00 on that basis (`1bf256b`: ledger hand-checks, "no feature tonight"). The operator
then sat down in an interactive session at 23:30 and redirected the window.** `STATE-night.json`'s
queue was rewritten to match the `ORDER:` below, because iteration 1 composes the queue and does not
run again. The rows below are the operator's, given in session.

- APPROVED  a-late-answer-is-delivered   operator, 2026-09-14 23:30, in session

`an-unstaffed-review-names-its-holders` gets **no token and is not built**. F352-free is still
unanswered, and tonight's first item is the exploration that reframes it — see below. Building the
rung-3 half before that answer would write a sentence against option (e) that the answer may
re-derive.

**Tonight's first work is a new change, from `openspec/explorations/2026-09-14-who-owns-a-loops-queue.md`.**
That exploration was written with the operator in session this evening and is code-grounded
throughout. It found the mechanism behind F352: on LoopEngine, eight tasks created by the Architect
while executing the loop landed with `loop_id` NULL, assigned to `dev` and `dev_2`. Nothing walks a
task outside a loop (`scheduler.py:717`), so nothing will ever move them, and each one disqualifies
its assignee forever (`scheduler.py:1022`). It is a ratchet: every follow-up an agent files costs the
project one agent, permanently. That is why the board recorded `review_unstaffed` 498 times with
four idle agents.

The operator's instruction for it: **one proposal round, then two review rounds, then implement.**
The adversarial `REV` step is deliberately skipped — this evening's session served its purpose, with
the operator reading the argument as it was built.

**Scope guidance for R1, from the operator's own reading and the exploration's last section.** The
full design (owner-vs-executer, an admission queue, non-blocking questions, the amend trigger) needs
`hub/hub/mcp_server.py` and UI. **The reachability predicate is severable** — `scheduler.py` only, no
migration, no `mcp_server.py`, no UI — and it is the half that unfreezes a board. R1 proposes the
whole design and scopes *this change* to the severable half unless it finds a reason not to, saying
which in `proposal.md`. The rest is specced for a later change, not built tonight.

**Why `mcp_server.py` is still to be avoided tonight even though the day-only F354 rule has lapsed:**
`:8000` spawns that file fresh from this working tree on every agent turn. LoopEngine is parked, so
the risk is low rather than absent, and nothing in the severable half needs it.

**The rest of today's fixes are not buildable tonight and are a note to tomorrow, not work.**
F357–F364, F347, F302, F362, F363 and F47 have no change directories. Per this playbook, a finding
with no proposal needs the day window first.

ORDER: who-owns-a-loops-queue-R1, who-owns-a-loops-queue-R2, who-owns-a-loops-queue-R3, who-owns-a-loops-queue-IMPL, who-owns-a-loops-queue-DRIVE, a-late-answer-is-delivered

**Why this order.** The new change goes first because it is the one that unfreezes a real board and
because its proposal does not exist yet — stopping anywhere after an early item leaves a complete
artefact rather than half a proposal. `a-late-answer-is-delivered` is last because it is already
specced through its adversarial review with 31 tasks and 0 ticked, so it is the item that can absorb
whatever time is left without needing any of it. If the window reaches it with under an hour, it
starts it anyway and splits in the log.

---

## 2026-09-13

Written by the FILL window, 2026-09-13, from `review/review-2026-09-13.html`. **No status token is
supplied below. That is the operator's to write.** A row with no token is not an approval, and the
FIX window builds nothing from it.

**The 2026-09-12 cycle is still not on `master`.** `autonomous/2026-09-12-daily` spans two days and
was **50 commits** ahead of `master` at `f5f0091` (`git rev-list --count master..HEAD`): 43 from the
2026-09-12 cycle, 7 from today. Both of last night's archived changes are among them. The merge
gate failed condition 3 twice, on CI intermittents in state-only commits: `F292` at `000fcbf`, then
`F314` at `b798ff6`. No failed job was re-run. That is decision 2 on the page.

**Note for whoever reads this at 23:00:** this section is now the newest, so the 2026-09-12 section
below is history. Both of its approved changes are built and archived
(`2026-09-13-a-url-is-not-a-path`, `2026-09-13-a-refused-review-leaves-nothing-behind`), and its
tokens and `ORDER:` are not instructions. There is deliberately **no `ORDER:` line** here. Section 5
of today's page walks the default queue: nothing to archive, and of the four open severity-A
findings, `F299`'s change is unapproved while `F301`, `F332` and `F325` (Codex, undrivable) have no
proposal. **An unapproved night lands no feature.**

**Operator, in a DECIDE session, 2026-09-13 ~14:20.** `master` was fast-forwarded to `ab7cf72` at
14:25, after all four gate conditions were re-measured, so the cycle above is landed. F299's question
is answered **(b)**, and the change is rejected:

- REJECTED  an-absent-approver-is-not-named   Option (b): 1b is handed back (DECISIONS.md, 2026-09-13 afternoon). F339 reproduced 1b's reason for rejecting acceptEdits as false, so the access path is re-decided as one question with F301, F339 and F340. The change is archived unbuilt, and its measurements are kept.

**F332 was specced in this session for tonight, and it passed the Opus pre-approval review.** R1
`071354a`, R2 `26cb73d`, R3 `cbf6b49`, and the review `3628cc8` (verdict *approve after repairs*,
with the repairs made). The operator approved it in advance, conditional on the review passing
(*"approve it for tonight if the review passes"*, 2026-09-13 ~14:20).

- APPROVED  a-quote-can-spell-a-slash   F332 (A). The approver's reader decodes bash's `$'…'` the way bash does, and judges the decoded word. Code is `hub/hub/mcp_server.py` only. 30 tasks, no migration, no API shape change, no UI.

ORDER: a-quote-can-spell-a-slash

**Sizing and rules for tonight:**
- **One change.** Last night finished two changes by 04:25, so one leaves room. Spend the room on the drive and the POSIX evidence, not on a second change. There
  is no second approved change.
- **Every round changed the decoder.** R2 and R3 each found escapes the previous decoder opened,
  and the review corrected R3's reason. **Build `tasks.md` §2.2's rules, not a prototype from
  `testbed/scratch/r1f332/`, `r2f332/` or `r3f332/`.** §1 pins rows that R1's and R2's decoders
  fail.
- **The mutations in §4.3–§4.5 bite only on POSIX.** Verify them under WSL or on CI's Linux
  `hub-test`, as the tasks say. A Windows run where they fail to bite is expected, not a pass.
- **F332 is POSIX-only.** Its `fixed <sha>` Status needs CI Linux `hub-test` evidence (the strict
  XFAIL at the pin, then PASS at the fix), as F331's did. A Windows drive shows only what
  `test-guide.md` says it can.
- **On Windows, N3/N4 (`\u` or `\U` above 0xFF) stay refused.** That is a deliberate, locale-safe
  over-refusal. The review found that this machine's Git Bash would write those names *inside* the
  workspace. The operator may revisit this; the night does not.
- **Give the drive its own profile and port. Never 8000 or 8010.** Port 8000 is the operator's live
  Hub, and it serves `hub/hub/static/ui` **from this checkout** (DEAD-ENDS, 2026-09-13). Tonight's
  change has no UI diff, so commit no bundle.
- **Never close out without the drive.**
- **The operator's own session committed to this branch this afternoon** (`a3237be`, `55a95de`,
  `e9f71c0` and `b7dce8a`: F341–F345, `pty_runner.py`, `subprocess_windows.py`, `cli.py`,
  `hub/ui`). None of them touches `mcp_server.py`. If the head holds commits the night did not
  make, do not revert them. Stage explicit paths only.

`an-absent-approver-is-not-named` — F299 (A), verdict `DECISIONS.md` 1b. **Answer the OPERATOR
QUESTION at the top of its `proposal.md` first, in one line.** Re-measured on `claude` 2.1.269
through the Hub's own argv and PTY: F299's configuration works until its first approval-needing call,
then the harness process dies (exit 1, no result line, usage recorded as unavailable). 1b as written
turns that into a turn that survives the refusal, with its model asking you to approve a prompt no
surface shows. The choices are:
- **(a)** 1b plus `--permission-prompts none`, gated on the build read from the refuting run's `init`
  line;
- **(b)** hand 1b back, because the missing piece is a Hub-authored sentence (research candidate 3);
- **1b as written**, which is what the change specifies.

The change has **24 tasks, 0 ticked** (22 agent-verifiable, H.1–H.2 human-only). Python only:
`runner_commands.py`, `launchability.py`, `agent_trigger.py`, `runner_parsing.py`, `db/models.py`,
one docs page. It adds **one migration, `0103`** (two nullable columns, no backfill), with no API
shape and **no UI bundle**. `agent-run-sandboxing` gets 1 ADDED and 2 MODIFIED requirements. The
MODIFIED ones are the harness's refusals recorded for every Claude run, joined on `tool_use_id`, and
the default-posture exception 1b decided (D11). `openspec validate --strict` passes.

All three rounds changed it:
- R2 found R1's *"no model call"* was a misreading, and made D3 exclude runs with no `init` line, so
  that one typo in a runner's flags is not a refutation.
- R3 found that a slow or crashed server also completes a turn, so D3 now reads the status `init`
  gives the Hub's server, and a test is anything but `connected`.

**Operator-visible:** approver-less Claude runs start recording harness-decided refusals.

**The second loop (`F327`) did not run.** It shares `agent_trigger.py` with this change, and the
playbook's rule is *"shares no file"*. It stays first in line for tomorrow's loop. Its row is absent
because nothing was specced, not because anything was decided.

The page carries **seven decisions**. Decision 1 is the row above. The other six are not work for
tonight and want no row here:
- the merge gate and `F292`/`F314`;
- `F336` (no UI control dispatches a review);
- the night's D11a departures;
- `F333` with `F334`;
- the archived changes' open human-only checks;
- `F292`'s priority.

`ORDER:` and `NOTHING TONIGHT` are both available.

**Added 2026-09-13, after the page was written, by `d6-repair`:** `F328` (D) is fixed in `a5cb384`
under the D-6 no-spec carve-out. Both the operator's withdrawal and the scheduler's give-up now
write only an entry that is still queued. Driven: 3 of 8 samples inconsistent before, 0 of 24
after. It wants no row and no token. `F326` was not taken, because it shares `agent_trigger.py`
with the change above. `F338` (D, read only) is new: delivery's own check-then-write.

**Added 2026-09-13 by `d7-ledger`:** research candidates 2 and 3 are filed as `F339` (B) and
`F340` (B). Both are open, want no row and no token, and are not repairs. `F339` carries an
operator question: does 1b's rejection of `acceptEdits` on no grounds stand on its remaining reason?
Its stated reason, *"removing the path check entirely"*, was reproduced false on 2.1.269. That is
separate from the one-line answer the change above asks for. `F340` stays with candidate 3's
decision, which the change above does not make (its D9).

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

**BUILT — `a-refused-review-leaves-nothing-behind`, written by the FIX window at close-out,
2026-09-13, not by the operator.** **49 of 52 tasks are ticked** with actuals. The three left open
are §6.1–6.3, which are human-only (see below).
- **Commits, in the approved order.** Pin `73ae6c5`, §2 `6ebcd9f` (F319), mutations 4.1–4.4c
  `229092e`, §3 `997ff5d` (F320), mutations 4.5–4.10 `f4bb1bb`, gate `449f706`, drives `fa07089`
  (pre-fix) and `1b3d52c` (fixed), close-out after them. Product code is `turn_scheduler.py` and one
  comment hunk in `agent_trigger.py`; no migration, schema, API shape or bundle change.
- **Mutations.** Twelve, each killed by the tests its task names.
- **Gate.** The whole Hub suite gave 4218 passed, 86 skipped, 0 failed. CI's lint set is clean.
- **Two findings, verified as two.** `F319` carries `fixed 6ebcd9f` and `F320` `fixed 997ff5d`,
  each with its own quoted §5.3 evidence and r7's pre-fix outcome. The pre-fix tree (worktree at
  `73ae6c5`) reproduced all four legs; the fixed tree left every task as it was and delivered F's
  queued-behind input in the give-up pass.
- **Left open, as approved.** `F326`, `F327` (option (a), `DECISIONS.md` `F327-scope`) and `F328`
  (narrowed by `6ebcd9f`, one dated line). **Filed by this change:** `F335` (D, the escaped
  `run_divergence_resolved` broadcast, measured at unit level), and from the fixed-tree drive
  `F333` (B, a `continue` says *"had nothing queued"*) and `F334` (B, the guard names a discarded
  assignee).

The two ADDED deltas were appended verbatim to `task-lifecycle-governance` and
`agent-conversation-workspace`. The main requirement *"Dispatching a review staffs the task,
whichever path dispatched it"* is byte-identical before and after (`cmp`). `validate --specs
--strict` passes 43/43. The change is archived as
`2026-09-13-a-refused-review-leaves-nothing-behind`.

**Still yours:** §6.1, what the UI's own dispatch control shows for the `409`. §6.2, whether being
told late (a *queued* answer, then the reason, then the give-up notice) is enough, now weighed with
F334's wording. §6.3 is answered in `DECISIONS.md` and is listed only because it is a human task.
And whether F333 and F334 go into one proposal.

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

---

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
