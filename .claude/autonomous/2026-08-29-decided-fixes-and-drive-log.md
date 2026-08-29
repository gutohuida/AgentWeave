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

## Iteration 7 — row 11's second half: a loop's two endings (18:13–18:27 local)

`next_action` named three thin rows and ordered them; (a) was row 11's ending — *"a loop that
fires, claims, works, drains and STOPS, then is re-enabled after stopping"*. Driven in full, both
endings, plus the check that separates them from a loop that merely *says* it stopped.

**The Hub was not restarted.** 8011's uvicorn started 18:06:50 (measured from `Win32_Process`
`CreationDate`, not assumed), `GET /api/v1/projects` lists `proj-dc4d43543bea` with its three Haiku
agents, and nothing under `hub/` changed this iteration — so it serves this branch's code and a
restart would have bought nothing.

| Harness | Ending it drives | Verdicts |
|---|---|---|
| `t_row11_loop.py` | queue drained (`ending_state: "completed"`) | **19/21** |
| `t_row11_loop_quiet.py` | stop time passed (`ending_state: "stopped"`) | **11/12** |

**What held.** The creating call made the job, the `Loop` row and both queue entries together and
reported the queue it had just seeded. One task at a time, two real Haiku turns, both artefacts on
disk with exactly the content asked for, each in its own task checkout on its own branch, `main`
untouched. A queue of completed-but-unapproved work **stalled rather than stopped**, and the
skipped row carried a reason naming the remedy — and a second identical tick incremented
`tick_count` on that row instead of writing a duplicate, which is design D6 working. Approving both
drained it; the next tick wrote all four ending facts. Three restart attempts, three refusals,
each machine-readable and each quoting a real `stopped_at` — the `"an unknown time"` fallback F13's
write-up found live did not appear once.

**And the one that matters most: stopped is *true*, not merely reported.** A loop given a `stop_at`
two minutes in the past ended on its first firing, spawned no agent at all (its queued task was
still `pending` afterwards — the stop condition is checked before the spawn), and then sat through
160 seconds of wall clock, three cron ticks, with `run_count` at zero and one history row. That is
the exact property `loop_ending.py`'s own docstring records going wrong once, when a loop that read
`stopped` at 23:09 ran twelve more real turns.

**F124 (B) — a loop's work can never reach the main branch.** Both loop tasks were approved by the
operator and `main` never moved. The integration record says why, honestly, and the UI renders it —
but for a loop the reason is *permanent*, which is precisely what `task_integration.py`'s own
comment says none of its reasons are. Commits are resolved through `TaskRequirementLink →
RequirementEvidence (accepted) → EvidenceFootprint`; a loop's `initial_tasks` carry no requirement
links, so `record_evidence` has nothing to name, so nothing can ever be accepted. The card offers
**"Try again"** anyway — pressed here, it answered `200` and appended a second identical `skipped`
row, while `integration-preview` already knew `will_merge: false, targets: []` and was not asked.
Three shapes costed in the finding, with a recommendation. Not F122: that task *had* evidence, and
its complaint is that a flow cannot get it accepted.

**F125 (C) — a task's title cannot be changed by anybody.** Found by accident: `TaskUpdate` has no
`title` field and `TaskDetailDrawer` has no editor. Filed rather than fixed, because whether that
is a gap or a contract is the operator's call. What is not in doubt is that **F116's own change is
what made it visible** — before the `RequestModel` base landed this PATCH answered `200` with the
title unchanged, F117's exact shape, on the field most likely to be edited by hand. The strictness
caught its first thing in the wild within a day, in a harness that was not looking for it.

**F121 strengthened, not restated.** The badge under-counts a stalled loop (`run_count` 2, history
4 rows over 5 ticks) exactly as it over-counts a wide flow (4 rows for 2 firings). Same word, two
divergences, opposite directions — which removes the reading that F121 is a flow-only quirk.

### Verification

