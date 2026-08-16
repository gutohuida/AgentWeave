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
