# Decisions waiting for the operator

The backlog of questions the unattended windows could not answer for themselves. Written by the
windows, cleared by the operator, and **durable** — before 2026-09-01 these lived only in
`STATE-night.json`, which each window rewrites, so the list survived by being copied forward by
hand and had drifted into duplicates.

Contract, matching `APPROVALS.md`: **the status token is the authority.** One row per decision.

```
- OPEN      <id>  the question
- DECIDED   <id>  what was decided, and when
- DEFERRED  <id>  why, and what would reopen it
```

A window may **add** rows and may sharpen an OPEN row's evidence. A window may never mark one
DECIDED. Absence is not consent.

---

## Re-triage of 2026-09-01, evening — eight rows to three

The morning triage folded 32 raw entries into 8 rows. An evening pass compared all eight **against
the code** rather than against each other, and six of them turned out not to be decisions.

Two structural faults caused most of it.

**One token cannot answer ten questions.** D-7 absorbed ten entries and D-8 seven. The contract at
the top of this file says one row per decision and the status token is the authority — so there was
no answer the operator could give that made either token true. Answer two of D-7's ten and it stays
`OPEN`, and the answered parts get re-asked. Both were unclosable by construction, which is why
both sat. **D-1 is the only row that ever closed, and it is the only one that was a single
question.** Grouping is good for reading and fatal for tokens: from here, group in prose, tokenise
per question.

**A label can block work it does not describe.** D-7 was named "response-shape and API-surface calls"
and justified as "each changes a contract an existing caller depends on". Measured against the code,
**one of its ten entries** actually does. Three are purely additive — `GET /tasks/{id}/transitions`
is a new route with nothing to break (verified: no route and no MCP tool exists, the thirteen code
references are all writes), and `F212` adds a `document_id` the same response already carries. Those
sat parked behind a rationale that was never true of them.

### Where every earlier row went

| Was | Now | Why |
|---|---|---|
| **D-1** fastmcp ceiling | **stays, DECIDED** | Ratified in session 2026-09-01. Kept below as history. |
| **D-2** pin fastapi | **→ R-1** | The path that actually bit is already closed; what remains is an instance of the unwritten ceiling rule. |
| **D-3** refusals with no surface | **→ R-1** | "One convention or eleven fixes?" is R-1's question, and this is its best-evidenced instance. |
| **D-4** standing rules vs instances | **→ R-1**, three rows dropped | Measured: three of its four sweeps are 2-9 sites. Only the fourth needs deciding. |
| **D-5** sweep vs repair | **→ queue** | Overtaken: two of its three severity-A items now have approved changes. |
| **D-6(a)** archive collision | **→ R-2** | A genuine tooling call, unrelated to (b). |
| **D-6(b)** corpus ahead of code | **→ R-1** | "May a task tick on backend evidence alone?" is a rule question. |
| **D-7** API-surface calls | **→ R-3 + queue + R-1** | Splits three ways; see below. |
| **D-8** stale rows | **→ queue** | A bring-forward list, not a decision — and it rests on a figure this file already disproved. |

Nothing is lost: every original entry number is still named by whichever row now carries it.

---

### R-1 — Does this repo enforce conventions, or repair instances?

**OPEN. The one decision that manufactures the answers to most of the others.** Absorbs D-2, D-3,
D-4, D-6(b), and behind them entries 3, 5, 8, 10, 11, 13, 15, 16, 20, 27, plus F169, F173, F178,
F179, F180, F187, F190, F195, F197, F201.

The question in one line: **when the repo learns a rule, does it write a check that enforces it, or
does it fix the instance and rely on remembering?**

**The repo already answers this two ways at once, which is the tell.** `fastmcp>=2.0,<4` and
`starlette<2.0` are the *same move* — a defensive ceiling so a major needs a conscious bump — taken
twice, months apart, each with the reasoning written into a comment beside it. That is a standing
rule in practice that no file states and no check enforces. Meanwhile the same defect class gets
re-filed: *the Hub computes a sentence for an operator and no file under `hub/ui/src` reads it* has
been filed **six times across two nights**.