| | |
|---|---|
| Suites | **not re-run, and deliberately** — nothing under `hub/`, `src/` or `tests/` changed this iteration. The only Python added is two `scripts/drive/t_*.py` harnesses that no test imports. The branch's last full verification stands (iteration 6: hub 3554 passed / 1 known F109 flake that passes alone, CLI 440 passed, ruff/black/mypy clean over CI's paths). |
| The product | driven live, 31 assertions across two harnesses, 30 held; every verdict asserts a durable artefact (`git ls-tree`, file contents) or an exact status code — never `>= 300`, never "the agent went idle" |
| Jobs / loops left enabled | **none** — `/jobs` and `/loops` empty in both 8011 projects, confirmed after teardown |
| Lint on the new harnesses | `scripts/` is outside CI's lint paths (`ruff check src/ hub/ tests/`), and the existing drive scripts are not black-clean either; the two new files match the directory as it is |

### What a reviewer should distrust

- **30 of 31 held, and the one that did not was my assertion being wrong rather than the product.**
  That ratio is the shape iteration 6 warned about. The mitigation is the same one it adopted: the
  artefact assertions read the file (`ALPHAONE`, `ALPHATWO`) and the branch (`git ls-tree main`),
  and the refusal assertions compare exact codes. It is still one hand writing both sides.
- **The two `[BAD]` verdicts in `t_row11_loop.py` are kept failing on purpose.** `run_count ==
  len(history)` asserts something the design never promised. Deleting it would delete the
  measurement that strengthened F121; leaving it green would have meant weakening it until it
  passed. Anyone running the harness sees two reds that are a footnote, and the footnote is in
  `FINDINGS.md`.
- **F124's third shape is a recommendation, not a finding.** What is measured is that a loop's
  approved work stays on its branch, that the reason is structural rather than situational, and
  that the retry offered for it appends a row and changes nothing. What to do about it is an
  argument.
- **Only one loop shape was driven per ending.** One agent, two tasks, no dependencies, no
  questions, no `blocked` task, no delegated `control`. A loop whose queue stalls on a *dependency
  gate* or an unanswered question reaches `_loop_stall_reason` by a different branch and was not
  driven.

## Iteration 8 — row 15's cutover leg, and a checkpoint that can be spent twice (18:33–18:45 local)

`next_action` ordered three thin targets and put row 15's cutover first: *"F89 was found there and
fixed; the cutover leg itself has not been driven end to end."* Driven in full —
`scripts/drive/t_row15_cutover.py`, **35 of 36 verdicts held**, and the one that did not is a real
defect with a live reproduction.

**The Hub was not restarted, and both halves of that were measured rather than assumed.** 8011's
uvicorn was created `2026-08-29 18:06:50` (`Get-CimInstance Win32_Process`), the newest commit
touching `hub/` is `17:04:08`, and `GET /api/v1/projects` lists `proj-dc4d43543bea`. It serves this
branch's code and nothing under `hub/` changed this iteration.

### What was driven

One real Haiku turn on `gamma`, deliberately shaped so the handover could be *proved* rather than
inspected: write `CHECKPOINT_A.txt` containing `ANCHORONE`, **do not** write `CHECKPOINT_B.txt`,
and end the reply with the line naming `CHECKPOINT_B.txt`/`RELAYTWO` as the next action. Then:
refuse a checkpoint with no runner configured, configure one, generate, render, cut over, press
cutover a second time, continue the successor, and look on disk.

**The relay is the assertion that matters, and it held.** The predecessor was told not to write
`CHECKPOINT_B.txt` and did not. After `POST /conversations/{successor}/continue`, the file exists
in `gamma`'s worktree containing `RELAYTWO`. The checkpoint carried the work across a conversation
boundary end to end, and a file on disk is the proof — not a summary, not a status field.

Also held, none of it driven live before: the no-runner refusal is exactly **409** and names project
settings rather than quietly spending another agent's runner; a partial `PUT /settings` left
`hop_budget` and `checkpoint_mode` alone; generation returned **201** in 17s with
`probe_status: passed`; `files_changed` was `["CHECKPOINT_A.txt"]`, the file the turn really wrote;
the rendered artifact is 2,035 characters of envelope + body and is *honest* about the task list not
being conversation-scoped; and after cutover the predecessor is `archived`, the successor is
`open`/`handoff` with a derived title, and its queue entry is `origin_type: checkpoint`, addressed
to the successor, framed with the delivery preamble.

