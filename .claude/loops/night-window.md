# The night window — FIX, 23:00 to 07:00

**You are a fresh process with no memory.** Everything you need is on disk. Read
`.claude/autonomous/STATE-night.json` for position and the newest entry at the **bottom** of
`.claude/autonomous/<date>-night-log.md` for context, then do exactly the one thing `next_action`
names, then rewrite the state and commit and push. One unit per firing. Never end an iteration with
a dirty tree.

This window **fixes**: it implements and drives. It does not write new proposals — the day window
already took them through three rounds. If a change you are implementing turns out to be wrong,
**stop implementing it**, record why in `decisions_for_user`, and move to the next queue item. A
proposal that survives three rounds and then fails contact with the code is exactly the finding this
whole arrangement exists to surface; do not paper over it at 03:00.

Map, tasks, state layout and the cycle-branch rule: `.claude/loops/README.md`.
File contract: `spec-queue/README.md`. Design and rejected alternatives:
`openspec/explorations/2026-09-01-a-daily-research-spec-and-build-loop.md`.

---

## Iteration 1 — compose the queue

Only the first firing of the window does this.

1. **Confirm the branch.** `git branch --show-current` must match `STATE-night.json`'s `branch` —
   the driver already checked, but check again against `git log`, and reconcile out loud in the log
   if they disagree. Never cut a branch here; the day window owns that.

2. **Read `spec-queue/APPROVALS.md`**, the newest day section only.
   - **`NOTHING TONIGHT`** → write a log entry saying so, set `next_action` to null, commit, exit.
     The driver unregisters itself on a null `next_action`. Spend no model invocation on work the
     operator has explicitly paused.
   - **`ORDER:`** → that is the queue for tonight, verbatim, and the default below is ignored.
   - Otherwise collect the `APPROVED` rows. `REVISING` and `REJECTED` are not yours to act on.
   - **No section for today, or an empty one** → the operator did not sit down. This is normal and
     needs no special case: the whole window goes to the backlog.

3. **Confirm the tree is green before building on it.** A window that starts on a red suite cannot
   tell its own breakage from the one it inherited, and will spend hours attributing one to the
   other. Run the relevant chunk, not the whole suite — that is **15–25 minutes** depending on what
   else is running (14:39 measured quiet on 2026-09-01, 24:50 measured contended on 2026-09-03) and
   exceeds the 600s command cap. If it is red and you did not break it, **that is tonight's first
   queue item** — fix the inherited breakage before adding to it, and say so in the log.

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
the transcription and the component. Rebuild the bundle, restart 8011 from the implementing code,
and look at the page. `scripts/drive/d1_aturn_browser.py` is the working pattern.

- Restart the drive Hub on **8011** from the implementing code first, and confirm no `.py` under
  `hub/hub` or `src` is newer than the process start time. A stale build is the most expensive
  failure mode there is: the window attributes its behaviour to code it just wrote.
  ```
  cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db" \
    py -3.11 -m uvicorn hub.main:app --port 8011 --host 127.0.0.1
  ```
  From `hub/`, from source. **Never `agentweave --port`** — the console script's bundled migrations
  lag this checkout and it dies with `Can't locate revision identified by '00NN'`.
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
- **Decisions that are genuinely the operator's go to `decisions_for_user`, not guessed.**
- Stage explicit paths, never `git add -A`. Never commit `kimichanges.md` or `kimiwork.md`.
- `.agentweave/` and `spec/` at the repository root belong to the migration and are not stray test
  output — do not delete them as cleanup.
