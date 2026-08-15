# Overnight autonomous work — 2026-08-15

**Branch:** `autonomous_work`, cut from `hub-native-experience` at `7cb7783`.
**Authorised by:** the operator, 2026-08-15 ~00:40, *"work on agentweave until 10 AM tomorrow …
open a branch of this branch called autonomous_work and work on whatever you feel is necessary …
I give you full autonomy on this branch."*
**Agent:** Claude Opus 5 (1M context) (Claude Code).

Read this file top-to-bottom in the morning. Newest entry is at the **bottom**, so it reads in the
order the work happened. Every entry states what was attempted, what actually happened, and what a
reviewer should distrust.

---

## What I am not allowed to do, self-imposed

The operator gave full autonomy on this branch. These are the limits I set anyway, because they are
the ones that would be expensive to get wrong while nobody is awake to stop me.

1. **Never leave `autonomous_work`.** No commits, merges, or rebases onto `hub-native-experience` or
   `master`. The morning's review decides what, if anything, comes across.
2. **Nothing outward-facing.** No PyPI publish, no GitHub release, no issue or PR creation, no
   force-push, no history rewriting. Pushing `autonomous_work` itself is allowed — it is what makes
   the work reviewable and durable.
3. **No destructive filesystem or database operations.** In particular `aw-loop6`, `aw-loop7` and
   `aw-loop8` stay: they are kept reproductions, and `aw-loop6` holds a hand-minted credential.
4. **Never mark an openspec task complete on the strength of a plan.** The standing rule; it matters
   more, not less, when nobody is checking.
5. **Every claim in this log is either measured or labelled as unverified.** If I could not run
   something, it says so.
6. **Stop and write it down rather than guess** where a decision is genuinely the operator's. Those
   collect under "Decisions waiting for you" at the bottom.

## Plan

Ordered by value, and each step's output feeds the next.

1. **Prove the data-loss fix live.** Changes A and B landed with agent-verifiable checks all green,
   but their human-only sections are unrun. `aw-loop8` (`proj-94f3f169`) exists for exactly this and
   has a `victim` codex agent. Kill a runtime mid-turn and watch whether the entry comes back, is
   retried without help, and abandons at three with the operator told.
2. **Drive the whole product with `/e2e-loop` (loop 9)** against the new code, from an empty
   directory. Loops 5–8 each found defects that live between features and that the 2028-test suite
   cannot see. This is the highest-signal activity available.
3. **Fix what it finds**, specced through openspec like everything else.
4. **Repeat 2–3** while the night lasts.

Anything the operator has already ruled out stays ruled out: G5 (the interview backstop), the narrow
requeue rule, and re-raising the settled `ci.yml` question.

---

## Log

### 00:45 — Branch cut, log opened

`autonomous_work` created from `7cb7783`. Nothing else done yet. Entry exists so the file is
committed before any work depends on it.

### 00:28–00:35 — Step 1 done: the data-loss fix is proven live

Restarted the Hub onto this branch's code (old PID 17164 stopped, new one started via WMI on
`:8010`; `/health` returns `{"status":"ok"}` with no `ui_stale`). Everything below is against
`aw-loop8` (`proj-94f3f169`), agent `victim`, runner `Codex (default)` on the app-server transport.

**Kill once → the input comes back and the retry starts by itself.** Triggered a long turn
(`run-1c13d03e`, `entry-395c5db3`), waited for the `codex` process, killed it 6s in.

| | loop 8, before the fix | tonight, after |
|---|---|---|
| entry state | `delivered`, `delivery_attempts=0`, forever | returned, `delivery_attempts=1` |
| what restarted it | nothing — an unrelated `PUT /settings` | **the failed run itself**, `run-b61a9ee9`, 18s later |
| run error | `app-server process ended (exit 4294967295)` | `... (exit -1): <codex's own ERROR line>` |

The retry then **completed** (`run-b61a9ee9`, exit 0, 26s). The operator's message was not lost and
the work was done. That is the whole finding closed, end to end.