### F126 (B) — a spent checkpoint can be cut over again

Two `POST .../checkpoints/ckpt-5acb5c671217/cutover` calls, two `200`s, two successors —
`conv-b21d999ecaf0` and `conv-c1799d084153` — both `open`, both `origin: handoff`, both carrying the
**identical** derived title. In the navigation tree they are indistinguishable.

**And the duplicate did real work.** `continue` was called exactly once, on the first successor.
Both entries came back `delivered`, in two different runs (`run-cdad300b6180`,
`run-99ba2ab65297`), and the second successor's transcript reads *"Good! The files already exist"*
before re-verifying and re-closing the same task. A whole billed turn spent rediscovering that
there was nothing to do.

Mechanism: `cut_over` refuses on `checkpoint.status != "ready"` (unchanged by a cutover) and on
`archivable(predecessor)` — whose first line is `if conversation.lifecycle == "archived": return
None`. That early return is correct for what `archivable` is *for*; it is the wrong question here.
Nothing records that a checkpoint has been spent.

The reason this has not shown up in the UI is the sharp part. `checkpointOperationStore` holds an
`inFlight` map and does take-then-cutover as one act — so a double-click *inside one tab* coalesces.
That guard is client-side and per-tab. A second tab, a reload between the 201 and the cutover, a
retried request, or any non-UI client gets two successors. The Hub's own standard elsewhere is a
server-side claim: `take_checkpoint` holds `_checkpoint_claims` for exactly this reason — on the
*cheaper* half of the pair. Generation is guarded; cutover, which is durable, is not.

Filed with three shapes costed and a recommendation (give `Checkpoint` a
`cut_over_to_conversation_id` and refuse when set — it also answers "where did this checkpoint go",
which nothing can answer today). **Not fixed:** it wants a migration, and a spec loop that cannot
finish before 20:00 must not be started.

Recorded alongside it, because it should be decided at the same time: the UI's cutover banner
filters on `trigger === 'context_pressure'`, so a checkpoint the operator generated **on purpose**
is never offered a cutover anywhere in the UI.

### Verification

