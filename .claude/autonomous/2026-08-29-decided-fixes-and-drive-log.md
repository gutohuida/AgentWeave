# Autonomous run — 2026-08-29, decided fixes and a drive

**Branch:** `autonomous/2026-08-29-decided-fixes-and-drive` from `master` at `b2d565e`
**Runner:** `claude` (Opus 5) · **Posture:** `unattended-full-access`
**Armed:** 2026-08-29 ~12:35 local · **Stop at:** 2026-08-29 20:00 local
**Brief:** `.claude/autonomous/STATE.json` · **Findings:** `scripts/drive/FINDINGS.md`

Newest entry at the **bottom**.

---

## Iteration 0 — arming (interactive session, operator present then departing)

The operator's words: *"Schedule a autonomous run to fix those issues and then drive a e2e loop and
fix issues that you can. Run untill 20:00. After scheduling run a handoff in this session."*

### What "those issues" are, and why none of them needs a decision

Four findings, every one with the operator's own decision already behind it. The brief quotes each
decision at the queue item so the run implements rather than re-litigates:

| | Decision, in the operator's words |
|---|---|
| **F116** | New this session. Fix shape is the one the finding names; pre-authorised as D1. |
| **F111 + F3** | *"No it does not belong in the product."* Self-registration is removed, not reworded. |
| **F113** | *"Clean."* — `blocking` gets the closure finding; the additive alternative is rejected and recorded as rejected. |
| **F115** | *"Worktree is a cwd — fix the honesty."* Native mode does **not** confine writes. |

F115's decision was taken with `AskUserQuestion` in the last minute before the operator left,
specifically because it was the one thing that would have stalled the run.

### Limits set for this run

Beyond the standing directives (all quoted in `STATE.json.limits`), two matter most:

1. **Do not merge to master.** This session merged 34 commits to master today with the operator
   present and CI green on all nine cells. An unattended run pushes its branch and stops there.
2. **The 17:00 rule.** The operator asked for the fixes *and* a drive. If the queue has not reached
   `E2E-DRIVE` by 17:00 local, park the spec loop in flight at a clean boundary — a completed round,
   committed — and start the drive anyway. Reaching the drive is part of the ask.

### What was prepared so the run would not have to

- **The four findings are written up in full** in `FINDINGS.md`, each with its live reproduction:
  F115 has four run rows and the sqlite query that proves all four recorded the same
  `workspace_dir`; F116 has both request shapes and both responses; F113 has the three-call
  reproduction; F111 has the search that proves no shipped client calls the route.
- **A working drive harness exists** — `scripts/drive/t_row13_row14.py`, written and run this
  session, with the two traps documented in-file (the question schema has no `status` string, and
  permission posture travels in `overrides`). The run reuses it rather than rediscovering them.
- **Green-at-arming is CI, not a local run.** Run `33247142872` at `c994af5` passed all nine cells
  including both 3.12 legs, which cannot be reproduced on this machine. Everything committed since
  touches only `scripts/drive/*.md` and two new drive scripts no test imports.
- **The F109 flake is named in `known_flakes`** with its three affected tests, so a red cell there
  is re-run rather than misattributed — and with an explicit *do not re-propose the fix*, because
  the operator declined it today.

### Four pre-authorised defaults

So the run does not park on a question at 3pm: D1 (proceed with forbidding extras), D2 (drop the
`contact_mode` column only if nothing live reads it), D3 (**not** pre-authorised as a design — if
no honest detection point fires in *default* posture, ship F115's other three parts and write part
2 up as its own finding, because a detector that misses the case the finding is about reads as
coverage), D4 (the stray root files are gone; nothing to do).

### Driver

Windows Scheduled Task, not `ScheduleWakeup` and not `CronCreate` — both die with the interactive
session, measured 2026-08-15 when a nine-hour run got forty minutes. Each firing is a fresh
`claude -p` process that reads `STATE.json`, does one iteration, commits, pushes, exits.

### What a reviewer should distrust in this entry

Nothing was implemented at arming. The claim that the four decisions are settled rests on this
session's transcript, and the F115 decision in particular was taken in one question with the
operator on their way out — if the implementation surfaces a consequence the question did not
cover, that is the place to look first.

---

## Iteration 1 — F116-R1: explore and propose (13:01 local)

**Branch and log reconciled.** `STATE.json`'s `parent_sha` said `00fb5e5`; the branch was already
cut and sits three commits past it (`956ab07`, `8e1dd96`, `eaf68d0` — all arming bookkeeping). The
log header says "from master at `b2d565e`". Both are describing the same branch at different moments
of the arming session; nothing has diverged and `origin/master` is still at `b2d565e`. No `iteration`
or `last_heartbeat` field existed yet — iteration 1 added both.

**Delivered:** `openspec/changes/2026-08-29-an-unknown-field-is-named/` — proposal, design, tasks,
and a delta for a new `api-request-strictness` capability. `openspec validate --strict` passes.

### What round 1 measured rather than assumed

The queue item asked which other request models allow extras and whether the lax setting is a
default or a choice. Round 1 answered by walking the **running app's routes** — every `APIRoute`
with `POST`/`PUT`/`PATCH`, body annotation unwrapped to its `BaseModel` subclasses, `model_config`
read off each:

**36 forbid extras. 19 do not.** Nothing in `hub/hub/` sets `extra` to a lax value on a request
model. The only two non-default lax settings in the package are `config.py:21` (environment parsing)
and `spec_payload.py:68` (stored-payload parsing) — neither a request body.

The sharpest evidence that this is omission rather than policy: **`EvidenceRecord` exists twice with
an identical field list** — `agent_actions.py:826` forbids, `api/v1/spec.py:329` does not.
`EvidenceDecision` is the same pair. Inside `api/v1/spec.py` alone, eight models forbid and five do
not.

### The find that changes the shape of the fix

`hub/hub/schemas/spec.py:13`'s `SpecDocumentCreate` is lax **on purpose**, says so in its docstring,
and is backed by a requirement that shipped 2026-08-12:
`openspec/specs/agent-document-creation/spec.md:50-58` requires that an agent supplying a path is
answered by *minting one anyway* — "unexpressible rather than merely refused". A 422 mints nothing.

**A blanket sweep would breach a shipped requirement.** That is the round-3-shaped failure this
repository keeps producing, caught in round 1 only because the audit read docstrings instead of
counting models. So the rule proposed is not "every request model forbids extras" but "every request
model forbids extras **or says in the code why it does not**", with an enforcement test that carries
the exemption list.

### The answer to "one model or a shared base"

**Shared base** — `RequestModel` in `hub/hub/schemas/common.py`, plus a test that walks the routes.
Forbidding on `TriggerAgentRequest` alone leaves 18 of the 19 and does not touch F116's actual
complaint. `model_config = {"extra": "forbid"}` written 36 times has *already* failed as a
mechanism: it is invisible when absent, which is exactly how `TriggerAgentRequest` came to be lax
with 36 strict siblings in the tree. A base class is visible when absent and a test can see it.

### D1 resolved, and the breaking change stated

D1's `raise_it_if` was "the audit finds a request model where extras are load-bearing, or a shipped
client that relies on the tolerance". The audit found **one** load-bearing case —
`SpecDocumentCreate` — and it is exempted by name rather than swept. **No shipped client relies on
the tolerance**, verified caller by caller: `transport/http.py`'s log, heartbeat and session-sync
bodies carry declared fields only; the three UI `agent/trigger` call sites likewise; and
`http.py:161` already strips eight identity fields *because* most schemas forbid extras. Proceeding
under D1.

Two lax routes get **better**: `post_agent_output` already catches 400/422 and retries with a legacy
body, a fallback that today never fires against a lax Hub — so structure is silently dropped instead.

### Two hazards handed to round 2 rather than waved away

- `ContextUsageCreate.normalize_legacy` is `mode="before"` and rewrites legacy keys, so ordering
  *should* preserve it — but the design says to **prove that by running it**, not by reading
  pydantic's docs. If extras were checked first, every legacy context-usage body would start
  failing, and that is the one way this change breaks something quietly.
- Whether `api-request-strictness` deserves its own capability document. The delta directory is the
  expensive thing to move after a sync, so round 2 decides it before implementation.

### What a reviewer should distrust in this entry

The counts. 36/19 is the entire argument, and round 1 produced them from one script run in one
process. Task 1.1 exists to make round 2 re-derive them independently rather than read this table —
if the population differs, the proposal is wrong before anything else is checked.

Nothing was implemented. No test was written or run; F116 is still open and still reproducible.

---

## Iteration 2 — F116-R2: the independent review round (13:03 local)

**Branch and state reconciled, nothing to correct.** `STATE.json` said `iteration: 1`,
`current: F116-R2`, heartbeat released at 12:22. `git log` matched exactly: `20abc75` (release),
`e4722ff` (the R1 proposal), `eebcec4` (claim). Iteration 2 claimed the branch at 13:03.

**Delivered:** `openspec/changes/2026-08-29-an-unknown-field-is-named/` revised — proposal, design,
tasks and the delta. Tasks 1.1–1.4 ticked with what was measured. `openspec validate --strict`
passes. **Nothing implemented**, per the round discipline.

### The rule round 2 was given, and what obeying it cost

Round 1's own instruction was *"do not read this table, re-derive it"*. That was obeyed: the route
walk was written fresh before opening `proposal.md`'s audit section.

**The count survives, twice.** Walk one classified endpoint annotations; walk two used
`route.body_field` — FastAPI's own answer to what the body is. Both return **55 models, 36 strict,
19 lax**, the same names on both sides. Round 1's foundation is sound.

Round 2 also asked a question round 1 did not: what about models nested *inside* a body? Two are
reachable one level down (`AgentQuestionCreate`, `QuestionOption`) and both already forbid. The hole
is empty — but the enforcement test must recurse anyway, because "empty today" is exactly the state
`TriggerAgentRequest`'s 36 strict siblings were in.

### Three arguments were wrong. The decisions they supported were right.

This is the failure mode the round discipline was written for, and it turned up three times in one
round.

**D2 rejected the self-declaring-marker alternative because it would "make laxness *expressible*
again".** That is false. Under a `RequestModel` base, a subclass writing
`model_config = ConfigDict(extra="ignore")` overrides the base and pydantic accepts it — run and
confirmed. Laxness never stopped being expressible; the base only made it *visible*. The decision
(exemption list lives in the test) is unchanged, and its real reason is now written down: an
exemption should cost a second file and a second reader, not a self-declaration.

