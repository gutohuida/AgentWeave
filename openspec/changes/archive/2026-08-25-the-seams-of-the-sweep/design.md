## Context

Twelve defects from the 2026-08-25 full-surface sweep (`scripts/drive/FINDINGS.md`, F27–F38), plus
F21 carried from 2026-08-24. Every one sits at a seam between two components that are individually
correct, which is why the suite was green at 3041 passed while all twelve were live.

The constraint that shapes most decisions below: **this codebase's signature quality is that its
refusals teach.** `task_transitions.refusal_detail` names the current state *and* every reachable
one, because *"an agent told merely 'forbidden' retries the same call."* Several findings are
places where that standard is not met, so the fix is usually to apply an existing standard rather
than invent one.

Two hard constraints carried from CLAUDE.md: `hub/hub/mcp_server.py` is spawned standalone and may
import **only stdlib + fastmcp**; and `approve_tool_call` must keep having no return annotation,
because FastMCP would derive `structuredContent` from one and silently defeat an `allow`.

## Goals / Non-Goals

**Goals:**
- Close the one path by which unearned work reaches `master` (F27).
- Make order-of-operations stop mattering where it silently does (F28).
- Apply the "refusals teach" standard where it is currently one-directional (F32, F35).
- Make what the operator is shown agree with what the system does (F30, F31, F34).
- Every fix small and at the seam; no subsystem rewrites.

**Non-Goals:**
- Reinstating the question backstop retired 2026-08-20 (migration `0082` dropped its table).
- Auto-re-delivering a turn that produced nothing — it spends money without being asked.
- Reducing the per-turn context floor (34,451 input tokens for a `SWEEP-OK` turn). Real, recorded,
  not a defect.
- F22, F24, F25, F26 — carried, not on the sweep report.

## Decisions

### D1 — F27: claiming binds, and only the holder may finish

Two conditions in `task_transition_service.apply_transition`, beside the dependency gate
(`-> in_progress`) and requirement gate (`-> approved`) already there:

1. `-> in_progress`, actor kind `run`: if the run holds no task, bind it. If it holds a *different*
   task, refuse.
2. `-> completed`, actor kind `run`: require `run.task_id == task.id`.

**Why this is sufficient and minimal.** `TRANSITIONS` (`task_transitions.py:112–117`) makes
`completed` reachable **only from `in_progress`**. So every legitimate completion already passes
through the claim, and (1) guarantees (2) is satisfiable. The Developer charter's *"call
`list_tasks` to see what is waiting"* behaviour keeps working end to end: find → claim (binds) → do
→ complete. The probe run would have bound on its first task and been refused on the other five.

Placement inside the service, not the route, matches the two existing gates: every surface —
operator route, agent HTTP, tool surface, jobs, and the runtime binding — is covered without knowing
the gate exists.

**Alternatives rejected.** *Require evidence at `completed`* — `requirement_gate`'s own docstring
explains why that deadlocks: evidence is accepted after review, and review follows completion.
*Refuse at `-> completed` without binding at `-> in_progress`* — would break the charter-sanctioned
path of an agent picking up waiting work, turning a real behaviour into a dead end. *Fix the
charter instead* — the charter is not wrong; going to find work is the behaviour asked for.

`bind_run_to_task` already sets `run.task_id` **before** calling
`apply_transition(..., origin=runtime)`, so the runtime path arrives already bound. No ordering
hazard, and no change needed there.

### D2 — F28: adopt on claim, rather than teach the queries a second key

Every loop-queue query reads `Task.loop_id` (`scheduler.py:314, 327, 644, 1305, 1569`).
`spec_tasks.materialise()` stamps it at creation (`spec_tasks.py:117`, `:216`) and nothing
back-fills.

**Decision: back-fill `loop_id` when a loop claims a document** — one write at the claim site,
beside the existing `_check_spec_document_conflict` (`jobs.py:115–123`), which already prevents
stealing another loop's document. Restricted to tasks whose `loop_id IS NULL`.

**Alternatives rejected.** *Make every queue read `spec_document_id` as a fallback* — five query
sites to change and two ways to be in a loop's queue forever after; the finding is that one binding
was not established, not that the queries are wrong. *Refuse the claim when the document is already
approved* — the artifact's own fallback suggestion, and a real improvement over silence, but it
turns a working intention into an error the operator must work around by rebuilding the flow.
Adopting makes the trap **not exist**, which is better than reporting it.