| | |
|---|---|
| Suites | **not re-run, deliberately** — nothing under `hub/`, `src/` or `tests/` changed. The only file added is one `scripts/drive/t_*.py` harness that no test imports. The branch's last full verification stands (iteration 6). |
| The product | driven live, 36 assertions, 35 held; every verdict asserts a durable artefact (a file's contents in the worktree, a queue row, a lifecycle) or an exact status code — never `>= 300` |
| Jobs / loops left enabled | **none** — both 8011 projects re-checked after teardown: two jobs, both `enabled: false`, zero loops |
| Settings left changed | none — `checkpoint_runner_id` is reset to `null` in the harness's `finally`, confirmed by re-reading `/settings` for both projects |

### What a reviewer should distrust

- **35/36 is again the ratio iteration 6 warned about.** The mitigation is the same: the
  load-bearing assertions read the filesystem (`CHECKPOINT_A.txt`, `CHECKPOINT_B.txt`) and exact
  status codes, not the Hub's own account of itself. It is still one hand writing both sides.
- **The second-cutover assertion was written expecting a refusal, from reading `archivable` first.**
  That is the honest order — the code was read, a refusal was predicted, and the drive contradicted
  the prediction — but it does mean the harness went looking for this one rather than tripping over
  it. The billed second turn was *not* predicted and was found only by reading the queue afterwards.
- **One checkpoint shape only.** Operator-triggered, `probe_status: passed`, no open questions, no
  permission decisions, no predecessor checkpoint in the chain. A checkpoint that fails its probe,
  or the second link of a chain (`previous_checkpoint_id` set), reaches cutover by paths not driven.
- **`continue` was tested on a successor that had a queue entry waiting.** Its refusal/waiting
  branches (`waiting_reason` non-null) were not reached.

## Iteration 9 — the stall shapes hold; two findings about pressing Run (18:43–19:45 local)

`next_action` offered three thin targets and (b) was the loop stalls: *"a loop that stalls for a
reason OTHER than 'nothing to review' — a dependency gate, or an unanswered question on a `blocked`
task. Iteration 7 drove only the completed-but-unapproved branch of `_loop_stall_reason`; the other
three exist and none has been driven."* All three are now driven, and the accident of getting the
setup wrong the first time found two defects the plan did not contain.

**The Hub was re-measured, not assumed.** 8011's uvicorn was created `2026-08-29 18:06:50`
(`Get-CimInstance Win32_Process`), the newest commit touching `hub/` is `17:04:08`, and
`GET /api/v1/projects` lists `proj-dc4d43543bea`. It serves this branch's code, and nothing under
`hub/` changed this iteration.

### What was driven — `t_row11_stalls.py`, 28 of 28

Three stall shapes, each asserted against the **exact** sentence rather than a substring: the
dependency gate with a workable prerequisite (`1 still awaiting a prerequisite's approval`), the
gate with a `rejected` one (`1 gated on a rejected prerequisite that will not clear on its own`),
and the ungated queue holding one `blocked` task (`no claimable task among 1 open (1 blocked)`).
Each came back **409** from `POST /jobs/{id}/run` with the loop left alive — `ending_state` null,
`enabled` true, `next_run` set. Skipped is not stopped.

Design **D6's coalescing** was driven for the first time and is correct: the same stall twice
appended no row, counted `tick_count` 1 → 2, froze `fired_at`, and emitted no second
`job_run_skipped` event; changing the shape wrote a new row and left the old count where it was.
Zero spend across four firings — every `JobRun` is a `skipped` with a null `session_id`, and the
loop's agent never left `idle`.

The operator-side dependency route (F36) was exercised on the way: 201, and afterwards the edge
reads from both ends (`prerequisites` on B, `dependents` on A).

### F127 (B) — a healthy loop answers 500 when you press Run while its agent is busy

The first run of the stall harness omitted `blocked_reason`, so the task never reached `blocked`,
the firing **claimed it and spent a real turn**, and the two firings after that came back
`500 Failed to fire job`. That was worth chasing rather than tidying away.

`_do_fire_job` has two branches that decline and deliberately record nothing. F48 fixed one of them
(`DECISION_IN_FLIGHT`) by having `run_job` re-derive the decision and answer 409 *"nothing is
wrong"*. The other is the **busy guard**, and F48's re-derivation cannot see it: it calls
`decide_firing`, which never reaches the guard. So the operator gets a 500 carrying the bare
fallback string, with no `JobRun` and nothing in the loop's history to explain it — while
`ending_state` is null, the job is enabled and its task is still `pending`.

Reproduced deterministically in `t_run_while_busy2.py`, **7/7**: park one active task on every
sibling agent so `_agents_that_are_free` is genuinely empty, put the job's own agent mid-turn, press
Run. Not fixed — the honest fix makes the re-derivation ask the same question the firing asked, and
that wants a round.

### F128 (B) — a loop runs on an agent its job does not name

The first attempt at F127 (`t_run_while_busy.py`) failed to reproduce and found this instead, so
five of its eleven verdicts are BAD: they are **the prediction being wrong, not the product
misbehaving**, and the file is kept with that stated at the top rather than quietly rewritten.

Job `busy-run` was configured `agent: gamma`. With gamma mid-turn, pressing Run answered **200** and
the work went to **alpha** — `conv-a51b18211d43`, origin `job`, the loop's id on it, and the task's
`assignee` reading `alpha`. `_loop_flow_busy_reason` refuses only when the job's agent is busy *and*
`_agents_that_are_free(session, project_id)` is empty, and that list is project-scoped. Its own
docstring asserts the invariant that a single-agent loop "reaches that by the general rule — its one
agent is the busy one and the free list is empty"; **that is only true in a project with exactly one
agent.** This is the failure mode CLAUDE.md names: an argument that is wrong about code that may
well be right. Design D12 chose width deliberately and `job.agent` really is D2's default — so this
is filed as **the operator's decision**, one decision with two shapes (loop-scoped free list, or
stop presenting `job.agent` as who runs the loop), not a fix.

### Verification