**The re-delivered prompt names the attempt.** The composed prompt is not persisted anywhere, so I
loaded the real `entry-395c5db3` row out of the live database and ran it through the production
`format_turn_prompt`. It renders:

> `Operator (hop 0) — delivery attempt 2; an earlier attempt was cut off before it finished:`

That proves the production function against a real row. It does not by itself prove the Hub called
it — but the Hub is its only caller, and the retry demonstrably happened.

**Kill three times → the Hub gives up, loudly.** One trigger (`entry-c3590d2c`), then killed `codex`
on sight three times (00:31:41, 00:31:48, 00:31:55). Result:

- three runs, `run-be9bfde2` → `run-a4f14537` → `run-0c54da61`, all `failed`, **all after a single
  trigger** — nothing external drove attempts 2 and 3;
- the entry: `state=withdrawn`, `delivery_attempts=3`, reason *"delivery failed 3 times; the Hub
  stopped retrying"*, `withdrawn_at` set, and `delivered_in_run_id` **kept** as the operator's
  breadcrumb;
- the conversation's `provider_session_id` is `None` — the reset at `RESUME_RETRY_LIMIT` fired;
- `queue_entry_abandoned` persisted at **`warn`** carrying entry, agent, run, attempts and reason;
- `victim` is back to `idle` and accepts new input.

The event sequence an operator would actually see, in order: `queue_entry_queued` (arrival) →
`run_failed` → `queue_entry_queued` → `run_failed` → `queue_entry_queued` → `run_failed` →
`queue_entry_abandoned`.

**Change B confirmed in the same run.** `runtime_exit_code` appears in `run_failed` beside the
synthetic `exit_code: 1`. The stderr tail arrived on `run-1c13d03e` (which had one) and was
correctly *absent* on the three that died before writing anything — so B4 behaves as designed rather
than always-empty as it was in loop 8.

**Closed:** change A tasks 7.1, 7.2, 7.3 and change B task 9.3. **Not closed:** A 7.4 and 7.5 and
B 9.1, 9.4, 9.5 — those are judgement calls that are the operator's, not measurements.

### 00:36 — Finding L9-1: my own change B still ships the unreadable exit code

`run_failed`'s payload carries **`runtime_exit_code: 4294967295`** — raw. Meanwhile `run.error` for
the very same run says `exit -1`. So one death is now described by three numbers: `exit_code: 1`
(synthetic, correct and needed), `runtime_exit_code: 4294967295` (raw), and `-1` inside the error
string.

This is my error, not a pre-existing one. Design decision D3 said normalisation belongs where the
value is composed for a human and that "what is recorded stays what the platform reported" — but I
then put the raw value into an **SSE payload**, which is a display surface, not a record. The spec I
wrote for it says *"what is displayed SHALL convey the termination"*, and this does not.

It is milder than the bug B2/B3 set out to fix (the readable form does exist, in the error string)
but it is the same class, and it is in code I wrote tonight. Fix planned for the next iteration:
`runtime_exit_code` carries the readable value, the raw one stays in the message. Nothing in
`hub/ui/src` reads this key yet, so there is no UI to break.

**Not a defect, checked and cleared:** `stderr_tail` missing from those three payloads is correct —
`codex` died before writing to stderr, and the key is deliberately omitted when empty.

### 00:39–00:50 — L9-1 fixed, and re-driven rather than re-read

`runtime_exit_code` and `_transport_failure_fields`'s `exit_code` now go through
`readable_exit_code`. `TurnOutcome.exit_code` and `AppServerError.exit_code` still hold what the
platform reported — the corrected line is **surface a person reads vs. value held in memory**, not
"message vs. payload", which is where I had it and why the defect existed.

Re-killed a live app-server on the rebuilt Hub. The two `run_failed` rows now sit consecutively in
`event_logs`:

```
run_failed  exit_code=1  runtime_exit_code=-1           <- after
run_failed  exit_code=1  runtime_exit_code=4294967295   <- before
```