### D3 — F28b: **withdrawn.** The firing was a symptom, not a second defect

This design originally proposed that a flow honouring `stop_when_queue_empties` must not fire
against an empty queue, on the strength of the finding's observation that it *"fires a real turn
against the empty queue anyway"*. **Reviewing the spec against the code before implementing — the
standing method — showed that would have been wrong, and would have broken working behaviour.**

`scheduler._loop_stall_reason` names three queue states outright:

```
nothing ready YET   open work, none claimable   -> skip this firing, keep polling
nothing LEFT        every task terminal         -> `_loop_stop_reason`, stop for good
never filled        no tasks at all             -> fire; the agent's job is to fill it
```

The third is a decision, not an oversight: a loop is created before its work exists, and
`_loop_stop_reason`'s own comment records that arming the stop condition at creation *"would
disable the loop on its first tick, before it had ever run anything, permanently"*. Firing an
empty, never-filled loop is how a flow whose job is to *produce* tasks gets to do it.

F28's flow held five tasks and looked never-filled, because `loop_id` was null — so it took the
third branch correctly, on false information. **D2 alone closes both halves of F28:** once the
tasks are adopted, `ever_count` is non-zero, the queue is genuinely non-empty, and the existing
machinery does the right thing without modification.

Consequently the `loop-firing-accountability` delta is withdrawn: there is no behaviour to change
there. Recorded rather than quietly dropped, because the finding's second paragraph reads as a
separate defect and the next reader will otherwise re-propose this.

### D4 — F32: capability announcement becomes symmetric

`agents.py:1321` carries the comment naming this exact failure mode and then guards a section
emitted **only when the grant is held**. The fix is the `else` branch, plus an audit of the rest of
the canonical-context builder for the same one-directional shape.

The withheld text must also say **what to do instead**. That is not politeness: unable to record
its verdict, the reviewer wrote a full review to a file inside its own worktree, which is isolated
by design, so the conclusion is on a branch nobody reads.

### D5 — F38: a non-outcome is recorded from state, never from prose

The retired backstop guessed whether trailing prose was a question. It was retired for a good
reason and is not coming back. **Nothing here requires guessing.** The Hub already holds every
fact needed as structured state: the run reached a terminal status, no `Question` row was written by
it, and the deliverable did not advance.

Record that conjunction and surface it to the operator. Pair it with a context statement made *in
advance* — for a turn whose deliverable is a document in `exploring`, ending without either
submitting or calling `ask_user` is not a valid way to finish.

**Alternative rejected:** re-delivering the turn with a nudge. Effective, and it spends money
autonomously; that is the operator's call, not this design's.

### D6 — F35: shape the refusal where the tool lives

`submit_spec_document` cost **718,650 input tokens** in one turn across ten retries, because each
retry resends the whole conversation and the agent was guessing a nested schema from
`errors.pydantic.dev` links. Model the refusal on `refusal_detail`: which field, what shape, one
minimal example.

Because `mcp_server.py` may import only stdlib + fastmcp, the shaping is **restated** there rather
than imported, with a test asserting the two agree — the convention this repo already uses for
everything that module needs from the Hub.

### D7 — F31: narrow the redaction rule rather than delete it

`_SECRET_VALUE_RE`'s third alternative `[A-Za-z0-9_=-]{32,}` matches any long identifier, so it eats
`mcp__agentweave__submit_spec_document` and `spread-fairness-metric-fix-for-idle-staff` — the Hub's
own tool names and its own minted slugs, removing exactly the identifier that says *which* document
an agent read.

**Decision: require the high-entropy alternative to contain no `_` and no `-`.** Real credentials
(hex, base64) have neither; the Hub's vocabulary has both. The two prefix alternatives
(`aw_live_…`, `sk-…`) are untouched and keep catching the credentials that actually exist.

**Alternative considered:** delete the third alternative entirely, as the report suggests. Kept as
the fallback if narrowing still proves noisy — but it would drop all defence against an
unknown-format secret, and narrowing costs nothing extra to test.