| | |
|---|---|
| Suites | **not re-run, deliberately** — nothing under `hub/`, `src/` or `tests/` changed. Three new `scripts/drive/t_*.py` harnesses, which no test imports, plus FINDINGS.md. The branch's last full verification stands (iteration 6). |
| The product | driven live: 28/28 on the stalls, 7/7 on the F127 repro, and one exploratory harness whose wrong prediction is documented in place |
| Jobs / loops left enabled | **none** — `GET /jobs` shows no enabled job and `GET /loops` lists none; every loop this iteration created was stopped through `PATCH stop_reason` and archived |
| Tasks parked for the repro | all rejected in the harness's `finally`, confirmed by re-reading `/tasks` |
| Agent spend | two Haiku turns deliberately (the F128 errand and the F127 errand), plus one accidental turn from the mis-set-up first run |

### What a reviewer should distrust

* **The stall assertions read the Hub's own account of itself** — status codes and `JobRun` rows —
  because a stall has no filesystem artefact by construction. The mitigation is that every sentence
  is asserted in full, and the "nothing was spawned" claim is anchored on `session_id` being null
  and the agent never leaving `idle`, not on the absence of a row.
* **F128 was found by a harness that was asserting something else.** Its measurements are real, but
  it was never designed to isolate this, and the substitution was observed once. A harness written
  *for* it would be better evidence.
* **The teardown discovery is not a finding.** A loop whose job is merely disabled cannot be
  archived; `PATCH /jobs/{id}` with `stop_reason` is the operator's ending path and it works. Both
  harnesses now use it. Recorded in FINDINGS.md as context, not as a defect.

### One self-inflicted incident, recorded rather than tidied away

Rewriting `STATE.json` through `py -3.11 -c "..."` in the Bash tool, the backticked spans inside the
new `next_action` were **command-substituted by the shell before python ever saw them**. Two effects,
both caught immediately: several phrases were silently deleted from the field (rewritten cleanly
afterwards from a script file), and one of them — <code>agentweave --port</code> — was actually
*executed*. It hit argparse's "expected one argument" and exited; **no Hub was started, nothing was
migrated, no database was touched.** 8010 and 8000 were never contacted. The rule it nearly broke is
one of this session's standing limits, so it is written down here rather than left in a scrollback.

Two shell traps now recorded in `next_action` for the next process: backticks inside a double-quoted
`-c` string are command substitution, and a heredoc whose body contains an odd number of apostrophes
fails to parse in this shell. Prose goes to a file via the Write tool; python reads the file.

---

## Iteration 10 — 2026-08-29 18:58 → 19:06 +01:00

**Position at start.** Branch `autonomous/2026-08-29-decided-fixes-and-drive` at `c61bce2`, clean,
matching STATE.json. `current: E2E-DRIVE`. `next_action` named four thin areas in order; this
iteration did **(a)**, the one that had never been driven at all.

**The Hub on 8011 was re-measured before being trusted**, as instructed: PID 27772, started
2026-08-29 18:06:50, and `GET /api/v1/projects` answers with this branch's project list. Nothing
under `hub/` has changed since it started, so it was not restarted.

### Row 10 — requirement drift, driven end to end for the first time

`scripts/drive/t_row10_drift.py`, **31/31 assertions good**, against a throwaway git repository at
`C:\Users\huida\Documents\drive-drift-0829` (branch `main`) registered on 8011 as
`proj-dec382cf5a97`. No agent turn and no spend — this row is entirely operator-side.

The full chain was exercised: a document with one requirement, one criterion and one task, approved;
operator evidence naming `cart.py`, whose footprint came back `kind=git`, `branch=main` and
`commit_sha` equal to HEAD; a scan on an unchanged tree raising nothing; a commit to the footprinted
file raising exactly one candidate whose `observed` names `cart.py` alone with distinct `was`/`now`
blob ids; coverage moving to `drifting` and back to `verified`; the 422 on an unknown resolution and
the 404 on an unknown id; the resolution holding against a re-scan; and a *further* change raising a
genuinely new row. Every status code is asserted exactly, never `>= 300`.

**Two of the harness's own failures were the harness being wrong, and are recorded as such.**

* A second run rewrote `cart.py` to content an earlier run had already produced. The scan raised
  nothing and the harness called it a defect — but a file byte-identical to its footprint *has not
  drifted*. Every write is now stamped with the repo's commit count, and the revert case is asserted
  deliberately as its own row.