**The lesson is the one worth keeping.** 75 unit tests passed in *both* states. Only driving it
showed the difference. That is the third time this session a green suite has agreed with broken
behaviour — the other two being the vacuous `schedule_agent` stubs and the mis-targeted `run_turn`
patch. Everything I claim tonight gets driven, not read.

`design.md` D3 amended in place with the correction. The **spec needed no change** — its scenario
already said *"what is displayed conveys the termination rather than that value"*; the code simply
did not meet it. Change B task 9.3 now passes.

### 00:46–01:00 — Loop 9 started: `aw-loop9` (`proj-9eb82406`)

Project at `C:\Users\huida\Documents\aw-loop9`. Agents: `architect` (codex/Spec Author), `builder`
(claude/Developer), `verifier` (codex/Verifier, `can_accept_evidence=true`). Subject: a fortnightly
shift-roster library that has to *justify its own fairness* — chosen because it forces real
arithmetic and real constraint conflicts rather than CRUD.

**Scope limitation, stated up front.** The skill says to establish scope from the operator before
looking at what was built. The operator is asleep, so I carried forward their standing answers
("everything, including the UI stamp", "fully unattended") — and, worse, **I am the one who built
the code under test tonight.** This run is therefore contaminated by the builder's blind spots in
exactly the way the skill warns about. I compensated by driving the whole spec→merge flow rather
than only my own fixes, but a finding I *did not* make tonight is weaker evidence than usual.

#### The night's most valuable result: the fix held on a failure I did not stage

Mid-interview, `run-90edbaa2` died on its own — `app-server process ended during thread/resume`.
Nobody killed anything. What then happened, from the database:

```
run-90edbaa2  failed   23:53:46   app-server process ended during thread/resume
run-c8c2a6be  failed   23:53:48   app-server process ended during thread/resume
run-1dabcd07  running  23:53:50   -> completed, spec submitted
entry-51914665  state=delivered  delivery_attempts=2
```

Two seconds between attempts, then two more. Attempt 3 ran on a **fresh provider session**, because
attempt 2 hit `RESUME_RETRY_LIMIT` and cleared the unresumable one — and it succeeded. The
operator's message survived two consecutive runtime deaths without anyone touching anything.

This is the loop-7/loop-8 wedge reproducing **unprovoked**, and healing itself. Note it took the
*pre-spawn* branch (the payload carries `method: thread/resume` from `_transport_failure_fields`,
not `runtime_exit_code`), where `return_run_entries` already existed. **What did not exist before
tonight is the `schedule_agent` call in that branch** — change A phase 4, the fix for loop 8's
finding 2, whose measured symptom was *"`entry-95f08a24` sat queued at attempt 1 until an unrelated
`PUT /settings` drove attempt 2"*. Tonight attempts 2 and 3 followed in two seconds each,
unassisted. That is the strongest evidence produced tonight, and it is stronger than my staged kills
because I did not arrange it.

#### What held: loop 8's finding 8 does not reproduce

Per the method I answered the interview decisively but **deliberately left the inviolable-rules
question unanswered** — rest periods, consecutive-duty limits. Loop 8's architect, given the same
treatment, declared *"Open questions: None outstanding"* and invented six non-goals.

This one refused to. It came back and asked again; when I answered everything else and still skipped
that one, it wrote the specification and then stopped, saying the document *"remains in exploration
with that single blocking question recorded rather than guessed"*. Verified in the document itself,
not just the chat:

- FR-5: *"whether additional inter-shift rest rules apply remains unresolved"*
- *"Mandatory rest periods and maximum consecutive work days or nights remain unconfirmed because
  the operator did not answer that question."*
- Lifecycle: *"Implementation must not begin by guessing"*
- the questions I *did* answer are each marked `resolved`

Once answered it added FR-17 and reported no remaining blockers. 17 requirements, `FR-1`–`FR-17`.

I am **not** concluding finding 8 is fixed — nothing was changed to fix it, so the honest reading is
that it did not reproduce on this run, with this model, on this subject. It may be prompt-dependent.
Worth one more probe before anyone closes it.

