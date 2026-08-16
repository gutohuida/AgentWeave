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