* `raised == []` was the wrong assertion in a project that has been driven before: an earlier run's
  evidence carries an older baseline and legitimately drifts. The harness now filters every `raised`
  list down to the candidates hanging off *this* run's evidence. Asserting the product was wrong
  because the harness could not tell two runs apart is exactly the mistake this file keeps warning
  about.

Two vocabulary facts worth carrying: the requirement's identifier is **minted by the Hub** (`FR-1`),
not the `key` the document used, and the decision route takes `accepted`/`rejected`, not
`accept` — it refuses the wrong word with a 422 that lists the permitted ones, which is the right
behaviour.

### F129 (B) — the feature is correct and the app cannot reach any of it

`POST /spec/drift/detect` is the **only** writer of a `RequirementDrift` row: no scheduler sweep, no
MCP tool, no second route calls `detect_drift`. And `hub/ui/src` never calls it. The string `drift`
survives in the UI in exactly two load-bearing places, both the *word* `drifting` as a coverage
state — `api/spec.ts:98` and `SpecCoverageBar.tsx:10`.

So the coverage bar carries a `drifting` bucket that cannot light up through the app; and if
something outside the app lights it up, `drifting` sits at the **top** of the coverage precedence,
so that requirement reads `drifting` on every screen permanently — with no way to see what moved, no
way to answer the question, and no way to clear it. The backend's own docstring says the outcome is
"a question for a person rather than a state the requirement acquires by itself". There is no person
it can ask. Written up in FINDINGS.md with the fix shape (three controls; keep the scan manual for
now, and why).

### Verification

| | |
|---|---|
| Suites | **not re-run, deliberately** — nothing under `hub/`, `src/` or `tests/` changed. One new `scripts/drive/t_row10_drift.py`, which no test imports, plus FINDINGS.md and the autonomous log. The branch's last full verification stands (iteration 6). |
| The product | driven live: 31/31, twice in a row from a dirty repo, which is what proved the two harness bugs above |
| Jobs / loops left enabled | none created this iteration |
| Drift candidates left open | none for this run's evidence; older candidates from earlier evidence rows are left as they are — they are correct, and resolving them would be inventing an operator judgement |
| Agent spend | **zero** — this row has no agent turn in it |

### What a reviewer should distrust

* **The 8011 project has been driven repeatedly**, so it carries several documents that all mint
  `FR-1` and several evidence rows with different baselines. Every assertion here is scoped by
  `requirement_id` or `evidence_id` rather than by the display identifier; a reader checking by hand
  against `GET /spec/drift` will see rows this harness deliberately ignores.
* **F129 is an absence**, and absences are the easiest thing to be wrong about. It rests on two
  greps — `detect_drift` has one caller in `hub/hub/`, and the UI's only occurrences of `drift` are
  the coverage-state word. Both are cheap to re-run and are quoted in the finding.

### Iteration 10, second unit — F128 isolated (the clock allowed it)

The drift work finished at 19:06, well inside `stop_at`, so `next_action`'s item (b) was done too:
a harness written **for** F128 rather than one that tripped over it.
`scripts/drive/t_f128_substitution.py`, **12/13**.

Confirmed against artefacts, not status codes: three idle agents, a job configured `agent: gamma`,
nobody parked; gamma put mid-turn; Run pressed → **200**; the conversation the firing created is
`origin: job` and ran on **alpha**; the loop's task is `in_progress` with `assignee: alpha`; and
`GET /jobs/{id}` still answers `agent: gamma`. Three firings across three runs, `alpha` every time.
F128's caveat from iteration 9 — "observed once, by a harness asserting something else" — is
discharged.

**The one BAD is F127 reproducing, and it strengthens F127 rather than weakening this harness.**
The second firing — healthy loop, one `pending` task, nothing in flight — answered
**500 "Failed to fire job"**. At that moment gamma was mid-turn, alpha was finishing the turn the
first firing started, and **beta was holding two `in_progress` tasks left over from an earlier
drive**, so the free list was empty and the busy guard refused with nothing recorded.
`t_run_while_busy2.py` had to park a task on every sibling to reach that state; here **ordinary
leftover work on one agent was enough**. Written into FINDINGS.md under both findings.