**D3 said "three of the models needing it also set `populate_by_name` … or run `mode="before"`
validators", naming four things.** Measured across all 55: **exactly one body model sets any
`model_config` key besides `extra`** — `messages.MessageCreate` — and it is already in the strict 36,
so it is not a model "needing it". No `spec_payload` model is a request body at all. Validators are
not `model_config` and were never at risk from what the base sets. Decision stands; the risk it
guards is one model and one key, not three.

**The proposal claimed `post_agent_output` "gets better, not worse"** — that forbidding extras makes
its `400`/`422` legacy-body fallback fire and do its job. It cannot. The fallback fires on what the
*server* answers, and the Hub it was written for is an old one running old code; nothing done to
this Hub's models reaches it. Against a current Hub the question does not arise at all:
`AgentOutputCreate` already declares all six fields the CLI sends. The claim is struck and replaced
with the true, smaller one — the value is prospective, not present. Round 1 also promised "two lax
routes get better" and named one; there is no second.

### D6 was proven, and proving it found a hole the change would have shipped

Task 1.2 said prove the `mode="before"` ordering **by running it**. Done at the model and through the
real route, with `extra="forbid"` on `ContextUsageCreate` alone:

```
POST …/agents/{a}/context-usage {"tokens_used":1200,"tokens_limit":200000}  -> 201
POST …/agents/{a}/context-usage {"status":"measured",…,"wat":1}             -> 422 extra_forbidden: wat
```

D6 is right: the before-validator runs first. **But the same probe found what D6 did not say:**

```
POST …/agents/{a}/context-usage {"tokens_used":1200,"tokens_limit":200000,"wat":1} -> 201
```

`normalize_legacy` builds a *fresh* dict, so on the legacy path an unknown field is dropped by the
translation before `extra` can see it. The route would have shipped **declaring that it refuses
unknown fields while one of its two vocabularies did not** — this change's own defect, reintroduced
inside the mechanism meant to satisfy it, and hidden better than the original.

Round 2's first answer was to write that down as a stated limit in the delta. That answer was wrong.
**The right one was already in the tree.** `TaskCreate`/`TaskUpdate` face the identical problem —
legacy `assigned_to`/`assigned_agent` aliases reaching a model that forbids extras — and solve it by
consuming only the aliases they recognise and passing everything else through, with the reason in a
comment at `hub/hub/schemas/tasks.py:92`:

> `# Remove legacy alias keys so extra='forbid' does not reject them`

So `normalize_legacy` is rewritten to that shipped pattern (new task **3.5**), not exempted. Run
against the real validator: every legacy shape still normalises (`{tokens_used, tokens_limit}` →
measured 1200; `{context_usage: 0.4}` → 40%), and `{…, "wat":1}` now answers `422` naming `wat`.
**The change needs no exemption for this route at all.** The operator's standing preference decided
this — the cleanest solution, and "more work" is never the objection — at the one place in this
round where taking the exemption was the easier move.

### The risk class is now enumerated, not sampled

A request body can carry two vocabularies by exactly two mechanisms, and both were counted across
all 56 body models including nested ones:

- **`mode="before"` model validators — three.** `ContextUsageCreate.normalize_legacy`, and
  `TaskCreate`/`TaskUpdate.normalize_assignee_aliases`. All three read: two already correct, one
  fixed by 3.5.
- **Field aliases — one.** `MessageCreate` (`from`/`to`), which already carries `populate_by_name`
  *and* `extra="forbid"` together, so both vocabularies work and unknown fields are still refused.

There is no third mechanism and no fourth instance. Round 3's task 1.6 was rewritten to re-derive
this rather than read it, because task 3.5 now rests on the enumeration being complete.

### 1.3 — the capability home, decided while moving is still free

**Its own document, renamed `hub-api-request-contract`** (`git mv`, round 2). No existing capability
can hold a rule spanning the operator- *and* agent-facing write surface: `agent-capability-plane` is
agent-facing (run credentials, the agent allowlist), `hub-interaction-feedback` is pointer and focus
states, `runtime-diagnostics` is the doctor's surface. Renamed because `hub-` is the corpus's prefix
for Hub-wide concerns while `api-` is used by no capability at all, and because a document named
after one property (`strictness`) has nowhere to put the second requirement about a request body —
`contract` is the subject, and the delta's own text already said "contract" seven times.

### 1.4 — all nineteen call sites, not the fifteen the task asked for

**Six of the nineteen have a UI write call site at all**, and every body sends declared fields only:
`agent/trigger` ×3 (`tasks.ts:365`, `AgentOutputPanel.tsx:655`, `NewConversationSurface.tsx:98`),
`accounting.ts:85`, `questions.ts:70`, `agents.ts:335` (from `AgentCreateDialog.tsx:185`), and
`agentChat.ts`'s rename. `session/sync` is **read** in the UI; its writer is the CLI. The CLI's own
bodies were re-read caller by caller and are clean, with `post_context_usage` the one that passes a
caller-supplied dict straight through — round 1 said so and it is still true.

**The five lax `project/spec/*` routes have no shipped caller of any kind** — only this repo's
`scripts/drive` harnesses — which is the likeliest reason their strict twins in `agent_actions.py`
were written and they were not.

