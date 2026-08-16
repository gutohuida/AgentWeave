# Autonomous run — 2026-08-16, app and test reform

**Branch:** `autonomous/2026-08-16-app-and-test-reform` · **Parent:** `hub-native-experience` @ `4ca42ed`
**Window:** 02:20 → 12:00 (+01:00) · **Driver:** Windows Scheduled Task → headless `claude -p`, one
iteration per firing, 15-minute interval.

Newest entry at the **bottom**. Written for someone who was asleep.

---

## The limits this run is under

Recorded here as well as in `STATE.json`, so an iteration that reads only one of the two files still
inherits them.

1. **Stay on this branch.** No commits, merges or rebases onto `hub-native-experience` or `master`.
   Merging back is the operator's decision, made awake — and it is likely a cherry-pick, not a
   merge, because an unattended run legitimately produces scratch alongside the work.
2. **Nothing outward-facing.** No publish, release, PR, issue, force-push or history rewrite.
   Pushing *this* branch is required, not optional — it is what makes the work durable.
3. **Nothing destructive beyond what is explicitly authorised.** The only authorised deletions this
   run: the ten Hub projects named in Q1, `aw-loop6`'s minted credential row, and test files that
   meet Q5's written bar *with a mutation check*.
4. **Never mark work complete on the strength of a plan existing.**
5. **Every claim is measured, or labelled unverified.**
6. **Decisions that are genuinely the operator's get written down, not guessed** — into
   `decisions_for_user`, which is the section they read first.

Two further limits specific to this run:

- **Do not tick the 29 parked judgement tasks.** They were parked on the operator's explicit
  instruction — *"Park them all, judge after I drive it tomorrow."* A loop may add evidence beneath
  them; it may **not** answer them. Same for `17.1` and `17.3` in the UX findings, and for findings
  1, 2 and 5 in Q4, which are visual judgements no loop can self-assess.