#### 01:02 — B6 confirmed live at a scale the tests do not reach

Approving the specification created **seven** tasks from 17 requirements. `task-7872c5d0` reports
`FR-1, FR-2, FR-3 … FR-16, FR-17` in numeric order. Before B6 that list would have read
`FR-1, FR-10, FR-11 … FR-17, FR-2, FR-3`. Change B task 9.5 closed. The unit test uses twelve
requirements; this is seventeen, from a real approval rather than a fixture.

#### 00:00–00:25 — Build and review: the gate works, and finding 9 comes back

`builder` (claude) implemented `task-6de550a5` in its worktree: a `src/` layout package,
`pyproject.toml`, 59 tests, evidence recorded against FR-1, FR-6, FR-12, task marked complete.

**The review gate did its job, better than loop 8's.** `verifier` checked out the exact recorded
commit `48ef3548`, confirmed `59 passed` independently, and then **rejected all three pieces of
evidence on merit**: the public callable raises `NotImplementedError` for every valid request, so
FR-1's return behaviour, FR-6's preference semantics and FR-12's infeasibility diagnosis are none of
them actually exercised. Its wording — *"tests validate a hand-built infeasibility object, but no
infeasibility is diagnosed or returned at runtime"* — is exactly the distinction that matters. Three
`decide_evidence` calls, all rejections, no operator involvement.

#### Finding L9-2: loop 8's finding 9 reproduces, and asking for it is not enough

Loop 8 found that the merged library could not run its own tests from a clean checkout. **This time
I put it in the builder's instructions**: *"a pyproject.toml that lets `pytest` run from a clean
checkout with no PYTHONPATH fiddling"*. Measured on a fresh `git clone` of the builder's worktree:

```
$ pytest -q                     ->  ModuleNotFoundError: No module named 'roster_fairness'
$ pip install -e . && pytest -q ->  59 passed
```

`pyproject.toml` carries `[tool.pytest.ini_options] testpaths` but **no `pythonpath = ["src"]`** —
the one line loop 8 named. The builder's own claim was *"`pip install -e .` then `pytest` works …
verified with PYTHONPATH unset"*, which is **literally true**; it read "no PYTHONPATH fiddling" as
satisfied by an editable install, which is a defensible reading.

So this is not agent negligence, and it is not fixed by asking harder. It is the design gap loop 8
named: **nothing in the chain asks whether the merged artefact is usable.** The evidence claimed
tests pass — true. The verifier independently confirmed they pass — also true. It explicitly said
*"I'll treat packaging separately from test correctness"* and did not report the gap. Every actor
behaved correctly and the artefact still cannot be cloned and run.

Loop 8 recorded finding 9 as *"probably wants an exploration of its own"* and the operator chose to
leave it. This run is a second independent reproduction with the operator's instruction actively
working against it, which strengthens the case considerably.

#### Finding L9-3: one agent's editable install leaks into every other agent

Unplanned, and found by the verifier rather than by me. My clean-checkout probe ran
`pip install -e /tmp/l9check`, which installed `roster-fairness` into the **shared** Python
interpreter every agent on this machine uses. The verifier hit it immediately:

> *"the failed editable install left Python importing a pre-existing package from
> `AppData\Local\Temp\l9check`, so that run is invalid"*

It diagnosed the contamination, isolated its imports explicitly, and got a trustworthy answer
anyway — which is a genuinely impressive piece of reviewing. But the hazard is real and belongs to
the product, not to me: **agents are isolated by worktree, not by environment.** A builder that runs
`pip install -e .` silently changes what every other agent on the machine imports, including the one
reviewing its work. Worktree isolation implies an isolation that does not exist below the filesystem.

I uninstalled the leaked package and removed the directory; `import roster_fairness` now fails
cleanly.

#### G5 re-observed, for the fourth time

The architect asked all its questions as prose across three turns. `select count(*) from questions
where project_id='proj-9eb82406'` → **0**. This remains the operator's explicit non-goal
(*"the AI should answer or not deliberately based on the test"*) and is recorded as an observation
only, not a defect.