Round 1's second named hazard is also closed: `SessionSyncRequest` declares `data` and nothing else,
and `sync_session` reads `body.data` at five sites and no sibling key.

### The suite measurement the proposal asked for, and what it cost to get an honest number

Round 1 left this open: *"R2/R3 must find every test that sends an extra field to a lax route. The
~23-minute cost is real, but the number is not a guess to carry into implementation."* Round 2 got
the number by patching all eighteen models to `extra="forbid"` — `SpecDocumentCreate` left alone —
and running the suite. **The number is zero.** Not one test in `hub/tests/` sends an undeclared
field to any of the nineteen routes.

Getting there was not clean, and the mess is worth recording because it cost most of the iteration.

| Run | Probe | Result |
|---|---|---|
| 1 | all 18 | stalled at ~95%, CPU frozen at 1019.6s across two samples ten minutes apart; killed |
| 2 | all 18 | stalled at the same place; killed |
| tail files, in two groups (16 files, 192 tests) | all 18 | **all passed**, 55s + 36s |
| `test_task_worktrees.py` alone (40 tests) | all 18 | **all passed**, 17s |
| baseline | none | **3510 passed, 84 skipped, 1 xpassed, 0 failed**, 26:04 |
| 3 (`-v -u`) | all 18 | **3510 passed, 84 skipped, 1 xpassed, 0 failed**, 25:46 |

Every one of the 3595 collected tests has now run with the probe genuinely applied — the first ~95%
in runs 1 and 2, the remaining files as groups — with **no failure anywhere**, and run 3 covered the
whole suite in one process with counts identical to the baseline's. The proposal's risk row "a hub
test sends an extra field to a now-strict route and goes red" is empty. That is a real result for
implementation: the eighteen edits should be behaviour-neutral for the existing suite, which also
means the suite currently proves nothing about this rule and tasks 2.2/2.3 have to supply that.

**What is not explained:** why runs 1 and 2 stalled at ~95% and run 3 did not. Run 1's stall is not
an inference — its CPU counter was byte-identical ten minutes apart while the process was alive, so
it was blocked, not slow. It is not the tree's: the baseline completed clean, and CI ran green on
all nine cells this morning. It is not any single test's: every file in the neighbourhood passes
alone and in groups with the probe on. Two candidates worth naming rather than guessing between —
the shared-connection interaction already written up as **F109** (one `StaticPool` connection across
sessions, order-dependent, known to bite ~1 run in 6), and this machine under three concurrent
`py -3.11` processes, which runs 1 and 2 had and run 3 did not. **It is not evidence about this
change, and it should not be carried into round 3 as if it were** — but a suite that can block
rather than fail is worth knowing about, and this is the second time F109's mechanism has cost a
session an hour.

### What round 3 gets

Tasks 1.5–1.7 stand, with 1.6 rewritten to re-derive round 2's two-vocabulary enumeration rather
than read it — task 3.5 now rests entirely on that enumeration being complete, and round 2 produced
it from one script and one reading, which is exactly the standing round 1's count was in.

### What a reviewer should distrust in this entry

The enumeration. "Three `mode="before"` validators and one aliased model, and there is no third
mechanism" is the strongest claim in this round and the one carrying the most weight, and it comes
from a single walk. If a body can carry a second vocabulary some way neither counted — a
`field_validator(mode="before")` on an individual field, a custom `__init__`, a dependency that
rewrites the body before it reaches the model — then 3.5 fixes one instance of a class that still
has members. Round 3 should try to break that sentence specifically.

Second: the suite result is a claim about *this* suite, not about callers. Zero red tests means no
test sends an undeclared field; it does not mean no client does. The callers were read separately,
by hand, and that reading is what D1 actually rests on.

Nothing was implemented. `hub/hub/` is byte-identical to where iteration 1 left it — the probe was
applied and reverted three times and `git status` is clean. F116 is still open and still reproducible.

---

## Iteration 3 — F116-R3: the second independent review (15:33 local)

**Branch and state reconciled, nothing to correct.** `STATE.json` said `iteration: 2`,
`current: F116-R3`, heartbeat released at 14:49. `git log` matched exactly: `368db0d` (release),
`5d1215d` and `6a48ebf` (the R2 revisions), `c01411a` (claim). Iteration 3 claimed the branch at
15:33.

**Delivered:** `openspec/changes/2026-08-29-an-unknown-field-is-named/` revised again — proposal,
design, tasks and the delta. Tasks 1.5–1.7 ticked with what was measured; two new decisions (D7,
D8), three new implementation tasks (2.2a, 3.6, 3.7), two new delta scenarios and one sharpened
requirement paragraph. `openspec validate --strict` passes. **Nothing implemented** — `hub/` and
`src/` are byte-identical to where iteration 2 left them, and the one scratch test written to drive
a claim was deleted before the commit.

Round 2 corrected three of round 1's *arguments* and left every decision standing. Round 3 corrected
two of the change's *decisions*. Both were found by running something, not by reading it.

### The population was never models — and rounds 1 and 2 counted models, twice

Round 1 counted `extra` across request models. Round 2 re-derived it by a second method and got the
identical answer: 36 strict, 19 lax, 55 models. Round 3 re-derived it a third time, from
`route.body_field` plus a recursive closure over the models' fields, and agrees again — 55 roots,
56 in closure, 37 strict / 19 lax.