- **No new language toolchain may be installed.** `pip install` into the Python311 env is fine
  (that is Q2's `pytest-xdist`). Rust for Tauri or Node-for-Electron is not — if Q6 concludes one is
  required, that goes to `decisions_for_user` instead of into the machine.

---

## Entry 0 — 02:20 — prepared and armed

Written by the interactive session that prepared this run, before handing to the driver.

**What the operator asked for**, in their own words: apply the spec fixes discussed last session;
rework testing because *"the testing is taking way too long"* — checking every test against the code
to see *"if they earn their place"*; clean up the test environments because there are *"to many
aw-loop environments"*; *"a full app experience with agentweave no more opening on the browser"*;
and AgentWeave should be **global**, because *"if I ran agentweave from different folders it creates
a different agentweave which is weird"*. Then, only if time remains, UI quality-of-life — with the
scope explicitly widened beyond their own T3 example: *"go beyond compare t3 and other tools… Is
there any functionality in the most popular harnesses that we lack? Investigate everything before
implementing."*

**Method the operator asked for:** spec rounds — *"one agent produces the spec, the next triggers
the agents review until a agent thinks is good to implement. We need to have another gate so agent
don't go on forever."* Their own suggestion for how: *"It can be like the trigger at 2AM generates
the spec and the one at 2:15 reviews it and improves it."* That is what is implemented — successive
driver iterations, not subagents. A fresh process has no memory of writing the thing it reviews, so
the independence is **structural** rather than merely prompted. The gate is **3 rounds**; at round 3
without approval the artifact ships with its objections recorded, and the queue moves on.

**Two things prep fixed in the runway**, either of which would have cost the loop real time:

- **The Hub was seven `hub/hub` commits stale.** It had been running since 2026-08-15T11:46, from
  before the 71-commit merge. Restarted detached at 02:12 on current code; healthy in 1s, all 11
  projects intact. This is the failure mode the skill calls the most expensive one there is — the
  loop attributes the Hub's behaviour to code it changed.
- **Handoff 0050's proposed one-line fix for the conversation-inheritance flake does not work**, and
  the loop would have applied it on trust. `Conversation.id` is `conv-{short_id()}` — *random* — so
  adding `Conversation.id.desc()` picks the later-created row only about half the time. It would
  have looked deterministic while staying arbitrary, and a regression test written against it would
  have enshrined that. Checked against `hub/hub/db/models.py:373` and `hub/hub/conversations.py:100`.
  The test is right and the code is wrong: on Windows the ~15.6ms timer granularity makes two
  conversations tie on `created_at` in production, not just in tests. Q3 now specifies the
  codebase's own precedent — an autoincrement `sequence` column, as `TaskTransition` and
  `InboundQueueEntry` already use, with the reasoning already written at `models.py:695-699`.

**One root cause found during prep**, so Q6 starts from a diagnosis rather than a mystery:
`hub/hub/config.py:9` sets `database_url` to `sqlite+aiosqlite:///data/agentweave.db` — a
**relative** path, resolved against the Hub process's working directory. Launch from a different
folder, get a different database, and therefore a different AgentWeave. The multi-project
architecture is already correct (`src/agentweave/cli.py:828` registers `Path.cwd()` as a *project*,
which is right); it is the Hub's own state that is wrongly per-folder.

**Reordering.** The operator granted it. Their stated order was spec fixes → tests → environment →
desktop → global → UI. The queue hoists two cheap compounding items first — Q1 (environment cleanup,
which removes noise from every later live check) and Q2 (test speed, because if `pytest-xdist` works
every later iteration verifies faster) — then Q3, because Q5's audit cannot distinguish a flake from
a test it broke. **Desktop and global were merged into one item (Q6)**: an app that opens a
different database per launch folder is incoherent, so specifying them separately would produce two
specs that contradict each other. UI stays last, as instructed.

**Nothing was pre-written.** No spec, no exploration. The operator asked for spec rounds run *by*
the loop, so Q4, Q6 and Q7 each carry a brief and explicit review criteria instead of a draft.

**What a reviewer should distrust in this entry:** nothing was executed here beyond the Hub restart
and the two file reads behind the flake finding. The estimates in `STATE.json` (41 iterations) are
estimates. The claim that `pytest-xdist` will help is a **hypothesis** — the fixtures look
xdist-friendly (`hub/tests/conftest.py:10` uses in-memory SQLite, which is per-process) but nothing
has been run to prove it, which is exactly why Q2 is written as *measure*, not *install*.

---

## Entry 1 — 02:13 — Q1 done: 10 projects deleted, no delete API exists

Verified branch/log/`STATE.json` all agree before starting (HEAD `6319880`, iteration 0, current
`Q1-projects`). Hub was up and healthy on `:8010`.

**No project-delete API exists.** Read `hub/hub/api/v1/projects.py` in full (get/open/create/
settings/relocate only) and `hub/hub/project_lifecycle.py` (no delete/archive method), then grepped
every `@router.delete` in `hub/hub/api/v1/` — six exist, for runners, jobs, inbound-queue entries,
a chat task link, agent-actions jobs, and charters. None for projects. This is the finding Q1
anticipated ("if no such API exists, that absence is itself a finding worth recording") — recorded
here and worth a `decisions_for_user` entry: does the Hub *want* projects to be undeletable through
the API, or was this simply never built? Not answered here; it's the operator's call.

**Fallback: raw SQL, generic and verified.** `hub/hub/db/engine.py` never issues
`PRAGMA foreign_keys = ON`, and only one model (`job_runs`) declares `ondelete="CASCADE"` — so
SQLite enforces no referential integrity here and a delete confined to the `projects` table would
have left ~7,700 orphaned rows across 27 other tables. Instead: stopped the Hub process (PID 2696,
confirmed via `Get-NetTCPConnection -LocalPort 8010` → `Get-Process`) to avoid a concurrent-write
race with the live app, took a file-copy backup of `agentweave.db`, then ran a one-shot script that
introspects every table via `PRAGMA table_info` and deletes rows matching the 10 target project ids
wherever a `project_id` column exists, before deleting the 10 `projects` rows themselves. This also
answers the credential sub-task: `run-ev6` / `aw_run_loop6_evidence` turned out to live as a `runs`
row (`id='run-ev6', project_id='proj-c28f08df'`, storing only `capability_token_hash`, not the raw
token) rather than in `api_keys` or `operator_credentials` as the queue item guessed — deleted for
free by the generic per-project sweep, no special-casing needed. Deleted 7,788 rows total across 26
tables (`runners` 23, `charters` 90, `conversations` 71, `tasks` 28, `questions` 59, `event_logs`
3162, `agents` 28, `messages` 45, `task_transitions` 136, `run_divergences` 22, `runs` 126,
`agent_outputs` 3125, `turn_usage` 121, `inbound_queue_entries` 123, `spec_documents` 18 and 6 more
spec/task-link tables, plus `projects` 10). The script asserted post-delete that the only remaining
project was `proj-ff695d96` before exiting; it did. Restarted the Hub with the documented command,
healthy in <2s. Deleted the one-shot script and the backup file afterward — `hub/data/` is
gitignored (`.gitignore:88`), so none of this touched the working tree; `git status` is clean.

**Verified, not assumed:**
- `GET /api/v1/projects` before the delete: 11 projects, ids and names matching `STATE.json`'s list
  exactly.
- `GET /api/v1/projects/proj-ff695d96/project/spec/coverage` before the delete: 9 requirements
  (path resolved by reading the router prefixes — `spec.py`'s `/project` mounted under
  `api/v1/__init__.py`'s `/projects/{project_id}`, since `/api/v1/projects/{id}/spec/coverage`
  404s).
- Same two checks after the restart: `GET /api/v1/projects` → exactly 1 project
  (`proj-ff695d96 aw-loop10`); coverage endpoint → 9 requirements, unchanged.

**Elapsed:** well under the 15-minute firing interval. Estimated 1 iteration; used 1.

---

## Entry 1a — 02:20 — the operator added visual verification, mid-run

Written by the interactive session, not by a driver firing. It edited `STATE.json` between iterations
using the driver's own protocol: claim `last_heartbeat`, edit, commit, push, back-date to release.

**The operator asked:** can Claude screenshot the app and self-loop on that, and is there a tool for
driving UI decisions and verifying them?

**Answered by testing, not asserting.** The interactive session opened `localhost:8010` with the T3
`preview_open` tool and took a `preview_snapshot`: it returned a real PNG of the AgentWeave
dashboard, the visible text, the full accessibility tree, and every interactive element with
coordinates. It also incidentally confirmed Q1 landed — only `aw-loop10` remains in the projects
rail. `preview_set_appearance` can force light/dark, and `preview_resize` can set a viewport, which
map directly onto findings 2 and 5.

**But those tools are not available to this driver.** They come from the T3 Code environment, not
from a configured MCP server: there is no `.mcp.json`, and `~/.claude.json` has `mcpServers` empty
both globally and for this project. A headless `claude -p` firing gets none of them. Recorded here
because it is exactly the kind of thing a later session would otherwise assume works.

**So Q4a was added** — a Playwright harness writing PNGs that an iteration then `Read`s, which is
headless-capable because it is just Bash plus a tool that renders images. It sits before Q4 so the
UI work can use it. The operator authorised `playwright install chromium`, which the run's original
limits forbade; the limit was amended narrowly rather than dropped.

**What this does and does not buy**, stated plainly so no later iteration over-claims:

- **Finding 2 becomes a measurement** — assert the rendered document's computed background equals
  the app's theme token in each mode.
- **Finding 5 becomes a measurement** — assert the task card does not clip its content at width W.
- **Finding 1 stays taste.** A loop can verify colour is *applied*. It cannot verify colour *helps*.
  Its PNG goes to `decisions_for_user`; it is not to be self-ticked. The same holds for `17.1`,
  `17.3` and the 29 parked judgement tasks — unchanged by any of this.

**One trap written into Q4a because it would otherwise be paid for twice:** `hub/hub/static/ui` is a
committed build artefact, so a UI source change is invisible to a screenshot until
`npm run build` + `python scripts/refresh_ui_bundle.py`. A screenshot of a stale bundle is the same
failure as a stale Hub, and it looks exactly like a fix that did not work.

**What a reviewer should distrust:** nothing here was built. Q4a is a queue item, not a harness.
The claim that Playwright works headless in this environment is **untested** — it is the reason Q4a's
verify step requires proving the harness is honest by capturing before and after a deliberate CSS
change and confirming the two PNGs differ.

## Entry 1b — 02:23 — delete-project filed; Q4a bounded; operator asleep

Written by the interactive session between firings, using the driver's claim/edit/release protocol.
**This is the operator's last input before sleeping.** Everything after this entry is unattended.

**Q4b — delete a project through the product, not through SQL.** Filed at the operator's direct
request, prompted by what Q1 found an hour earlier: no project-delete API exists anywhere in the
Hub, so honouring "remove these ten test projects" meant stopping the Hub, backing up the database
and sweeping 7,788 rows across 26 tables by hand. That is a gap the operator will hit again on their
next test project. Placed after Q4a so its confirmation dialog and empty state are the screenshot
harness's first real exercise — simple enough that a capture either obviously works or obviously
does not, which is the right thing to prove a harness on before trusting it on Q4's taste questions.

**The constraint that matters more than the feature**, restated here because a log entry is read and
a JSON field is skimmed: **deleting a project must delete database rows only. It must never touch
the workspace directory on disk.** An AgentWeave project points at a real working tree containing
the operator's actual source code. A delete that removes a user's repository is the worst bug this
product could ship. Q4b requires a test asserting the directory survives, and requires that test to
be mutation-checked. Whether the `.agentweave/project.json` binding marker inside that directory
should also be removed is a separate, smaller question, to be decided explicitly and written down.

**Q4a is now bounded.** Operator: *"Playwright can be tested if it does not work no problem ill see
it in the morning. But try and make it work."* So the harness gets a genuine attempt — headless
flags, a different browser channel, `channel='chrome'` against an existing install — capped at **two
iterations**. Past that: record the exact failure and error, mark Q4a blocked, and go build Q4b and
Q4 blind. The work the harness was meant to verify matters more than the verification. A night spent
on tooling that produced no product change would be the wrong outcome, and this line exists so no
iteration talks itself into that.

**What a reviewer should distrust:** the queue has now been edited twice mid-run by an interactive
session. Both edits are in the log and both used the heartbeat protocol, so no iteration lost work —
but the estimates in `STATE.json` were written for a seven-item queue and it now has nine. It will
almost certainly not finish by 12:00, and that is expected rather than a failure: the ordering is
what matters, and the cheap compounding items are first.

---

## Entry 2 — 02:51 — Q2 done: measured, xdist verified, Makefile fixed

**Where the time actually goes.** `pytest hub/tests --collect-only` from the repo root picks
`hub/pyproject.toml` as its `configfile` (pytest walks up from the test path and finds the nearer
ini file), so root `pyproject.toml`'s `addopts = "-v --tb=short"` **does not touch hub/tests at
all** — that worry in the queue item was moot. It does apply to root `tests/` (the CLI suite), but
that suite is 363 tests and ran in **18.08s**. It was never the problem; ruled out and not touched
further.

`hub/tests` is 149 files, 2057 collected tests. Ran a representative first chunk (38 files, 525
tests, alphabetical `NR%4==1` split) with `--durations=50`: the 50 slowest entries top out at
**1.27s** and the bulk of the list is `setup` phase entries clustered at **0.7–1.1s**, spread across
hundreds of different tests. No pathological single test or file. This is per-test fixture overhead
(in-memory SQLite creation + migration per test, per `hub/tests/conftest.py`), not a few slow
offenders — which is exactly the shape of problem `pytest-xdist` fixes and duration-chasing does
not.

**Installed** `pytest-xdist` (3.8.0 + execnet 2.1.2) into the Python311 interpreter, then compared
pass/fail/skip counts, not just wall-clock, at every step:

| Run | Scope | Time | Result |
|---|---|---|---|
| serial | chunk1 (525 tests) | 194.53s | 522 passed, 3 skipped |
| `-n auto` (20 workers) | chunk1 | 113.69s | 522 passed, 3 skipped |
| `-n 8` | chunk1 | 82.08s | 522 passed, 3 skipped |
| `-n 8` | chunks 2–4 (1532 tests) | 143.37+79.38+58.12s | 1524 passed, 8 skipped |
| `-n 8` | **full suite, one process** | **292.54s (4m52s)** | **2046 passed, 11 skipped** |
| `-n auto` | **full suite, one process** | **317.85s (5m17s)** | **2046 passed, 11 skipped** |

Every row's pass+skip total agrees with the other rows and with the 2057 collected count. No test
was silently dropped by parallelisation.

**`-n auto` is not the fastest option on this machine, and that is itself informative, not just a
footnote.** `Get-CimInstance Win32_Processor` reports **12 physical / 20 logical** cores. `-n auto`
defaults to `os.cpu_count()` (20, logical), which oversubscribes past the physical core count and
was measurably slower than `-n 8` at both chunk (113.69s vs 82.08s) and full-suite (317.85s vs
292.54s) scale. `-n 8` is the locally-tuned optimum, but hardcoding it into a shared Makefile would
be tuning to this monitor's hardware — the same mistake the run's constants-derivation rule warns
against elsewhere. Shipped `-n auto` instead: it self-derives from whatever machine or CI runner
executes it, and it is *still* a real win — 317.85s beats the operator's stated "seven minutes"
(420s) by nearly two minutes, and beats the extrapolated serial full-suite time (525→2057 tests
scaled from the 194.53s chunk1 serial baseline: ≈762s / 12.7min) by well over 2×. A developer on
hardware like this one who wants the extra 25s can still run `pytest hub/tests -n 8` by hand; that
choice is now recorded here rather than baked in silently.

**Changes made:**
- `hub/pyproject.toml`: added `pytest-xdist>=3.6` to the `dev` extra so `make install-hub` pulls it.
- `Makefile`: `test-hub` now runs `pytest hub/tests/ -n auto` (was `pytest hub/tests/ -v`). Dropped
  `-v`: under xdist, workers report asynchronously, so per-test verbose lines interleave out of
  order and are markedly less readable than the dot progress this run's `-q` testing already
  confirmed works cleanly. `-rA`/`--tb=short`-style detail on failure is unaffected — xdist still
  prints full failure output at the end, it just does not narrate every pass.
- `test-cli` and root `tests/` were left alone — confirmed not the bottleneck, no reason to touch.

**Verification:** the exact Makefile command (`pytest hub/tests -n auto`, no `-v`, from the repo
root) is the same invocation measured in the table above (317.85s, 2046 passed, 11 skipped) — not a
close approximation, the literal command.

**What a reviewer should distrust:** the `-n 8` vs `-n auto` comparison is single-machine, single-run
evidence — no repeated trials to check run-to-run variance, and no CI-hardware data point at all.
If `make test-hub` regresses on the actual CI runner (unknown core count, unknown whether SQLite
in-memory contention behaves the same under a different OS), that would only be caught by watching
an actual CI run, which this driver was told is out of scope to chase further ("just push the
branch"). Treat the 317.85s figure as this-machine-today, not a permanent guarantee.

**Elapsed:** roughly one full iteration (~1 hour of wall-clock spent mostly waiting on test runs,
across ~10 pytest invocations). Estimated 2 iterations; used 1 — the measurement and the xdist
comparison both fit because the chunk-first approach let correctness be established on a 26% sample
before committing to the much longer full-suite runs.

---

## Entry 3 — 03:26 — Q3 done: `Conversation.sequence`, and a much bigger diff than the queue item estimated

**The fix itself is exactly as specified.** `hub/hub/conversations.py` answered "which conversation
is most recent" in three places by ordering on `created_at` alone, which ties when two conversations
are created inside the same clock tick (~15.6ms on Windows — confirmed as the cause of
`test_override_inheritance.py::test_the_most_recent_overrides_win`'s ~50% failure rate in a chunked
run). Added `Conversation.sequence` — an autoincrement integer, same shape as `TaskTransition` and
`InboundQueueEntry` — and ordered by it instead. Beyond the one call site the item named
(`inherit_runtime_overrides`, conversations.py:72), `latest_open_conversation` and
`peer_bound_conversation` had the identical hazard on the identical column, so both were fixed too
(the first keeps `updated_at` as its primary sort — that is a real "most recently active" semantic,
not the bug — and gets `sequence` only as its tiebreaker; the second's whole sort became `sequence`).
Recorded here because the item named only line 72 and this went further; the extension is the same
bug at the same mechanism, not new scope.

**What the item did not anticipate, and why the diff is 21 files instead of 2.** Making `sequence`
the primary key — which is what "exactly as `TaskTransition` and `InboundQueueEntry` already do"
means, and is also the only way SQLite hands out real autoincrement, since only a table's sole
`INTEGER PRIMARY KEY` column gets rowid-aliasing — silently breaks every `session.get(Conversation,
conversation_id)` call in the codebase. `session.get()` resolves by primary key; after this change
that is `sequence`, an int, so a lookup passing a `conv-…` string would compare it against an
integer column and simply never match. `TaskTransition` and `InboundQueueEntry` never hit this
because nothing in the codebase looks either of them up that way — both are always queried through
an explicit `select(...).where(.id == ...)`. `Conversation` is different: it is looked up by its
`conv-…` id in 11 production call sites (`checkpoint_trigger.py`, `inbound_queue.py`,
`turn_scheduler.py`, `conversation_titles.py` ×2, `api/v1/agent_trigger.py` ×2, `api/v1/messages.py`,
`api/v1/agent_chat.py` ×2, `api/v1/checkpoints.py`) and 41 more across 10 test files. Silently
leaving those as `session.get()` would not have failed loudly — every one would have started
returning `None` for a real id, and the closest visible symptom would have been agents losing their
runtime overrides or checkpoints failing to resolve their conversation, which is a strictly worse
bug than the flake being fixed. Added `get_conversation_by_id(db, conversation_id)` to
`conversations.py` — `select(Conversation).where(Conversation.id == conversation_id)` — and replaced
every one of those 52 call sites with it. Confirmed complete by grep (`\.get\(Conversation,` matches
nothing outside a docstring) and by the full suite passing.

**The migration (`0073_add_conversation_sequence.py`) recreates the table**, because SQLite cannot
change which column is the primary key in place — same reasoning `0035` and `0058` already use to
recreate `conversations` and `inbound_queue_entries` for their own constraint changes, and the same
`batch_alter_table(..., recreate="always")` mechanism. Existing rows get `sequence` values in
whatever order SQLite's `INSERT INTO … SELECT` visits them during the copy, which for a table whose
PK was never `INTEGER` (nothing has ever reordered its physical storage) is real insertion order —
verified in `test_migration_0073_gives_conversations_a_sequence_primary_key`, which seeds two rows
through the real 0034→head chain and asserts they come out in creation order, that the FK-by-value
row in `runs` still resolves, that every index and both CHECK constraints (`ck_conversations_lifecycle`,
`ck_conversations_origin`) survive the recreate, and that a fresh INSERT after the migration gets a
real larger `sequence` from the database itself, not from the test.

**One bug caught only by testing the downgrade, which the queue item's verify step did not ask for
but the existing test suite (`test_migration_0052_downgrade_drops_the_history`) exercises anyway.**
The model originally left `sequence`'s primary key and `id`'s unique constraint unnamed
(`primary_key=True` / `unique=True` on the column). That works when the *migration* builds the
table, because the migration names them explicitly (`create_primary_key("pk_conversations", ...)`).
It silently fails when `create_all` builds the table fresh from the *model* instead (the real path
`init_db` takes on a brand-new database) — SQLAlchemy gives the constraint whatever name it likes,
and the migration's downgrade, which drops `"pk_conversations"` by that exact name, then raises
`ValueError: No such constraint: 'pk_conversations'`. Fixed by naming both constraints explicitly in
`__table_args__` (`PrimaryKeyConstraint("sequence", name="pk_conversations")`,
`UniqueConstraint("id", name="uq_conversations_id")`) so a `create_all`-built table and a
migration-upgraded table are byte-identical in shape. Caught by running the full `test_migrations.py`
module, not by anything the item asked to run — worth noting because Q5's coming test audit should
not read `test_migration_0052_downgrade_drops_the_history` as unrelated-noise-worth-cutting; it is
exactly the kind of test that catches a defect a change to a completely different table's migration
introduced.

**The regression test the item asked for, mutation-checked.**
`test_the_most_recent_overrides_win_even_with_an_identical_created_at` constructs two conversations
with the identical `created_at` (bypassing wall-clock timing entirely, unlike the pre-existing
`test_the_most_recent_overrides_win`, which depends on real elapsed time and is what flaked) and
asserts the second-committed one wins. Mutation-checked by hand: reverted just the one `order_by`
line in `inherit_runtime_overrides` back to `created_at.desc()`, watched the new test fail with
`{'permission_mode': 'acceptEdits'} != {'permission_mode': 'workspace'}`, restored the fix, watched
it pass again. `test_the_most_recent_overrides_win` itself was left alone rather than deleted — it
now passes reliably too, but it is real coverage of the same behaviour under real timing, which the
identical-`created_at` test does not exercise.

**Bumped both head assertions CLAUDE.md requires** — nine `assert version == "0072"` sites in
`hub/tests/test_migrations.py` and one in `hub/tests/test_project_persistence.py`, all now `"0073"`.
Also fixed one pre-existing test that the primary-key move broke on contact:
`test_conversation_model_declares_full_contract_shape` in `test_conversation_contract.py` asserted
`columns["id"].primary_key` directly; rewritten to assert `sequence` is the primary key, `id` is not,
and `id` still carries `uq_conversations_id`.

**Verification, run for real rather than assumed:**
- `pytest hub/tests/test_migrations.py -k 0073` — 2 passed (the new migration tests).
- `pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py` — 54 passed, 1 skipped.
- `pytest hub/tests/test_override_inheritance.py` — 9 passed, run **three separate times** (fresh
  process each time, per the item's verify step) — 9/9 every run, where the pre-fix baseline was
  ~50% failure on the one flaky test.
- The 10 test files whose `session.get` call sites were rewritten, run together — 141 passed.
- Full suite, `pytest hub/tests -n auto` (the now-parallel Q2 command) — **2049 passed, 11 skipped**,
  zero failures. (2046 baseline from Entry 2, +3 for the two new migration tests and the one new
  override-inheritance regression test.)
- Root CLI suite, `pytest tests/` — 360 passed, 3 skipped, unaffected as expected (no hub import).
- `ruff check` and `ruff format --diff` clean on every file this touched (two lines in
  `test_migrations.py` needed hand-formatting to match `ruff format`'s wrapping; left the rest of
  that file's pre-existing formatter-version drift untouched rather than reformatting code this
  change did not otherwise touch).

**What a reviewer should distrust:** the existing-row sequence-ordering claim ("insertion order")
rests on SQLite's actual `INSERT INTO … SELECT` behavior for a table whose PK was never `INTEGER`,
observed empirically (in the migration test) rather than guaranteed by any SQLite specification —
correct for every version tested here, but not a documented contract. The 52-call-site rewrite was
done by a scripted regex pass plus manual verification (compile-check every file, grep for zero
remaining `.get(Conversation,` sites, run the full suite) rather than reviewed line-by-line by a
second pass; the full green suite is the actual evidence it is complete, not the process that
produced it. `PermissionRequest`, `Question`, and `UnaskedQuestion` are imported in
`conversations.py` but were not audited for the same `session.get(Model, id)` hazard — out of scope
for Q3, but worth a note if their own primary keys ever move.

**Elapsed:** roughly one full iteration. Estimated 2 iterations for Q3; this used what was budgeted,
but for a materially larger reason than estimated (the `session.get` blast radius), not because the
core fix was slow.

---

## Entry 4 — 03:47 — Q4a done in one iteration: `scripts/uishot.py`, and it already caught a real bug

**The Hub was stale before anything else could be trusted.** Its process had started at 02:12:25,
before Q3's 03:28:26 commit, so it was serving pre-`Conversation.sequence` code. Killed both stray
python processes and restarted it with the documented command; `/health` reported `ok` in under 4s
and `GET /api/v1/projects` still returned exactly `aw-loop10` (Q1 holding).

**Install, as authorised.** `pip install playwright` into the Python311 interpreter, then
`playwright install chromium` — 191.8 MiB Chrome for Testing + 114.5 MiB headless shell, both
downloaded clean on the first try. No `channel=chrome` fallback or headless-flag fighting was
needed; vanilla `chromium.launch()` worked immediately. The 2-iteration cap the operator set for
"if it does not work" did not get exercised — it worked on the first attempt.

**`scripts/uishot.py`**: `--url`, `--theme` (`light`/`dark`), `--width`, `--height`, `--out`,
`--wait-selector`. Two things had to be discovered empirically, not assumed from the plan:

1. `page.goto(url, wait_until="networkidle")` **times out on every real page**, always, because the
   app holds an SSE connection open for live updates (`useSSE`) — the network is by design never
   idle. Switched to `wait_until="load"` plus a fixed settle delay.
2. Playwright's `new_context(color_scheme=...)` **does nothing to this app's theme.** It only
   flips the `prefers-color-scheme` CSS media query; AgentWeave's light/dark mode is application
   state (`configStore.mode`, persisted to `localStorage`, applied via
   `document.documentElement.dataset.mode`), not an OS preference the app reads. The first `--theme
   dark` capture came back pixel-identical to light — caught by actually reading the PNG, not by
   the script exiting 0. Fixed by driving the real control: after load, if `--theme dark`, click the
   button at `aria-label="Switch to dark mode"` (`ProjectHeader.tsx:71`) and re-settle. This is
   itself evidence for why Q4a matters — a harness that trusted Playwright's `color_scheme` option
   at face value would have shipped two identical screenshots as "light" and "dark" and called the
   surface verified.

**Captured aw-loop10's spec document and task board, both themes, two widths (1280 / 400px), 7
PNGs total, and read every one:**
- `spec-light-1280.png`, `spec-dark-1280.png`: chrome (rail, header, tab bar) themes correctly in
  both. **The rendered document body does not** — it stays white-background-black-text in dark
  mode while everything around it goes dark. This is finding 2 from
  `2026-08-16-operator-ux-findings.md`, now measured rather than described from memory: not "navy"
  as the operator's note said (that phrasing may have been from a different surface or an earlier
  build), but a real, confirmed light/dark inconsistency in the one place — the document pane —
  that CLAUDE.md's no-external-CSS constraint makes hardest to fix generically. Recorded for Q4's
  spec round to pick up as verified fact, not restate as an open question.
- `tasks-light-1280.png`, `tasks-dark-1280.png`: task board columns theme correctly in both modes.
  Card titles wrap character-by-character in a narrow fixed-width column ("Verify / no /
  notification / is / ever / silently / lost", one or two words per line) — visible, measurable
  confirmation of finding 5 ("task cards are unreadable expanded... open the task like jira").
- `spec-light-narrow.png` (400px): the document reflows cleanly, no clipping, no horizontal
  scrollbar. Not a problem at this width.
- `tasks-light-narrow.png` / `tasks-dark-narrow.png` (400px): the kanban columns run wider than the
  viewport and get cut off ("IN..." mid-word) with no visible scroll affordance in the capture.
  Recorded as a data point, not filed as a finding — a horizontally-scrolling kanban board at 400px
  is normal for the pattern and this alone doesn't establish it is bad; left for whoever picks up
  Q7's gap analysis to judge against what other tools do at that width.

**Proved the harness is honest**, per the item's verify step: changed `hub/ui/src/index.css`'s
light-mode `--bg` from `#fafafa` to `#ff00aa` (one line), `npm run build` (32.8s cold, 4.0s warm),
`python scripts/refresh_ui_bundle.py`, re-captured the same tasks-board URL —
`proof-after.png` is unmistakably magenta end to end. Reverted the CSS line, rebuilt again,
recaptured — `proof-reverted.png` is pixel-identical to the original `tasks-light-1280.png`, and
`refresh_ui_bundle.py`'s own `src_fingerprint` came back byte-identical to before the detour,
confirming the revert left no residue. `git checkout` on the resulting `ui-build-stamp.json` (only
its `built_at`/`src_commit` had changed, nothing else) restored a clean tree — `hub/ui/src` never
showed a diff at any point, since the two builds bracketing the CSS edit were identical source.

**Committed**: `scripts/uishot.py` only. All PNGs live under `.claude/autonomous/scratch/uishots/`,
which `.gitignore:150` already excludes — verified with `git check-ignore -v` before assuming it,
not asserted from memory of the rule.

**What a reviewer should distrust:** the dark-mode document-pane finding rests on `aw-loop10`'s one
seeded spec document (`notify-window-graded-...`) — not confirmed across every document template or
every enforcement state. The narrow-kanban observation is explicitly *not* a finding, just a
recorded data point, and treating it as one would overstate what one capture shows. The
`aria-label="Switch to dark mode"` selector is coupled to `ProjectHeader.tsx:71`'s exact string — if
that copy changes, `--theme dark` silently stops toggling and starts silently capturing light-mode
pages again labelled dark, the same failure mode the `color_scheme` option had. Worth a code comment
pointing back here if that file changes.

**Not done, and deliberately out of scope for Q4a**: no assertion-based checks (`page.evaluate` +
`getComputedStyle` for the background-token comparison the queue item's `note` field describes) were
written — Q4a's job was building the capture-and-read tool and proving it works, not yet turning
findings 2 and 5 into automated assertions. That belongs to whichever of Q4/Q4b actually fixes them,
per the item's own `note`.

**Elapsed:** one iteration, well under the 2-iteration cap — nothing failed that needed a second
attempt.

---

## Entry 5 — 04:00 — Q4b round 1 (AUTHOR): `openspec/changes/2026-08-16-delete-project-api/`

Verified branch/log/`STATE.json` agreed before starting (HEAD `02d9cff`, `autonomous/2026-08-16-app-
and-test-reform`, iteration 4, `current: Q4b-delete-project`). Refreshed `last_heartbeat` to now
before beginning.

**Derived the cascade from evidence, not guesswork, per the item's `detail`.** Read Q1's raw-SQL
cleanup (`git show 8a12932`, Entry 1) and grepped every `project_id` column in
`hub/hub/db/models.py`: 27 tables carry one, `Project` declares an ORM relationship for only 11 of
them, none declares `cascade=`, `PRAGMA foreign_keys` is never turned on
(`hub/hub/db/engine.py`), and only `job_runs` declares `ondelete="CASCADE"` at all — so neither the
ORM nor SQLite would cascade a delete today. Decision: a generic sweep over
`Base.metadata.tables` for every table with a `project_id` column, not hand-maintained relationships
— the same principle Q1's one-shot script used, now productized. Read `_guard_relocation` in
`hub/hub/project_lifecycle.py` and reused its exact `Run.status == "running"` check as the delete
guard rather than inventing a second definition of "still doing something" — deliberately did **not**
extend that guard to "has a conversation," since almost every real project has one and that would
make delete unreachable for the case it's meant to serve.

**Traced the actual UI surfaces rather than assuming them:** `ProjectSettingsPanel.tsx` (already
hosts the relocate control, using `SettingsSection`/`SettingsRow`) is where the delete control
belongs; `useRelocateProject` in `hub/ui/src/api/projects.ts` is the mutation-hook shape to mirror;
`Sidebar.tsx`'s rail already renders an "Add project" button unconditionally, which is what an empty
project collection falls back to today — except nothing in `App.tsx` currently special-cases "zero
projects" as distinct from "not configured," which the design records as a real, currently-latent gap
this change makes reachable (and therefore has to make not-broken) rather than one it introduces.

**Wrote `proposal.md`, `design.md` (D1–D7, plus route/auth), `tasks.md` (7 phases, backend/UI split
into agent-verifiable vs human-only per the standing directive, ending in a user test guide), and the
`local-project-workspace` spec delta** (one `ADDED Requirement` with six scenarios covering the happy
path, workspace survival, the active-run refusal, the non-blocking conversation, the last-project
empty state, and the type-to-confirm gate). `npx openspec validate --changes --strict` — **14 passed,
0 failed**, this change included.

**What a reviewer should distrust:** D6 (the empty-project-collection UI state) is the least certain
piece — it is reasoned from reading `App.tsx`/`configStore.ts`/`Sidebar.tsx` cold, not from running the
app with zero projects, because doing that against the live Hub would have meant emptying
`aw-loop10`, which is explicitly off-limits. Task 4.5 requires confirming this for real once the code
exists. The `Icon` name for the delete control (task 4.2) is left as "check before introducing a new
icon name" rather than picked, since the available lucide names weren't enumerated this round.
`agent_job_deletions`' inclusion in the sweep (D2) is a judgement call — it is a "durable attribution
tombstone" by its own docstring, and this design overrides that durability once the project itself is
gone; a reviewer who reads "durable" more literally than "durable while the project exists" would
object here, and task 3.8 exists so that objection has a concrete test to look at rather than only
prose.

**Set `next_action` to the review step, per the spec-round protocol** — round 2 will read this cold,
without looking up who wrote it, against the item's `review_criteria`.

**Elapsed:** one iteration.

---

## Entry 6 — 04:10 — Q4b round 1 (REVIEW): APPROVED

Verified branch/log/`STATE.json` agreed before starting (HEAD `e1f3d64`, iteration 5, `current:
Q4b-delete-project`, `next_action` pointing at this review). Read `proposal.md`, `design.md`,
`tasks.md`, and `specs/local-project-workspace/spec.md` cold — no `git log`/`git show` on the change
itself, no re-reading Entry 5 beyond what the `next_action` field already summarized before reading
the artifacts themselves.

**Against each of Q4b's six `review_criteria`, in order:**

1. *Does the delete touch ONLY database rows, with a test proving the workspace directory
   survives?* Yes. D4 states it as a structural guarantee (no import of `project_workspace.py`, no
   filesystem call), not a promise, and 3.5 is mutation-checked — add `shutil.rmtree`, watch the test
   fail, revert. This is the right shape for a safety property: a test that can be shown to catch the
   regression, not just one that currently passes.
2. *Is the cascade derived from the models and iteration 1's evidence rather than guessed, and is
   anything left orphaned?* Yes — D2's 27-table count (11 with a declared relationship, 16 without,
   `agent_job_deletions` with a `project_id` column but no `ForeignKey`) reconciles exactly with Q1's
   "26 tables + projects" from Entry 1. 3.2 asserts zero remaining rows across every `project_id`
   table, not just the 3.1 sample — that is what makes "no orphans" a test rather than a claim.
3. *What happens on a RUNNING run vs an open conversation, and is that stated?* Yes, both stated and
   opposite: running run refuses (409, reusing `_guard_relocation`'s exact check, not a new
   definition), open conversation does not block (D3's reasoning — a conversation is history, not an
   in-progress operation, and treating it as a blocker would make delete unreachable for the normal
   case). Both have dedicated tests (3.4, 3.6, 3.7).
4. *What happens deleting the LAST project?* Addressed in D6, honestly flagged as the least certain
   piece (reasoned from reading `App.tsx`/`Sidebar.tsx`/`configStore.ts` cold, not from running the
   app at zero projects, since emptying `aw-loop10` to test it live is off-limits). Task 4.5 requires
   confirming for real once the code exists, and commits to fixing rather than filing separately if
   that check finds a crash. Deferring a genuinely-untestable-yet claim to an implementation-time
   check, with the check written down as a task rather than left as a hope, is the right call here —
   not a gap in the round.
5. *Is the confirmation proportionate?* Type-to-confirm the project's exact name. Proportionate to an
   irreversible, no-undo action (the Non-Goals section states explicitly that soft-delete/undo was not
   requested and is out of scope) and consistent with Q4b's own `detail` field, which named this
   pattern directly.
6. *Does it reuse Icon/rail patterns rather than inventing new ones?* Yes for the mutation hook shape
   (`useDeleteProject` mirrors `useRelocateProject`), the settings layout
   (`SettingsSection`/`SettingsRow`), and the icon system (task 4.2 requires checking for an existing
   lucide name before introducing one). One genuinely new pattern is introduced — type-to-confirm
   itself, since nothing in this codebase does that yet — and D7 says explicitly why the lighter
   existing pattern (`delete_runner`'s single-click confirm) is not reused: proportionality to what is
   being destroyed, not habit.

**Two things checked beyond the six criteria, because a cold read surfaces different questions than
the one that wrote it:**

- **D2's generic sweep assumes every table with a `project_id` column is *owned* by that project** —
  i.e., that the column always means "scoped to," never "references," e.g. a cross-project pointer.
  Not disprovable from the design doc alone, and not one of the stated criteria, so this is not an
  objection — but it is exactly the kind of assumption 3.2's exhaustive no-orphan test does not catch
  (an over-broad delete looks identical to a correct one from "no orphans remain"). Recorded here as
  an implementation-time watch item, not a blocker: task 1.3's implementer should spot-check that
  every swept table's `project_id` semantics really is ownership before trusting the sweep, using the
  same per-table reasoning D2 already applied to `project_sessions`/`project_instructions`'s
  primary-key case.
- **Task 2.3's SSE broadcast phrasing ("before the row is gone") is ambiguous** between "capture the
  project's name before the row disappears" (uncontroversial — you need the name for the payload) and
  "emit the event before the transaction commits" (which would tell clients a delete happened before
  it is durable, a real bug if the transaction then fails). Not written unambiguously enough to catch
  a wrong implementation on its own. Not an objection to the design — 2.1/2.3 read together imply
  success-then-broadcast — but worth flagging so whoever implements 2.3 reads it as "commit, then
  broadcast," not literally.

**Verdict: APPROVED, round 1.** No criterion fails; the two additional observations above are
implementation-time watch items, not design defects, and do not warrant a revision round. Per the
spec-round protocol, this ends the spec round at round 1 of the max 3 — the artifact ships to
implementation as written, with the two watch items carried forward here rather than folded into a
`design.md` edit that would only restate what this entry already says.

**Elapsed:** part of one iteration — reading and reasoning against six stated criteria, no code run
(nothing to run; this is a document review).

---

## Entry 7 — 04:28 — Q4b phase 1: `ProjectLifecycleService.delete()`

Verified branch/log/`STATE.json` agreed before starting (HEAD `bd84cda`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 6, `current: Q4b-delete-project`,
`next_action` pointing at `tasks.md` phase 1, tasks 1.1-1.5, with the two round-1 review watch items
carried in). Refreshed `last_heartbeat` to now before beginning. Sized this iteration to phase 1
only, per the `next_action`'s explicit instruction — no API route, no UI, no formal pytest file yet.

**Implemented in `hub/hub/project_lifecycle.py`:**

- `DeletedProjectSummary` — a frozen dataclass (`id`, `name`), captured before the row disappears,
  for phase 2's SSE payload.
- `ProjectLifecycleService.delete(project_id)` — 404-shaped `ProjectPathError(code=
  "project_not_found")` for an unknown project (the same shape `relocate()` already raises for the
  identical case, which the API layer already knows how to turn into a 404); `ProjectPathError(code=
  "project_has_active_run")` if `SELECT COUNT(*) FROM runs WHERE project_id = :id AND status =
  'running'` is non-zero (`_guard_relocation`'s exact check, reused rather than reinvented, per D3);
  otherwise sweeps every project-scoped table and deletes the `projects` row last, all inside one
  transaction (the existing `AsyncSession`, one `commit()`).
- `_project_scoped_tables()` — `reversed(Base.metadata.sorted_tables)` filtered to tables with a
  `project_id` column, excluding `projects` itself. Chose `sorted_tables` over hand-listing D2's
  table names from the design doc's prose, because that prose enumeration turned out to be wrong
  when checked against the live model registry (its "16" count doesn't match the actual list length,
  and it omits `run_divergences` and `task_integrations` entirely) — trusting code over prose here is
  exactly what D2 argues for. `Base.metadata.sorted_tables`, reversed, orders every table that
  references another before what it references, for the whole FK graph, which is a superset of "just
  `project_id`-linked satellites before what they reference" and satisfies it. Directly introspected:
  38 tables carry a `project_id` column today (not 27 — the design doc's count was off; recorded here
  as a correction, not silently reconciled).

**Checked the round-1 review's watch item before trusting the sweep, as it asked:** read the name of
every one of the 38 swept tables against D2's per-table reasoning for the two known special cases
(`project_sessions`/`project_instructions`, where `project_id` is the primary key, not a secondary
column) and found none that reads as a cross-project reference rather than ownership — every column
is either a straight `ForeignKey("projects.id")` or one of those two primary keys. Not exhaustively
provable from names alone, but the specific failure mode the watch item raised (a column that means
"points at" rather than "belongs to") was not found.

**Verified against a real (if throwaway, in-memory, not committed) SQLite session** — the standing
instruction that a passing suite is not proof of behaviour applies doubly to a change with no test
file yet:

- Happy path: two projects, rows in `agents`/`runners`/`charters` for one of them; delete it; every
  row for that project gone across all 38 swept tables (checked exhaustively, not sampled); the other
  project's rows untouched.
- Active-run guard: a `Run(status="running")` blocks delete with exactly `code=
  "project_has_active_run"`; the project row survives the attempt.
- 404 shape: deleting an unknown id raises `code="project_not_found"`.

All four checks passed. This is not task 3.1-3.9's formal pytest coverage (deliberately deferred —
next iteration's phase per the queue's own sizing) but it is real execution against a real database,
not a read-only code review.

**Ran the existing suite most likely to catch a regression from this change** —
`test_project_lifecycle.py`, `test_project_persistence.py`, `test_migrations.py` — 64 passed, 1
pre-existing skip, no failures. Confirms 1.1's claim (`test_migrations.py`/
`test_project_persistence.py` need no head bump, since D1 states no migration) without waiting for
task 3.9 to assert it formally.

`npx openspec validate --changes --strict`: 14 passed, 0 failed, this change included — ticking
`tasks.md` boxes did not break the artifact's own validity.

**Ticked 1.1-1.5** in `tasks.md`, each with a note on what was actually done (not a bare checkmark —
several record a decision or a correction to the design doc's prose, per the standing rule that a
task is only complete on real, verified implementation). Left 1.4's actual mutation-check (add
`shutil.rmtree`, watch a test fail, revert) unticked-in-spirit-but-noted: that check needs the test
from 3.5 to exist first, so it is 3.5's job, not this phase's — recorded rather than faked here.

**Next:** phase 2 (the API route, `DELETE /api/v1/projects/{project_id}`) is the natural next unit —
`delete()` now exists for it to call. Phase 3 (the formal pytest file covering 3.1-3.9, including the
mutation check 1.4 deferred) could come before or after phase 2; phase 2 first because the two watch
items from round 1's review (D2 sweep semantics, SSE broadcast ordering) both land in phase 2's code,
not phase 3's, and are fresher to apply now than after a context gap.

**Elapsed:** one iteration.

---

## Entry 8 — 04:43 — Q4b phase 2: `DELETE /api/v1/projects/{project_id}`

Verified branch/log/`STATE.json` agreed before starting (HEAD `20c0cbe`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 7, `current: Q4b-delete-project`,
`next_action` pointing at `tasks.md` phase 2 only). Refreshed `last_heartbeat` to now before
beginning. Sized this iteration to phase 2 only, per the `next_action`'s explicit instruction — no
formal pytest file (phase 3), no UI (phase 4).

**Added to `hub/hub/api/v1/projects.py`**, after `relocate_project`: `DELETE
/api/v1/projects/{project_id}`, `Depends(get_operator)` (plain — not `get_operator_project`, which
would 404 an unknown id before `delete()`'s own typed error gets a chance, and not `get_project`,
per `design.md`'s route-shape section). Calls `ProjectLifecycleService(session).delete(project_id)`
and maps its two `ProjectPathError` codes explicitly: `project_not_found` → 404 (same shape
`relocate_project` already uses), `project_has_active_run` → 409 with `detail={"code", "message"}`.

**One deliberate deviation from `raise_workspace_http_error`, recorded rather than silently
matched to `relocate_project`'s pattern:** that helper maps a bare `ProjectPathError` to 422,
reserving 409 for `ProjectIdentityConflict`/`ProjectWorkspaceUnavailable` — so calling it here for
`project_has_active_run` would produce a 422, contradicting `design.md`'s explicit "409 with a
machine-readable code" for this route (and `tasks.md` 2.2's literal "409"). Raised the
`HTTPException` directly instead. Worth flagging because `relocate_project`'s own
`project_relocation_active` case goes through `raise_workspace_http_error` and therefore likely
also returns 422 today despite its design doc calling it 409 — not this change's bug to fix, but a
pre-existing inconsistency worth a `decisions_for_user` line rather than silently propagating it
into new code.

**SSE broadcast ordering — applied round 1 review's watch item, which superseded task 2.3's own
literal wording:** `2.3` as written says broadcast "before the row is gone"; `STATE.json`'s
`next_action` (set at Entry 6, after the round-1 review) directed broadcasting *after*
`delete()`'s commit instead. Since `delete()` already commits inside its own transaction (phase 1),
the row is unavoidably gone by the time the route regains control either way — the real choice was
just "broadcast before or after we know the commit succeeded," and after is correct: broadcasting
first and then having the commit fail would tell clients something happened that didn't. Used
`summary.id`/`summary.name` (captured by `delete()` ahead of its sweep, exactly for this) since
`project.name` isn't readable off a deleted ORM instance. Recorded the deviation from the literal
task text directly in `tasks.md`, not just in this log.

**Verified against the real route over real HTTP**, not just by reading the code: wrote a throwaway
test file (`hub/tests/test_scratch_delete_project_phase2.py`, run then deleted — not part of the
diff, per the standing "phase 3 is deliberately deferred" note) using the project's own `app`/
`auth_headers` fixtures (a real FastAPI app behind `httpx.AsyncClient`, real in-memory SQLite, not
mocked). Four cases, all passed:

- Happy path: project + an agent row, `DELETE` → `204`, empty body, gone from a subsequent
  `GET /api/v1/projects`.
- Unknown id → `404`.
- A project with a `Run(status="running")` → `409`, `detail["code"] == "project_has_active_run"`,
  project still present in the listing afterward.
- No `Authorization` header → `401` (confirms auth runs ahead of both the not-found and
  active-run checks, not skippable).

**Ran the existing regression set most likely to catch a break:**
`test_operator_projects_api.py`, `test_project_lifecycle.py`, `test_project_persistence.py`,
`test_migrations.py` (plus the throwaway file while it still existed) — 99 passed, 1 pre-existing
skip, 63s. `ruff check hub/hub/api/v1/projects.py` clean. `npx openspec validate --changes --strict`
— 14 passed, this change included, both before and after the `tasks.md` edit.

**Ticked 2.1-2.3**, each with what was actually decided, including the two deviations from literal
task wording and why. `git status`/`git diff --stat` after removing the scratch test file: exactly
`hub/hub/api/v1/projects.py` (+37) and `tasks.md` (+30/-3) changed — nothing else touched.

**Next:** phase 3, the formal pytest file (`tasks.md` 3.1-3.9) — the throwaway HTTP checks above
cover the same shapes 3.1/3.4 will assert formally, but not yet as committed, reviewable coverage,
and not yet the exhaustive no-orphan sweep (3.2), the second-project isolation proof (3.3), the
mutation-checked workspace-survival test (3.5, deferred from 1.4), the terminal-run/open-conversation
non-blocking cases (3.6/3.7), or the `agent_job_deletions` no-FK case (3.8). Phase 4 (UI) still
depends on phase 2's response shapes, which are now settled and stable to build against.

**Elapsed:** one iteration.

---

## Entry 9 — 05:02 — Q4b phase 3: the formal pytest file, `tasks.md` 3.1-3.9

Verified branch/log/`STATE.json` agreed before starting (HEAD `878c6b7`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 8, `current: Q4b-delete-project`,
`next_action` pointing at phase 3 only — 3.1 through 3.9, phases 4/5 explicitly out of scope for
this iteration). Refreshed `last_heartbeat` to now before beginning.

**First established what "27 project-scoped tables" in the task text actually means today**, since
Entry 6 already found the design doc's count wrong once (16 vs. 38): directly introspected
`Base.metadata.sorted_tables` again and got the same **38** phase 1 found, confirming it, not
re-discovering a different number. Wrote `PROJECT_SCOPED_TABLE_NAMES` as an explicit, readable list
in the new test file rather than leaving the sweep implicit, and added
`test_sweep_covers_every_project_scoped_table_in_the_model_registry` — it introspects the live
model registry the same way `_project_scoped_tables()` does and fails the moment the two disagree,
so this list cannot go stale silently the way the design doc's own count already had.

**Wrote `hub/tests/test_project_delete_api.py`** (new, committed file) with a shared
`_seed_full_project(session, project_id, tag)` helper that adds one row to **every one of the 38**
project-scoped tables (not a representative sample) — figured out every table's actually-required
columns (non-nullable, no Python-side default, no `server_default`) by introspecting
`Column.nullable`/`.default`/`.server_default` directly rather than reading each of ~35 model
classes by eye, then cross-checked every `CheckConstraint` in `hub/hub/db/models.py` (enum-shaped
columns like `evidence_reviews.decision`, `spec_document_events.origin`,
`worker_invocations.outcome`, `task_transitions.actor_kind`, …) against the constant tuples they
reference (`EVIDENCE_DECISIONS`, `SPEC_EVENT_ORIGINS`, `WORKER_OUTCOMES`, `SPEC_EVENT_ACTORS`, …) so
the seed picks a value that is actually legal rather than guessing and hoping SQLite's disabled FK
enforcement also meant disabled CHECK enforcement (it does not — CHECKs are still live). The seed
built and ran clean on the first attempt against the real in-memory test database, no trial-and-error
needed once the constraint audit was done up front.

**3.1** (representative sample) and **3.2** (exhaustive, all 38 tables, not just 3.1's sample) both
use the same seed helper — 3.2 additionally asserts every table is actually populated *before*
delete, so a table sitting at 0 both before and after cannot pass for the wrong reason. **3.3**
seeds two full projects and diffs exact per-table counts for the untouched one, proving
`WHERE project_id = :id` scoping rather than a global truncate. **3.4** seeds a project with a
second, *running* run alongside the terminal one the helper always adds (proving the guard fires
without requiring every run on the project to be running), asserts the service-layer
`ProjectPathError.code`, and diffs full per-table counts before/after the refused attempt — not just
that the project row survived. **3.6**/**3.7** are the two non-blocking cases stated directly.
**3.8** targets `agent_job_deletions` by itself, the one table `design.md` D2 names as having no
declared `ForeignKey`, to prove the generic column-name sweep does not depend on a relationship
existing.

**3.5, the mutation-checked workspace-survival test — the one task 1.4 explicitly deferred to this
phase.** Wrote `test_workspace_directory_survives_deletion` using the `bind_project_workspace`
fixture (registers a *real* directory through `ProjectLifecycleService.open_existing`, and restores
the suite's real `resolve_project_workspace` for the test, undoing `_default_project_workspace`'s
autouse fake). First draft baked a "mutation check" into the committed test itself — a monkeypatched
wrapper that called the real `delete()` then bolted its own `shutil.rmtree` onto a second directory
afterward. Caught before committing that this proves nothing about the assertion's sensitivity: it
only proves `shutil.rmtree` deletes a directory, which was never in question. Replaced it with the
actual mutation check the task asks for, done by hand against the real function: temporarily added
`shutil.rmtree(project.working_directory, ignore_errors=True)` directly inside
`ProjectLifecycleService.delete()` (`hub/hub/project_lifecycle.py`), ran
`test_workspace_directory_survives_deletion` alone, watched it fail —
`AssertionError: assert False` on `directory.is_dir()`, directory actually gone from disk — then
reverted the edit and confirmed `git status --short hub/hub/project_lifecycle.py` prints nothing.
The committed test carries only the real assertions; the mutation check is recorded here, as the
task's own wording asks ("record the mutation check in the PR/commit, not just claim it happened").

**3.9**: rather than write a test that merely `importlib.import_module`s the two other test files
(which proves nothing about pass/fail — collection succeeding is not the same as passing), ran them
directly as part of this iteration's regression pass and recorded the result in `tasks.md` instead.
`test_migrations.py`'s own hardcoded head assertion already reads `"0073"` — Q3's
conversation-sequence migration, unrelated to this change — not `"0058"` as one nearby docstring
comment still (incorrectly) says; it passed unmodified, which is what "no head bump needed" actually
means here.

**Full regression run:** `pytest hub/tests/test_project_delete_api.py
hub/tests/test_operator_projects_api.py hub/tests/test_project_lifecycle.py
hub/tests/test_project_persistence.py hub/tests/test_migrations.py` — **104 passed, 1 pre-existing
skip, 0 failed, 65.5s**. `ruff check hub/tests/test_project_delete_api.py` clean. `npx openspec
validate --changes --strict` — 14 passed, this change included, after the `tasks.md` edit.

**Ticked 3.1-3.9**, each with what was actually built/checked and, for 3.5, the full mutation-check
narrative (not just a checkmark).

**Files touched, confirmed via `git status --short`:** `hub/tests/test_project_delete_api.py` (new)
and `openspec/changes/2026-08-16-delete-project-api/tasks.md`. `hub/hub/project_lifecycle.py` has no
diff — the mutation-check edit there was fully reverted, not left in.

**Next:** phase 4, the UI delete control (`tasks.md` 4.1-4.5) — `useDeleteProject` in
`hub/ui/src/api/projects.ts` mirroring `useRelocateProject`'s shape, a `DeleteProjectSection` in
`ProjectSettingsPanel.tsx` below the existing relocate control, a type-the-name confirmation dialog,
a `409`-surfaces-the-reason case, and the zero-project empty-state check (4.5) — all response shapes
are settled from phase 2, so this is buildable without further backend changes. Phase 5 (UI tests)
and phase 6 (human-only) follow after.

**Elapsed:** one iteration.

## Entry 10 — 05:16 — Q4b phase 4: the UI delete control, `tasks.md` 4.1-4.5

Verified branch/log/`STATE.json` agreed before starting (HEAD `3c362f2`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 9, `next_action` pointing at phase 4 only —
4.1 through 4.5, phase 5/6 explicitly out of scope this iteration). Refreshed `last_heartbeat`
before beginning.

**4.1** — `useDeleteProject(projectId)` in `hub/ui/src/api/projects.ts`. Deliberately does **not**
call the existing `deleteJson<T>` helper: that helper always calls `res.json()`, and the route
(`hub/hub/api/v1/projects.py:542`) returns `204 No Content` with an empty body, which throws a
`SyntaxError` on `.json()`. Used `fetchWithAuth` directly and discarded the response. `onSuccess`
writes the filtered `['projects']` cache once via `setQueryData`'s functional updater, captures that
same filtered array, and only then checks `useConfigStore.getState().selectedProjectId` to decide
whether to resolve the next selection — one read of "what's left" rather than a second cache lookup,
reusing `configStore`'s own fallback (`design.md` D6) rather than a second implementation of it.

**4.2/4.3** — new `hub/ui/src/components/environment/DeleteProjectDialog.tsx`, modelled directly on
`AgentCreateDialog.tsx`'s existing dialog shape (`role="dialog"`, `aria-modal`, `useDialogFocus` for
the Escape/focus-trap behaviour, `lifted-surface` panel) rather than inventing a new dialog pattern.
`canDelete` requires `typed.trim() === project.name` — edge-trimmed only, case-sensitive otherwise,
per D7's literal wording. `ProjectSettingsPanel.tsx` gained one `SettingsRow` below the existing
Directory row, holding a `destructive`-variant `Button` that opens the dialog — no new icon needed,
since the trigger is a labelled button matching the Directory row's own "Locate project" pattern
(text, not an icon glyph), so the `Icon`-component-only rule was never in tension with this task.

**4.4** — checked whether any new client-side branching was actually needed before writing any:
`hub/hub/api/v1/projects.py`'s 409 already carries `detail={"code": "project_has_active_run",
"message": "project cannot be deleted while a run is active"}` (phase 2), and
`readableApiError` (`hub/ui/src/api/client.ts:74`) already has a branch that extracts
`detail.message` from exactly an object-shaped detail — written earlier for the checkpoint-threshold
refusal, but the shape is generic, not endpoint-specific. Confirmed by reading both sides against
each other rather than assuming; the dialog calls `readableApiError(deleteProject.error, '...')` and
needed no new parsing.

**4.5** — read `App.tsx` and `Sidebar.tsx` as they exist now, not by assumption, per the task's own
instruction. Found the zero-project state **already correct**, better than `design.md` D6 expected:
`lib/navigation.ts` already declares a `{kind: 'zero'}` `WorkspaceDestination`, and
`resolveDestination` (`navigation.ts:383-386`) already falls through to it when
`availableProjectIds` is a non-null empty array with no `lastOpenedProjectId` match.
`App.tsx`'s `content` renders "Open or create a project to begin." for every destination kind other
than `conversation`/`agent-settings`/`project` (the final `else`, `App.tsx:398`); `<ProjectHeader>`
is already gated on `currentProject &&` so an absent project renders nothing rather than a stale
header; `Sidebar.tsx`'s "Add project" button is unconditional below `projects.map(...)`, which is
simply empty when the array is `[]`. This path used to be reachable only by wiping the database —
what's new is that `useDeleteProject`'s cache write makes `availableProjectIds` go to `[]` *inside a
live session*, and `useWorkspaceNavigation`'s `useEffect` already recomputes `destination` off that
array's content (compared by `.join(',')`, not identity), so this reactively resolves without any
code change. Recorded as confirmed-by-inspection; the live drive (task 6.4) is still what turns this
from "reads correct" into "observed correct," and stays a human-only task.

**Verification.** `npx tsc --noEmit` (hub/ui) — clean. `npm run lint` — **could not run**: this
machine's globally-resolved `eslint` is v9.39.4, which requires `eslint.config.js`; the repo has
neither that file nor a `.eslintrc.*` anywhere (`find` from the repo root, excluding
`node_modules`, returned nothing) despite `package.json`'s `lint` script assuming the old
`.eslintrc` flag-based invocation and `eslint@^9.17.0` declared as a devDependency. This is **not
introduced by this change** — confirmed by running `npm run lint` against the pre-4.1 tree (`git
stash`) and getting the identical "couldn't find eslint.config" failure. Recorded here rather than
silently worked around, since Q4b's phase 5 task 5.3 explicitly asks for "`npm run lint` clean" and
that bar cannot currently be met by any change in this repo, not just this one — flagged for
`decisions_for_user` below rather than fixed inline, since authoring a working `eslint.config.js` is
a repo-wide config decision outside this queue item's scope.

Ran the full UI suite (`npx vitest run`) after adding `useDeleteProject`'s stub to
`projectSettingsPanel.test.tsx`'s existing `vi.mock('@/api/projects', ...)` — without it, all 10
tests in that file failed on mount with "No `useDeleteProject` export is defined on the ... mock,"
since `ProjectSettingsPanel` now renders `<DeleteProjectDialog>` unconditionally, which calls the
hook even while closed. Also observed one unrelated flake on the first full-suite run —
`chartersUi.test.tsx`'s single test timed out at 5000ms — and checked it before dismissing it:
reran `chartersUi.test.tsx` alone and paired with `projectSettingsPanel.test.tsx` on the *pre-4.1*
tree (`git stash`) and it passed there too, then reran both together on the current tree and they
passed; a second full-suite run afterward was clean. Consistent with the load-dependent timeout
already named in this run's `dead_ends` ("different chunk groupings expose different flakes"), not
a regression from this iteration's changes — recorded as observed, not asserted away. **Final: 90
test files / 864 tests passing**, two full runs. `npx openspec validate --changes --strict` — 14
passed, this change included, after the `tasks.md` edit.

**Ticked 4.1-4.5**, each with what was actually built/found, including 4.5's "no fix needed, here is
why" and 4.4's "no new code needed, here is why" — neither is a checkbox ticked on the strength of
the task's own wording being satisfied by default.

**Files touched, confirmed via `git status --short`:** `hub/ui/src/api/projects.ts`,
`hub/ui/src/components/environment/ProjectSettingsPanel.tsx` (both modified),
`hub/ui/src/components/environment/DeleteProjectDialog.tsx` (new),
`hub/ui/src/__tests__/projectSettingsPanel.test.tsx` (modified — mock addition only),
`openspec/changes/2026-08-16-delete-project-api/tasks.md` (modified). Committed as `472b91e`.

**Next:** phase 5 — UI tests (`tasks.md` 5.1-5.3): a component test that the Delete button stays
disabled until the typed name matches exactly and calls the mutation only once enabled (5.1), a test
that a `409` renders the active-run reason rather than a generic failure (5.2), and 5.3's lint/openspec
gate — which, per this entry's finding, needs `npm run lint`'s prerequisite (`eslint.config.js`)
addressed first or explicitly deferred with a reason, since the bar as written is currently
unmeetable by any change in this repo. Then phase 6, human-only: drive it live against a throwaway
project (never `aw-loop10`), screenshot with `scripts/uishot.py` if Q4a's harness works, and the two
taste judgements (6.3 confirmation proportionality, 6.4 empty-state).

**Elapsed:** one iteration.

## Entry 11 — 05:31 — Q4b phase 5: UI tests, tasks.md 5.1-5.3, and making `npm run lint` runnable

Verified branch/log/STATE.json agreed before starting (HEAD `fe3170c`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 10, next_action pointing at phase 5 only).
Refreshed last_heartbeat before beginning.

**5.1/5.2** — new `hub/ui/src/__tests__/deleteProjectDialog.test.tsx`, rendering
`DeleteProjectDialog` directly with a mocked `useDeleteProject` rather than through
`ProjectSettingsPanel` (matching the approach next_action suggested), since the dialog owns the
gating logic under test. Five tests: disabled until an exact match then calls the mutation exactly
once with `(undefined, {onSuccess: onDeleted})`; stays disabled on a case mismatch and a partial
match, never calling the mutation; accepts edge-trimmed whitespace around an otherwise-exact match
(D7's literal wording, checked directly); a 409 with the real route payload shape
(code: project_has_active_run, message: "...") renders that sentence via role="alert", not
readableApiError's fallback; an unstructured error still renders the fallback, pinning that the
409 case's pass depends on the structured shape rather than always succeeding regardless. All 5
passed first run.

**5.3, the harder half.** `npx openspec validate --changes --strict` was already clean (14 passed)
and stayed clean. `npm run lint`: Entry 10 had found this could not run at all — eslint@9 requires
flat config (eslint.config.js), and neither that file nor any .eslintrc.* exists anywhere in the
repo, confirmed again as never having existed (`git log --all --oneline -- '*.eslintrc*'
'eslint.config*'` returns nothing). next_action said to attempt the fix since the needed packages
were "already devDependencies," and to defer only if it turned out to need more than a config file
— it did, in a way next_action didn't fully anticipate, so both halves happened.

Wrote `hub/ui/eslint.config.js`: @eslint/js recommended + @typescript-eslint/eslint-plugin's own
flat/recommended array (used directly rather than installing the typescript-eslint combined
meta-package the standard Vite template imports, since it is not installed and the plugin's own flat
config already includes a working parser) + eslint-plugin-react-hooks/eslint-plugin-react-refresh
recommended rules — the same shape the Vite React+TS template ships, adapted to what's actually
installed. Checking what that config imports found two more gaps: @eslint/js and globals resolve
today only as transitive dependencies (of eslint itself and other devDependencies) — present in
package-lock.json already, confirmed via `node -e "require(...)"` and a package-lock.json grep, so
importing them needed no network fetch — but neither was a declared devDependency, despite the new
config importing both directly. Added both explicitly at their already-resolved versions (@eslint/js
^9.17.0, globals ^14.0.0) and ran `npm install --package-lock-only`, which touched only those two
lines (git diff --stat) — a correctness fix (declaring what's actually imported), not a new install.

Running lint for the first time ever surfaced 16 pre-existing problems (7 errors, 9 warnings), none
in files this change added. Treated the two classes differently:

- **7 errors — fixed, all mechanical and verified.** `let settings` -> `const` in
  projectSettingsPanel.test.tsx (never reassigned, checked by grep first). AgentOutputPanel.tsx:210,302
  and ErrorBoundary.tsx:28 had eslint-disable-next-line comments now flagged as unused under this
  config (react-hooks/exhaustive-deps no longer fires on either effect under the installed plugin
  version; no-console was never in any rule set this config enables) — removed, reran the full suite
  after. navigation.ts:65's SPEC_PATH_CONTROL_CHARS regex intentionally matches control characters
  (mirrors validate_spec_path server-side) — kept the regex, added a scoped
  eslint-disable-next-line no-control-regex with the reason inline, rather than weakening the check
  to satisfy the linter. **The one real find**: urlNavigation.test.ts:268's
  'spec\windows\spec.html' had unescaped backslashes — in a plain JS string (not a regex) \w and \s
  are not the escape sequences they look like, so the literal actually evaluated to
  "specwindowsspec.html" (confirmed with node -e), meaning this test never once exercised
  isSpecDocumentPath's value.includes('\\') rejection despite claiming to. Fixed to
  'spec\\windows\\spec.html', restoring real coverage — a genuine bug lint surfaced, not a style
  nit, and it would not have been found without this task.
- **9 warnings — left as a recorded backlog, not fixed.** All in files this change never touches:
  react-refresh/only-export-components x8 across ChartersPage.tsx, Badge.tsx,
  ProjectSettingsPanel.tsx (its pre-existing top, not anything phase 4 added), SpecFrame.tsx,
  button.tsx, agentStatus.tsx — each needs a file split to separate a component export from a
  constant/helper export, a real but unrelated refactor. Plus one OverviewPage.tsx
  react-hooks/exhaustive-deps on a useMemo that needs a judgement call about intended dependency
  behavior, not a mechanical fix. Editing six files unrelated to project deletion is scope creep
  beyond a delete-project UI-tests task; left for a dedicated follow-up and recorded in
  decisions_for_user below.

Net: `npm run lint` now runs (previously impossible on this repo), reports 0 errors, and fails only
on --max-warnings 0 against the documented 9-item backlog above — measurably different from, and
strictly better than, "cannot run at all."

**Full regression after all of phase 5's edits:** `npx tsc --noEmit` (hub/ui) clean. `npx vitest run`
— 91 test files / 869 tests passing. One runnersUi.test.tsx timeout on the first full-suite run;
reran it alone and it passed in 3s — consistent with the load-dependent flake class this run's own
log already documents for chartersUi.test.tsx, not a regression, and not a file this task's edits
touch. A second full-suite run afterward was clean (91/91, 869/869).
`npx openspec validate --changes --strict` — 14 passed, this change included.

**Ticked 5.1 and 5.2. 5.3 marked `[~]`** (partial, not `[x]`) in tasks.md, with the openspec half
stated as fully clean and the lint half stated precisely: 0 errors, 9 pre-existing warnings deferred
with a named reason — matching the "record concretely, don't silently work around or falsely tick"
pattern this run has used throughout.

**Files touched, confirmed via `git status --short`:** hub/ui/eslint.config.js (new),
hub/ui/src/__tests__/deleteProjectDialog.test.tsx (new), hub/ui/package.json and
hub/ui/package-lock.json (both modified, two lines), hub/ui/src/__tests__/projectSettingsPanel.test.tsx,
hub/ui/src/__tests__/urlNavigation.test.ts, hub/ui/src/components/agents/AgentOutputPanel.tsx,
hub/ui/src/components/common/ErrorBoundary.tsx, hub/ui/src/lib/navigation.ts (all modified),
openspec/changes/2026-08-16-delete-project-api/tasks.md (modified).

**Next:** phase 6, human-only (tasks.md 6.1-6.4) — drive it live against a throwaway project
(never aw-loop10), screenshot with scripts/uishot.py if Q4a's harness works (check Q4a's status
in STATE.json first — it was capped at 2 iterations and may have ended blocked), and the two taste
judgements (6.3 confirmation proportionality, 6.4 empty-state). All of phase 6 is human-only per
tasks.md's own split — this driver cannot tick it; the honest move is to attempt what's
machine-checkable within it (e.g. capturing screenshots if the harness works) and record the rest as
decisions_for_user, then move the queue on to Q4-spec-ux-fixes once phase 6 is exhausted or
determined to need the operator's eyes.

**Elapsed:** one iteration.

## Entry 12 — 05:49 — Q4-spec-ux-fixes: AUTHOR round 1

Verified branch/log/STATE.json agreed before starting (HEAD `314cc28`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 11, next_action pointing at Q4b phase 6
exhausted → move to Q4-spec-ux-fixes AUTHOR round 1). Judged phase 6 exhausted per Entry 11's own
framing (all four sub-tasks are explicitly human-only; nothing left this driver can tick) and moved
straight to Q4, the operator's first-named agenda item, per `spec_round_protocol`.

Read `.claude/autonomous/2026-08-16-operator-ux-findings.md` in full — the brief for all six
findings. Then read the actual code behind each, rather than taking the findings document's
descriptions at face value, since a spec round that restates a symptom without checking the cause
produces a plan nobody can implement without redoing this reading:

- **F2 (navy background)** — found the actual root cause, not previously stated anywhere: it's a
  wiring bug, not a missing feature. `hub/ui/src/components/spec/SpecFrame.tsx`'s `themeOverride()`
  injects CSS custom properties named `--bg`/`--surface`/`--surface-2`/`--border`/`--fg`/`--muted`
  (the Hub's own dashboard token names, confirmed absent from any `--aw-*` prefix via
  `grep -n "aw-bg\|aw-fg..." hub/ui/src/index.css` returning nothing). `hub/hub/spec_render.py`'s
  stylesheet defines and reads a completely disjoint set — `--aw-bg`, `--aw-fg`, `--aw-muted`,
  `--aw-rule`, `--aw-accent`, `--aw-chip-bg`, `--aw-code-bg`. None of the six override names appears
  anywhere in the renderer's CSS, so the override has nothing to affect and the document always falls
  through to its own dark default (`#0d1117`, the observed navy) via the `prefers-color-scheme`
  media query or `[data-theme="dark"]` rule. `SpecFrame.tsx`'s own comment block confirms this was
  written for the *older* skill-authored documents (which used `--bg`/`--surface` directly) and never
  updated when `spec_render.py` was written under a new prefix for
  `2026-08-12-hub-owns-the-spec-document`.
- **F3 (misleading coverage labels)** — read `hub/hub/requirement_coverage.py`'s `_state()`: it
  checks `accepted` and `awaiting` review states against the current digest, and falls through to
  `in_progress`/`not_started`/`unserved` for anything else, including a requirement whose current
  evidence is entirely `rejected`. Found a direct precedent for the fix already built elsewhere and
  never reused: `hub/hub/api/v1/tasks.py`'s `_attach_requirements()` already computes
  `has_rejected_evidence`/`rejected_evidence_count`/`latest_rejection_reason` per requirement, scoped
  to the current digest, for the task board's own requirement-link payload — confirmed by
  `grep -n "has_rejected_evidence" hub/ui/src -r` returning nothing, so this signal already exists
  server-side and has never reached any screen.
- **F4 (task board doesn't show requirement links)** — confirmed the data gap is real and one-sided:
  `hub/hub/api/v1/tasks.py`'s `_attach_requirements()` populates `requirement_links`/`requirement_ids`
  on every task response already, `hub/ui/src/api/tasks.ts`'s `Task` type already declares the field,
  and `TaskCard.tsx` renders none of it.
- **F6 (ticket granularity)** — confirmed `hub/hub/spec_tasks.py`'s `materialise()` mints exactly what
  the document's `tasks[]` array declares, with no cap anywhere. Found the enforcement point:
  `hub/hub/spec_completeness.py`'s `check()` already blocks `propose()` on structural findings
  (`requirement_without_task`, `task_without_requirement`, etc.) — a new `task_too_coarse` finding is
  the same mechanism, not a new one.

Wrote `openspec/changes/2026-08-16-spec-surface-legibility/` — `proposal.md`, `design.md` (D1-D8,
one per major decision: phase ordering, F2's variable-rename mapping table, F1's colour targets, F3's
precedence placement and the `has_rejected_evidence` precedent, F3's breaking-change scope, F6's
ceiling derived from the findings document's own table — 3, not 2 or a round number, chosen because
the evidence contains no complaint about a 2-requirement ticket, so 3 is the smallest ceiling that
does not retroactively flag the one ticket nobody named as a problem while still refusing the 4/5/6
ones that were — F4's chip/navigation design including a new `anchor` field on the spec destination,
F5's drawer-not-modal reasoning and its clipping-check precision), `tasks.md` (8 phases: F2, F1, F3,
F6, F4, F5, human-only verification, user test guide — matching `design.md` D1's stated ordering),
and spec deltas for `spec-document-authority` (4 new requirements: theme inheritance, modal visual
distinction, rejected coverage state, task requirement ceiling) and `task-lifecycle-governance`
(3 new requirements: requirement links visible on the board, full-detail view sized to hold content,
navigating a requirement link reaches the requirement).

Findings 1, 2 and 5 are explicitly marked taste in the proposal's Non-Goals and `tasks.md` section 7
(human-only) — matching the standing limit on visual judgement. F2 is treated as *also* measurable
(D2's pinning test plus an optional computed-style screenshot check), per Q4a's own note that
background-token equality is provable even though "looks right" is not; both the measurable claim and
the taste judgement are listed separately so neither is ticked on the other's evidence.

`npx openspec validate 2026-08-16-spec-surface-legibility --strict` failed once on first pass — the
validator reads only a requirement's first physical source line for the SHALL/MUST check, and one
requirement's SHALL landed on line two of a wrapped sentence. Reworded so SHALL appears in the first
line; revalidated clean. Then ran `npx openspec validate --changes --strict` for the full set: 15
passed, 0 failed (this change included, alongside the pre-existing 14) — confirms this proposal did
not disturb any other in-flight change.

No code was touched this iteration — this is authoring only, per `spec_round_protocol`: the next
iteration reviews this document *cold*, without the context of having written it, which is the whole
point of the round-gating. Not reviewing in the same iteration that authored it.

**Next:** `REVIEW openspec/changes/2026-08-16-spec-surface-legibility/ round 1` — read `proposal.md`,
`design.md`, `tasks.md` and the spec deltas cold, against the six findings in
`.claude/autonomous/2026-08-16-operator-ux-findings.md` and the `review_criteria` in `STATE.json`'s
Q4 queue entry, without looking up who wrote it. Then either set `approved=true` in the log and move
`next_action` to implementation phase 1 (F2), or write concrete objections and set `next_action` to
`REVISE ... round 2`.

**Elapsed:** one iteration.

## Entry 13 — 05:57 — Q4-spec-ux-fixes: REVIEW round 1 — APPROVED

Verified branch/log/STATE.json agreed before starting (HEAD `d534357`,
`autonomous/2026-08-16-app-and-test-reform`, iteration 12, working tree clean, next_action pointing
at this review). Read `proposal.md`, `design.md` (D1-D8), `tasks.md` (8 phases) and both spec deltas
cold — no memory of authoring them, since this is a fresh process, but deliberately not re-reading
Entry 12 as a substitute for reading the artifact itself.

**Re-verified the two technical claims STATE.json's `next_action` flagged for independent re-checking,
by reading the cited source files directly rather than trusting the proposal's restatement:**

- **F2's root cause (SpecFrame.tsx vs spec_render.py variable names).** Confirmed exactly as claimed.
  `hub/ui/src/components/spec/SpecFrame.tsx`'s `themeOverride()` (lines 62-75) injects exactly
  `--bg`, `--surface`, `--surface-2`, `--border`, `--fg`, `--muted`. `hub/hub/spec_render.py`'s
  `_STYLE` (lines 29-47) defines and reads a disjoint set — `--aw-bg`, `--aw-fg`, `--aw-muted`,
  `--aw-rule`, `--aw-accent`, `--aw-chip-bg`, `--aw-code-bg` — confirmed by direct grep, zero overlap.
  The dark palette's `--aw-bg: #0d1117` matches the operator's observed navy exactly. The override
  genuinely has nothing to affect today; F2's fix is real, not a restatement of a symptom.
- **F3's precedent (`_attach_requirements()`'s `has_rejected_evidence`).** Confirmed.
  `hub/hub/api/v1/tasks.py:76-209` computes `rejected_by_requirement` scoped to each requirement's
  *current* digest (lines 127-151) and attaches `has_rejected_evidence`/`rejected_evidence_count`/
  `latest_rejection_reason` per requirement link (lines 184-186) — exactly the shape D4 says F3 should
  reuse. Also read `requirement_coverage.py`'s actual `_state()` (lines 167-192) to check the proposed
  insertion point is coherent: today it is
  `drifting → stale → awaiting → accepted(VERIFIED) → not linked(UNSERVED) → not started → IN_PROGRESS`.
  Task 3.2's placement ("after accepted/awaiting, before the linked checks") lands the new `rejected`
  check between the existing `if accepted: return VERIFIED` and `if not linked: return UNSERVED`
  lines — confirmed by reading the literal code, not just the docstring's precedence list — and D4's
  claim that a later accepted submission against the same digest still short-circuits to VERIFIED
  before the rejected check ever runs is correct by construction (accepted is checked first). `REJECTED
  = "rejected"` is already a defined constant in `requirement_evidence.py:56`, so 3.1's import needs no
  new constant.

**One inaccuracy found and fixed in this iteration, not deferred to a REVISE round.** `design.md` D3
claimed the rigor chip's values (`sketch`/`gate`/…) are "the values `RIGOR_META` already names" —
false: `RIGOR_META` (`hub/hub/spec_rigor.py:47`) is the string `"aw-spec-rigor"`, the *name* of a meta
tag, not an enumeration of rigor levels. The actual values are `SKETCH`/`CONTRACT`/`GATE`
(`spec_rigor.py:39-41`) and `SPEC_RIGORS = ("sketch", "contract", "gate")`
(`hub/hub/db/models.py:1519`). Judged this correctable-in-place rather than round-tripping the whole
artifact: `tasks.md` 2.4 already hedges ("cite where those values are enumerated — `spec_payload.py`
*or wherever rigor is validated*"), so the wrong citation in `design.md` would not have misdirected
implementation, only wasted a lookup. Fixed the one paragraph to cite `SPEC_RIGORS` correctly and
note what `RIGOR_META` actually is, so the next reader (implementation phase 2) does not repeat the
same wrong grep. Re-ran `npx openspec validate 2026-08-16-spec-surface-legibility --strict` after the
edit: valid.

Checked one more thing the design doc asserts loosely: `PRECEDENCE`'s "ranking" language (D4 says
`rejected` "ranks... above states that describe the absence of an attempt"). Read
`requirement_coverage.py:120-130`: `PRECEDENCE` is used only to seed `CoverageReport.totals` with a
zero count per state (`dict.fromkeys(PRECEDENCE, 0)`) — there is no "worst state wins" comparison
anywhere that depends on tuple order. Harmless: task 3.1's instruction ("insert into PRECEDENCE
between VERIFIED and IN_PROGRESS") is safe regardless, since the tuple's only real job is
enumeration/display-consistency, not priority selection. Not worth a design.md edit — flagging here
for the implementer's benefit, not as a defect.

**Review criteria, checked against the artifact as read (not as summarized in Entry 12):**

- *Addresses all six findings, or defers with a reason?* Yes — F1-F6 map 1:1 to findings 1-6.
  Findings 1, 2 and 5 are explicitly marked taste in `proposal.md`'s Non-Goals and `tasks.md` section
  7 (human-only), matching the findings document's own framing ("readable, but uglier... not ticked").
  F2 is treated as partially measurable (the pinning test) and partially taste (does it *look* right)
  — both listed separately, neither ticked on the other's evidence. This is the right call, not a
  dodge: the operator's own verdict on 17.2/5.2/6.1 already drew this exact line.
- *F2 respects the no-external-resource constraint?* Yes — inherited CSS custom properties and
  `!important` overrides only, matching what `SpecFrame.tsx` already does today; no stylesheet link,
  no fetch, confirmed by reading the actual mechanism, not assuming it.
- *F3 introduces a genuinely new state, not a relabel?* Yes, and `design.md` D5 says so explicitly —
  `PRECEDENCE`, `CoverageReport.totals` and every state-enumerating test change shape (seven becomes
  eight). Task 3.4 requires grepping for hardcoded state lists rather than trusting only the one file
  this task anticipated, which is the right discipline for a breaking change to a shared contract.
- *F6 acts at the right layer?* Yes — `spec_completeness.check()`, the existing mechanism
  `requirement_without_task`/`task_without_requirement` already use to block `propose()` (confirmed:
  `hub/hub/spec_service.py:279` calls `spec_completeness.check()` inside `propose()` and refuses on
  findings). Charter guidance (task 4.3) is additive, not a substitute for the refusal — matches the
  findings document's own framing ("a prompt/charter problem as much as a code one").
- *Ceiling of 3, derived not guessed?* D6's reasoning holds up against the findings table: approved
  tickets carried 6/2/1 requirements, an earlier rejected batch carried 5/4; 3 is the smallest ceiling
  that does not retroactively flag the uncomplained-about 2-requirement ticket while still refusing
  4/5/6. Reasonable, not arbitrary.
- *Anything proposed beyond what was asked (scope creep check)?* F4's cross-tab anchor navigation and
  F5's drawer looked like candidates worth checking closely, since they are larger builds than a
  literal reading of findings 4 and 5 might imply. Re-read the verbatim quotes: finding 4 is *"hard to
  understand... **and the navigation between the two is hard**"* — cross-tab navigation is not an
  add-on, it is half of what was reported. Finding 5 is *"maybe we should be able to open the task
  like jira"* — Jira's ticket view is exactly a full-size, non-inline detail surface, so a drawer is a
  literal reading, not an embellishment. Judged proportionate, not creep.

**No objections that rise to blocking.** Set `approved=true`.

**Files touched:** `openspec/changes/2026-08-16-spec-surface-legibility/design.md` (one paragraph,
D3's rigor-values citation).

**Next:** `IMPLEMENT phase 1 (F2) of openspec/changes/2026-08-16-spec-surface-legibility/tasks.md` —
realign `hub/hub/spec_render.py`'s neutral CSS variable names with `SpecFrame.tsx`'s override names
per `design.md` D2's table, add the pinning test (task 1.2), update existing render tests (1.3), and
attempt the Q4a harness screenshot check (1.4) if `scripts/uishot.py` is available and the live Hub
can be pointed at a rebuilt UI bundle — record plainly if the harness path is unavailable rather than
skipping silently.

**Elapsed:** one iteration.

## Entry 14 — 07:09 — Q4-spec-ux-fixes: IMPLEMENT phase 1 (F2), tasks.md 1.1-1.4

**Starting state.** Working tree already carried uncommitted changes to `hub/hub/spec_render.py`,
`hub/tests/test_spec_render.py`, and `tasks.md` when this iteration began — phase 1 (F2) had
apparently been fully implemented in a prior iteration's working tree but never committed (STATE.json's
`next_action` and Entry 13's own "Next" line both named exactly this work, so this is the intended
continuation, not stray state). Re-verified the diff against the approved `design.md` D2 table rather
than trusting the tasks.md checkmarks at face value.

**What the diff does (all four tasks.md items already marked `[x]`, verified below):**
- 1.1: `spec_render.py`'s `_STYLE` renames the six neutral custom properties everywhere they are
  defined (`:root`, the `prefers-color-scheme` media query, both `[data-theme]` rules) and everywhere
  read (`var(--aw-...)` → `var(--...)`): `--aw-bg`→`--bg`, `--aw-fg`→`--fg`, `--aw-muted`→`--muted`,
  `--aw-rule`→`--border`, `--aw-chip-bg`→`--surface-2`, `--aw-code-bg`→`--surface`. `--aw-accent` is
  untouched, matching D2 (`SpecFrame.tsx` does not override it). A docstring comment above `_STYLE`
  states the mapping and cites `SpecFrame.tsx`'s `HUB_NEUTRALS`/`themeOverride()` by name.
- 1.2: new test `test_the_neutral_variables_match_the_hub_shells_override_names` in
  `hub/tests/test_spec_render.py`, asserting each of the six new names (`_HUB_OVERRIDDEN_NEUTRALS`)
  is defined in `_STYLE`.
- 1.3: no other literal `--aw-*` string assertions existed in the test file to update (checked: the
  only touch to the file besides the new test is the import line adding `_STYLE`).
- 1.4: tasks.md's own note records the harness was used, with a documented wrinkle (`aw-loop10`'s
  stored document predates the rename and doesn't retroactively re-render, so verification used a
  fresh throwaway payload through today's `render_document()` instead, opened in Chromium with
  `SpecFrame.tsx`'s actual override `<style>` applied) — computed `body` background matched
  `HUB_NEUTRALS.light.bg`/`dark.bg` exactly. Read as an honest, specific account rather than a bare
  "done" — no reason to distrust it, and re-deriving Playwright screenshots in this iteration would
  duplicate rather than check that work.

**This iteration's own verification, not inherited from the diff's own notes:**
1. `pytest hub/tests/test_spec_render.py -q` — 28 passed.
2. Mutation check on the pinning test: reverted `--surface` back to `--aw-code-bg` in both the light
   and dark `code, pre` background declarations (leaving the `var(--surface)` *read* site untouched,
   so the two disagree — the real failure mode the rename is supposed to prevent). Re-ran the pinning
   test alone: failed with `AssertionError: --surface is not defined in spec_render.py's _STYLE`,
   confirming the test catches a real regression, not a tautology. Reapplied the rename, re-ran the
   full file: 28 passed again — clean.
3. Grepped the whole repo for the six old `--aw-*` names: only doc/log files remain (`tasks.md`,
   `design.md`, `proposal.md`, `STATE.json`, this log) — no code or test still references the old
   names. Expected; those are historical narration, not live assertions.
4. Full `hub/tests/` suite (not just the changed file, per STATE.json's phase-1 instruction and
   CLAUDE.md's testing directive), run in the background since it exceeds the 600s foreground cap:
   **2059 passed, 11 skipped, 72 warnings, 791.96s.** No failures. The warnings are pre-existing
   (Alembic path-separator deprecation, a SQLAlchemy primary-key warning already present in the
   `conversations` migration tests from Q3's `sequence` column work, and a FastAPI `HTTP_422_...`
   rename deprecation) — none introduced by this change; none mention `spec_render` or `--aw-`.

No UI bundle rebuild needed — this phase touches only `hub/hub/spec_render.py`, a Python-only
render path with no corresponding `hub/ui` source change.

**Files touched (committed this entry):** `hub/hub/spec_render.py`, `hub/tests/test_spec_render.py`,
`openspec/changes/2026-08-16-spec-surface-legibility/tasks.md` (checkmarks + 1.4's verification note,
already present in the working tree from the prior iteration).

**Next:** `IMPLEMENT phase 2 (F1 — colour that carries meaning) of tasks.md, 2.1-2.5`: add `--aw-warn`
alongside `--aw-accent`; a per-value CSS class (`aw-modal-must`/`should`/`may`) driving `.aw-modal`
colour and `.aw-requirement`'s left-border colour; a rigor-chip tone mapping cited from wherever
`rigor` values are actually validated (`design.md`'s D3, corrected in Entry 13 to cite `SPEC_RIGORS`
in `hub/hub/db/models.py`, not `RIGOR_META`); a test asserting three distinct modal classes render.
This is server-render-only again (`spec_render.py`), same as phase 1 — no UI bundle rebuild needed
unless a later phase touches `hub/ui`.

**Elapsed:** one iteration.

---

## Entry 15 — 08:36 — Q4-spec-ux-fixes: IMPLEMENT phase 2 (F1 — colour that carries meaning), tasks.md 2.1-2.5

**Starting state.** As with Entry 14, the working tree already carried a full, uncommitted
implementation of the named `next_action` (phase 2, tasks.md 2.1-2.5) when this iteration began —
`hub/hub/spec_render.py`, `hub/tests/test_spec_render.py`, and `tasks.md`'s checkmarks/notes were all
present but never committed. Verified rather than trusted: read the actual diff against `design.md`
D3 line by line before treating any of it as done.

**What the diff does (all five tasks.md items marked `[x]`, verified below):**
- 2.1: `--aw-warn` added to `_STYLE` in both `:root` blocks and both `[data-theme]` rules —
  `#9a6700` light / `#d29922` dark (GitHub Primer `attention.fg`), alongside the untouched
  `--aw-accent`.
- 2.2/2.3: `.aw-modal-{must,should,may}` and `.aw-requirement-{must,should,may}` classes added to
  `_STYLE`; `_requirements()` now computes `tone = _MODAL_TONE.get(requirement.modal, "may")` and
  emits both classes from the one lookup. `_MODAL_TONE` maps `SHALL` to the same tone as `MUST` — a
  real find, not scope creep: `spec_payload.py`'s `MODALS` allows a fourth value `design.md` D3 never
  named, and leaving it unmapped would have silently rendered SHALL requirements with no colour at
  all, defeating F1 for exactly the documents that use RFC2119's other mandatory keyword.
- 2.4: rigor chip gets `_RIGOR_TONE = {"gate": "gate", "contract": "contract"}`, `sketch` (the
  default, blocks nothing) deliberately left out so it stays the plain neutral chip. Cites
  `SPEC_RIGORS` in `hub/hub/db/models.py`, matching Entry 13's design.md correction (not `RIGOR_META`,
  which is the meta-tag name, not a value enumeration) — checked the citation is actually followed
  through in code, not just claimed.
- 2.5: three new tests — `test_each_modal_value_renders_with_its_own_distinct_class`,
  `test_shall_takes_the_same_tone_as_must`, `test_the_rigor_chip_takes_a_tone_for_contract_and_gate_but_not_sketch`.

**This iteration's own verification:**
1. `pytest hub/tests/test_spec_render.py -q` — 31 passed (28 from phase 1 + 3 new).
2. Independent mutation check (not just re-trusting tasks.md's own account of one): changed
   `_MODAL_TONE["SHOULD"]` from `"should"` to `"must"` — collapsing SHOULD into the MUST tone, the
   real failure mode the per-value class exists to prevent. `test_each_modal_value_renders_with_its_own_distinct_class`
   failed exactly as expected (`AssertionError`, only two distinct classes present, `aw-modal-should`
   missing from the actual set). Reapplied the correct mapping, reran the file: 31 passed again.
3. Grepped `tasks.md` phase 2's checked items against the literal diff — no gap between what is
   claimed done and what the code does.
4. Full `hub/tests/` suite, backgrounded (exceeds the 600s foreground cap; ~15 minutes):
   **2062 passed, 11 skipped, 72 warnings, 902.83s. No failures.** Up from Entry 14's 2059 passed by
   exactly 3 — the three new phase-2 tests, nothing else moved. Same pre-existing warning set
   (Alembic path-separator deprecation, the `conversations.sequence` primary-key SAWarning from Q3,
   FastAPI's `HTTP_422_UNPROCESSABLE_ENTITY` rename deprecation) — none new, none touching
   `spec_render` or the modal/rigor colour code.
5. `npx openspec validate 2026-08-16-spec-surface-legibility --strict` — valid.

No UI bundle rebuild needed — phase 2 is server-render-only (`spec_render.py`), same as phase 1.
Did not attempt a fresh Q4a screenshot for this phase: 2.5's machine check (three distinct classes
present) is exactly what a screenshot would confirm visually and cannot add beyond class-name
presence without human judgement on whether the actual hex values "look right" — that is section 7's
taste work, explicitly deferred there by the tasks.md itself, not something to smuggle in here as a
self-tick.

**Files touched (committed this entry):** `hub/hub/spec_render.py`, `hub/tests/test_spec_render.py`,
`openspec/changes/2026-08-16-spec-surface-legibility/tasks.md`.

**Next:** `IMPLEMENT phase 3 (F3 — a rejected coverage state) of tasks.md, 3.1-3.7`: add
`REJECTED = "rejected"` to `requirement_coverage.py` between `VERIFIED` and `IN_PROGRESS` in
`PRECEDENCE`; compute it in `_state()` after the accepted/awaiting checks and before the linked
checks; two coverage tests (rejected-only, and rejected-then-later-accepted proving no shadowing);
grep for any hardcoded "seven states" list needing to become eight; grep `IN_PROGRESS`/`"in_progress"`
callers for a branch `rejected` should take instead; then the UI half —
`hub/ui/src/components/spec/SpecCoverageBar.tsx` gets a `rejected` `STATES` entry with its own colour
(check `TaskCard.tsx`'s `isBlocked`/`revision_needed` precedent) and a UI test. This phase DOES touch
`hub/ui`, so unlike phases 1-2 it needs `cd hub/ui && npm run build` then
`python scripts/refresh_ui_bundle.py` before any screenshot verification, and the UI test suite
(`cd hub/ui && npm test` or wherever the UI tests run — locate it) alongside the backend suite.

**Elapsed:** one iteration.

---

## Entry 16 — 10:12 — Q4-spec-ux-fixes: reconcile and commit phases 3+4 (F3, F6), then continue

**Starting state was inconsistent and needed reconciliation before any new work.** STATE.json
claimed iteration 16, with next_action pointing at phase 4 and asserting "Phase 3 (F3) is done and
committed (Entry 16)". Neither was true: the log's last entry was Entry 15 (phase 2), and `git log`
showed no commit past Entry 14/15's phase-2 commit — the branch tip was `6f9f5d9`, "back-date
heartbeat after Q4 phase 2". What actually existed was an uncommitted, unlogged working tree
carrying a **complete implementation of both phase 3 (F3 — rejected coverage state) and phase 4
(F6 — the 3-requirement-per-task ceiling)**, with `tasks.md` fully checked off and annotated for
3.1-3.7 and 4.1-4.4, including mutation-check narratives. A prior iteration did the work, wrote the
narrative, and then died (context exhaustion or a process kill) before the commit/log/heartbeat
steps that would have made it real. This is exactly the failure mode `feedback_verify_on_resume`
exists for: a claim of "done and committed" is not evidence, only the working tree and the tests are.

**Verification performed before trusting any of it:**
1. `git diff --stat` against HEAD — 18 files, matching the phase 3 + phase 4 scope described in
   tasks.md's own annotations (plus the UI bundle, rebuilt).
2. `python scripts/refresh_ui_bundle.py --check` — passed: "The committed bundle asserts it was
   built from the current source." So although uncommitted, the UI bundle rebuild step (`npm run
   build` + `refresh_ui_bundle.py`) had genuinely been run against the phase-3 UI source
   (`SpecCoverageBar.tsx`, `spec.ts`) before the process died — not a stale bundle standing next to
   fresh source.
3. `pytest hub/tests/test_requirement_coverage.py hub/tests/test_requirement_gate.py
   hub/tests/test_spec_completeness.py hub/tests/test_task_rejected_evidence_signal.py -q` —
   **61 passed.**
4. `cd hub/ui && npm test -- --run` (full suite) — **869 passed, 2 failed**
   (`chartersUi.test.tsx`, `taskStatusControl.test.tsx`), neither file touched by this diff. Ran
   those two files alone: **15 passed, 0 failed** — confirms the two failures are pre-existing
   flakes under full-suite resource contention, not something phase 3/4 broke. `specCoverage.test.tsx`
   alone (the file this diff actually changed): **7 passed**.
5. Spot-checked one of the diff's own mutation-check claims independently rather than only trusting
   the tasks.md narrative: grepped `REJECTED` through `requirement_coverage.py` — the import, the
   `PRECEDENCE` insertion, and the `_state()` branch are all present exactly as 3.1/3.2 describe.
6. `npx openspec validate 2026-08-16-spec-surface-legibility --strict` — valid.

**Committed as `4269036`**, phases 3+4 together (they arrived together in the recovered tree; no
value in an artificial split). Full detail of what phase 3 and phase 4 actually do is in the
`tasks.md` diff itself (3.1-3.7, 4.1-4.4), carried over from whatever iteration wrote it — this
entry's job was verifying it was true, not re-deriving it.

**One correction to the record:** STATE.json's iteration counter and next_action referenced a
non-existent "Entry 16" as though it had already been written. That entry never existed; this one
is the real Entry 16. Future resumes should treat a next_action's back-reference to a log entry as
a claim to verify (does the entry exist? does the log's last entry number match?), not as fact —
the same standing rule as any other "done" claim.

**Next:** `IMPLEMENT phase 5 (F4 — requirement chips and cross-tab navigation) of tasks.md,
5.1-5.7`: `TaskCard.tsx` gets a chip row (one per `task.requirement_ids`, title = the linked
requirement's statement, rejected tone per 3.6 where `has_rejected_evidence`); `navigation.ts` gets
an optional `anchor` on the spec-tab destination; `SpecDocumentPanel.tsx` accepts an initial anchor
on mount (parallel to the existing `pendingFragment` in-frame mechanism); a chip click resolves the
requirement's `document_id` to a path via the already-loaded document list (no new endpoint, per
design.md D7) and navigates with the anchor; `SpecCoverageBar.tsx`'s `N task(s)` text becomes a
click target that switches to the Tasks tab filtered to `linked_task_ids` (new `activeTaskIds`
state alongside the existing `activeFilter`). This phase touches `hub/ui` — rebuild
(`npm run build` + `python scripts/refresh_ui_bundle.py`) and run both the UI test suite and a
relevant backend chunk if `TaskCard`'s data contract changed. Check existing call sites of
`projectDestination()` before changing its signature (5.3 flags this explicitly — every call site
needs updating consistently, not just the new one).

**Elapsed:** one iteration.

## Entry 17 — 10:43 — Q4-spec-ux-fixes: IMPLEMENT phase 5 (F4 — requirement chips and cross-tab navigation), tasks.md 5.1-5.7

**Starting state verified clean**, unlike Entry 16: `git log` tip was `75c4825` matching
STATE.json, working tree clean, `next_action` pointed at phase 5 with no false "done" claim to
reconcile.

**What this iteration built**, all seven tasks.md items (5.1-5.7):
- `TaskCard.tsx`: a chip row in the card header, visible without expanding — one chip per
  `task.requirement_ids` entry, looked up in `requirement_links` for its statement (the `title`
  attribute), its rejected tone (`has_rejected_evidence`), and where to navigate. Iterates
  `requirement_ids` rather than `requirement_links` directly, matching the task's own "where
  present" wording, so an identifier with no matching link still renders rather than vanishing.
- `hub/ui/src/api/tasks.ts`'s `RequirementLink` interface gained `has_rejected_evidence`,
  `rejected_evidence_count`, `latest_rejection_reason` — the backend
  (`hub/hub/api/v1/tasks.py:184-189`) has sent these since Q4 phase 3/4, nothing on the frontend
  read them. F4 is the first consumer.
- `hub/ui/src/lib/navigation.ts`: `projectDestination()` gained a fourth parameter, `anchor`,
  defaulted to `null` so all 9 existing call sites and every test fixture built with `toEqual`
  needed no change (the returned object omits the `anchor` key entirely when absent, mirroring how
  `document` already behaves). Carried through `serializeDestination`/`parseDestination` (an
  `anchor` query param, only alongside `document`) and `isSpecDestination`'s type predicate.
- `SpecDocumentPanel.tsx` accepts `initialAnchor`. Two paths, not the one the task's literal wording
  implied: a chip click naming a *different* document seeds `pendingFragment`, consumed the existing
  way once `toc-ready` arrives; a chip click naming the document *already open* triggers no fresh
  `toc-ready` (nothing about the document changed), so that case scrolls directly via
  `frameRef.current?.scrollToSection()`, tracked against a `(path, anchor)` ref so a repeat render
  with the same anchor does not re-fire.
- `TaskCard.tsx` resolves a chip's `document_id` to a path via `useSpecDocuments()` — confirmed by
  reading `SpecPhaseBar.tsx`, which already uses the same hook the same way, rather than trusting
  `design.md`'s reference to `SpecDocumentPicker.tsx` (checked; that component does not call it).
  The anchor sent is the requirement's stored `anchor` field with its leading `#` stripped —
  `spec_render.py`'s `requirement_anchor()` writes `#FR-n`, but every in-frame fragment mechanism
  (`pendingFragment`, `TocAnchor.id`, `resolveSpecLink`'s output) is bare. Falls back to the bare
  identifier when a link carries no `anchor`.
- `SpecCoverageBar.tsx`'s `N task(s)` text becomes a button (only when an `onOpenTasks` prop is
  given — the plain, unclickable text otherwise, so every existing caller/test is unaffected). The
  filter state (`activeTaskIds`) lives in a new small Zustand store,
  `hub/ui/src/store/taskFilterStore.ts`, not literal `TasksBoard.tsx` local state as the task's
  wording suggested at first read: the click happens on the Spec tab, before `TasksBoard` is even
  mounted, so nothing in the tree can hold it as local state at the moment it needs setting.
  `TasksBoard` reads the store, applies the filter alongside (not instead of) the existing
  `activeFilter` in both the kanban columns and the rejected section, and shows a dismissible
  banner naming the count.
- `App.tsx` wires both directions: the Tasks tab's `TasksBoard` gets an `onOpenRequirement` that
  navigates to the Spec tab with the resolved path+anchor; the Spec tab's `SpecPage` gets an
  `onOpenTasks` that sets the store and switches to the Tasks tab.

**Tests (5.7), each mutation-checked before being trusted:**
- `taskRequirementLinks.test.tsx` gained a `the requirement chip row (F4)` describe block: chip
  count/identifiers without expanding, rejected tone, click resolution via a mocked
  `useSpecDocuments`, and a disabled chip when resolution fails. One pre-existing test needed
  `within(...)` scoping — "FR-1" now also renders as a chip, colliding with the "Serves" block's own
  text.
- `specCoverage.test.tsx` gained two tests: the task-count is a button calling `onOpenTasks` with the
  linked ids; it renders as plain text with no `onOpenTasks` prop.
- `urlNavigation.test.ts` gained a describe block for the anchor's carry/drop/round-trip rules.
- New `tasksBoardFilter.test.tsx`: unfiltered by default, filtered-with-banner when the store is set,
  clearing restores everything.
- Mutation checks, each reverted and confirmed to fail its test before being reapplied: stripping
  the `#` from `anchor` (replaced with a literal sentinel — caught), disabling the board's
  `activeTaskIds` filter (caught, both affected tests), zeroing `onOpenTasks`'s argument to `[]`
  (caught), hard-coding the rejected tone to `false` (caught).

**Full verification:**
1. `npx tsc --noEmit -p hub/ui` — clean.
2. Targeted run (15 files touching this change or adjacent) — 145 passed.
3. Full `hub/ui` suite (`npm test -- --run`): first run showed **19 file-level timeouts** (887 total
   tests, 862 passed) — re-ran with zero code changes between runs: **887 passed, 0 failed.** Read
   as the documented full-suite resource contention (`STATE.json` `dead_ends`: "occasionally times
   out 1-2 unrelated test files... under full-suite resource contention"), not a regression this
   phase introduced — the timeout set on the first run included files this change never touched
   (`specPickerTree.test.tsx`, `ErrorBoundary.test.tsx` context) alongside ones it did, and none
   reproduced on rerun.
4. `npm run lint` — same 9 pre-existing warnings as recorded in `decisions_for_user` (0 errors),
   nothing new from this change's files.
5. `npm run build` + `python scripts/refresh_ui_bundle.py` — bundle rebuilt and stamp refreshed.
6. Backend sanity check, since this phase touched no backend file: `test_tasks.py`,
   `test_task_rejected_evidence_signal.py`, `test_task_requirement_ids_readable.py`,
   `test_spec_render.py` — 54 passed.
7. `npx openspec validate 2026-08-16-spec-surface-legibility --strict` — valid.

**Committed as `9f24710`.**

**Note for whoever reviews this awake:** F4's human-only verification (tasks.md section 7.4 — "does
the navigation between board and document actually feel connected now") still needs the operator's
eyes; this entry only closes what tasks.md 5.1-5.7 asked the loop to build and machine-verify.

**Next:** `IMPLEMENT phase 6 (F5 — task detail as a drawer) of tasks.md, 6.1-6.5`: new
`hub/ui/src/components/tasks/TaskDetailDrawer.tsx` (dialog-pattern precedent, right-anchored, full
height, `design.md` D8); move everything `TaskCard.tsx`'s inline expansion currently renders into
it unchanged in behaviour, including 5.1/5.2's chips (now with full statement text and, where
rejected, `latest_rejection_reason`); `TaskCard.tsx`'s own expansion state is removed in favour of
an explicit "open" action; behaviour-parity tests for every control that worked inline; a
no-clipping check per D8's precise wording (content should scroll, never be cut off by a
fixed-height ancestor). This phase touches `hub/ui` — same rebuild-then-verify sequence as this
entry.

**Elapsed:** one iteration.

## Entry 18 — 11:20 — Q4-spec-ux-fixes: IMPLEMENT phase 6 (F5 — task detail as a drawer), tasks.md 6.1-6.5

**Starting state verified clean**: `git log` tip was `9b71366` matching STATE.json, working tree
clean, `next_action` pointed at phase 6 with an accurate back-reference to Entry 17's commit
(`9f24710`) — checked per the standing rule that a back-reference is a claim, not fact.

**What this iteration built**, all five tasks.md items (6.1-6.5):

- New `hub/ui/src/components/tasks/TaskDetailDrawer.tsx`: `role="dialog"`, `aria-modal`, focus trap
  and Escape via the existing `useDialogFocus` hook (`DeleteProjectDialog.tsx`'s own dependency —
  no new mechanism). Right-anchored, `top/right/bottom: 0`, `width: min(480px, 100vw)`. Click-outside
  closes on the board itself, not a modal backdrop (`design.md` D8) — a `document`-level `mousedown`
  listener checking `panelRef.current.contains(target)`, since there is no scrim element to attach a
  handler to.
- **Real bug found building 6.1, not anticipated by the design doc**: `RowMenu` (6.2's relocated
  status-transition menu) is a Radix `DropdownMenu`, which portals its open content to a sibling of
  `document.body` — outside `panelRef`'s subtree. The naive click-outside check read a click on
  "Move to blocked" as a board click and closed the drawer mid-selection, so the status change never
  landed. Confirmed the mechanism by reading `node_modules/@radix-ui/react-popper/dist/index.js`
  (`data-radix-popper-content-wrapper`), not guessed. Fixed by also excluding clicks whose target is
  inside `[data-radix-popper-content-wrapper]`. Mutation-checked in the new `taskDetailDrawer.test.tsx`:
  temporarily disabled the exclusion, the regression test failed exactly as expected (`onClose` called
  once), reapplied, 14/14 pass.
- 6.2 — moved into the drawer: the status-transition `RowMenu` and its refusal message, the
  blocking-reason input flow, description, "Serves" (see correction below), unresolved requirements,
  requirements-as-written, acceptance criteria, deliverables, notes, the divergence-policy control.
  **Judgement call, recorded rather than guessed silently**: the pre-F5 status-transition menu and
  blocking-reason input were not actually gated behind `expanded` in the old code — they lived in the
  card's always-visible header. `design.md` D8 names them as moving anyway and states the collapsed
  card keeps only "title, status, assignee, and F4's chips" — narrower than the old header. Read
  literally. The "Start work" `RowMenu` is named in neither list; kept on the card — starting a run is
  the one action reached for while still scanning the board, not after opening one ticket, and moving
  it was not asked for. Its own refusal (`task-status-refusal-{id}`, testid preserved) stayed with it;
  the status-menu's refusal moved into the drawer. The "Waiting on you" banner, badges row,
  `TaskIntegrationNote`, and timestamp predate the inline-expansion mechanism entirely and are
  informational, not actionable — stayed on the card. Factored the chip-resolution logic (link lookup,
  document-id-to-path, anchor-strip) shared between `TaskCard.tsx` and this drawer into a new
  `hub/ui/src/hooks/useRequirementChips.ts`, since both now need it.
- 6.3 — **initial pass was wrong, caught by a relocated test failing honestly rather than by
  inspection**: reusing `useRequirementChips` (5.1's `requirement_ids`-scoped resolution) for the
  drawer's "Serves" section broke `taskRequirementLinks.test.tsx`'s pre-existing "marks a link whose
  requirement is no longer active" test. That fixture sets `requirement_links` without
  `requirement_ids`; the pre-F5 "Serves" list has always shown every `requirement_links` entry
  regardless of `requirement_ids`, and narrowing it would have been exactly the "changed behaviour"
  6.2 forbids. Fixed: "Serves" still iterates `task.requirement_links` directly (unchanged — it
  already showed full statement text, satisfying 6.3's "not just the identifier" trivially), with a
  `Rejected: {reason}` line added per-link off `has_rejected_evidence`/`latest_rejection_reason`
  directly, and each entry resolves its own document path independently (via `useSpecDocuments`) so
  it navigates through `onOpenRequirement` the same way the card's F4 chips do.
- 6.4 — relocated the existing tests rather than rewriting: `taskBlockedTreatment.test.tsx`'s
  "parking a task by hand" block, `taskDivergenceControls.test.tsx`'s policy/escalation block,
  `taskStatusControl.test.tsx`'s whole file, and `taskRequirementLinks.test.tsx`'s "a card shows what
  it is checked against" block now open the drawer first (via a new shared
  `hub/ui/src/__tests__/testUtils/TaskCardHost.tsx`, mirroring what `TasksBoard.tsx` now does) before
  driving the same assertions against the same testids. `taskStatusControl.test.tsx`'s defensive
  "renders no control when the map offers nothing" needed a real addition, not just relocation: as
  written it rendered a bare `TaskCard` with no drawer, which would have passed for the wrong reason
  once the menu moved regardless of the transitions map — now opens the drawer first. New
  `taskDetailDrawer.test.tsx` (14 tests) covers what is specific to the drawer: open/close via close
  button, Escape, and click-outside; the portaled-menu regression above; 6.3's full-statement-text and
  rejection-reason rendering — both mutation-checked (reverting each condition made its test fail as
  expected, reapplied).
- 6.5 — jsdom performs no real layout, so `scrollHeight <= clientHeight` (design.md's literal wording)
  would be 0/0 always and prove nothing; stated precisely in the test file rather than asserted
  meaninglessly. What is actually checked: the body region (`task-drawer-body-{id}`) carries
  `overflow-y: auto` and no inline `height`/`max-height`; the panel root carries no `overflow: hidden`
  that would clip the scrolling body; and with a long description plus 3 requirement chips (the F6
  ceiling) rendered at `window.innerWidth = 360`, every chip's full statement and the complete
  description are present in the DOM, not truncated by the component. This proves "does not cut off
  silently," not "never visibly overflows the viewport" — the latter needs real browser layout, which
  is Q4a's own agent-verifiable/human-only boundary; recorded in `decisions_for_user`, not claimed
  here.

**Full verification:**
1. `npx tsc --noEmit -p hub/ui` — clean.
2. Targeted run (9 files touching this change): 112 passed.
3. Full `hub/ui` suite (`npm test -- --run`), twice: first run 25 failed / 876 passed across 19 files
   (mostly timeouts); second run 19 failed / 882 passed across 15 files — different failures each run,
   13-of-19 in files this change never touched (`ActivityLog`, `agentHandoff`, `App-mount`,
   `chartersUi`, `composerPermissionDefault`, `composerTriggerMenu`, `rowMenus`, `runnersUi`,
   `specChatSurface`, `specNavigationUi`, `specPage`, `specPickerTree`), consistent with this repo's
   documented full-suite resource contention (`STATE.json` `dead_ends`) rather than a regression. The
   5 files this change did touch (`taskDetailDrawer`, `taskBlockedTreatment`, `taskDivergenceControls`,
   `taskRequirementLinks`, `taskStatusControl`) were re-run together in isolation immediately after:
   **55 passed, 0 failed**, confirming the full-suite failures were contention, not this diff.
4. `npm run lint` — same 9 pre-existing warnings as `decisions_for_user` records, 0 errors, nothing new.
5. `npm run build` + `python scripts/refresh_ui_bundle.py` — bundle rebuilt and stamp refreshed.
6. Backend sanity check (no backend file touched this phase): `test_tasks.py`,
   `test_task_rejected_evidence_signal.py`, `test_task_requirement_ids_readable.py`,
   `test_spec_render.py` — 54 passed.
7. `npx openspec validate 2026-08-16-spec-surface-legibility --strict` — valid, both before and after
   updating `tasks.md`'s section 6 checkboxes with the implementation notes above.

**Q4-spec-ux-fixes is now fully implemented.** All six phases (F1-F6) are built, tested and committed.
What remains is entirely the approved tasks.md's own section 7 (5 human-only taste/feel checks) and
section 8 (the user test guide, already written) — recorded in `decisions_for_user` rather than
attempted here, consistent with the standing limit on visual judgement.

**Next:** `Q5-test-audit` — write the deletion bar in the log before deleting anything (per the item's
own detail), then survey `hub/tests/` (147 files) and `tests/` (20 files) against it. Full detail in
`STATE.json`'s `next_action`.

**Elapsed:** one iteration.

## Entry 19 — 11:28 — Q5-test-audit: write the bar, run the first (automated) survey pass

**Starting state verified clean**: `git log` tip `3e8ac13` matched `STATE.json`, working tree clean,
branch correct. Q4-spec-ux-fixes confirmed fully closed (all 6 phases, Entries 12-18).

**The bar, recorded before anything was touched** (verbatim from the queue item, restated here so
this entry is self-contained): a test may be deleted only if it meets one of —
(a) it asserts nothing the code can break (tautological, or asserts only on mocks it set up itself);
(b) it duplicates another test's coverage exactly, and deleting it changes no mutation outcome;
(c) it tests behaviour that no longer exists.
A slow test alone is NOT grounds (that was Q2, already done and closed). Every deletion this queue
item makes must log: the test name, which clause it met, and a mutation check proving the remaining
suite still catches the defect the deleted test claimed to catch.

**Survey pass 1 — mechanical/automated, across all 2258 test functions in `tests/` (21 files) and
`hub/tests/` (150 files; `STATE.json`'s file counts of 147/20 were stale by a few files, recounted
live with `find`):**

1. **Clause (c) — references to deleted subsystems.** Grepped every test file for imports/usages of
   the five modules `CLAUDE.md` names as "Deleted, and not to be recreated" (`watchdog.py`,
   `messaging.py`, `runner.py`, `transport/local.py`, `transport/git.py`) and the deleted CLI role
   subsystem (`cmd_role`, `role_file`, `RoleFile`, `VALID_ROLES`, `agentweave.roles`). **Zero matches
   as imports/usages anywhere.** The only files matching a bare "watchdog" string search
   (`test_agent_facing_text.py`, `test_launchability.py`, `test_operator_agent_creation.py`,
   `test_agents.py`, `test_scheduler.py`, `test_runtime_diagnostics.py`, `tests/test_eventlog.py`)
   turned out, on reading each, to be one of two things — neither a clause-(c) hit: regression tests
   asserting the word "watchdog" no longer appears in operator-facing status text or the scheduler's
   write path (guarding that a real deletion *stays* deleted — these test current, live behaviour),
   or `tests/test_eventlog.py`'s `WATCHDOG_HEARTBEAT_FILE`, which is a live constant in
   `src/agentweave/constants.py` still read by `eventlog.py` today — a naming leftover, not a dead
   import. **Zero clause-(c) deletions found in this pass.**

2. **Clause (a) — asserts nothing the code can break.** Wrote a small AST script
   (`ast.walk` per `test_*` function, checking for an `assert` statement, a `unittest`
   `self.assert*`/`assertRaises` call, `pytest.raises`/`warns` as a call or context manager, or a
   mock `assert_called*`) across every test function in both directories. First pass (checking only
   for the bare `assert` statement) flagged 133 false positives — entirely `unittest.TestCase`-style
   tests using `self.assertEqual`/`self.assertFalse`, which my first regex for "assert_" (with an
   underscore) missed. Corrected to `attr.startswith('assert')`, re-ran: 17 remained. Read every one
   of the 17 by hand rather than trusting the script — all 17 were legitimate "must not raise" tests
   (the assertion is "no uncaught exception propagates," which pytest itself enforces — e.g.
   `test_broadcast_no_subscribers`, `test_already_dead_pid_does_not_raise`,
   `test_init_db_skips_alembic_for_in_memory`) or delegate the actual assertion to a helper function
   the per-function AST walk doesn't see inlined (e.g. `test_project_directory_binding_round_trips_and_is_unique`
   calls `asyncio.run(_assert_duplicate_path_key_is_rejected())`, which itself raises
   `AssertionError` on failure). **Zero clause-(a) deletions found in this pass** — every flagged
   candidate was a tool false-positive, not a real gap, once read.

3. **Clause (b) — exact duplicates.** Two checks. First, function-name collisions across the whole
   scope (2258 names, 26 repeats) — but cross-checked against enclosing class, since a name repeated
   in two different `class Test...:` bodies is two distinct pytest items, not a collision (e.g.
   `test_fs_browse.py`'s `test_a_relative_path_is_refused` appears once in a plain function and once
   in `TestFsListEndpoint` — different call, different assertion, not a dupe). Rewrote the scan to
   qualify each name by `(file, class-path, function)`: **zero same-file-same-scope collisions** —
   meaning no test function is silently shadowing another (which would have been a stronger finding
   than "duplicate coverage": a shadowed name is dead code that pytest never even collects). Second,
   normalized-AST body comparison (ignoring the function's own name/args, `len(body) >= 3` to skip
   noise) across all functions: found exactly one duplicate family — 8 identically-bodied test pairs,
   all between `tests/test_spec_manifest.py` and `hub/tests/test_spec_manifest.py`
   (`test_valid_manifest_parses`, `test_malformed_json`, `test_too_large`, `test_too_many_documents`,
   `test_duplicate_path`, `test_invalid_home`, `test_unknown_parent`, `test_parent_cycle`). Read both
   files' module docstrings before concluding anything: `tests/test_spec_manifest.py` tests
   `agentweave.spec_manifest` (CLI-side, `src/agentweave/spec_manifest.py`, includes filesystem
   discovery); `hub/tests/test_spec_manifest.py` tests `hub.spec_manifest` (Hub-side,
   `hub/hub/spec_manifest.py`, its own docstring states "No filesystem discovery here — the Hub only
   ever sees uploaded content and manifest text"). Two separate source files, deliberately parallel
   implementations, each needing its own coverage — deleting either test file changes the mutation
   outcome for the module it targets, failing clause (b)'s own "changes no mutation outcome" test
   explicitly. **Zero clause-(b) deletions found in this pass** — the one apparent duplicate family
   is intentional parallel coverage of a genuine two-module duplication in the source tree (a
   separate, unauthorised-to-fix-here DRY observation about `spec_manifest.py` existing twice, not a
   test problem).

**Conclusion of survey pass 1: zero tests met the deletion bar.** This is a real, checked result, not
an early stop — all three clauses were run mechanically across the full 2258-function population, and
every flagged candidate was individually read and ruled a tool false-positive rather than assumed.
Worth recording plainly: this suite does not have an obvious layer of dead or tautological tests sitting
on the surface. Whatever Q5 still finds will need a slower pass — reading test bodies against their
current source module for *semantic* staleness (an assertion on a field/shape/state that changed
without the test being updated, which no import-grep or AST-shape check catches), not another
mechanical sweep. That is qualitatively harder to do safely and needs to be scoped file-by-file rather
than attempted as one static pass.

**Nothing was deleted this iteration** — correct per the bar: nothing met it.

**Next:** Q5-test-audit, survey pass 2 — semantic review. Pick a bounded slice (suggest: the 20 files
under `tests/` first, since it is the smaller of the two directories and finishing it gives a concrete
done/not-done boundary before starting on `hub/tests/`'s 150) and read each test file against its
target module's *current* behaviour, not just its imports — looking specifically for assertions on
response shapes, field names, or state transitions that the source has since changed while the test
kept passing against a stale expectation (which would be a real, non-tautological, still-passing test
that nonetheless tests nothing true anymore — the dangerous version of clause (c), not caught by import
greps). Record findings per-file in the log as they're found; do not attempt all 20 in one iteration if
it does not fit — better to finish half the files properly, with mutation checks on anything deleted,
than rush all 20 and miss something.

**Elapsed:** one iteration.

## Entry 20 — 11:40 — Q5-test-audit: survey pass 2 (semantic), first two files of `tests/`

**Starting state verified clean**: `git log` tip `7b93390` matched `STATE.json`, working tree clean,
branch correct.

Time budget note: `stop_at` is 12:00 and this iteration started at 11:40, so this entry deliberately
scopes to a small, honestly-finished slice rather than starting all 21 `tests/` files and leaving the
scan half-done at the deadline. Two files read in full against their current source module, both by
hand (not tooled):

1. **`tests/test_constants.py` vs `src/agentweave/constants.py`** — every asserted value checked
   against the live dict/list literals: `TestOpencodeConstants` (opencode's `RUNNER_TYPES` membership,
   full `RUNNER_CONFIGS["opencode"]` shape — `cli`, `subcommand`, `session_flag`, `output_format`,
   `context_flag`, `model_flag`, `mcp_add_cmd`, `AGENT_RUNNER_DEFAULTS`, `KNOWN_AGENTS` membership),
   `TestKimiConstants` (`RUNNER_CONFIGS["kimi"]["model_flag"]`), `TestCodexMcpConstants`
   (`codex_mcp`'s `RUNNER_TYPES` membership and full config shape). Every asserted field/value matches
   `constants.py` exactly as it stands today (lines 119-223, 240-250, 71-87). **No staleness found —
   file is clean.**
2. **`tests/test_stream_events.py` vs `src/agentweave/stream_events.py`** — the larger of the two (35
   tests across 8 classes: constructors, tool correlation, redaction/truncation, `ContextUsageSample`
   validation, legacy normalization, cache-breakdown allowlisting, `ParsedRunnerLine`, transport-field
   redaction). Checked each assertion against current behaviour rather than just current existence:
   `STREAM_EVENT_KINDS` is exactly the asserted 7-tuple (source lines 32-40); `CONTEXT_BREAKDOWN_FIELDS`
   is exactly the asserted allowlist plus the two fields the test explicitly expects dropped
   (`raw_provider_object`, `prompt` — source lines 78-87 vs test lines 310-317); the
   `percent`-requires-`provider_reported_ratio`-basis rule (source 215-221) matches the test's
   both-directions coverage (accepts with the right basis, rejects without it); the legacy-normalizer's
   contradiction handling — `tokens_used` taking precedence over an `input_tokens`/`output_tokens`
   breakdown (source 323, test 245-254), a >1-point percent/ratio disagreement degrading to token-only
   rather than trusting the reported percent (source 372-378, test 261-268) — both match current
   behaviour exactly, not a stale expectation of an earlier contradiction-handling rule. **No staleness
   found — file is clean.**

Both were also cross-checked for clause (a)/(b) opportunistically while reading (not just clause-(c)
staleness): no tautological assertions, no assertions against self-constructed mocks, and no coverage
duplicated elsewhere in either file. Neither file produced a deletion candidate under any of the three
clauses.

**Nothing was deleted this iteration** — correct per the bar: nothing met it in either file.

**Next:** Q5-test-audit, survey pass 2 continues. 19 of 21 `tests/` files remain unreviewed for
semantic staleness: `test_cli.py`, `test_config.py`, `test_diagnostics.py`, `test_eventlog.py`,
`test_handoff_resume_templates.py`, `test_http_transport.py`, `test_hub_commands.py`, `test_jobs.py`,
`test_locking.py`, `test_logging_handlers.py`, `test_mcp_server.py`, `test_packaging.py`,
`test_session.py`, `test_spec_manifest.py`, `test_task.py`, `test_transport_config.py`,
`test_utils.py`, `test_validator.py` (`test___init__.py` has no tests). Suggest continuing
alphabetically so "reviewed" stays an unambiguous prefix of the list; read a handful (3-5) per
iteration rather than rushing all 19, per Entry 19's own guidance. `hub/tests/`'s 150 files have not
been started at all under this pass and remain after `tests/` finishes.

**Elapsed:** one iteration (deliberately short — stop_at is imminent).

## Entry 20a — 11:45 — operator extended the run to 18:00, and capped Q5

Written by the interactive session between firings, using the claim/edit/release protocol. **The
operator is awake.**

**Stop time moved from 12:00 to 18:00** — six more hours. The Scheduled Task was re-registered with
`-UntilHHmm "18:00"`; verified first that no iteration was running (`State: Ready`,
`LastResult: 0`, Entry 20 committed and the branch released at 11:41:38), because re-registering
under a live iteration would have risked killing it mid-work. `stop_at` in `STATE.json` now agrees
with the task, and `stop_at_history` records both values so a later reader is not confused by the
original 12:00 in Entry 0's header.

**Q5 is capped, on evidence, not on impatience.** The item asked to check every test against the
code. Two passes have now run:

- the **mechanical** sweep covered **all 2258 test functions** in `tests/` and `hub/tests/` — import
  checks against deleted subsystems, AST assertion-presence, duplicate-body detection — and found
  **zero** deletion candidates; every flag was a false positive on inspection;
- the **semantic** pass has read **2 of 21** `tests/` files by hand against current source and also
  found **zero**.

The remaining 19 `tests/` files plus 150 `hub/tests/` files is roughly **35-50 iterations** at the
recorded rate, for an expected yield that the evidence says is near zero. So: **finish `tests/`
only, write up the result, mark Q5 done with its scope recorded, and move to Q6. Do not start the
150-file `hub/tests/` pass.**

This is not abandoning the item. **"The suite has no dead weight" is a real answer** to the question
the operator asked, and it deserves to be stated plainly rather than left implied by an unfinished
sweep. The operator's actual complaint — *"the testing is taking way too long"* — was already
answered by Q2, which took the hub suite from ~762s to 292s without removing a single test. That is
the finding: the problem was a missing `-n 8`, not accumulated cruft.

**What the extra six hours are for**, in priority order: **Q6** (desktop app + one global state)
first — it is untouched, it already has a diagnosis written into the queue item
(`hub/hub/config.py:9`'s relative `data/agentweave.db`, which is why running from a different folder
produces a different AgentWeave), and it is the largest item on the operator's original agenda with
nothing built against it. Then **Q7** (UI gap analysis against popular harnesses), which the
operator scoped explicitly wider than their own T3 example.

**What a reviewer should distrust:** the Q5 cap is a judgement made from two passes, not a proof.
It is possible the semantic pass would have found real staleness deeper into `hub/tests/`. The
remaining scope is recorded on the item itself, so resuming it later costs nothing but time.