### D8 — F30: launchability keys on the runner, not on how the agent was created

`launchability.py:353` gates the bound-runner merge behind `not agent_row.self_registered`. The
exemption's *intent* is "a self-registered agent has no Runner" — written as an assumption and never
enforced, while `self_registered = 1` with a non-null `runner_id` is reachable through two ordinary
API calls. Key the merge on `runner_id`, which is what `trigger_agent_directly` already reads.

**The invariant worth testing is the agreement**: the probe and the spawn must not disagree about
the same agent. Today they do, and the probe is the one the operator sees.

### D9 — F37: archive through the phase machine, not a second removal path

An orphan is unreachable in every direction: `archived` only from `approved`, `approved` only from
`proposed`, `proposed` needs requirements it lacks, `DELETE` is `405`. Open `exploring -> archived`
(and `proposed -> archived`), guarded on nothing having been materialised from the document.

**Alternative rejected:** a `DELETE` route. Removal would become a second mechanism beside the
phase machine, and `spec_lifecycle`'s whole guarantee is that phase is read from a row. `archived`
already exists and already clears the drift banner.

### D10 — F36: one writer for `TaskDependency`

`TaskDependency` rows are written in exactly one place (`spec_tasks.py:375`). Adding a second
writer for the operator path would give two ways to build the same graph. Extract a small service
function and have **both** the spec path and the new operator path call it — the spec path keeps its
document-local key resolution, the operator path names task ids.

### D11 — F34: the documented form is the one that must work

`--help` documents `agentweave [--port PORT] ... {status,…}`, and that is the form that silently
does nothing. Thread the global value as the subcommand's default, with an explicit subcommand flag
winning. Also: report a native `uvicorn` process as native rather than Docker, and have `doctor`
examine the Hub the project is actually bound to instead of defaulting to port 8000 and a database
nobody serves.

### D12 — F29: mark divergence on read; do not refuse it

`spec_lifecycle.divergence()` has exactly one caller (`spec_service.py:236`) and it is the **save**
path, so tampering is noticed only when someone tries to write. Call it on the read paths too.

**Mark, not refuse** — refusing would break the ordinary edit-then-save flow, which is a legitimate
thing to be doing. The listing route already carries `divergence`/`diverged` fields that came back
`None`; they simply need populating.

### D13 — F41: "not written" is a count of writes, not the absence of a digest

**Written after the live re-drive, and it corrects D5.** D5's rule is right and its implementation
was not: it asked whether the document carried a recorded content digest, reasoning that its absence
means nothing has ever been written there.

No creation path leaves it absent. Both `api/v1/spec.py` `create_document` and the agent's own
`create_spec_document` call `spec_service.save_document` with a scaffold payload immediately after
the row exists, and that write sets the digest. Measured on the live database: **50 documents, 0
without one.** The check could not fire, and six tests passed because the fixture built a
null-digest document the product does not produce.

The original subject settles it. `spec/changes/teal-manticore/spec.html` — the document the author
was given and never wrote — records `created` and `content` at the same microsecond,
`2026-08-25 08:15:40.650773`, with `{"requirements": []}`. The check written for that turn would
have returned False on that turn.

**The signal used instead is the number of `content` events on the document.** The scaffold
contributes exactly one, so a second is the first time anybody wrote anything. Considered and
rejected: `requirement_digests` being empty, which is simpler but fires on a document written with
prose and no requirements — a real thing an author may do on the way to a draft, and reporting it as
"produced nothing" would teach the operator to ignore the notice, which is the failure mode D5
already argues against.

Every property of D5 survives: state only, the agent's prose never read.

### D14 — F35 reversed: the schema, not the refusal, and the machinery goes with it

D6 shaped a refusal at the tool, accepting untyped annotations as the price. The operator reversed
that on 2026-08-25 and chose the schema. The trade was stated when it shipped and the reversal is
one the design anticipated; what the design did not say is what happens to the machinery.

It is **removed**, not left behind a restored type hint. The framework validates before a tool body
runs, so with `Dict`/`List` annotations restored, `_check_submit_shapes` is unreachable by every
path. Keeping it would have produced a second F41 inside the change that found the first: code that
reads as a safeguard, is counted as one, and cannot be triggered. `test_the_structured_fields_advertise_their_shape`
now fails if an `Any` returns, and the parameter list records that reversing again means restoring
the annotations *and* the machinery together, since neither works without the other.

