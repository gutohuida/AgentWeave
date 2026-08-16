# Run log — 2026-08-16 night: the spec corpus, and loops as a first-class concept

Newest entry at the **bottom**. Written for someone who was asleep.

**Branch:** `autonomous/2026-08-16-spec-corpus-and-jobs`
**Parent:** `hub-native-experience` @ `b2b0cd5` — that is what this run is a diff against.
**Window:** 2026-08-16T21:35 → 2026-08-17T08:00 (+01:00)
**Driver:** Windows Scheduled Task `AgentWeaveAutonomousSession`, firing `claude -p` every 15
minutes. Each firing is a **fresh process** that reads `STATE.json`, does one iteration, commits,
pushes and exits. Nothing is held in memory between iterations — that is what makes it survive the
interactive session ending, which is what killed the 2026-08-15 attempt at forty minutes.

---

## Entry 0 — the limits, before any work

Recorded first so a later session inherits them even if this one dies mid-thought. Full text lives
in `STATE.json`'s `limits`; this is the short form.

1. **Stay on `autonomous/2026-08-16-spec-corpus-and-jobs`.** No commit, merge or rebase onto
   `hub-native-experience` or `master`. Merging back is the operator's decision, made awake.
2. **Nothing outward-facing.** No publish, release, PR, issue, force-push or history rewrite.
   Pushing *this* branch is required, not optional — it is what makes the work durable.
3. **Nothing destructive.** In particular: do not delete `hub/data/agentweave.db` (the preserved
   pre-migration original), and do not repoint the trial Hub's database.
4. **Install nothing new.** No new dependency in any language. The operator confirmed the spec cap
   but explicitly declined to authorise `pywebview` and declined to restate a general toolchain
   allowance. A package that seems necessary is a `decisions_for_user` entry, not a `pip install`.
5. **Never mark work complete because a plan exists.** Only verified implementation closes a task.
6. **Every claim measured or labelled unverified.** If it could not be run, the log says so.
7. **Decisions that are the operator's get written down, not guessed.**

### The one setting most likely to surprise a reader

`spec_round_protocol.at_cap` is **APPROVE AND EXECUTE**. Changed by the operator this session, in
these words: *"one more change after the 3 round spec cap approve and execute."* On the previous run
that gate shipped an artifact with its objections recorded and stopped, which is exactly why Q6
ended at 0/21. Tonight N2, N2b and N3 are expected to land as **working code**.

This delegates approval to the run for tonight, **in openspec only**. It does not touch the
product's own rule that only an operator may approve a spec document — that rule is code, in
`spec_lifecycle.transition`, and N2 must not weaken it while adding an operator-only archive act.

**N4 is the single exception**: spec only, no implementation, because implementing it needs
`pywebview` and no new dependency is authorised.

### Baseline — any red below is this run's own

Verified interactively at `b2b0cd5`, immediately before starting. Do not re-verify from scratch.

| Gate | Result |
|---|---|
| `pytest hub/tests/ -n 8` | 2068 passed, 11 skipped |
| `pytest tests/ -n 4` | 362 passed, 3 skipped |
| `npm test` | 921/921 |
| `npm run lint` | clean |
| `npx tsc --noEmit` | clean |
| `ruff check` | clean |
| `black --check` | 383 files clean |
| `openspec validate --changes --strict` | 17/17 |

Four of those were **red** at the start of the interactive session and were fixed before seeding:
the UI suite was flaky (a different `userEvent` test timed out on roughly every full run), UI lint
exited 1 on nine warnings, eight Python files had drifted out of `black` format, and Q6's own
`app-lifecycle` delta failed strict validation.

### Preparation already done — do not redo it

`/autonomous-prep` ran with the operator awake; eight `AskUserQuestion` rounds, and the resulting
plan was presented in full and explicitly approved before the run started. There is **no interview
left to do**. Every answer is in `STATE.json` under `limits`, `decisions_for_user` or
`spec_round_protocol`.

Four rulings are binding and must not be re-litigated:

- **Archiving is an operator act**, mirroring the existing rule that an agent cannot approve.
- **The corpus absorbs a finished change by explicit authored merge**, not automatic migration.
- **Capability documents sit outside the phase machine**, and carry a **dedicated phase value with
  no transitions** — not a permanent `approved`, because that row would lie about what it is.
- **The job system composes with AgentWeave's own primitives** and supports **many named loops** at
  different cadences, never a singleton.

One question is deliberately **open**: the task board at scale. The operator said *"Maybe make a
task board by spec? I don't know"* and meant it. N1 answers it with evidence; N2b acts on the
answer, or records why not.