All three counts answer a question the change does not ask. It needs to know *which write bodies
refuse an unknown field*. A body annotated `dict` is not a model, so it was never in the population,
and no re-derivation of a model count could ever have found it. There are three:

```
POST  /projects/{id}/agents/register        (agents.register_agent)
PATCH /projects/{id}/agents/{name}          (agents.patch_agent)
PUT   /projects/{id}/project/instructions   (instructions.put_instructions)
```

The test drafted in task 2.2 would have passed straight over all three — `body_field` is present,
the unwrap finds no `BaseModel`, nothing is asserted, green. The change's own delta says *"the
system SHALL detect a write contract that neither refuses undeclared fields nor states why it does
not"*, and it would have shipped a detector blind to the three worst cases. That is this change's
own subject, committed by the change.

**They are not academic, and this was driven rather than read.** `put_instructions` reads
`body.get("content", "")`. Through the real route:

```
PUT  {"content": "the operator's real instructions"}  -> 200 {"content": "the operator's real…"}
PUT  {"contents": "a typo"}                           -> 200 {"content": ""}
GET                                                   -> 200 {"content": ""}
```

One letter, and the operator's project instructions are gone. F116 loses a supervision posture;
this loses text. `patch_agent` fails two ways at once — absorbed silently for a self-registered
agent, and for a configured one it flips the reserved-name guard
`set(body.keys()) <= _unrestricted_fields` into a `409` blaming the agent's *name* for a typo in a
*field*.

**D7 decides each rather than sweeping them.** `put_instructions` gets a model here (task 3.6): it
is two lines and it is the live data-loss case. `register_agent` is recorded as declining, because
F111 — the very next change in this queue — deletes the route, and writing a contract for it is work
with a negative lifespan. `patch_agent` is recorded as declining and filed as its own finding: a
wide `"x" in body` partial update whose modelling turns per-field `400`s into `422`s across the
agent-editing UI, which needs its own review rather than riding in on this one. Task 2.2a makes the
test assert a body **is** a contract, with both exemptions named and reasoned. A defect that is
listed is a decision; a defect the walk cannot see is the omission this change exists to stop.

### D6's repair, taken at its word, breaches a requirement that shipped first

Round 2 found that `ContextUsageCreate.normalize_legacy` builds a fresh dict and so swallows unknown
fields on the legacy path, and fixed it — task 3.5, in these words: *"keep every key it did not
consume, so `extra='forbid'` refuses it."*

Round 3's instruction was to re-derive the enumeration 3.5 rests on. It did that, and then did the
thing the enumeration could not tell it: **implemented round 2's sentence literally and ran it.**
Four legacy bodies are refused:

```
{"tokens_used":1200,"input_tokens":1200,"tokens_limit":200000}          -> 422  input_tokens
{"tokens_used":1200,"tokens_limit":200000,"context_limit":200000}       -> 422  context_limit
{"context_usage":0.4,"context_usage_ratio":0.4}                         -> 422  context_usage_ratio
{"tokens_used":1,"tokens_limit":10,"observed_at":1.0,"updated_at":1.0}  -> 422  updated_at
```

`normalize_legacy` picks each operand first-wins from an alias tuple, so *consumed* means the alias
that won, not the alias set — and a body carrying two names for one operand is not a mistake, it is
what a rolling upgrade emits. Two of those four fields are named in a **shipped requirement**,
`agent-context-usage`'s *Legacy context compatibility*:

> readers SHALL normalize unambiguous legacy aliases including `tokens_used`, `tokens_limit`,
> **`input_tokens`**, **`context_limit`**, and ratio-form `context_usage`.

Round 2 tested two legacy shapes and each happened to carry one alias. This is the same shape as
2026-08-28, when round 3 caught rounds 1 and 2 both breaching a four-day-old requirement — and it is
sharper here, because the breach was inside the repair for the previous round's finding.

**D8 corrects it:** the residue is the request minus the *whole* legacy vocabulary, not minus the
names that were read. Verified over twelve bodies — every legacy shape normalises exactly as today,
the modern path is untouched, and only the genuinely undeclared field is refused. One side effect,
now asserted rather than discoverable: `breakdown`, a *declared* field the fresh dict silently drops
on the legacy path, survives into the model.

The precedent round 2 cited is right and its transcription was wrong. `tasks.py:92` removes **both**
assignee aliases whichever one it read. And that precedent carries the narrower version of the same
hole — measured live, `TaskCreate {"assignee":"a","assigned_to":"a"}` answers `422 assigned_to`,
a rolling-upgrade body refused a name the contract itself accepts. One line, so task 3.7 rather than
a finding, plus a delta scenario so the rule covers it.

### What round 3 confirmed rather than corrected

- **1.6, the pydantic layer holds.** Re-derived from `__pydantic_decorators__` — pydantic's own
  registry — rather than a grep: 3 `model_validator(mode="before")`, 1 aliased model. Nine further
  candidate mechanisms measured **empty**: `mode="wrap"` model validators, `before`/`wrap` field
  validators, v1 `@root_validator`, v1 `@validator`, `Annotated` before/wrap/alias metadata,
  `alias_generator`, custom `__init__`, custom `__get_pydantic_core_schema__`, overridden
  `model_validate`. The route-layer escape is empty too: **no** write endpoint takes a `Request` or
  reads `request.json()`/`.body()`/`.form()`, so nothing rewrites a body before its model sees it.
