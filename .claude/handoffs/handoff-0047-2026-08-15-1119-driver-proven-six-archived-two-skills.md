# Handoff: the autonomous driver is proven, six changes archived, and two loop skills exist

**Date:** 2026-08-15T11:19+0100 · **Branch:** autonomous_work · **HEAD:** `ffb8d98`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0046-2026-08-15-1040-the-loop-that-died-and-the-skill-that-survives-it.md`
**Status:** **chunk complete.** Everything committed and pushed, 0 unpushed, tree clean apart from
one pre-existing stray file. No work is half-done.

## Goal

Close out the loop-8 line of work by archiving what shipped, and make unattended work actually
survivable — the previous overnight run was asked for nine hours and ran forty minutes.

The *why*: the product's value proposition is spec → verified → merged. Two of this session's
threads test that claim from opposite ends — archiving proves the specs are real, and the loop
skills exist so the next long run does not lose its work to a session ending.

## Current state

### Shipped this session

1. **Two integration tests closed** (`cb26717`). `approved-means-it-is-in-the-product` tasks 6.2 and
   6.7 were agent-verifiable tests left open because the footprint bug made them vacuous — *"the
   commit reaching `main` was `main`'s own"*. That blocker was removed by
   `the-seams-loop7-found` phase 1, so they became writable and nobody had gone back. 6.7's test
   asserted only the `approved` half; it now also asserts coverage reads `state=verified`,
   `integration=not_integrated` after a **genuinely failed merge**. Both mutation-checked.
2. **Six changes archived in dependency order** (`3ac9808`). The last three carry MODIFIED
   requirements against ones the earlier ones ADD; it resolved as `~1`, `~1`, `~4`. Specs validate
   30/30, remaining changes 14/14.
3. **The autonomous driver proven** (`1f79918`, `73ecd70`, plus smoke-test commits). A Windows
   Scheduled Task fires headless `claude -p`; each firing is a fresh process that reads
   `STATE.json`, works, commits and pushes. Two real iterations ran. **Task is now unregistered.**
4. **`/loop-prep` created** (`ffb8d98`) and `/autonomous-session` wired to it.

### Branch layout — read this before merging anything

`autonomous_work` is **7 commits ahead** of `hub-native-experience`. They are not all wanted:

| commit | keep? |
|---|---|
| `81bd5e0` seed STATE.json | **no** — smoke-test scaffolding |
| `53e469b` Driver smoke test: iteration 1 | **no** — driver-written test residue |
| `1f79918` Fix the three defects… | **partially** — its message is right but it contains only a file deletion (see Dead ends) |
| `73ecd70` Commit the driver script changes that 1f79918's message described | **YES — this is the real fix** |
| `122e37b` Driver smoke test: iteration 2 | **no** |
| `3396582` Record iteration 2's out-of-scope reconciliation | **no** |
| `ffb8d98` Add the loop-prep skill… | **YES** — also deletes the smoke-test residue |

Recommended: cherry-pick `73ecd70` and `ffb8d98` onto `hub-native-experience`, leave the rest on
`autonomous_work` as the record. Do **not** plain-merge — it would bring `driver-proof.md` and a
smoke-test `STATE.json` onto the main line.

### The three driver defects, all fixed and verified

- **Stop time was parsed as `HH:mm` against today**, so a run installed at 23:00 to stop at 07:00
  considered itself finished and unregistered on its first firing — silently killing the overnight
  case. The installer now resolves it to an absolute instant and rolls to tomorrow. Verified by
  installing with a past time (`09:00`) and reading back `StopAt "2026-08-16T09:00:00"`.
- **`driver.log` left the tree dirty at every boundary** — the runner appends after the agent has
  committed. Now gitignored and untracked.
- **The log carried a UTF-8 BOM** from `Add-Content -Encoding utf8`. Now written via
  `UTF8Encoding($false)`; verified `head -c 3` reads `202`, not `efbbbf`.

### Loop 9 — still paused, unchanged

`aw-loop9` (`proj-9eb82406`) at `C:\Users\huida\Documents\aw-loop9`. 6 tasks `pending`,
`task-6de550a5` `under_review` with **3 rejected** evidence rows. The approve→merge half has never
been exercised. Agents: `architect` (codex), `builder` (claude), `verifier` (codex,
`can_accept_evidence=true`). Hub is up on `:8010` and returned `200` at 11:19.

## Files touched

`git status --short` shows only `?? hub/agentweave.db` — a stray empty SQLite file **already
untracked at session start**, named in the last six handoffs. Not the live database; that is
`hub/data/agentweave.db`. `git diff --stat HEAD` is empty.

| path | what |
|---|---|
| `hub/tests/test_task_integration.py` | new `coverage_for()` helper; `test_a_failed_merge_leaves_the_approval_standing` now asserts the coverage half. Finished. |
| `openspec/changes/archive/2026-08-13-approved-means-it-is-in-the-product/` | archived; `tasks.md` records 6.2 and 6.7 closed with their mutation checks. |
| `openspec/changes/archive/2026-08-14-the-seams-loop7-found/` | archived; 9.3 annotated as passing-but-deliberately-unchecked. |
| `openspec/changes/archive/2026-08-14-{what-the-product-actually-built,the-loop-agents-can-drive,a-failed-run-does-not-eat-its-input,what-a-failure-tells-the-operator}/` | archived. |
| `openspec/specs/{task-lifecycle-governance,local-project-workspace,agent-capability-plane,agent-configuration,agent-context-onboarding,agent-run-sandboxing,project-environment-settings,spec-document-authority,agent-conversation-workspace,runtime-diagnostics}/spec.md` | updated by the archive operations. |
| `.claude/skills/autonomous-session/scripts/install-driver.ps1` | resolves stop time to an absolute instant; adds the gitignore line. Finished. |
| `.claude/skills/autonomous-session/scripts/run-iteration.ps1` | takes `-StopAt` absolute; BOM-free logging. Finished. |
| `.claude/skills/autonomous-session/SKILL.md` | Step 1 now skips its interview when `STATE.json` exists. Finished. |
| `.claude/skills/loop-prep/SKILL.md` | **new**. Finished. |
| `.gitignore` | `+ .claude/autonomous/driver.log`. |
| `.claude/autonomous/{STATE.json,driver-proof.md}` | created then **deleted** — smoke-test scaffolding. Gone deliberately. |
| `.claude/autonomous/2026-08-15-overnight-log.md` | unchanged this session. |

## Key decisions

1. **Archive the six despite open tasks.** Every remaining unchecked item is an operator judgement
   call ("does the first automatic merge feel safe"). Rejected: waiting for them, which would block
   archiving indefinitely. They are listed under Open questions so they are not silently buried.
2. **Renamed each archived directory to drop the CLI's archive-date prefix.** It produced
   `2026-08-15-2026-08-13-…`, matching neither the other 60 archive entries nor anything else,
   because this repo already dates change names.
3. **`the-seams-loop7-found` 9.3 stays unchecked** even though the behaviour now passes.
   `a-failed-run-does-not-eat-its-input` made it true; ticking it there would credit the wrong
   change. Annotated instead.
4. **Stop time became an absolute instant computed by the installer**, not `HH:mm` parsed by the
   runner. Rejected: making the runner smarter about "did they mean tomorrow" — only the installer
   knows when it was installed.
5. **`driver.log` is gitignored rather than written outside the repo.** Rejected `%TEMP%`: the log
   is the first thing you want in the morning and should sit beside the work log.
6. **`/loop-prep` asks intent before reading the handoff.** Rejected reading first: a brief built
   from what was last shipped proposes more of the same and inherits its assumptions — the
   contamination `/e2e-loop` warns about and that loop 9 suffered.
7. **Smoke-test `STATE.json` and `driver-proof.md` deleted.** A stale file saying
   `"purpose": "DRIVER SMOKE TEST"` would be read as a real queue by the next loop.

## Constraints and user directives (verbatim)

**From this session:**
- **"test the autonomous driver"**
- **"yes fix now"** — on the three defects the driver's first run exposed.
- **"Ahh let's also create a skill for loop preparation. It's basically interviewing the user using
  the information that we know from the latest handoffs and at what point we are in the development
  of the current project to see if we need to create any artifact, do any exploration, any spec,
  anything in order to have a smoother loop"**
- On next work, the operator chose **"Archive the six outstanding openspec changes"** over proving
  the driver, the explorations, and finishing loop 9.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- **G5 (the interview backstop) is a non-goal** — *"actually that's okay because this is a AI test.
  The AI should answer or not deliberately based on the test."* Observed a fourth time in loop 9.
- The requeue rule is **"any failed run, capped at 3"** — do not re-propose the narrow variant.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Evidence: *"The evidence can be anything… Whatever the model thinks it's necessary to show that
  his work is good."* · *"only test agents can accept the evidence… If no tester agent then all
  defers to the operator."*
- On narrowing command execution: *"That would be the work for hooks. Which are not implemented yet."*
- Handoff cadence: only when asked, or when an openspec change is done.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; **never mark a task complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.
- Session directive: **do not call the Agent tool, and do not use workflows or deep-research, unless
  the user requests it.**

## Dead ends

**New this session:**

- **`git add <path-that-was-deleted-and-already-unstaged>` aborts the whole `add`.** I ran
  `git add .gitignore .claude/autonomous/driver.log .claude/skills/autonomous-session` after
  `git rm --cached` + `rm` on the log. The pathspec matched nothing, git errored, `2>/dev/null` hid
  it, and **nothing was staged** — so `1f79918` contains only a deletion while its message describes
  three fixes. **Stop suppressing stderr on staging commands.** The next driver iteration caught it
  and committed the real changes as `73ecd70`.
- **`npx openspec status --change <name>` rejects names starting with a digit** (`"Change name must
  start with a letter"`), but **`npx openspec archive <name>` accepts them.** Do not conclude from
  the first that archiving is blocked.