fastmcp 3.1.0 was checked for the escape D6 hoped for: `Tool.from_function` takes `output_schema`
and has no input equivalent, so there is still no way to hold both halves without `pydantic.Field`,
which this module may not import.

### D15 — F40's cause was the patch scope, not the snapshot

Recorded because the finding's diagnosis was reasonable and wrong, and the wrong one is the kind
that gets re-proposed.

F40 attributed the flake to `for task in list(_background_runs): await task` snapshotting the set.
That is a real defect and is fixed. It is not what made the test fail: replacing the snapshot with a
wait on the condition made the failure **deterministic** under load, which is how the real cause
surfaced. Run immediately after `test_conversation_contract.py`, the test failed every time with
`assert 2 == 1` — two runs on one conversation, both `failed`, where the isolated run was one and
`completed`.

The `PtySession.spawn` patch closed at the end of the relocate request, while the run it starts is a
background task that spawns after the response returns. Lose that race and the run reaches the real
spawn, fails for want of a `claude` binary, and the product does the right thing:
`return_run_entries` puts the entry back and a second run picks it up. Awaiting the settle inside
the patch closes it.

**Not claimed as eliminated.** 24 of 25 runs of the reproducing combination pass, against 4 of 5
before, and a full suite went green; one failure remains unexplained. The general lesson is worth
more than the fix: a narrowly-scoped `patch` around a call that *schedules* background work is a bug
of this shape wherever it appears.

## Risks / Trade-offs

- **D1 refuses a legitimate completion path nobody remembered** → `completed` is reachable only from
  `in_progress`, which bounds the exposure to one edge; the full Hub suite plus a live re-drive of
  area 7 is the check. Baseline to beat: 3041 passed locally / 3037 in CI.
- **D2 adopts a task some other loop should have owned** → restricted to `loop_id IS NULL` and
  placed behind the existing document-conflict guard, so a document already claimed cannot be
  re-claimed.
- **D7 narrows redaction and lets a real secret through** → the two credential prefixes are
  untouched; the test asserts both directions, that the Hub's own vocabulary survives *and* that
  credential formats still redact.
- **D10 admits a dependency cycle the spec path could not create** → reject cycles in the shared
  writer, so both paths get the check rather than only the new one.
- **D12 costs a file read per document on the listing route** → measure; bound or defer the listing
  half if the cost shows, keeping the single-document read path which is where an agent actually
  reads.
- **D13's write count miscounts a legitimate re-render** → `rerendered` is its own event kind,
  distinct from `content`, so a Hub-initiated regeneration of the navigation region does not read as
  an author having written something.
- **Scope grew during the re-drive.** Thirteen findings became nineteen — see the proposal's
  scope section. Mitigated the same way: each disposition is its own commit with the full suite run
  between, and none depends on another.
- **Scope.** Thirteen findings in one change is large. Mitigated by group order: each group is
  independently shippable and committed on completion, and Group 1 alone closes the A.

## Migration Plan

One optional data migration for D2, back-filling `loop_id` where a loop already claims the document
a task was materialised from — so flows already broken (including `aw-sweep`'s, which is a live
reproduction) repair themselves instead of needing a rebuild.

If added: guard for a missing table as `0033`/`0034` do, because upgrades from an early revision
reach it with only that revision's tables; and bump the head assertions in **both**
`hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`.

Rollback is per-group: each is a separate commit and no group depends on a later one.

## Open Questions

- **F21's remedy is not settled.** The symptom is clear — a Haiku agent looped on `ToolSearch`,
  ended `completed` with a confident summary and zero evidence rows — but the fix depends on how
  this surface defers tools (`src/agentweave/tool_surface.py`, `hub/hub/mcp_server.py`). Needs a
  short investigation in Group 3 before the approach is fixed.
- **Whether D12's divergence check belongs on the listing route** as well as single-document read,
  given the per-document file read.
- **Whether F37 should also address the seam that created the orphan** — a conversation carried an
  attached document and the agent made a second one, with nothing asking whether that was meant.
  Recorded as secondary; not planned in this change.