- **1.5, a second tolerance-dependent requirement exists and is out of reach.**
  `spec-document-authority`'s *The payload contract is versioned and forward compatible* — "no
  validation error is raised on their account" — but that tolerance lives inside
  `SpecDocumentSubmission.document: Any` and `MergeRequest.payload: dict`, below models that already
  forbid extras. Recorded so that narrowing either field later is known to breach it. Two near
  misses cleared: `agent-stream-events`' cross-version compatibility is about *response* fields and
  text-only producers that send *fewer* fields, so `AgentOutputCreate` is safe to tighten.
- **1.7 is clean four ways.** All 19 lax models set no `model_config` of their own. `MessageCreate`
  is the only strict model setting more than `extra` (the `validate_by_*` keys beside it are
  pydantic 2.11 derivations of `populate_by_name`, not source). No body model has a subclass, so no
  `ConfigDict` propagates onto anything else, and none has a non-`BaseModel` base. And a question
  rounds 1 and 2 did not ask: two body models are **also** response models (`QueueSettings`, nested
  `QuestionOption`), so `extra="forbid"` reaches a response path — both safe, because their handlers
  return constructed instances rather than dicts. That is now a named risk instead of an accident.

### What a reviewer should distrust in this entry

**D7's decision, not its finding.** That the three `dict` bodies exist is measured and that
`put_instructions` blanks is driven. What is a judgement is deferring `patch_agent`: the argument is
that modelling it changes `400`s to `422`s across the agent UI and belongs in its own review. If
that is wrong, this change ships a named exemption over a live defect, which is better than a silent
one but is not a fix.

**The twelve-body verification of D8 is a model-level run, not a route-level one.** Round 2 drove
`ContextUsageCreate` through the real route and round 3 did not — it validated against the real
model class. The `mode="before"`-runs-before-`extra` ordering that makes this work is what round 2
proved at the route, and nothing in D8 changes that ordering, but the twelve rows themselves have
not been through HTTP. Task 4.5 should carry one of the rolling-upgrade pairs.

**Nothing was implemented and the suite was not re-run.** Round 2's 26-minute measurement stands
untouched, deliberately — no code changed. `hub/` and `src/` are byte-identical to iteration 2's
tree; the only files this iteration wrote are the four under
`openspec/changes/2026-08-29-an-unknown-field-is-named/`.

**F116 is still open and still reproducible.** Three rounds are done and the change is ready to
implement, which is exactly where the round discipline says it should be.

---

## Iteration 4 - F116-IMPL: the change is implemented, driven and archived (15:48-16:36 local)

Started at 15:48, twelve minutes inside the 17:00 rule, so F116-IMPL ran rather than being parked.
It finished: the change is implemented, the full hub suite is green on it, it is driven live, and
`hub-api-request-contract` is in the corpus. **F116 is closed.**

### What shipped

`RequestModel` (`extra="forbid"`) in `hub/hub/schemas/common.py`, and **every one of the 57 request
body models reachable from `app.routes` now inherits it** except the single named exemption. The
route that started it:

```
POST .../agent/trigger {"agent":"asker","message":"...","permission_mode":"manual"}
  -> 422 {"loc":["body","permission_mode"],"type":"extra_forbidden"}
```

Driven against a Hub on **8011 running this branch** - restarted onto it, because the instance that
was up had been running since yesterday 16:57 and served stale code (confirmed by its start time and
its empty project list, then reseeded with a project, a Haiku runner and a bound agent). The working
path was driven in the same session and still works end to end: posture in `overrides` -> card in
six seconds -> operator allows -> `hello.txt` written -> run idle. A refusal that broke the working
path would not have been a fix.

Three repairs the forbidding required, none of them exemptions:

- `PUT .../project/instructions` took `body: dict` and read `body.get("content", "")`, so
  `{"contents":"x"}` answered `200` and **blanked the project's instructions**. Driven live before
  and after: it now `422`s naming `contents`, and the stored text survives - the second half is the
  point.
- `normalize_assignee_aliases` stripped its aliases only when `assignee` was absent (`TaskCreate`)
  or never at all (`TaskUpdate`), so a rolling-upgrade body was refused for a name the contract
  accepts. Both strip unconditionally now; the canonical value wins.
- `normalize_legacy` - see below.

Committed in five pieces so the behaviour change, the refactor and the documentation are reviewable
apart: the red test first, then the fix, then the 37-model refactor, then the suite's finding, then
the archive.

### The test was red before it was green, and red again on demand

2.2 / 2.2a / 2.3 were committed **red on purpose**, naming the eighteen tolerant models, both
non-exempt untyped bodies, and F116's own body answering `409` where it should answer `422`. 4.2's
mutation check: reverting `TriggerAgentRequest` to `BaseModel` reds both the surface walk and F116's
body. A test that has never failed proves nothing, so this one has failed twice on request.

### What the full suite found - and why it matters more than the fix

4.3 called itself "a regression check, not a discovery run - a red test here is something 3.1-3.5
did". It was a discovery run. Four tests went red:

```
test_bola.py:142          {"percent": 50, "warning": False}         -> 422 warning
test_context_usage.py:216 {"agent": ..., "percent": 0, "warning": False,
                           "critical": False, "updated_at": ...}    -> 422 warning
```

