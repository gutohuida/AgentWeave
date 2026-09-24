# The night window — FIX, 23:00 to 07:00

**You are a fresh process with no memory.** Everything you need is on disk. Read
`.claude/autonomous/STATE-night.json` for position and the newest entry at the **bottom** of
`.claude/autonomous/<date>-night-log.md` for context, then do exactly the one thing `next_action`
names, then rewrite the state and commit and push. One unit per firing. Never end an iteration with
a dirty tree.

**Every firing, before `next_action`: read CI's verdict for the previous firing's pushed sha.** One
`gh run list --branch <branch> --limit 5 --json headSha,conclusion,createdAt` call, no waiting — the
previous push is normally 10-20 minutes old and concluded. Write the verdict in the iteration's first
line. **If it is `failure`, fixing it replaces `next_action` for this firing** (read the failed
job's log with `gh run view <id> --log-failed`), whatever `next_action` says. Reading CI once at
compose is not enough: measured 2026-09-22 night, the first build commit (`384254e`) turned the CLI
matrix red and the window pushed **16 more commits onto it over five hours** without looking again.

This window **fixes**: it implements and drives. It does not write new proposals — the day window
already took them through three rounds. If a change you are implementing turns out to be wrong,
**stop implementing it**, add an `OPEN` row to `spec-queue/DECISIONS.md` recording why, put only that
row's id in `decisions_for_user`, and move to the next queue item. A proposal that survives three
rounds and then fails contact with the code is exactly the finding this whole arrangement exists to
surface; do not paper over it at 03:00.

Map, tasks, state layout and the cycle-branch rule: `.claude/loops/README.md`.
File contract: `spec-queue/README.md`. Design and rejected alternatives:
`openspec/explorations/2026-09-01-a-daily-research-spec-and-build-loop.md`.

## Budget discipline

The subscription's weekly limit is shared with the operator and no longer fits an all-Opus window
(`spec-queue/DECISIONS.md`, `### 2026-09-15`). Measured on 2026-09-14: ~60% of a window's cost is
cache reads, i.e. every token in context re-read on every later call. So context is the budget.

- **The driver picks your model and effort** from `.claude/loops/usage-policy.json` by the id in
  STATE's `current`: spec rounds and REV on Opus/high, `-impl` on Sonnet/high, drives, gates,
  archives, ledger and compose on Sonnet/medium, anything else on Opus/high. **Keep `current` equal
  to the id `next_action` names**, or the next firing runs on the wrong model.
- **When composing, give every item a standard suffix** (`-r1`..`-r3`, `-rev`, `-impl`, `-drive`,
  `-gate`, `-archive`, `ledger-`), or set `model`/`effort` on it explicitly. An improvised id falls
  to Opus/high. Escalate a genuinely hard build with `"model": "opus"` on that one item.
- **Read by section.** Grep for the heading or symbol, then Read with `offset`/`limit`. Whole-file
  Reads over 60 KB are refused in autonomous runs (`.claude/hooks/large-read-guard.py`). Find the
  newest log entry by its heading. Never `cat` a spec-queue file or `FINDINGS.md`.
- **Keep STATE small.** Each queue item is `id`, `status`, `title`, optional `model`/`effort`, and a
  `detail` of at most ~600 characters. Results go in the log, never prepended to `detail`. Collapse
  a done item's `detail` to one line.
- **Subagents run in the foreground.** The adversarial REV is spawned with `model: "opus"`;
  Explore runs on Sonnet (`.claude/agents/Explore.md`). A background subagent from a headless run is
  waited for at most 60 minutes, then killed.
- **Close-out:** the window's final log entry includes
  `py -3.11 .claude/loops/usage_report.py --windows --since <today>` output for this window.

---

## Iteration 1 — compose the queue

Only the first firing of the window does this.

0. **Read the backlog page first — `spec-queue/BACKLOG.html`.** One command, before anything
   else in this iteration:

   ```bash
   py -3.11 scripts/backlog_page.py --check
   ```

   Non-zero means the ledger has moved since the page was built; run it without `--check` to
   refresh, and read the `SINCE LAST GENERATION` block it prints. That block is the cheapest
   orientation there is: what is open by severity, **where each item came from** (found by driving,
   found by reading code, or asked for by the operator), **whether it is ready** for anyone to pick
   up, the drain, and what each window is holding. Reading it costs one tool call and stops the two
   failures this loop keeps having — filing something already filed, and queueing a finding that
   has no proposal and therefore cannot be built.

   **Never `cat` the HTML.** It is 300 KB and reading it burns the context this iteration needs.
   The printed report is the interface; the page is for the operator's browser.

1. **Confirm the branch.** `git branch --show-current` must match `STATE-night.json`'s `branch` —
   the driver already checked, but check again against `git log`, and reconcile out loud in the log
   if they disagree. Never cut a branch here; the day window owns that.

2. **Read `spec-queue/APPROVALS.md`**, the newest day section only — **and only if its `## <date>`
   heading is the date this window armed** (the `Armed` line at the top of tonight's log). A section
   is for the night that begins on its date, including an operator redirect written into it after
   23:00. An older section is history: its `ORDER:` and `APPROVED` tokens have usually
   already been built by the night they were written for. Confirm against `git log` (look for its
   change names in `impl`/`archive` commits and in `openspec/changes/archive/`) and treat the night
   as "no section for today". Operator decisions made in session with no daily window running land
   in `spec-queue/DECISIONS.md` (`## Decided`, newest first), not here — read its newest dated
   entries too. Measured 2026-09-15: two compose firings took 09-14's `ORDER:` verbatim and queued
   a proposal round for a change built, driven and archived the night before (`9e140e1`..`a099af2`).
   - **`NOTHING TONIGHT`** → write a log entry saying so, set `next_action` to null, commit, exit.
     The driver unregisters itself on a null `next_action`. Spend no model invocation on work the
     operator has explicitly paused.
   - **`ORDER:`** → that is the queue for tonight, verbatim, and the default below is ignored.
   - Otherwise collect the `APPROVED` rows. `REVISING` and `REJECTED` are not yours to act on.
   - **No section for today, or an empty one** → the operator did not sit down. This is normal and
     needs no special case: the whole window goes to the backlog.

3. **Confirm the tree is green before building on it.** A window that starts on a red suite cannot
   tell its own breakage from the one it inherited, and will spend hours attributing one to the
   other. Run the relevant chunk, not the whole suite — that is **15–47 minutes** depending on what
   else is running (14:39 measured quiet on 2026-09-01, 24:50 contended on 2026-09-03, **46:41 on
   2026-09-08**) and far exceeds the 600s command cap, so background it and block on the output
   file. If it is red and you did not break it, **that is tonight's first queue item** — fix the
   inherited breakage before adding to it, and say so in the log.

   **And read CI's verdict for the sha you inherited, in the same step.** The local suite is not the
   signal that decides whether anything you build tonight can ever land: the day window's merge gate
   opens only on a CI `success` for an exact sha, so a branch CI cannot pass is a branch that does
   not merge, however green this machine is. One call, no waiting — you are reading a conclusion
   that already exists, never blocking on one that does not:

   ```
   gh run list --branch <branch> --limit 20 --json headSha,conclusion,workflowName,createdAt
   ```

   **Record the verdict for your inherited sha in the log's first entry, every night**, in one line,
   including when it is `success` or absent. Then:

   - **Red, whatever the signature** — triage it the way you would triage a red local suite: it is
     tonight's first queue item. **That includes F292 (`database is locked`) and F314 (`bound to a
     different event loop`).** This file used to let the night name those two and carry on
     building. Both are fixed (F292 `b630252`, F314 `416f6e8`), so either signature now is a
     regression of a closed finding, not a known flake, and waving it through would hide exactly
     that (operator, 2026-09-22). Do not re-run it here; find why it came back.
   - **Red for more than three consecutive shas** — say so explicitly and in those words. This is
     the case the loop has no other way to see. Measured 2026-09-19/20: CI was red for **16
     consecutive runs across 20 hours and 14 pushes**, every one of them F292 alone, while the local
     suite stayed green throughout and the night window built nine commits onto it. Nothing noticed,
     because nothing was looking. A streak is a fact about whether the week's work can land, and it
     belongs in front of the operator the next morning, not in a gate that may never run.
   - **No run for that sha at all** — say so. It is not a pass and it is not a failure.
   - **`in_progress` for more than 60 minutes** — that run is **hung**, not pending (F394). A normal
     `ci.yml` run concludes in 13-20 minutes; F394 measured three `master` runs sitting
     `in_progress` for 5-6 hours until GitHub's job timeout killed them, and a window reading "no
     conclusion yet" waited on them as if they had just started. Compute the age from the run's
     `createdAt`, write **`HUNG`** with the run id and its age in the log, and treat it as red with
     an unknown signature — triage it, do not wait on it. (`3491580` added a per-test
     `--timeout=300`, so a wedged test should now fail in minutes; a run still hung past 60 minutes
     is wedged outside a test, which is exactly the case nothing else will report.)

4. **Write the queue**, in this order unless `ORDER:` says otherwise. Backlog first, decided
   2026-09-01; the rejected alternative was approved-first, which would let 8 unarchived changes and
   173 findings rot while the loop shipped new ideas.

   1. **Unarchived changes that are implemented and only need archiving.** Cheapest work in the
      repository. Read `openspec/changes/a-conflict-refusal-names-what-clears-it`'s task 6.4a
      **first**: it must not be archived before `a-loop-declares-whether-it-needs-evidence` is. That
      ordering constraint is real, and archiving out of order is not trivially reversible.

      **Archiving a change retires the findings it fixes, in the same commit.** For every `F<n>` the
      change's `proposal.md` names, set that section's `**Status:**` line in
      `scripts/drive/FINDINGS.md` to `fixed <sha>`, and correct the index paragraph's open
      severity-A list. This is not optional tidying — it is the step whose absence makes source 2
      below unusable. Measured 2026-09-03: 145 of the ledger's 280 entries carry no status at all,
      and the summary has twice been provably wrong about what is open (it read "one" for a week
      while F188 sat in it, and carried F12 as open years after `5237ec5` fixed it). A backlog that
      cannot say what is done is read as a backlog of everything.
   2. **Open findings from `scripts/drive/FINDINGS.md`,** severity A before B before C. A finding
      with no proposal needs the day window first — queue it as a note to tomorrow, not as work.
   3. **`APPROVED` rows**, via `openspec-apply-change`.

   Size each item to finish inside one firing. If an item ends without a commit, it was too big;
   split it in the log so the next firing inherits the split.

---

## Implementing

`openspec-apply-change` is the method. Beyond it, the things that have cost this repository real
time:

- **A green suite agrees with broken behaviour more often than you expect.** Mutation-check anything
  you claim: delete the line the test exists for, and watch a **named** test fail. If nothing fails,
  the test was asserting over nothing.
- **Never mark a task complete on the strength of a plan existing.** This matters more when nobody
  is checking, not less.
- **F392 rule 1 — a full-suite task carries its count inline, or it is not ticked.** Any task that
  runs `pytest hub/tests/` or `pytest tests/` in full (typically a "what must not move" group's
  6.x) is ticked `[x]` only with the actual result written **into that task line in `tasks.md`**:
  passed / failed / skipped / errors and the wall-clock duration, e.g. *"4474 passed, 86 skipped,
  47:37"*. A pointer — *"see the log"*, *"recorded in iteration N"* — does not count. Measured
  2026-09-20 (F392): a 6.2 ticked *"recorded in the log rather than here"* cited a log entry that
  was never written, while three tests in a sibling change's guard file were red. If the run has not
  finished, the task stays `[ ]` and the log says it is still running.
- **F392 rule 2 — a change's regression set is the union of every open change's guard files.**
  Before starting a change and again before closing it, list the guard/regression test files named
  by **every** unarchived change under `openspec/changes/` (grep each `tasks.md` for
  `hub/tests/test_*.py` and `tests/test_*.py` in its "what must not move" or regression group), and
  run that union — not only the files your own change names. Record the file list and the counts in
  the log. Measured 2026-09-20 (F392): `a-loop-staffs-the-agent-it-names` task 3.3 broke three cases
  in `test_a_task_nothing_will_move_holds_nobody.py`, a guard file named only by a *sibling* change,
  and no artifact of the change that broke it mentioned that file anywhere.
- Adding a database column: field in `hub/hub/db/models.py`, a migration that **guards for a missing
  table** (as `0033`/`0034` do, because upgrades from an early revision reach it with only that
  revision's tables), bump the head assertions in **both** `hub/tests/test_migrations.py` and
  `hub/tests/test_project_persistence.py`, then the Pydantic schema if the UI needs it.
- `hub/hub/mcp_server.py` is spawned standalone and may import **only stdlib + fastmcp**.
  `approve_tool_call` has **no return annotation** and must not gain one — FastMCP would derive
  `structuredContent` from it and silently defeat an `allow`.
- UI: commit `hub/ui/src` and `hub/hub/static/ui` together, via
  `py -3.11 scripts/refresh_ui_bundle.py` after `npm run build`. Only that script writes the stamp.
- Tests under `py -3.11`, never bare `python` — bare `python` is a venv that yields three phantom
  `pty_runner` failures on a green tree. `black --target-version py311`.
- Lint exactly what CI lints: `ruff check src/ hub/ tests/`,
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`.
- **Run the CLI suite, `py -3.11 -m pytest tests/ -q`, before every commit — including commits that
  touch only `hub/` or only `openspec/`.** It takes about a minute. It is not the "CLI's" suite in
  the sense of guarding only `src/`: it imports `hub.config` (`test_hub_commands.py`) and it reads
  every in-flight `openspec/changes/*/tasks.md` (`test_openspec_task_evidence.py`), so a Hub change
  or a tasks.md edit can break it. Measured 2026-09-22 night: the window ran only `hub/tests/` for
  16 iterations while `tests/` was red, first on a `hub.config` import and then on a tasks.md line
  quoting an old `3 failed` probe count. Record its count in the log next to the Hub counts.
- **A change whose last group is done is archived in the same firing** (see compose step 4.1).
  Leaving a finished change in `openspec/changes/` keeps its `tasks.md` under the CLI suite's
  in-flight checks, and a stale header there misleads the next reader.

---

## Driving

**Three rounds are not a substitute for driving it.** Rounds check the argument; a drive checks the
product. On 2026-08-28 all three rounds read the code and none thought to ask what the HTTP route
*returns* when the function it calls raises; the first live drive found it in one request.

Every change this window implements gets driven before its queue item is closed.

**A UI change is driven in a browser against the served bundle, or it is not driven.** No exception,
and in particular a transcription of the component into another language is not a drive. This rule
is here because `a-turn-says-how-it-ended` was verified in phases 6 and 7 against `aturn_model.py`,
a Python transcription of the React component, and passed 29/29 — then the next morning's drive
loaded the real bundle in Chromium and found **F274** in a single session: the very symptom F190 was
filed for, still live, against the change that closed F190. A transcription can only confirm what
the person who wrote it already believed, so it cannot find a defect that lives in the gap between
the transcription and the component. Rebuild the bundle, restart the drive Hub from the
implementing code, and look at the page. `scripts/drive/d1_aturn_browser.py` is the working pattern.

- Restart the drive Hub from the implementing code first, and confirm no `.py` under `hub/hub` or
  `src` is newer than the process start time. A stale build is the most expensive failure mode
  there is: the window attributes its behaviour to code it just wrote.
- **The drive port is chosen each night, not fixed.** Pick one only after
  `netstat -ano | grep LISTENING` shows it free — on 2026-09-10 both 8011 and 8012 were already
  listening. **Never 8000** (the operator's real usage) **and never 8010** (the trial Hub). Record
  the port you chose in the log; every later step that talks to the drive Hub uses that port.
- **The drive database is a fresh per-night profile**, `profiles/drive<MMDD>/agentweave.db`
  (e.g. `drive0912`); the launch creates the directory and migrates it (`init_db`,
  `hub/hub/db/engine.py`). Do not reuse another night's profile, and do not point at `beta`: that
  profile was deleted on 2026-09-07, with the others CLAUDE.md lists.
- **Name the operator key on the first launch.** A source launch writes no `bootstrap-key.txt`. It
  mints a random credential into the database unless `AW_BOOTSTRAP_API_KEY` is set, so set it, to
  `aw_live_` plus 32 hex characters, and keep it for the night.
  ```
  cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/drive<MMDD>/agentweave.db" \
    AW_BOOTSTRAP_API_KEY="aw_live_<32 hex>" \
    py -3.11 -m uvicorn hub.main:app --port <drive port> --host 127.0.0.1
  ```
  From `hub/`, from source. **Never `agentweave --port`**: the console script's bundled migrations
  lag this checkout and it dies with `Can't locate revision identified by '00NN'`.
- **Export `AW_HUB` before any `scripts/drive/` harness runs.** `aw.py` defaults it to
  `http://127.0.0.1:8010`, which is the trial Hub, not the drive Hub. Set
  `AW_HUB=http://127.0.0.1:<drive port>` and `AW_KEY=<that key>` explicitly on every run.
- **8010 is the other trial Hub. 8000 is the operator's real usage — never touch it, never probe it,
  never start anything on it.**
- Reuse the harnesses in `scripts/drive/`; several already exist per area. `scripts/drive/aw.py` is
  what they all use.
- **Never drive against `proj-5e960453` or `proj-18e5d4e0`.** Fresh project every drive.
- Every real agent turn binds **Haiku** (`claude-haiku-4-5`). Standing directive, no budget gate.
- **Never leave a job enabled.**
- Record the result in `scripts/drive/FINDINGS.md`. When a drive **disproves** part of a finding,
  say so there — the ledger being wrong in one place is itself worth recording.

---

## Ending the window

At `stop_at`, or when the queue empties, write a final log entry that makes the morning easy:

- **What changed** — commits, marking which carry product code and which are only documentation, so
  the operator knows what to review closely versus skim.
- **What was proven, with evidence** — and separately, what was inferred. Distinguish what you drove
  from what you only tested.
- **What is open** — findings, with enough detail to act on.
- **Decisions waiting for the operator** — the section they read first.
- **What to distrust** — where you tested your own work, what you could not verify, where the run
  was contaminated.

Then set `next_action` to null so the driver unregisters itself rather than spending another
invocation.

---

## Limits

- **Stay on the cycle branch.** No commits, merges or rebases onto `master`. **Never auto-merge** —
  merging is the operator's decision, made awake. Push every iteration.
- **Nothing outward-facing.** No publish, no release, no PR or issue creation, no force-push, no
  history rewriting. **Push, do not open PRs.**
- **Nothing destructive.** No deleting projects, databases, or kept reproductions.
- **Do not browse the open web.** Nothing in this window's work needs it.
- **Every claim is measured or labelled unverified.**
- **Recording that something is wrong is not fixing it.** If a firing establishes that a file,
  figure or instruction in this repository is wrong and does not repair it in that firing, it goes
  into the queue as an item — not only into a log entry, a `DECISIONS.md` row, or a paragraph of
  prose. This window is good at noticing and has been poor at converting: both playbooks carried a
  Hub-suite figure that `spec-queue/DECISIONS.md` had already recorded as wrong, in writing, for two
  days, while the window went on sizing its work against it. A note nobody is scheduled to act on is
  indistinguishable from not having noticed.
- **Decisions that are genuinely the operator's get an `OPEN` row in `spec-queue/DECISIONS.md`, with
  only that row's id in `decisions_for_user`** — never guessed, and never free text (F305: one
  channel, `DECISIONS.md` is the authority; day-window.md's iteration 1 step 3 is where an inherited
  id gets dropped once its row stops reading `OPEN`).
- Stage explicit paths, never `git add -A`. Never commit `kimichanges.md` or `kimiwork.md`.
- `.agentweave/` and `spec/` at the repository root belong to the migration and are not stray test
  output — do not delete them as cleanup.