### Two environment traps that cost the most if forgotten

- **Start the Hub from `hub/`, never the repository root.** `python -m uvicorn` puts the working
  directory on `sys.path[0]`, so this repo's own `hub/` directory shadows the installed `hub`
  package. The parent process survives, so migrations run and only the spawned server dies — 60
  seconds later, with its output already sent to `DEVNULL`.
- **`pytest` has no timeout plugin here.** `--timeout=` is an unrecognised argument and fails
  collection outright with exit 4.

Next: install the driver and release the branch to it. First work item is `N1-corpus-at-scale`.

---

## Entry 1 — N1: the corpus-at-scale exploration (2026-08-16T21:50 +01:00)

First iteration to actually run under the driver. Verified before starting: branch is
`autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head is `46e2a74` matching STATE.json's
implicit position (iteration 0, no heartbeat yet — this is genuinely the first firing), working
tree clean. No reconciliation needed.

Did the reading N1's `next_action` specified, in order: `openspec/specs/` (30 capability
directories, confirmed) and read `spec-document-authority/spec.md` in full (573 lines) as the
"what does a current-behaviour document read like" sample; `openspec/changes/` (17 unarchived, 67
archived, confirmed) and read one archived change's `specs/` delta
(`2026-08-14-what-the-product-actually-built/specs/task-lifecycle-governance/spec.md`) to see the
ADDED-Requirements delta convention concretely; `hub/hub/db/models.py` around `Task` (595-660) and
`SpecDocument`/`SPEC_PHASES` (1500-1580); `taskFilterStore.ts`, `App.tsx:330-358`, and
`SpecCoverageBar.tsx` to trace the existing outside-the-board filter mechanism end to end
(`onOpenTasks` → `setActiveTaskIds` → navigate → `TasksBoard` reads `activeTaskIds` and filters
every column, with a "Showing N tasks linked from…" banner). Also spot-checked
`hub/hub/api/v1/tasks.py` for an existing `spec_document_id` query filter — there isn't one yet
(the field is used to *populate* task responses, not to filter the list), which the document
states honestly as unverified/out-of-scope rather than assuming.

Wrote `openspec/explorations/2026-08-16-a-corpus-at-scale.md`, answering N1's five questions:

1. **Capability vs. change document** — the distinction already lives in file layout and prose
   (absolute requirements vs. ADDED/MODIFIED/REMOVED deltas); the Hub-side gap is only that
   `SpecDocument.kind` has never taken a second value. Recommends the capability/change split be a
   rendering-schema concern, not a new phase.
2. **The folder tree at scale** — `openspec/specs/` stays flat and fine at 30; the real scale risk
   is `openspec/changes/archive/` at 67, which is unindexed by capability. Recommends a
   capability-linkage index (Hub-side query, not a folder reorganization) over moving 67
   directories around, and separately flags that a *capability document's own length* (863 lines
   for `task-lifecycle-governance` today) is the sharper long-run risk than folder layout.
3. **What a finished delta does to the corpus** — ports the already-proven openspec convention
   (delta reviewed and hand-merged into the capability doc) into the Hub's data model, and
   separates "merge the delta" from "archive the change document" as two acts, not one, so evidence
   can keep accumulating on an already-merged change without forcing a premature archive.
4. **The task board at scale** — traces the existing `taskFilterStore`/`SpecCoverageBar` mechanism
   as proof a document-scoped filter is a second caller of code that already works, not new
   machinery: one new query plus one UI affordance, no schema change.
5. **What archiving does to a change's tasks** — recommends a *view-level* default-filter exclusion
   (archived document's tasks hidden from the unscoped board only if the task itself is also
   terminal; open tasks from archived documents stay visible), explicitly not a task mutation, and
   notes it composes with N2 (same query surface) without being decided by N1 which of N2/N2b
   implements it — restated from N2b's own brief rather than re-litigated.

Six numbered recommendations close the document, addressed to N2 and N2b by name, concrete enough
to spec from per N1's `output` requirement. No code changed; this item is spec-only by design.

**Verification**: read-only exploration work: no test suite applies. Confirmed the document exists
and reads coherently top to bottom after writing it (no separate "run tests" step for this item —
the deliverable is the document itself, and N1's `output` field asks only for a document, not
running code).

Advanced `current` to `N2-archive-and-capability` and wrote its `next_action`: round 1 (author) of
the change's spec artifacts, informed by N1's recommendations above, following N2's own `detail` in
the queue for the migration/lifecycle mechanics (0074, the SQLite CHECK-constraint recreate trap,
enforcing archive-is-operator-only inside `spec_lifecycle.transition`). N2b remains pending,
contingent on N1 as already stated — N1 did NOT conclude the board needs no scoping, so N2b is not
skipped.

---

## Entry 2 — N2 spec-round 1: the archive transition and the capability kind (2026-08-16T22:14 +01:00)

Verified before starting: branch `autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head
`2f7f22c` matching STATE.json, working tree clean. `current` was already `N2-archive-and-capability`
from entry 1's handoff. No reconciliation needed.