The second test's own docstring says what that body is: *"An older CLI posts `{"percent": 0}` on
every session reset/compaction."* The deleted watchdog computed `warning`/`critical` from the
percentage and pushed them with every sample (`_check_context_usage`, found in commit `578afad4`),
and the body repeated the agent's name beside the one already in the route's path.

**D8 enumerated the legacy vocabulary from the names `normalize_legacy` reads. These three it reads
nowhere** - no alias tuple mentions them, no line consumes them - because the contract stopped
acting on them: the Hub derives its own thresholds, and the route already carries the agent. A name
nothing reads leaves no trace to enumerate, and the fresh-dict rebuild is exactly what kept that
invisible: rebuilding drops them silently, so the omission had no symptom until the rebuild stopped.

And the first body is *verbatim* `agent-context-usage`'s scenario **"Legacy data claims zero without
a limit -> the UI SHALL show unavailable rather than a trusted zero-percent bar."** A `422` means
the sample never becomes `unavailable`; it becomes an error. That is a breach of a shipped
requirement - the same class D8 protected, by the same mechanism, one layer further out.

Fixed as `_RETIRED = ("agent", "warning", "critical")` in the vocabulary, with a test naming both
shapes, **and with a delta paragraph and scenario** so the rule covers the case rather than the code
carrying a patch under a rule that does not mention it. Recorded as D9.

**Three rounds in a row the defect was the enumeration, not the code.** Round 2 found round 1's,
round 3 found round 2's, implementation found round 3's. Each was strictly narrower than the last,
and none was found by re-reading the previous round - they were found by re-deriving the population
by a different route, and finally by running everything. That is the round discipline's actual
mechanism, and it is worth more than this change is.

### F117 filed, not fixed

`PATCH .../agents/{name}` still takes `body: dict`. Driven live: `{"permission_timeout_secondz": 5}`
answers `200` and changes nothing - F116's own shape, on the route carrying an agent's *safety*
settings. D7 described its guard too generously ("400 for an unknown key"); measured, the
`set(body.keys()) <= _unrestricted_fields` check fires **only** for a session-synced configured
agent and answers `409` about the *name*. For a Hub-owned agent - every agent an operator creates in
the UI - there is no check at all. Named in `NO_CONTRACT_BY_DESIGN` with that reason, because a
named exemption over a live defect is better than a silent one but is not a fix.

### Verification, in full

| | |
|---|---|
| Hub suite | **3540 passed / 84 skipped / 1 xpassed / 0 failed**, 26:00 - the 3510 baseline plus exactly this change's 30 tests |
| CLI suite | 440 passed / 3 skipped |
| ruff / black / mypy | clean over CI's exact paths |
| `openspec validate --specs --strict` | **43/43** with `hub-api-request-contract` added |
| Live drive | F116's body, the `overrides` path with a real Haiku turn and an allowed card, the instructions blanking, and a rolling-upgrade context pair - all on 8011 running this branch |

Two suite runs, not one: the first was killed at 29% once the four reds were diagnosed, because its
remaining results would have been about code that no longer existed.

### What a reviewer should distrust

- **The 37-model refactor (3.4) is asserted behaviour-preserving and only the suite backs that.**
  Each model dropped a hand-written `model_config` for an inherited one; `MessageCreate` keeps
  `populate_by_name` and `ProjectSettingsUpdate` swapped `__config__=ConfigDict(extra="forbid")` for
  `__base__=RequestModel`. Both were checked by reading their merged `model_config` back. Nothing
  else distinguishes the refactor from the fix except the commit boundary.
- **F117's deferral is a judgement, not a finding.** That the defect is real is measured live. That
  it belongs in its own review - because modelling the body turns the handler's hand-raised `400`s
  into `422`s across the agent settings UI - is an argument, and if it is wrong this change ships a
  named exemption over a live defect.
- **`_RETIRED` is three names, and what found them was a suite run, not an enumeration.** There is
  no reason to believe a fourth retired name does not exist in some older writer's output; what
  there is, now, is a test that goes red the moment one arrives rather than a silence.
- **The queue's later items are untouched.** F111+F3, F113 and F115 are still unproposed, and
  E2E-DRIVE has not started. F116 is one of four.

## Iteration 5 — reconciled from its commits, because it died before writing this (17:00-17:11 local)

Iteration 5 left no log entry. It committed six times and then stopped mid-suite: `97b2dbc`,
its last act, is a heartbeat with the message *"heartbeat while the hub suite runs"*. So the
verification it started was never read by the process that started it. What it did, from the
commits and the working tree:

- `b30c0d4` / `5e038df` — **F118 and F119 fixed.** `_SECRET_VALUE_RE`'s credential prefixes were
  unanchored and `task-` ends in the literal `sk-`, so every task id the Hub has ever minted was
  stored as `ta<redacted>`. Both prefixes now carry `(?<![A-Za-z0-9_])`. `scheduler`'s second
  copy of the whole rule, predating F31, was deleted rather than synced.
- `666d83b` — **rows 12 and 16 driven**, F118-F122 filed.
- `155167a` — **row 17**, and F122 proved from the other side.
- `53bd8a8` — **row 19's concurrency and stop halves**, both held.