**The evidence, verified against the tree 2026-09-01:**

- `ChartersPage.tsx:191` is `createCharter.mutate(values, { onSuccess: … })` — **no `onError`**. The
  refusal is a plain 422 the mutation already holds. Nothing needed computing, wiring or designing,
  which is what makes this a missing convention rather than a refactor.
- `GET /documents/{path}/rigor-history` exists (`hub/hub/api/v1/spec.py:535`) and returns **zero
  hits** across `hub/ui/src`. Ten more operator-only routes are 0-hit in both the source and the
  served bundle. `spec_rigor.py`'s own docstring justifies allowing demotion *on the grounds that
  the audit trail exists* — and no screen shows it.
- The old D-2 is closed at the point it actually bit: `starlette<2.0` is pinned nineteen lines below
  `fastapi>=0.110`, and its comment names the exact incident — *"an unbounded fastapi>=0.110 once
  let pip silently resolve starlette 1.6.0 in CI while dev ran 0.52.1."* Both CI failures were
  Starlette crossings. What is left is FastAPI's own major: real, unrealised, and a *third* instance
  of the same unwritten rule.
- `runner-registry/spec.md:72-73` is a shipped requirement whose UI half was never built — ticked on
  backend evidence alone and archived. The approved `runner-model-is-chosen-from-the-catalog`
  repairs that instance; whether a task may tick on backend evidence alone is the rule question.
  *(Pointer corrected 2026-09-02, night window: that requirement now starts at
  `openspec/specs/runner-registry/spec.md:67`, because the change's delta was synced into it on
  2026-09-02, and it is **no longer unbuilt** — the picker shipped and was driven against the
  served bundle. The instance is closed; the rule question the bullet raises is not, which is why
  the bullet stays.)*

**The "ten more", enumerated — measured 2026-09-02 by the night window.**

The second bullet above has asserted *"ten more operator-only routes are 0-hit in both the source
and the served bundle"* since 2026-08-31 without the list ever being written down. Here it is, and
**the figure is not eleven — it is 35.**

Reproduce with `py -3.11 scripts/drive/n10_route_reachability.py`. Routes are read from
`hub.main:app`'s own route table rather than from decorators, so an include-time prefix cannot be
mis-transcribed; UI call sites are the `/api/v1…` literals `client.ts`'s helpers require, with the
HTTP verb taken from which helper carries each one.

| | |
|---|---|
| declared `/api/v1` route+method pairs | **187** |
| under `/api/v1/agent-actions` (the agent API, operator-invisible by construction) | 32 |
| everything else | **155** |
| reached from `hub/ui/src` with a matching verb | 110 |
| not reached from the UI | **45** |
| — of those, called by the CLI's `HttpTransport` instead | 10 |
| — **of those, called by no client anywhere in this repo** | **35** (33 distinct paths) |

**Verb matters and path-only sweeps get this wrong.** `GET /projects/{id}/charters/{charter_id}`,
`DELETE /projects/{id}/jobs/{job_id}` and `POST /projects/{id}/agents/{name}/output` all sit on
paths the UI *does* call — with a different verb. A sweep that compares paths reports 40 unreached
and calls those three reached; comparing (verb, path) reports 45 and is right.

**The CLI is a second client, and its ten are not operator gaps.** `HttpTransport._request` takes a
path *relative* to one of three prefixes (`transport/http.py:145-149`), so its calls never contain
the string `/api/v1` and any repo-wide grep for the literal misses every one: `POST …/agents/{name}/
heartbeat`, `/output`, `/context-usage`, `POST …/logs`, `POST …/messages`, `POST …/questions`,
`GET …/questions/{id}`, `POST …/session/sync`, `POST …/tasks`, `DELETE …/jobs/{job_id}`.

**The 35 with no client at all**, grouped by the file that declares them:

| Area | Routes |
|---|---|
| `spec.py` — 17 | `GET …/project/documents/{path}/rigor-history` · `PUT …/project/documents/{path}/content` · `POST …/project/documents/{path}/merge` · `POST …/project/documents/adopt` · `POST …/project/spec/adopt` · `POST …/project/spec/documents/arrange` · `POST …/project/spec/reindex` · `GET …/project/spec/requirements` · `GET …/project/spec/requirements/{identifier}` · `GET …/project/spec/drift` · `POST …/project/spec/drift/detect` · `POST …/project/spec/drift/{drift_id}/resolve` · `GET …/project/spec/evidence` · `POST …/project/spec/evidence` · `POST …/project/spec/evidence/{evidence_id}/decision` · `GET …/project/spec/evidence/{evidence_id}/reviews` · `PUT …/project/spec/evidence-retention` |
| `agents.py` — 5 | `GET …/agents/agent-context` · `GET …/agents/configured` · `GET …/agents/context` · `POST …/agents/register` · `POST …/agents/request` |
| `events.py` — 3 | `GET /api/v1/events/ticket` · `GET …/events` · `GET …/events/ticket` |
| `tasks.py` — 2 | `POST …/tasks/{task_id}/dependencies` · `DELETE …/tasks/{task_id}/dependencies/{depends_on}` |
| `inbound_queue.py` — 2 | `GET …/queue/settings` · `PATCH …/queue/settings` |
| `loops.py` — 2 | `POST …/loops/{loop_id}/archive` · `POST …/loops/{loop_id}/control` |
| four singletons | `GET …/projects/{project_id}` · `GET …/charters/{charter_id}` · `GET …/checkpoints/{checkpoint_id}/rendered` · `GET …/worktrees/conflicts` |

Each is 0 in the served bundle too, probed by string literal rather than by symbol name — Vite
renames every local, so an absent hook name proves nothing, while template literals survive intact
(``/api/v1/projects/${n}/loops/${e}`` is in `index-x3nWU-L2.js` verbatim). Five fragments that
*must* be present are probed alongside as controls; all five are.

**The second class the bullet did not separate: a client exists, and nothing renders it.** Six more
routes have a working hook in `hub/ui/src/api/` that no component outside its own file imports —
`requestCompact` (`POST …/agents/{name}/compact`), `requestNewSession` (`…/new-session`), `useJob`
(`GET …/jobs/{job_id}`), `useRunnerLaunchability` (`GET …/runners/launchability`),
`useAgentLaunchability` (`GET …/agents/launchability`) and `useDivergences`
(`GET …/tasks/divergences/recent`). This is F260's shape, and it is worse than it reads: **the
bundler tree-shakes them, so all six paths are 0 in the shipped bundle** — measured with the
terminating backtick, because `runners/launchability` *is* in there as the prefix of
`runners/launchability-by-provider`, which is the variant that ships. The client code exists,
passes its unit tests (`useAgentLaunchability` is named by nine test files) and is not in the
product. `useUpdateJob` is orphaned the same way but its route is not, because `usePauseJob` and
`useResumeJob` `PATCH` the same path.

**What the eleven was probably counting: unknown, and no subset of the measurement lands on it.**
The nearest natural groupings are both 17 — the `spec.py` routes, and the `GET`s among the 35. The
figure looks like an estimate that was never enumerated, which is the whole reason this item
existed.

**110 is an upper bound, not a count of what an operator can reach.** The unrendered-hook pass is
depth-1: it asks whether any *file* outside the hook's own names it, so a hook imported by a
component that is itself imported by nothing reads as consumed. F260 is exactly that — `useMessages`,
`useMessageHistory` and `useMarkRead` are all imported, by `MessagesFeed`, which nothing imports and
which is absent from the bundle. So `GET …/messages` and `PATCH …/messages/{id}/read` are counted
in the 110 here and are unreachable in the shipped app. Sizing that class properly needs a reachability
walk from `App.tsx`, not a symbol grep; this measurement does not attempt one, and the 35 and the 6
are both floors.