- **`openspec archive` prefixes the archive date**, producing `2026-08-15-2026-08-13-…` in a repo
  that already dates change names. Rename after archiving.
- **`Register-ScheduledTask` reports `LastTaskResult 267011` before a task has ever run** — a stale
  slot, not an error. `267009` means "currently running".
- **PowerShell 5.1 `Add-Content -Encoding utf8` writes a BOM.** Use
  `[System.IO.File]::AppendAllText` with `UTF8Encoding($false)`.
- **Editing a file with Python `newline='\n'` when git has it as CRLF** shows as modified with an
  empty `--numstat`. `git checkout --` it; it is whitespace-only.

**Tooling quirks, re-confirmed:**
- Keep `.ps1` files **ASCII-only** — PS 5.1 reads BOM-less UTF-8 as ANSI and an em dash inside a
  quoted string breaks parsing several tokens away. Syntax-check with
  `[System.Management.Automation.Language.Parser]::ParseFile`.
- `pytest hub/tests/` is ~7 minutes and exceeds the 600s cap — run in three file chunks
  (`head -48`, `sed -n '49,96p'`, `sed -n '97,144p'`).
- Start the Hub detached via `Win32_Process.Create`; it is the one thing that survived the night.
- The Hub API key is `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (`hub/.env`).
- Event rows are in **`event_logs`**, payload column `data`.
- `git commit -F -` with a heredoc; `@'…'@` is PowerShell syntax.

## Verification

**Ran, with real output:**
- `pytest hub/tests/test_task_integration.py` — **22 passed**.
- **Two mutation checks on the newly-closed tasks:** recording `MERGED` without merging fails
  `test_approving_a_task_puts_its_work_on_main`; forcing `is_reachable_from_main` to return `True`
  fails `test_a_failed_merge_leaves_the_approval_standing`. Both **caught**.
- `npx openspec validate --specs --strict` — **30 passed**. `--changes --strict` — **14 passed**.
- `ruff check hub/ src/` — clean.
- **The driver, end to end, twice.** Iteration 1 committed `53e469b` and pushed, 35s, exit 0.
  Iteration 2 committed three times and pushed, exit 0. Verified independently of the driver's own
  claims: commits exist, content correct, `0` unpushed, tree clean, only `.claude/autonomous/`
  touched.
- **Stop-time rollover:** installed with `-UntilHHmm "09:00"` (already past) and read the registered
  argument back as `StopAt "2026-08-16T09:00:00"`.
- **BOM removal:** `head -c 3 driver.log` → `202`.
- Both `.ps1` scripts parse clean via `Parser::ParseFile`.

**NOT run, and it matters:**
- **The full `pytest hub/tests/` has not been run since `55bfadb`.** `cb26717` changed
  `test_task_integration.py` (that file passes, 22/22) and nothing else touches Python behaviour,
  but the whole suite is an inference, not a measurement.
- `pytest tests/` (CLI), `npx vitest run` and `npx tsc --noEmit` were **not** run this session. No
  CLI or UI source changed.
- **`/loop-prep` has never been invoked.** It is written and unexercised.
- **`/autonomous-session` Step 1 has never been exercised** — the driver test used a hand-written
  `STATE.json`, bypassing the interview.
- **Loop 9's approve→merge half is still unexercised.**
- `make ui` has never been executed anywhere — `make` does not exist on this machine.

## Git state

Branch `autonomous_work`, HEAD **`ffb8d98`**, working tree **clean** except `?? hub/agentweave.db`,
**0 unpushed commits**.

`hub-native-experience` is at `3ac9808`, pushed, and is **7 commits behind** `autonomous_work`. See
the branch-layout table above — cherry-pick, do not merge.

**Live environment:** Hub on `:8010`, detached via WMI, `200` at 11:19. The
`AgentWeaveAutonomousSession` Scheduled Task is **not registered** (unregistered after the test).

**Projects in the database:** `aw-testbed`, `newtest`, `test2`, `aw-loop-4`, `aw-e2e`, `aw-loop5`,
`aw-loop6` (`proj-c28f08df`), `aw-loop7` (`proj-e6c1de74`), `aw-loop8` (`proj-94f3f169`),
`aw-loop9` (`proj-9eb82406`).

**Keep `aw-loop6`–`aw-loop9`.** Loop 6 holds a hand-minted credential `run-ev6` /
`aw_run_loop6_evidence` — **delete that row if ever shared.**

## Next steps

1. **Cherry-pick `73ecd70` and `ffb8d98` onto `hub-native-experience`**, in that order:
   `git checkout hub-native-experience && git cherry-pick 73ecd70 ffb8d98`. `ffb8d98` deletes
   `.claude/autonomous/STATE.json` and `driver-proof.md`, which do not exist on that branch — expect
   and resolve that conflict by keeping them absent. Then push.
2. **Write the L9-2 exploration** at
   `openspec/explorations/2026-08-15-nothing-asks-whether-the-artefact-is-usable.md`. Evidence is
   already gathered in `.claude/autonomous/2026-08-15-overnight-log.md`: a fresh `git clone` of
   `C:\Users\huida\Documents\aw-loop9\.agentweave\worktrees\builder` fails with
   `ModuleNotFoundError: No module named 'roster_fairness'`; after `pip install -e .` it is
   `59 passed`; `pyproject.toml` has `testpaths` but no `pythonpath = ["src"]`. **The point is not
   the missing line** — it is that the operator asked for a clean-checkout run, the builder's claim
   was conditional and literally true, and the verifier said *"I'll treat packaging separately from
   test correctness"*. Every actor behaved correctly and the artefact is unusable.
3. **Triage the 14 in-flight openspec changes.** Fourteen simultaneously is itself a signal; some
   are likely done-but-unarchived, some possibly abandoned. `2026-08-13-the-tool-list-matches-the-tools`
   is the obvious outlier at 6 done / 17 open.
4. **Run the full suites once** to convert the inference above into a measurement.

## Open questions for the user

1. **Which next?** The operator's stated preference last time was archiving; that is done. My
   recommendation is L9-2, then loop 9's merge half as the way to test whatever it concludes.
2. **The judgement calls archived unanswered** — worth resurrecting any? The two I would actually
   want answered: *does an abandoned queue entry read as "the Hub gave up" clearly enough to act
   on?* and *do two exit codes on one event read as informative or as noise?* Both concern surfaces
   built this week that nobody has used in anger.
3. **Delete `autonomous_work` after cherry-picking?** It would then hold only smoke-test residue.
4. Carried, still unanswered: should `.claude/handoffs/` stay tracked (**now 133 files**)?

## Read on resume

- `.claude/autonomous/2026-08-15-overnight-log.md` — the overnight findings with evidence; L9-2 and
  L9-3 are written up there and step 2 builds directly on it.
- `.claude/skills/loop-prep/SKILL.md` — the new skill, unexercised. Read before running any long
  loop.
- `.claude/skills/autonomous-session/SKILL.md` — the loop itself, and the post-mortem of why the
  first one died.
- `openspec/changes/archive/2026-08-13-approved-means-it-is-in-the-product/tasks.md` — 6.2 and 6.7
  record what "vacuous test" meant here and how it was proven closed.
- `hub/tests/test_task_integration.py` — `coverage_for()` and the failed-merge test are the pattern
  for asserting a state through real behaviour rather than by forcing a flag.