Read N1's exploration in full before writing anything, as `next_action` required, plus the code it
grounds itself in: `hub/hub/spec_lifecycle.py` (the whole file — `transition()`'s operator-only
approval check is the shape everything else in this round copies), `spec_service.py` (`save_document`,
`rename_document` — the ordering discipline "everything that can be refused is refused before anything
moves" is reused rather than reinvented), `spec_payload.py` (`SpecPayload`, `KINDS`, `validate_payload`)
and `spec_render.py`, `hub/hub/db/models.py` around `SpecDocument`/`SPEC_PHASES`, migrations `0058` and
`0073` (the two prior CHECK-constraint-recreate migrations this round's `0074` follows), `0065` (the
guarded plain-`create_table` idiom the new `spec_document_merges` table follows), and
`hub/hub/api/v1/spec.py` and `agent_actions.py` end to end to see which routes are operator-credentialed
versus agent-credentialed.

**One correction to N1, found by reading code N1 had not read this closely.** N1's recommendation 1
said a capability document needs a distinct payload schema (absolute requirements vs. a
change-spec's ADDED/MODIFIED/REMOVED delta), reasoning from the *openspec file* convention. Reading
`spec_payload.py` shows the Hub's `SpecPayload` has never modelled a delta at all — every document's
`requirements` field is a flat, absolute list, `change-spec` included, because nothing in the Hub's own
JSON payload has ever had ADDED/MODIFIED/REMOVED semantics; that convention exists only in the
hand-authored `openspec/` markdown files N1 read. So a capability document needs **no schema change** —
recorded as design D2's correction, with the reasoning, rather than silently doing something different
from what N1 recommended.

**One latent bug found while tracing the write path, fixed in the same change rather than filed
separately.** `spec_service.save_document` → `spec_lifecycle.record_content` sets `document.kind =
payload.kind` on **every** content submission, unconditionally — an agent's payload can silently
reclassify a document's `kind` today, and nothing has ever needed a document's `kind` to be trustworthy
enough to notice. Once `kind='capability'` starts governing which phase a document is allowed to
occupy (this change's whole point), that same drift would let a submission defeat the coupling. Design
D3 pins `kind` at creation and refuses a submission whose `kind` disagrees with the document's own —
argued in the design doc as belonging in this change, not a follow-up, because shipping the coupling
without it ships a coupling with a known hole.

Wrote the full artifact set at
`openspec/changes/2026-08-16-the-corpus-keeps-what-shipped/`:

- **`proposal.md`** — the gap, what changes, capabilities touched (`spec-document-authority` only,
  modified — this is additive machinery inside its existing domain, not a new capability area),
  impact, and six explicit non-goals (no task-board scoping — that's N2b; no merge-before-archive
  requirement; no general capability-document content editor beyond creation and merge; no unarchive
  transition; no `openspec/` reorganisation; no import of openspec's existing 30+67 documents).
- **`design.md`**, eight sections: D1 the two new phase values and the one new transition, enforced in
  `transition()` exactly where approval already is; D2 capability documents (created directly at
  `current`, written only by the operator, and the schema correction above); D3 the kind-pinning fix;
  D4 the new `spec_document_merges` table — chosen over N1's left-open JSON-field alternative because
  an unindexed JSON scan does not answer "what touched this capability" as a query, and given a
  `CHECK actor_kind = 'operator'` stronger than every other actor-kind CHECK in the schema, because this
  table exists specifically to make the operator's-authorship rule true; D5 the merge endpoint
  (`POST /project/documents/{path}/merge`, operator-only, sources named by path, must be `approved` or
  `archived`); D6 migration `0074` in two pieces (the `ck_spec_documents_phase` recreate plus two *new*
  CHECKs — a `kind` vocabulary CHECK that has never existed before, and a cross-column
  `(kind='capability') <=> (phase='current')` CHECK in the shape `0058` already established for
  `origin_type`/`origin_agent` — and a guarded plain `create_table` for the merge table); D7 the three
  UI changes (an Archive button, a latent "Reopen shows for every non-exploring phase" bug fix that
  becomes load-bearing once `archived`/`current` exist, a muted chip treatment); D8 states explicitly
  what this leaves untouched for N2b (no task is read or written by anything in this change).
- **`tasks.md`** — 11 sections, unchecked: migration, model, lifecycle, service, API, the agent-route
  refusal (which needs no code change if D2's refusal is placed correctly — task 6.1 says to confirm
  this by reading and by test, not assume it), UI, agent-verifiable tests, driven-against-the-running-Hub
  checks, human-only verification, and a user test guide. Task 8.5 deliberately leaves one edge case
  undecided rather than silently picking an answer: can a capability document itself be cited as a merge
  *source*? Design D5 doesn't rule it out and probably should — flagged for round 2 or for whoever
  implements to resolve, not guessed at here.
- **`specs/spec-document-authority/spec.md`** — three ADDED requirements (archiving, the capability
  kind, the authored merge) and two MODIFIED (the phase-transition requirement gains `current`'s
  no-transitions rule; the approval-is-the-operator's requirement gains archiving as its sibling, with
  a scenario stating the refusal holds "regardless of caller" — the same wording this session's own
  `spec_lifecycle.py` docstring uses for why the check lives in the function and not the route).

**Validation friction worth recording**, since CLAUDE.md asks every friction with the spec flow itself
to be recorded rather than worked around: `openspec validate --strict` refused the merge requirement
with "must contain SHALL or MUST" even though the full paragraph plainly contains SHALL — the parser
only reads the **first physical line** of the requirement's opening paragraph, not the full sentence
after a hand-wrapped line break. Every existing requirement in the corpus that wraps its opening
sentence happens to have its modal verb before the first line break by accident of phrasing; this one
didn't. Rewrote the sentence so SHALL appears in line one. This is a real authoring trap for anyone
writing openspec by hand — worth a line in a later pass over the `openspec-propose` skill's own
guidance, not something to fix in this run.

**Verification**: `npx openspec validate 2026-08-16-the-corpus-keeps-what-shipped --strict` → valid.
`npx openspec validate --changes --strict` → **18 passed, 0 failed** (17 baseline + this one), matching
the `verified_green_at_b2b0cd5` baseline plus one. No code was touched this iteration — round 1 is
author-only per `spec_round_protocol` — so `pytest`/`npm test`/etc. are unchanged from baseline and were
not re-run; nothing in this iteration could have moved them.

`current` stays `N2-archive-and-capability`. Advanced `next_action` to round 2: a cold review against
the four binding rulings and N2's own queue detail, with explicit call-outs to the judgment calls this
round made on its own authority (the schema correction, the kind-pinning bundling, the table-over-JSON
choice, the cross-column CHECK, path-based source naming) so round 2 does not have to rediscover them
from scratch — and a reminder that `at_cap`/on-approval means proceed straight to implementation in the
same run, tasks.md section by section, not stop at another artifact.

---

## Entry 3 — N2 spec-round 2: cold review, one load-bearing gap found and fixed (2026-08-16T22:23 +01:00)

Verified before starting: branch `autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head
`b07b1f6` matching STATE.json, working tree clean. `current` already `N2-archive-and-capability`,
`next_action` already round 2. No reconciliation needed.

Read `next_action`'s checklist in full and read code cold rather than trusting round 1's own
account of it: `hub/hub/spec_lifecycle.py` end to end (`transition()`, `create_document`,
`record_content`), `hub/hub/spec_service.py` (`save_document`, `rename_document`, `propose`),
`hub/hub/spec_payload.py` (`KINDS`, `validate_payload`, `SpecPayload`), `hub/hub/db/models.py`
around `SpecDocument`/`SPEC_PHASES` and every `actor_kind` CHECK in the file, migrations `0058`
(the cross-column CHECK precedent) and `0073` (the batch-recreate precedent), and
`hub/hub/api/v1/spec.py` (`_operator`, `_require_document`, `create_document`, `set_phase`,
`agent_actions.py`'s `submit_spec_document`) to see the actual write paths rather than take
`design.md`'s account of them.

**Confirmed accurate, no action needed:** D2's correction of N1 (verified directly in
`spec_payload.py` — `SpecPayload.requirements` really is one flat shape for every `kind`, no delta
schema anywhere); D4's actor_kind CHECK claim (every existing `actor_kind` CHECK in `models.py` is a
plain `IN ('operator', 'agent', 'system')` — six of them, grep'd — so the new table's
`CHECK actor_kind = 'operator'` really is stronger than the rest, not a stray tightening); D6's
cross-column CHECK precedent (`0058`'s `origin_type`/`origin_agent` pair is exactly that shape);
`0073`'s batch-recreate-with-guard idiom matches what D6 claims for `0074`; `agent_actions.py`'s
`submit_spec_document` really does catch `SaveRefusedError` generically (`code=exc.code`, no fixed
mapping) — task 6.1's conditional ("if the route maps a fixed set of codes, extend it") correctly
hedges on a premise that turns out false, not a bug.

**One load-bearing gap, found by tracing the write path rather than trusting the design doc's
account of it.** `spec_payload.KINDS` is `("baseline", "system-map", "roadmap", "change-spec")`
today, and `validate_payload` refuses any `payload.kind` outside it — unconditionally, before
either of D2's or D3's new refusals ever run. Design D2 states in prose that `KINDS` "gains
`capability` as a valid value," but round 1's `tasks.md` never turned that into a checklist item —
no task anywhere touches `spec_payload.py`. Traced the consequence concretely: the *existing,
unchanged* `create_document` API route (`hub/hub/api/v1/spec.py:810`) already calls
`spec_service.save_document` immediately after creating any document, of any kind, to write its
initial scaffold (`payload = {"kind": document.kind, "title": ..., ...}`). So creating a capability
document at all — not merging into one, just creating the empty scaffold task 8.4 tests — would hit
`validate_payload`, find `kind="capability"` outside `KINDS`, and refuse `payload_invalid` before
D2's phase or D3's kind-pinning logic ever run. The entire mechanism this change exists to build
would be unreachable from its own first step.

**Fixed in place, not just flagged.** Added task 4.4 to `tasks.md` (`spec_payload.py`: `KINDS`
gains `"capability"`), marked load-bearing with the reasoning above so whoever implements does not
skip it as a nice-to-have. Fixed task 1.2's wording, which had computed the migration's
`ck_spec_documents_kind` CHECK as `spec_payload.KINDS + ("capability",)` — now that 4.4 makes
`KINDS` include it directly, that concatenation would just duplicate the value in the SQL `IN`
list; reworded to reference `spec_payload.KINDS` directly once both tasks are done, so there is one
source of the vocabulary, not two that happen to agree today. Fixed a dangling cross-reference in
`design.md` D2 (`"(§ D5)"` — D5 never mentions `KINDS` at all) and added a short "Round 2
correction" paragraph there stating the gap and the fix, so a reader of `design.md` alone sees why
task 4.4 exists without having to find this log entry.

**One clarification, not a gap.** Task 8.5 flagged "can a capability document itself be a merge
source?" as an edge case design D5 doesn't rule out and should. Reading D5 step 4 again: it already
refuses any source document whose `phase` is not `(APPROVED, ARCHIVED)`, and a capability document's
phase is always `current` — so citing one as a source is *already* refused today, by the same
`source_not_finished` code, as a pure side effect of the phase gate, no extra code required. Not
actually undecided; reworded task 8.5 to say so and to note the only real open question is whether
`source_not_finished` is the right *message* for a document that was never a change (nice-to-have,
not a blocker) — so the test still needs writing, but the implementer isn't asked to invent
behaviour that already falls out of D5.

**Verification**: `npx openspec validate 2026-08-16-the-corpus-keeps-what-shipped --strict` →
valid. `npx openspec validate --changes --strict` → **18 passed, 0 failed**, unchanged from round
1's count (a revision, not a new change). No code touched this iteration — round 2 revising an
artifact is still artifact-only work — so `pytest`/`npm test` are unchanged from baseline and were
not re-run.

`current` stays `N2-archive-and-capability`. Advanced `next_action` to round 3: a fresh cold check
specifically of whether task 4.4's fix is complete and correctly placed (does anything else assume
`KINDS` is the original four-tuple? — `ck_spec_documents_kind`'s literal SQL list in the migration
file needs to be written from the *post-4.4* `KINDS`, not copy-pasted from this round's now-stale
description of it), plus a final pass over anything this round didn't have time to re-derive from
scratch (the UI section, the human-only verification list, the user test guide) — and then, per
`spec_round_protocol.at_cap` (round 3 is the cap), record any remaining objections in `design.md`
and proceed straight to implementation in the same run, `tasks.md` section by section: migration
0074 first (task 4.4 done first within that pass, since 1.2 now depends on it being decided), then
model, lifecycle, service, API, agent-route refusal, UI, then the test sections.