**Limits, stated rather than left implied.** A static sweep can show that no caller *in this repo*
names a route; it cannot show the route is dead, and an external client is out of scope. The bundle
probe is path-level, so a bundle hit does not distinguish verbs — it is used here only to confirm
absences. Nine matches were ambiguous because the UI computes a segment (``/projects/${action}``
could be `create`, `open` or `{project_id}`); each was resolved by reading the line and is recorded
with its line number in the script's `HAND_RESOLVED`. Two more are composed by
`agentChat.ts:213`'s `conversationPath()` helper rather than written at the call site, which the
literal scan cannot see; both are in fact called. The unrendered-hook pass names exported symbols,
which would miscount a hook re-exported through a barrel — `hub/ui/src/api/` has no barrel and no
`export *`, checked.

**This block adds evidence only.** R-1's two halves, (a) and (b) below, are untouched and remain
the operator's to answer.

**What the old D-4 got wrong, measured.** It presented four findings as symmetric, each naming "a
grep that would say how big it is". The greps were never run. They are:

| From | Measured sweep |
|---|---|
| **F190** | **2** functions — and both are deleted by the change approved 2026-09-01 |
| **F195** | 21 `subprocess.run`/`Popen` sites, **13 already pass `cwd`** → ~8 |
| **F201** | **9** `model_validator`s under `hub/hub/schemas/` |
| **F197** | **133** `useQuery` declarations; 62 of 97 component files never mention `error` |

At 2, 8 and 9 sites the rule-or-instance question is academic — do both, in an afternoon. Those
three rows are **queue work, not decisions**, and are moved below. Only **F197** is large enough to
need an answer, and its real question is not the one D-4 asked: it is whether an unrendered query
error is a defect *at all* in every case, since a background poll's failure may be correctly
invisible. (133 is an order-of-magnitude grep, not a defect count.)

**F197 sized, 2026-09-02 (night window, N-11).** The row above is now superseded by a count.
Harness: `scripts/drive/n11_query_error_surface.py`, one command, no product code touched. The
write-up with the quotes is in `scripts/drive/FINDINGS.md` under *"F197 sized, 2026-09-02"*.

**133 was the wrong unit and does not reconstruct.** There are **57** `useQuery` declarations in
`hub/ui/src/api/`, in 56 exported hooks. `useQuery` appears on 138 lines and 114 outside imports;
no natural grep of this tree lands on 133. The `62 of 97` half does reconstruct — 97 `.tsx` files
under `components/`, 61 with no `error` in them today — but a file is not a defect count either: a
hook called by three components is three chances to render an error, and a file that never says
`error` is one missing chance, not one per query it runs.

**The unit that is a defect is a call site.** There are **107** outside `api/`, in 48 files. **6**
bind the query's `error`/`isError` and render it. **101** do not — and 3 of those could not have,
because two hooks (`useAgentOutput`, `useLogs`) destructure `useQuery` internally and return a
narrower object with no error field, so no component fix reaches them.