Two facts about driving loops, learned by being wrong twice and recorded in the harness itself: a
loop delivers one task at a time (a second Run while the first is in flight is correctly refused
409), and a Haiku errand does not close the task it was handed — four minutes of waiting proved it,
so the harness now has the operator complete it.

Spend: four Haiku turns across three runs. Teardown verified after each: no enabled job, no loop
listed, every task this harness created rejected. The two stale `in_progress` tasks on beta are
**older than this iteration** and were left alone — they are somebody else's drive state, and
rejecting them would erase the very condition that reproduced F127.

---

## Iteration 11 — 2026-08-29 19:18–19:25 — E2E-DRIVE: the second link of a checkpoint chain, and F130

`next_action` item (a): the checkpoint shapes row 15 never reached. Two were named — a checkpoint
that fails its probe, and the second link of a chain. **The chain is now driven**
(`scripts/drive/t_row15_chain.py`, **25/25** on the second run, 22/24 on the first with both BADs being harness bugs); the failing probe is **not**, deliberately, and the
reason is in "What was not done" below.

### What the chain leg establishes

The anchor is per **conversation** (`latest_checkpoint`, `hub/hub/checkpoints.py:95`), not per
lineage across a cutover — a cutover creates a new conversation, so its first checkpoint founds a
new lineage and `previous_checkpoint_id` stays NULL. That is why `t_row15_cutover.py` never reached
link two, and why reaching it means checkpointing **the same conversation twice**, not cutting over
twice. Worth writing down: the obvious reading of "chain" (predecessor → successor across a
handover) is the one shape that does **not** set the column.

Driven live, on real Haiku turns, exact status codes, artefacts not codes: three checkpoints on one
conversation come back linked `#1 → #2 → #3`, each naming its predecessor, all three carrying the
founder's `lineage_id`, exactly one with no predecessor, each render printing
`Previous checkpoint: <id>` at the top, and the list route reporting the same links.

### F130 — pressing Checkpoint twice poisons every later checkpoint in that conversation

The empty-span checkpoint answers **201**, `ready`, `probe_status: passed`, and stores
`covers_through_run_id = NULL` because there were no runs to name (`checkpoints.py:367`).
`runs_to_cover` reads NULL as *unknown, so cover everything* (`checkpoints.py:179`) — so the **next**
checkpoint silently re-covers the conversation from turn one. Measured: #3's `files_changed` names
`CHAIN_ONE.txt`, which #1 had already covered, alongside the new `CHAIN_TWO.txt`.

The fallback is defended in its own docstring against a different case — an anchor naming a run the
conversation no longer has. There, NULL means information is missing. Here the anchor is intact and
the emptiness is a **fact**. One NULL is being asked to carry both meanings and only one is handled.

In the first of the two runs the re-covered checkpoint's body opened *"No progress. The file
creation task remains incomplete—the file has not been created"* while its own computed half listed
`CHAIN_ONE.txt`. So the cost is not only wasted worker price on a long conversation: it produced a
checkpoint that contradicts its own file list. The probe passed, correctly — it grades a blind
reader's recovery of files/tasks/questions, not whether the prose is true. Full write-up, three fix
shapes costed, in FINDINGS.md F130.

### The harness bug worth carrying forward

The first run scored 22/24, and **both BADs were mine, not the product's**:
`POST /agent/trigger` without `conversation_id` opens a **new** conversation, so the second turn
landed where the chain could not see it and #3 covered no new work for an innocent reason. The
patched harness passes `conversation_id` explicitly. This is the same class of mistake as iteration
10's global-emptiness assertions: a harness that does not say *which* container it means will be
handed a different one.

### Verification

| | |
|---|---|
| Suites | **not re-run, deliberately** — nothing under `hub/`, `src/` or `tests/` changed this iteration. One new `scripts/drive/t_row15_chain.py`, which no test imports, plus FINDINGS.md and this log. |
| The product | driven live twice against the Hub on 8011 serving this branch: 22/24 then, after the harness bug below was fixed, **25/25** — F130 reproduced in both, on two independent chains (`ckpt-5270b01ef65a…` and `ckpt-0aef4c72ee9c…`) |
| Jobs / loops left enabled | none created this iteration |
| Teardown | `checkpoint_runner_id` reset to NULL in a `finally`, both runs |
| Agent spend | four Haiku turns plus five checkpoint-generation worker turns across the two runs; each generation took 12–20s |