**Iteration 6 finished its verification.** Hub suite `3554 passed / 84 skipped / 1 xpassed /
1 failed` in 27:01 — the failure is `test_agent_trigger.py::test_spawn_failure_broadcasts_run_failed_event`,
named in `known_flakes` as F109's ~1-in-8, and **it passes alone** (re-run, 1 passed in 2.86s).
CLI `440 passed / 3 skipped`. `ruff` / `black` / `mypy` clean over CI's exact paths. So iteration
5's fix is green, and the branch is green.

## Iteration 6 — row 19's crash half, four ways (17:38-18:2x local)

`next_action` said E2E-DRIVE, and the row the last three sweeps kept deferring was the one that
needs the Hub itself killed. Four harnesses, all in the `drive-wt-0829` fixture on 8011 against
this branch, all with `Stop-Process -Force` so `lifespan`'s `terminate_all_active_runs()` never
runs — a crash, not a bounce.

| Harness | What it kills the Hub on | Verdict |
|---|---|---|
| `t_row19_crash.py` | a plain turn | held |
| `t_row19_crash_card.py` | a **permission card** on screen | held |
| `t_row19_crash_question.py` | **`ask_user`** blocking | held |
| `t_row19_crash_task.py` | a **task-bound** run, three times | held |
| `t_row19_crash_job.py` | a **job firing** | held, and **F123** |

**The load-bearing measurement.** `reconcile_interrupted_runs` skips any run whose
`pid_alive(run.pid)` is still true, so the whole recovery depends on the spawned CLI being dead.
Measured rather than assumed, by listing the descendant tree before the kill and re-checking each
pid after: the `Run` row's pid **is `claude.exe`**, and it dies with its Hub along with the
`OpenConsole.exe` between them. Had the ConPTY child been orphaned the way a Windows grandchild
ordinarily is, every crashed run would stay `running` forever and wedge its agent.

**What held, briefly.** Four seconds from the Hub answering again to the operator's message being
back in a live turn, with no operator action — and the agent reads the *"delivery attempt 2; an
earlier attempt was cut off"* note and says so in its own transcript. A pending card becomes
`expired` and answering it returns `409 … already expired`. A question needs no expiry pass at all
because `asker_waiting` is derived from the asking run's status, and both UI surfaces read the
field rather than merely receiving it. Three crashes on one input walk `attempts 1 → 2 (provider
session cleared) → 3 (withdrawn)`, and the loss is announced on four separate surfaces including
a red **"not delivered"** chip carrying the reason.

**F123 (C, open)** is the one thing that is wrong. The Hub's own crash recovery redelivered a
job's message, a new run on the same conversation completed the work — and the job's history still
reads `failed`, with no row for the retry, because `finalize_job_run_for_conversation` matches only
`status == "in_progress"` and reconciliation has already moved the row on. Not fixed: it is a
decision about what a `JobRun` *is*, and **F121** is already open against the same table for the
same confusion. Three shapes costed in the finding, with a recommendation and why the other two
are worse.

**Two readings corrected by measurement rather than argument.** The abandoned runs had zero stored
output rows next to a completed run of the same work with sixteen, which reads exactly like a
crash eating the transcript. Killed deliberately *after* rows existed: 4 before, 4 immediately
after, 4 after the restart — nothing is discarded. What made that look impossible is that an
interrupted run's `ended_at` is the **restart** time, so its duration is inflated by the outage;
not a finding today because `ended_at` is on no response schema and no UI component reads it, but
a nine-hour outage would report a nine-hour run to whoever surfaces it first.

**And one harness that lied.** `t_row19_crash_card.py`'s first run posted `{"decision": "allow"}`
when the field is `allow`, scored the resulting `422` as *"deciding a dead card is refused"*, then
failed to answer the fresh card with the same typo — which expired at 120 s, ended the run without
the write, and was scored *"the work completed after the crash"* because the check watched the
agent go idle rather than the file appear. **Two green verdicts, both false, from one misspelled
field.** That is F116's own lesson arriving from the other side: the `422` did everything right and
the client that caused it still misread it. The re-run asserts the artefact (`os.path.exists`) and
the exact status code (`== 409`, not `>= 300`).

### Verification

| | |
|---|---|
| Hub suite | 3554 passed / 84 skipped / 1 xpassed / 1 failed (F109's known flake; passes alone) |
| CLI suite | 440 passed / 3 skipped |
| ruff / black / mypy | clean over CI's exact paths |
| UI | untouched this iteration — no `hub/ui/src` change, so no bundle rebuild |
| Jobs / loops left enabled | **none** — `/jobs` and `/loops` empty in both 8011 projects |

### What a reviewer should distrust

- **Five "held" verdicts and one finding is a suspicious ratio**, and the card harness proves the
  mechanism by which it could be wrong. Every remaining verdict in these harnesses asserts either
  a durable artefact or an exact status code, but they were written by the same hand that got it
  wrong once.
- **The crash window is not controlled.** Each harness kills the Hub a fixed number of seconds
  after the agent reports `running`, so all five specimens died at roughly the same point in a
  turn. A crash during the final flush, or between `run.status = "completed"` and the commit that
  follows it, is a different case and is **not** driven.
- **F123's recommendation (a `continuity_warning`-style field) is an opinion, not a finding.** What
  is measured is that job history says `failed` for work that completed.