| What the 101 render when the fetch fails | |
|---|---|
| **MISREPORT** — a false statement reaches the screen | **60** |
| — on a surface an operator can reach | **57** (3 sit in `MessagesFeed`, F260's dead component) |
| — of those 57, an empty picker rather than a sentence | 13 |
| — a sentence, a number, or a terminal skeleton | **44** |
| **SUPPRESSED** — an alert or affordance silently does not render | 16 |
| **BLANK** — a decoration or lookup is missing; nothing is claimed | 24 |
| **NAMED** — says the data is unavailable without binding `error` | 1 |

The rule was written before it was applied and is at the top of the script; every one of the 101
is classified individually in `CLASSIFIED`, each naming the line it was read off. The mechanical
part is the 107/6/101 split and the poll flags — which of the four labels a site earns is a
reading, and disputable per row rather than in aggregate.

**The rule gained two labels while it was applied, which the brief asked it not to.** `SUPPRESSED` was split out of `BLANK` (a blocked run's approval card not rendering is not a missing avatar colour) and `NAMED` did not exist at all until `RunnersPage.tsx:198` turned up. Both narrow `MISREPORT` rather than widen it, so neither inflates the headline; both are recorded in the script's docstring.

**The question this row existed to answer — how many are background polls whose errors are
correctly invisible — has a hard answer: at most four, and none of them misreports.** Exactly two
of the 56 hooks poll (`usePendingPermissionRequests` and `useQuestions`, 3s), reaching 4 of the 101
sites; three are `SUPPRESSED` and one `BLANK`. The Hub pushes SSE rather than polling (8 of 22 api
files invalidate on an event), and an SSE-invalidated query that fails its **first** load does not
retry until the next event arrives. Even the four are pardoned only after a first success — a poll
that fails cold renders the same false empty as any other query. So the "much of this is correctly
invisible" reading of the 133 does not survive: on this tree it accounts for 4 sites, not a
fraction of the whole.

**What is on the screen, from the 44.** *"No agents connected. Run `agentweave start` to connect
agents"* (`OverviewPage.tsx:79` — it also instructs the operator to do the wrong thing);
*"Everything here is archived"* (`SpecPage.tsx:35`); *"No quality governance configured"* and
*"All reviewed tasks clear"* (`QualityHealthPanel.tsx:25-26`); *"This agent is no longer in the
roster"* (`AgentSettingsPage.tsx:42`); four `?? 0` counts in the status bar. The sharpest is not a
display defect at all: `InstructionsPage.tsx:9` seeds its editor from `if (data) setContent(...)`,
so a failed load leaves an **empty textarea with Save enabled**, and a save writes `''` over the
stored instructions. Static read, not driven.

**Two facts that bear directly on (b), stated as evidence and not as an answer.** First, the repo
already contains the worked pattern *and* its rationale: `QuestionsPanel.tsx:86` renders its error
only `if (isError && unanswered === undefined)` — *"A failed fetch used to fall through to 'No
pending questions' — an error rendered as reassurance, on the one screen where 'nothing is waiting
on you' is the most expensive thing to say wrongly"* — and deliberately does **not** replace a
screen of real questions when its 3s poll blips. Second, a check phrased as *"the site binds
`error`"* would misfire in both directions: it would call `RunnersPage.tsx:198` a defect, which
renders *"The model catalog is unavailable — this runner will use the provider's default"* from
`!!catalog` and binds nothing, and it would pass any site that binds `error` and drops it.
`JobCard.tsx:146` shows the near-miss the other way: a comment that reasons the claim must not be
made before the answer arrives, guarded on `isLoading`, which is false after an error.

**Falsified rather than asserted: none of the 60 has an error branch elsewhere in its file.** Every
`MISREPORT` site's file was re-read for any `error`/`isError` token outside the call site. 34 of the
60 have one — and all 34 are a *mutation's* error, a local `useState` error, a severity enum, a
`console.error`, or a **different** query's (`TasksBoard.tsx:57` handles `useTasks` and not
`useAllowedTransitions` one line below). Not one is a branch that would cover the query in question.
`ProjectSettingsPanel.tsx:84` is the original F197 sentence restated by the pass: `const error =
update.error ?? relocate.error` — two mutations, never the query.

**Which is the asymmetry worth carrying into (b).** The UI renders mutation failures routinely — 18
`readableApiError(...)` call sites across 13 component files, every one of them fed by a mutation or
a handler's `err` — and query failures 6 times in 107. It is not that this codebase does not handle
errors. It handles the ones it caused and not the ones it merely observed.

**Blind spot, N-10's again.** Sites are found by symbol, one level deep, so a site in a component
nothing imports counts as live; 3 of the 60 are exactly that, and were caught only because F260
had already named `MessagesFeed`. 57 and 101 are therefore upper bounds on what an operator can
reach.

**Blind spot closed, 2026-09-02 (day window, D-5).** Harness:
`scripts/drive/d5_reachability_walk.py`, which imports the two night scripts rather than
reimplementing them, so its numbers differ from theirs by the module filter and by nothing else.
The write-up is in `scripts/drive/FINDINGS.md` under *"What D-5 measured, 2026-09-02"*.

Of 170 source files under `hub/ui/src`, **157 are reachable from `main.tsx` and 13 are not** —
and 12 of the 13 have every literal that occurs nowhere else in `src/` absent from the shipped
bundle, with a dozen reachable files probed as controls and every one of their literals present.
The thirteenth, `badgeVariants.ts`, is reached only by an `import type`, which the compiler erases.
The choice of entry point does not matter: `App.tsx` alone reaches 155, the two extra being
`main.tsx` and `ErrorBoundary.tsx`.

| Figure | Depth-1 | Reachable only | What moved |
|---|---|---|---|
| routes reached from the UI | 110 | **106** | 4 pairs are reached only from dead code |
| operator routes with no live client | 45 | **49** | 35 no client + 10 CLI-only + these 4 |
| query call sites outside `api/` | 107 | **99** | 8 in dead code, of which N-11 knew 3 |
| unhandled sites | 101 | **93** | |
| MISREPORT | 60 | **54** | N-11's "57 an operator can reach" is **54** |
| SUPPRESSED | 16 | **14** | |

**The four routes are a category (a) did not have.** `GET /messages`,
`PATCH /messages/{id}/read`, `POST …/compact` and `POST …/new-session` are not *"no client was ever
written"* — a client exists, in `api/context.ts` and `api/messages.ts`, and its screens were
removed. When (a) asks whether the operator-only routes are en route to a screen, deliberately
API-only, or dead, this is a fourth answer: **the screen was there and went away**, leaving the
route and its client behind. Whatever standing rule (a) settles on has to say what happens to these.

**One line of the evidence above is wrong and is corrected here.** *"What is on the screen, from
the 44"* lists *"four `?? 0` counts in the status bar"* (`StatusBar.tsx:15`). `StatusBar.tsx` is
imported by nothing and is not in the bundle, so those four counts are on no screen —
`Sidebar.tsx:112` says as much in passing. F259, whose headline is built on the same chip, is
amended in `FINDINGS.md` for the same reason; its substance (nothing marks a message read; the
scheduler depends on the flag) is untouched.

**And the count was never the interesting number.** F271 — filed the same day, severity A — is one
of these unhandled sites, and dozens of the others are cosmetic. What separates them is whether a
failed load can be **written back**: does the query's data seed component state, does the file
write, and is there an early return that stops the write rendering while the fetch is failing. Of
the 54 MISREPORT sites, **2** seed state and write it back with no guard (`InstructionsPage.tsx:9`,
which is F271, and `AgentOutputPanel.tsx:207`), 2 do so behind a guard, 23 write without seeding,
and 27 do not write at all. If (b) becomes a repo check, that ordering — not the total — is what it
should be built on: a check that fires on all 54 equally will be turned off.

**Still evidence only.** Nothing here answers (a) or (b), nothing is marked `DECIDED`, and no
recommendation is offered.

**The decision has two halves, unchanged from D-3 and still the right two:**

**(a)** Are the eleven operator-only routes en route to a screen, deliberately API-only, or dead? A
standing answer settles the sweep's remaining rows too.
**(b)** Should a repo check assert that a server-side refusal string is grep-able somewhere in the
UI, and that a mutation whose failure an operator must see carries an `onError`?

**Why this one first.** Answering it settles the old D-2 and D-6(b) for free, empties three of
D-4's rows into the queue, and supplies the missing axis for what an unattended window may take —
see *The axis that actually predicts it* below.

---

### R-2 — Should `openspec archive` refuse a colliding delta?

**OPEN.** Was D-6(a). Absorbs entry 18. A tooling call, unrelated to R-1.

Applying a delta against the current corpus warns about nothing when two changes both carry a
`## MODIFIED` block for the same requirement. Archiving the second **reverted the first**, dropping
a qualification that had just landed. Caught only because the diff was read before committing;
repaired, and the other six were swept — exactly one collision in a batch of seven. **Two changes in
flight against one requirement is not rare here.**

Should archiving be gated on a collision check, and does that belong in a repo script, in the
`openspec-archive-change` skill, or upstream?

---

### R-3 — Four small product calls

**OPEN, but each is one question with two defensible answers and closable in a sentence.** These are
what is left of D-7 once the additive work and the already-answered rows are removed. Absorbs
entries 1, 6, 19, 21.

- **F209** — `accept` declares a 2000-character `reason` and **stores nothing**; `reject`, three
  functions away, keeps it. Thread it through, or delete the field. The current state promises
  something it discards.
- **F196 + F198** — should `PATCH /queue/settings` exist at all? It writes four columns
  `PUT /projects/{id}/settings` already owns, with a weaker contract on both ends, and the UI never
  calls it.
- **Entry 19** — should a bare `uvicorn hub.main:app` from `hub/` **refuse to start** on the
  relative default rather than silently opening a second database beside the one everything else
  uses? This has cost time twice.
- **Entry 21** — `model_catalog.py` names `~/.codex/models_cache.json` as its source of truth and
  nothing re-checks it; it has drifted. Per-machine and absent in CI, so it can only be a
  skip-if-missing check or a `scripts/` tool. *Doing nothing is defensible; doing nothing silently
  is what let a phantom default model sit in the catalog for four weeks.*

---

## The axis that actually predicts what a window may take alone

D-7 asked *which kinds of change need the operator*, and answered "response-shape ones". Measured,
that answer was wrong about nine of its own ten entries. The property that actually separates them
is not the kind of change:

```
        is the right answer already written down?
                    │
        ┌───────────┴────────────┐
       YES                      NO
        │                        │
     REPAIR                  DECISION
   a window takes it        needs the operator
        │
        └── ...but wide or irreversible?
                    │
              REPAIR + GATE
        observe first, verify after
```

The gate arm is not theoretical: `a-turn-says-how-it-ended` was approved 2026-09-01 as a **BREAKING**
response-shape envelope — precisely D-7's blocked class — and what made it safe was not a signature
but a condition. Its phase 0 stops any builder until the defect has been observed live, and its
phase 7 puts verification in a different sitting than implementation. Authorization queues on a
person; evidence queues on a check.

**R-1 is this axis restated.** Deciding whether the repo enforces conventions is deciding whether
answers get written down — which is what moves work from the right branch to the left.

---

## Not decisions — moved to the queue

These were carried as decisions and are not. Each is work with a known answer, or a scheduling call
already made.

**From D-7 — additive, nothing to break, window-takeable:**

- **F203** — `task_transitions` is append-only, carries actor/run/policy, has a reader, and no route
  or MCP tool exposes it; drives have had to open sqlite. Verified 2026-09-01: **no GET route and no
  MCP tool exist** — the thirteen code references are all writes. `GET /tasks/{id}/transitions` is a
  new route with no existing caller to break.
- **F212** — `GET /spec/coverage` projects `unserved` to bare identifiers, which are minted per
  document, so 34 entries all read `FR-1` and feeding one back answers **422**. The same response's
  `requirements` array already carries `document_id`. Additive.
- **F202** — `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next`,
  so at 241 tasks the Overview says "100 tasks". Part two is independently fixable: `list_tasks` in
  `mcp_server.py` has no limit or offset at all. Both additive.

**From D-7 — already answered by something already written down:**

- **F185 + F181** — agent queries with no lifecycle filter. D-7 itself named clearing the bindings
  on archive as "cleanest, closes both at source", and the operator's standing directive is that the
  cleanest solution wins and "more work" is never the objection. Apply it; note that `unarchive`
  must then say the bindings are gone.
- **F193** — what archiving an agent means for its open threads. **The product already made that
  three-way choice explicitly** for archiving a conversation with a live run. Follow the precedent
  unless it is wrong.

**From D-4 — sweeps small enough that the meta-question is moot:** F190 (2 sites, already in an
approved change), F195 (~8), F201 (9). Do the narrow fix and the sweep together.

**From D-5 — overtaken by events.** Its recommendation was to spend a window on F173, F188 and F190
rather than on coverage row 9c. Since it was written, **F173** has an approved change
(`runner-model-is-chosen-from-the-catalog`) and **F190** has one approved conditionally
(`a-turn-says-how-it-ended`). Verified 2026-09-01: **F188 has no change and no design** — nothing
under `openspec/changes/` references it. What is left is not a prioritisation decision but one queue
entry: *F188 is the last unspecced severity-A.* Its cited ledger size of 219 headings is now 289.

**From D-8 — a bring-forward list.** Absorbs entries 22-26, 28, 29. Re-queue or close, per row; none
needs a decision from the operator except by being scheduled. One correction: the row claims the Hub
suite runs "~25 minutes". **This file already disproves that** — `hub/tests/` was measured at
**14:39** on 2026-09-01, recorded under *Closed by measurement* below. `STATE-night.json:101` still
carries the 25-minute figure and should be corrected with it. Also still live there: F47/F120's
categorical third-actor prohibition, F77 (an agent has no way to address the operator), F53/F65
never queued, five findings queued 2026-08-29 and dropped from three runs, and the 8010 trial Hub
serving four-day-old code.

---

## Decided

### D-1 — Ratify or widen the `fastmcp <4` bound

**DECIDED 2026-09-01 — RATIFIED by the operator, in session.** The bound stands as taken. Absorbs entries 17, 31. Severity: low, reversible in one line.

FastMCP 4.0.0 reached PyPI 2026-08-31T18:20:31Z. This repo declared `fastmcp>=2.0` **unbounded** in
three places, and CI resolves fresh with no lockfile — so CI and this machine had already diverged
on the process that starts every agent turn (`pip index versions fastmcp`: LATEST 4.0.0, INSTALLED
3.1.0). The night bounded it to `>=2.0,<4` unattended and added
`hub/tests/test_fastmcp_api_contract.py` (6 tests, verified passing again 2026-09-01 08:09).

**Nothing was measured broken.** The research probed all four FastMCP APIs `mcp_server.py` uses
against 4.0.0 and all four survive. The bound was taken because v4 additionally pulls
`pydantic>=2.12`, `FastAPI>=0.133.0` and `httpx2` — a transitive set this suite has never run
against.

**Recommendation: ratify.** The cost of the bound is a deliberate upgrade later; the cost of no
bound is an unannounced major crossing under the agent runtime. If you widen it instead, run the
contract test first and read what it says.

**Coupling:** fastmcp 4 requires `FastAPI>=0.133.0`. The old D-2 tracked that; it is now part
of **R-1**, since `fastmcp<4` and `starlette<2.0` are the same unwritten rule applied twice.

---

## Closed by measurement, 2026-09-01

- **Entry 32 — "the hub suite has not run on this branch."** Answered by measurement, not decided.
  Run in the 2026-09-01 morning session before merging:

  | Suite | Result |
  |---|---|
  | `hub/tests/` | **3831 passed, 84 skipped, 1 xpassed** in 14:39 |
  | `tests/` | **440 passed, 3 skipped** |
  | `ruff` / `black --target-version py311` / `mypy src/` | clean over CI's own path lists |
  | `hub/ui` | **not run, and not needed** — the branch's product-code diff is three files (`pyproject.toml`, `hub/pyproject.toml`, `hub/tests/test_fastmcp_api_contract.py`); `hub/ui` is untouched. Measured with `git diff --name-only`, not inferred. |

  The baseline at `9fa4c4b` was 3,825 / 84 / 1, so **+6 is exactly the six new contract tests**.
  CI was also confirmed green on `master@ad60b7b`, the merge base.