### What a reviewer should distrust

* **The failing-probe shape is still unreached, and that is a choice.** `grade_probe`
  (`checkpoint_generation.py:376`) fails only when a blind reader's recovered files/tasks/questions
  disagree with the Hub's computed record. Nothing on the operator surface makes that happen on
  demand — it needs a worker that writes a body omitting or inventing a path, which is the worker's
  judgement, not an input. Forcing it would have meant reaching past the product surface, which this
  drive does not do. It wants either a fault-injection seam or a unit test, and that is a decision,
  not an oversight.
* **The worktree already held `CHAIN_ONE.txt` from the first run** when the second ran, so "the
  first turn wrote its anchor file" is weak evidence on run two. Every F130 assertion is scoped to
  the checkpoint ids *this run* minted, and the `files_changed` claim comes from run footprints, not
  from the worktree's contents.
* **F130 rests on two code paths and one measurement.** Both lines are quoted with file and line;
  both are cheap to re-read.

### Iteration 11, second unit — the `continue` endpoint's unreached branches, and F131

The clock allowed a second unit (the first finished at 19:25, not the 19:52 I had estimated before
stamping a real time), so `next_action` item (c) was driven too:
`scripts/drive/t_continue_branches.py`, **16/16**, run twice.

**The two waiting branches are fine and are now covered.** Pressing Continue with nothing queued
answers 200 with `started: false, waiting_reason: "queue is empty"`; pressing it while the agent is
mid-turn answers 200 with `waiting_reason: "agent is already running"`. Both name the reason, and
neither starts anything. `t_row15_cutover.py` had only ever seen `started: true`.

**F131 is what the third probe found.** `POST /conversations/{id}/continue` resolves the conversation
only to 404 on it, then calls `schedule_agent(project_id, conversation.agent)` — which takes the
agent's next queued entry, whatever conversation it belongs to — and returns
`{"conversation_id": <the one you pressed>, "started": true}`. Measured twice with different ids: a
cutover left one checkpoint entry queued for a successor, Continue was pressed on a **different**
open conversation of the same agent with nothing queued for it, and the answer was `started: true`
against the pressed conversation while the successor's entry was consumed and the run landed on the
successor (checked by hand against the `runs` table the first time: exactly one new run in the
window, on the successor, none on the pressed conversation).

The scheduling is right — a turn is a per-agent resource and the correct work ran. What is wrong is
that the endpoint is **addressed per conversation and answers as if it were**: an operator watching
the conversation they pressed sees a success and then nothing at all. Same family as F116 (a route
that accepts an input, does something else, and hands the input back as success) and F128 (a loop
that reports the agent it was configured with rather than the one that ran). Three fix shapes costed
in FINDINGS.md F131; the smallest is to return the conversation id of the entry actually picked.

### Verification, second unit

| | |
|---|---|
| Suites | still not re-run — nothing under `hub/`, `src/` or `tests/` changed all iteration |
| The product | driven live twice: 14/15 then, after the two dead assertions below were replaced, **16/16** |
| Jobs / loops left enabled | none |
| Teardown | `checkpoint_runner_id` reset to NULL in a `finally`, both runs |
| Agent spend | two Haiku turns plus two checkpoint generations |

**Two of the first run's assertions were dead, and this is the correction.** `runs_of()` called
`GET /projects/{id}/conversations/{id}/runs`, which does not exist — it answered 404, the helper
returned `[]`, and one check passed vacuously while the F131 check failed for the wrong reason. There
is no per-conversation runs route on the API; the first run's landing evidence therefore came from
reading the `runs` table read-only, and the harness now asserts what the API can actually see (the
queue entry being consumed, and the mismatch between the reported and the queued conversation). A
helper that swallows a 404 into an empty list turns "I could not look" into "there was nothing there"
— the same shape as the global-emptiness trap from iteration 10, one layer down.
