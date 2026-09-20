# Design — an archived agent holds nothing and is offered nowhere

## Round 1, 2026-09-20

Written by the day window's first spec round. The remedy was already decided
(`spec-queue/DECISIONS.md:637`, *"clear an archived agent's bindings at source"*), so this round
explored **where** that lands in the code and **what it costs**, and did not re-open **whether**.
Everything below was read in the working tree at `1fdfc4d`; each claim names the file and line it
came from so R2 and R3 can re-derive it against the code rather than against this file.

## Round 2, 2026-09-20 — independent re-derivation

R2 re-opened `charters.py`, `agent_lifecycle.py`, `agents.py` (`patch_agent`,
`get_agents_launchability`, `list_agents`, the archive/unarchive routes), `runners.py`,
`db/models.py` and `usage_accounting.py` and compared them against this document, **without
re-reading R1's reasoning first**. R1's findings all reproduce and its conclusions mostly survive.
Four things the code contradicted, and two corrections of fact:

- **C1 — D3's justification was false** (the conclusion survives on a different reason).
  "A runner is the record of what this agent ran with" is not true of this code: `TurnUsage`
  (`db/models.py:1235-1248`, written by `usage_accounting.record_turn_usage`) already records
  `runner` and `model` for every Hub-owned run and is untouched by archival. D3 rewritten to the
  reason that *is* measured — a display dependency — and the price of that choice is now stated.
  The same false sentence was in the **normative spec text** (`agent-configuration`), and is fixed
  there too.
- **C2 — D2(c)'s sentence contradicted D8 and under-delivered the decision's rider.** *"bind one
  before this agent's next turn"* reads as though a charter were required; D8 of this same document
  says an agent with no charter is fully usable. It also never said the release is **permanent**,
  which is literally what the operator's rider asked unarchive to say. New sentence in D2 and in
  task 2.2.
- **C3 — group 2 reaches no operator at all** (new **D9**). `useArchiveAgent`'s `onSuccess` takes
  no argument, so the only client of both routes discards the response body. Every sentence group 2
  adds is an API fact nothing renders. Group 2 is kept and its claims are corrected.
- **C4 — D6's second justification was false.** The agent settings page does not probe
  `/agents/launchability`; nothing does. D6 now says what the `lifecycle` parameter is actually for.
- **C5 — the cut line is not free.** Group 5 exists *because* D3 keeps `runner_id` bound. Cutting
  it leaves F390 open as this change's own consequence, not as an unrelated leftover. Said in D4
  and at the cut line in `tasks.md`.
- **C6 — D1's grep count was off by one** (four references, not three). Corrected in place.

R2 changed no task's intent, added one task (2.5) and one design section (D9), and re-ran
`openspec validate --strict`.

## Round 3, 2026-09-20 — second independent re-derivation

R3 opened `agent_lifecycle.py`, `agents.py` (`patch_agent`, `get_agents_launchability`,
`list_agents`, both archive routes, `create_agent`), `charters.py`, `runners.py`,
`usage_accounting.py`, `run_reconciliation.py`, `db/models.py` and the UI's `agents.ts` /
`AgentSettingsPage.tsx` **before reading this document's Round 2 section**, then compared. R2's
corrections were the target: C1-C6 and D9 had had no second reader.

**Every one of R1's and R2's conclusions survives. No task's intent changed.** Three claims were
narrowed or sharpened, and one defect neither round found was filed.

- **R3-C1 — R2's C1 premise holds; two of its sentences are too strong.** R3 enumerated every
  terminal `Run.status` write in `hub/hub/`: `agent_trigger.py:1915`, `:2061`, `:2313`, `:2887`,
  `:2960` and `run_reconciliation.py:66` — six, each with a `record_turn_usage` call beside it
  (`:1925`, `:2067`, `:2334`, `:2892`, `:2981`, `run_reconciliation.py:80`). (`scheduler.py`'s
  status writes and `run_reconciliation.py:252` are `JobRun`, not `Run`.) **A run cannot end
  without a `TurnUsage` row**, so R2's C1 stands. But *"records `runner` and `model` for every
  run"* does not: `model` is read only from `sample.model`, and `sample=None` on all four failure
  paths and on reconciliation, so **every unmeasured outcome carries `model = NULL`**
  (`usage_accounting.py:44`), and `runner` is `Optional` by design (`usage_accounting.py:21-24`).
  Narrowed in D3 and in the `agent-configuration` spec text.
- **R3-C2 — D3's conclusion is confirmed a third time, now demonstrated instead of asserted, and
  its cost is worse than D3 says.** See D3: `create_agent` writes `config={}`, which is the step
  neither earlier round took, and the blanked row is not blank but **false**.
- **R3-C3 — new, and neither round found it: archiving an agent persists no event and broadcasts
  nothing.** New **D10**. It bears directly on group 2 and on the operator's rider, and it is filed
  as **F391 (C)** because it is a standing defect of archival rather than something this change
  introduces.
- **R3-C4 — C3/D9 confirmed by independent measurement, and C4 reaches further than R2 said.**
  `onSuccess` at `hub/ui/src/api/agents.ts:230` takes no argument; the `mutationFn` types the
  response `{ name, lifecycle }`, so `released_charter_id` is not even in the type; and the one
  non-test caller, `ArchiveControl` (`AgentSettingsPage.tsx:224-263`), reads `archive.error` and
  `archive.isPending` and **never `archive.data`**. Nothing else under `hub/ui/src` posts to either
  route. So group 2 is user-invisible, D9 is right, and **the change still acquires no bundle
  refresh.** Extending C4: R2 measured zero call sites for `useAgentLaunchability`; R3 measured that
  **`AgentCard` is rendered nowhere outside its own test** (`grep -rn "<AgentCard" hub/ui/src/`
  returns only `__tests__/agentCardCollaboration.test.tsx`), so the `launchability` prop has no
  production consumer either. D6's "preventive" label is strengthened, not changed.
- **R3-C5 — `patch_agent` can re-bind `runner_id` to an archived agent too, and tasks 1.6-1.8 were
  silent about it.** The adjacent branch in the same unguarded route (`agents.py:2462-2470`) has
  the identical missing lifecycle check. Under D3 the right answer is that it **stays permitted** —
  an archived agent is meant to keep its runner — but left unsaid it reads as an oversight rather
  than a decision. One sentence added to task 1.6, so that whoever later "finishes the job" by
  adding the symmetric guard has to revisit D3 first.
- **R3-C6 — D3's citation `agents.py:2461-2470` is off by one** (the branch opens at `:2462`).

**What R3 re-derived and found unchanged**, listed because a round that confirms is doing its job:
D1's single caller and the four-reference grep; D5's necessity and `0104` still being head
(`hub/hub/migrations/versions/` holds `0103` and `0104`); D7's hole (no lifecycle check anywhere in
`patch_agent`, confirmed by reading the whole route); D8's trigger refusals at `agent_trigger.py:661`
and `:1370`; F181's shape (`get_agents_launchability` seeds `session_agents_meta` from **all**
`Agent` rows with no lifecycle filter, `agents.py:186-191`); the two symmetric `DELETE` walls
(`charters.py:96`, `runners.py:175-183`); C5's point that group 5 exists because of D3.

**One objection R3 raised against D3 and then closed itself, recorded so R4 does not re-raise it.**
On the reconciliation path `TurnUsage.runner` is recovered from the **live** `Agent.runner_id`
binding — `_runner_cli_for_agent` joins `Runner` on `Agent.runner_id` (`run_reconciliation.py:33-48`)
and says so: *"`Run` does not carry the runner, so a crashed run's is recovered from the agent's
binding."* So if `archive()` released `runner_id`, a crashed run of an archived agent would record
`runner = NULL`. That hazard is **unreachable**: `archivable` refuses while a run's status is
`"running"` (`agent_lifecycle.py:34-44`), a crashed run keeps `"running"` until reconciliation, and
`reconcile_interrupted_runs` runs inside `lifespan()` **before the Hub serves a single request**
(`main.py:415`, `run_reconciliation.py:144`). Archive and recovery cannot interleave. This *removes*
an objection to clearing `runner_id` rather than adding one — D3 therefore rests on the display
argument alone, which is exactly where R2 left it.

R3 changed no task's intent, added no task and no group, edited one task (1.6), added one design
section (D10), and re-ran `openspec validate --strict`.

## R1's own measurement — all four claims driven through the API, not read

Both findings were re-reproduced on `1fdfc4d` before a word of this proposal was trusted, in a
throwaway test against the suite's ASGI app (written, run, and deleted — no test file was added by
this round). Verbatim:

```
ARCHIVE RESPONSE:      {'name': 'aq2', 'lifecycle': 'archived'}
DELETE CHARTER:        409 {"detail":"Charter is bound to agent(s): aq2. Unbind before deleting."}
REBIND ARCHIVED:       200  charter-e8a5c807c901
UNARCHIVE RESPONSE:    {'name': 'aq2', 'lifecycle': 'open'}
LAUNCHABILITY KEYS:    ['pmb0233']
ARCHIVED AGENT VERDICT:{'runner': 'claude', 'cli': 'claude', 'present': True, 'authorized': True,
                        'runnable': True, 'reason': None, 'collaboration_ready': True, ...}
TRIGGER:               409 {"detail":"pmb0233 is archived and cannot be triggered. Unarchive it first."}
```

Four things that matter, in order of how much they change the proposal:

1. **F185 reproduces**, unchanged, with `aq2` absent from `GET /agents` at the moment the refusal
   names it.
2. **D7's hole is real and not theoretical:** `PATCH /agents/aq2 {"charter_id": ...}` on an
   *archived* agent returned **200** and re-bound it. Any fix that only clears at archive is
   undoable by one call.
3. **D2's problem is real:** neither the archive nor the unarchive response says anything at all
   about a binding today, so there is nothing to extend — the sentences are new.
4. **F181 reproduces**, and the two answers are one call apart: `runnable: true` and
   `collaboration_ready: true` for an agent the trigger route refuses as archived in the same test.

---

## D1 — the charter binding is released inside `agent_lifecycle.archive`, not at the route

`archive()` is three lines and has exactly **one caller**: `agents.py:2641`, through
`archive_agent_row` (`agents.py:18`). Verified again by R2 — `grep -rn "agent_lifecycle" hub/hub/`
returns four references, all in `agents.py`: three imports (`:17-19`) and one docstring mention
(`:2609`). Nothing else in `hub/hub/` names the module. No MCP tool archives an agent
(`mcp_server.py`'s only archive tool is `archive_job`).

So route-level and module-level are equivalent *today*, and the module is still the right place:
the module's own docstring is where archival's meaning is written down, `archivable`/`archive`/
`unarchive` are the triple that states it, and a second caller added later (an MCP tool, a
project-level cleanup) inherits the release instead of forgetting it. The alternative — clearing at
the route — puts the invariant one layer above the function whose name is the invariant.

**Rejected: filtering the reader instead.** Adding `Agent.lifecycle == "open"` to
`charters.py:95-98` would make the 409 correct without touching archival. It was rejected for two
reasons beyond the operator's decision: it leaves an archived agent pointing at a charter row that
`DELETE` then removes — a dangling `charter_id`, which this app does not catch, because
`PRAGMA foreign_keys` is never turned on for its SQLite connections (`hub/hub/db/models.py:2352`,
`hub/hub/project_lifecycle.py:334`) — and it is the per-call-site pattern `list_agents:262` already
names as the thing that fails: *"one missed site leaves an archived agent selectable."*

## D2 — archiving says what it released; unarchiving says nothing is bound

The decision carried a rider: *"note that `unarchive` must then say the bindings are gone."*
Satisfying it needs care, because **after the release, `unarchive` cannot know whether a charter
was ever bound** — the binding it would report is the one it just destroyed.

Three ways were considered:

- **(a) Remember it** — an `archived_charter_id` column, restored on unarchive. Rejected: it makes
  archival reversible in a way the rest of the product is not, adds a column and a migration to
  carry a fact nothing else reads, and re-creates the very state (an archived agent holding a
  charter) this change exists to remove.
- **(b) Say it at archive time only.** The archive response knows exactly what it released and can
  name it. Necessary, not sufficient — an operator who unarchives weeks later reads a different
  response.
- **(c) Both, with a standing sentence at unarchive.** Chosen. Archive names the released charter;
  unarchive returns `charter_id: null` **explicitly** (not by omission) together with one sentence
  that states the rule and the current state.

**R2 replaced R1's sentence.** R1 proposed: *"No charter is bound. Archiving releases an agent's
charter, so bind one before this agent's next turn."* Two defects, both found by reading it against
this document's own D8:

1. *"bind one before this agent's next turn"* is an instruction that implies a charter is
   **required**. D8 records the opposite, measured: an agent with no charter is fully usable and the
   product says so. The sentence would tell the operator to do something the product does not need.
2. It never says the release is **permanent** — which is the one thing the operator's rider
   (*"note that `unarchive` must then say the bindings are gone"*) actually asked for. "Archiving
   releases an agent's charter" describes archival; it does not say unarchiving will not undo it.

The sentence is therefore:

> *"No charter is bound. Archiving releases an agent's charter and unarchiving does not restore it.
> An agent with no charter still runs — bind one only if this agent should have one."*

It is true, in every clause, of an agent that never had a charter: the first clause is its state,
the second is the rule, the third is the product's actual behaviour, and the fourth is conditional
rather than imperative. The property to attack in R3 is unchanged — a sentence that reads as *"your
charter was removed"* would be false for a never-bound agent, and this one must not drift into
that — with one added: it must not drift back into implying a charter is required.

## D3 — `runner_id` is **not** released, and that asymmetry is deliberate

The decision says "bindings", plural. Applied literally it would clear `runner_id` too. Measured
cost of doing so:

- `list_agents` resolves the bound runner to render an agent's runner and display model
  (`agents.py:518`, `:568-569`); with no runner bound, both fall through to their `"native"` /
  `"Native"` defaults, which is what the same file's comment at `:512-515` exists to prevent.
- An archived agent is resolved through `?lifecycle=archived` / `all` — the roster's own docstring
  says that path exists *"because its own configuration is where unarchiving happens"*
  (`agents.py:264-266`), and the UI reaches it through `useAgents(lifecycle)`
  (`hub/ui/src/api/agents.ts:180-205`).

So clearing `runner_id` would blank what an archived agent ran with, on the single screen that
still shows it, in exchange for closing a 409 that D4 closes with a sentence instead.

**R2 rejected R1's stated reason and kept its conclusion.** R1 justified the asymmetry as a
difference in kind: *"a charter is instruction for turns the agent will take; a runner is the record
of what this agent ran with."* The first half is true. **The second half is not true of this code.**
The record of what an agent ran with already exists, per run, somewhere else:
`TurnUsage` (`hub/hub/db/models.py:1235-1248`, *"The immutable accounting outcome for one Hub-owned
run"*) carries `runner` and `model`, is written for every run by
`usage_accounting.record_turn_usage`, and archival does not touch it. **R3 narrowed the second
half of that sentence.** The *row* is written for every run — R3 enumerated all six terminal
`Run.status` writes in `hub/hub/` and found a `record_turn_usage` call beside each, so a run cannot
end without one. But its *contents* are not uniform: `model` is read only from `sample.model` and
`sample=None` on every failure and reconciliation path, so **an unmeasured outcome carries
`model = NULL`** (`usage_accounting.py:44`), and `runner` is `Optional` by design
(`usage_accounting.py:21-24`). This matters only for the fallback floated at the end of this
section: recovering an archived agent's display from its most recent `TurnUsage` would often
recover a runner and no model. `Run` itself carries no
runner or model column at all (`models.py:1105-1229`) — R2 checked, because R1's sentence implied
one.

Structurally the two bindings are the *same* kind of thing, not different kinds:

- adjacent, identically-shaped branches in `patch_agent` — each validates that the referenced row
  exists in the project, then assigns (`agents.py:2462-2470` and `:2472-2478`, corrected from R2's `:2461` by R3);
- adjacent fields on the same response model (`AgentSummary`, `agents.py:568`, `:569`);
- each walls a `DELETE` with the same sentence, one word apart (`charters.py:95-98`,
  `runners.py:175-183`).

So there is no principle separating them. **What actually separates them is a display dependency,
and it is real and measured:** `list_agents` derives the runner and display model from the live
binding **and from nothing else** — `runners_by_id.get(agent_row.runner_id)` at `agents.py:517-524`
— and never reads `TurnUsage`. Clearing `runner_id` would therefore drop an archived agent's row to
the `"native"` / `"Native"` fall-through that the comment at `:512-515` exists to prevent, on the
one screen that still shows that agent, with no fallback to recover it from.

**R3 took the step neither earlier round took, and the conclusion is demonstrated rather than
asserted.** R1 and R2 both argued the fall-through from `list_agents` and from its comment; neither
checked what an archived agent's `config` actually holds, and the fall-through only fires if
`agent_meta` has no `runner` key of its own. It does not: `create_agent` writes **`config={}`**
(`agents.py:673`) for every Hub-created, runner-bound agent. So `agent_meta.get("runner", "native")`
reaches its default and `_display_model` resolves through its own `.get(_runner, ...)` fall-through.
The blanking is real, and it is now proved from the creation site.

**And R3 found the cost is worse than "blanked".** The row does not go empty — it goes **wrong**.
`runner: "native"` and `display_model: "Native"` are a *positive claim* naming a runner kind this
product supports, so an operator reading an archived agent's configuration would be told it ran
natively when it ran on Claude. D3 has argued this cost twice as lost information; it is stated
falsehood, which is the stronger form of the same argument and the one this repository's own idiom
already reaches for (`run_reconciliation.py:77-79`, on why an absent accounting row was worse than
an inaccurate one: *"Absence was worse than a wrong number"* — here it is the inverse). **The
conclusion is unchanged for the third time; only its price is stated correctly.**

**The price of that choice, which R1 did not state.** Keeping `runner_id` bound is precisely what
leaves `runners.py`'s refusal able to name an agent the default roster does not show. **F390 and
tasks group 5 exist because of this decision** — see D4. They are not an unrelated third site.

**And reversing it is not "one line", as R1 claimed.** It would take: the line in `archive()`, a
second `UPDATE` in migration `0105` for already-archived rows, the deletion of group 5 (F390 would
close by construction), and acceptance of the blanked display — or, instead of accepting it,
teaching `list_agents` to fall back to the agent's most recent `TurnUsage`, which is a larger change
than this whole proposal. R3 should weigh that trade on those terms, not on R1's.

## D4 — the third site: `runners.py`, closed by naming rather than by releasing

`runners.py:175-183` is the same query and the same sentence as `charters.py:95-98`:

```python
select(Agent.name).where(Agent.project_id == project_id, Agent.runner_id == runner_id)
```

Since D3 keeps `runner_id` bound, this refusal **can** still name an agent the default roster does
not show — F185's exact wall, one route over, filed by this round as **F390 (C)**. It is answered the other way:
the refusal states that the holder is archived and where to reach it, so the operator can act on
the name instead of hunting for it.

**R2: this site is a consequence of D3, not an independent discovery.** If `archive()` released
`runner_id` the way it releases `charter_id`, no archived agent could hold a runner and this refusal
could not name one — group 5 would be unnecessary rather than cuttable. D3 chose the display over
the wall; group 5 is what pays for that choice. Cutting it is therefore not "narrowing the blast
radius" but shipping a change that knowingly leaves its own consequence open, and the cut must be
recorded that way, not as deferring an unrelated finding.

This is the one part of the change outside `DIRECTION.md`'s stated blast radius
(`charters.py`, `agent_lifecycle.py`, `agents.py`). It shares no file with today's item 2
(`hub/hub/config.py`) or with either approved-and-unbuilt change. **If it has to be cut, cut it
here** — tasks group 5 is self-contained, and nothing in groups 1-4 depends on it.

## D5 — the migration is not optional

`archive()` runs at archive time. Every agent archived before this change keeps `charter_id` and
keeps walling its charter — including on the operator's live database, which is where the finding
was met. Migration `0105` clears `charter_id` for every row with `lifecycle = 'archived'`.

Its downgrade cannot restore what it cleared and SHALL NOT pretend to: the downgrade is a
documented no-op, which is the honest shape for a migration whose forward direction destroys the
value it rewrote. `hub/hub/migrations/versions/0104_question_subject_key.py` is the current head.

## D6 — launchability filters where the roster filters, and for the same stated reason

`list_agents` applies its filter **after every source has contributed a name**, with a comment
saying exactly why (`agents.py:359-369`): a name reaches that dict from session config, from 24h of
activity and from being a task's assignee, so *"filtering only the `Agent` query would let an
archived agent back in through any of those."*

`get_agents_launchability` has **two** sources — `_get_session_data`'s `agents` map and the `Agent`
rows (`agents.py:186-191`) — not the roster's four. R2 checked whether that makes it a smaller
hazard or no hazard: it is a smaller hazard **of the same shape**. `ProjectSession` is still
written (`hub/hub/api/v1/session_sync.py:70`, from the CLI's `push_session`,
`src/agentweave/session.py:153`), so the session-config source is live rather than vestigial, and a
name can reach this dict from it while the agent's row is archived. A filter on the `Agent` query
alone would let exactly that agent back in. So the filter goes in the same place, with the same
*"an agent with no row cannot have been archived, so it counts as open"* rule, and **before** the
per-name loop, which does a `get_agent_config` and a `Runner` lookup per agent.

**Signature:** the same `lifecycle: Literal["open", "archived", "all"] = Query("open")` the roster
takes, rather than an unconditional exclusion.

**R2 struck one of R1's two reasons as false.** R1 wrote that *"the agent's own settings page is
entitled to probe an agent it can display."* The settings page does not probe this route, and
nothing else does either: `useAgentLaunchability` (`hub/ui/src/api/agents.ts:376-385`) has zero call
sites, the only caller anywhere in the tree is `hub/tests/test_launchability.py`, and a drive
recorded on 2026-09-01 measured 41 requests with the agent rail open, **none** of them to
`/agents/launchability` (that is F178's subject). The parameter serves no caller that exists today. **R3 measured one step further:** the component
that would consume a per-agent verdict, `AgentCard` (whose `launchability` prop exists and is typed,
`AgentCard.tsx:12-20`), **is itself rendered nowhere outside its own test** —
`grep -rn "<AgentCard" hub/ui/src/` returns only `__tests__/agentCardCollaboration.test.tsx`. So the
renderer F178 refers to does not exist even in skeleton form, and neither the hook nor its consumer
is wired to a screen.

What it is actually for, stated honestly: **F181's fix here is preventive.** The default is what
closes the defect, and it closes it *before* whoever wires the indicator up (F178) inherits an
archived agent in a selector. The parameter exists so that renderer copies the roster's call shape
instead of inventing a second one — which is worth three lines, and is not the same claim as saying
a screen needs it now.

**What this does not change:** `probe_agent`'s verdict for an agent that *is* returned. An archived
agent asked for explicitly still reports whatever it would have reported; the change is which
agents are in the response at all. Stating a *lifecycle* reason inside the probe verdict was
considered and rejected as a second vocabulary for a fact the roster already carries.

## D7 — the hole that would reopen it: `PATCH /agents/{name}` binds a charter with no lifecycle guard

Found by reading, this round, and it is the difference between a fix and a fix that stays fixed.
`patch_agent` (`hub/hub/api/v1/agents.py:2472-2478`) accepts `charter_id`, validates only that the
charter exists and belongs to the project, and assigns it. **There is no lifecycle check anywhere in
that route.** So the moment D1 ships, one ordinary API call — the same one the settings page's
`CharterPicker` makes (`hub/ui/src/components/agents/AgentSettingsControls.tsx:257-292`) — puts an
archived agent back in the state F185 reproduces.

So the route SHALL refuse binding a charter to an archived agent, naming unarchiving as the repair.
Clearing the binding (`charter_id: null`) stays permitted: it is not a re-binding, and refusing it
would make an existing repair fail.

**The part this change deliberately does not do, and why the operator should look at it.** The
picker stays enabled on an archived agent's Charter section (`AgentSettingsPage.tsx:124-135`
renders it for any agent the page resolves, and it resolves archived agents by design), and on
failure it shows a generic *"Could not update charter binding."* — it does not render the server's
sentence. So the refusal is correct and the operator is told **something**, but not the reason.
Fixing that properly means disabling the control for an archived agent and surfacing the server
detail — a `hub/ui/src` change, which means a bundle refresh, which means it reaches the operator's
`:8000` app. That is a bigger blast radius than this change otherwise has, and it is the F187 shape
(a refusal the client drops) rather than this change's shape.

It is recorded as an operator decision rather than taken silently either way: **fold the UI half in
and accept the bundle, or ship the backend refusal alone and file the picker as its own finding.**
The change is complete and shippable without it.

## D9 — R2: nothing renders these responses, so group 2 reaches no operator today

`useArchiveAgent` (`hub/ui/src/api/agents.ts:214-241`) is the only client of **both** routes, and
its one non-test caller is `AgentSettingsPage.tsx:224`. Its `mutationFn` types the response
`{ name: string; lifecycle: string }` and its `onSuccess` **takes no argument at all** — it
invalidates the roster queries and returns. The body is *discarded*, not merely under-typed.

So `released_charter_id`, the archive sentence and the unarchive standing sentence are correct API
facts that **no operator can read**. Group 2's tests (2.3) assert the response body and will pass.
That is this repository's named dominant failure mode — a fix that passes its tests and cannot fire
where the operator is — so it is written down here rather than found later.

**R3: it is worse than unrendered — it is unrecorded.** See D10. Archival persists no event, so the
HTTP response is the *only* place `released_charter_id` ever exists, and `useArchiveAgent` discards
it. The identity of the released charter is irrecoverable from the Hub the moment the request
returns. That does not change group 2's shape, but it makes the case for keeping it stronger than
the two reasons R2 gave: deleting the field would not defer a display, it would destroy the fact.

**Group 2 is kept**, for two reasons that do not depend on today's client: an API that states the
fate of a binding it silently changed is right whether or not anything reads it yet, and the
sentence is the thing a future renderer renders. But three claims had to be corrected:

- the proposal said *"the product says so rather than letting the operator find out at the next
  turn."* It does not. R2 rewrote that sentence.
- group 2's title was *"The operator is told what archival released."* It is not. Retitled to what
  the group actually does.
- the operator's rider — *"note that `unarchive` must then say the bindings are gone"* — is **half
  discharged** by this change: the API says it, the app does not show it. Task 2.5 records the
  measurement so the next round cannot mistake silence for coverage.

**This does not raise a second operator decision.** Rendering these sentences is a `hub/ui/src`
change, therefore a bundle refresh, therefore it reaches the `:8000` app — the *same* wall as D7's
`CharterPicker`. R2 folds it into that one decision, which is now correctly framed as *"does this
change accept a bundle refresh at all?"* and covers two UI halves: disabling the picker on an
archived agent, and rendering what archive/unarchive now say.

## D10 — R3: archiving an agent persists no event and broadcasts nothing

Found by R3 by reading, after asking where `released_charter_id` goes once the response is
discarded, and then **driven through the API** rather than left as a read: an archive and an
unarchive leave `GET /events/history` unchanged, while a heartbeat on the same agent lands in it as
a control (F391 carries the verbatim output). The answer is nowhere. `grep -rn "agent_archived\|agent_unarchived" hub/ src/` returns
**no match anywhere in the tree**, and both routes (`agents.py:2602-2644`, `:2648-2660`) end the
same way — mutate the row, `commit`, `refresh`, `return` — with no `persist_event` and no
`sse_manager.broadcast`. Every neighbouring agent route has one: `agent_created` (`:689`),
`agent_requested` (`:2133`), `agent_heartbeat` (`:2682`). Archival is the lifecycle transition that
leaves no trace.

Three consequences, in the order they matter to this change:

1. **It is why D9's problem is unrecoverable rather than merely invisible.** The released charter's
   identity exists only in a response body nothing reads.
2. **It is the cheapest route past the rider's half-discharge, and it is server-side.**
   `persist_event` needs no bundle refresh, so an `agent_archived` event carrying
   `released_charter_id` would make the fact durable and queryable without touching `hub/ui/src`.
   D2 rejected option (a), *remembering* the binding, because an `archived_charter_id` column
   re-creates the live state this change removes — that objection is right about a column and does
   **not** apply to an event, which records that something happened rather than that something is
   bound. Neither R1 nor R2 considered the distinction.
3. **Durable is still not displayed.** `useSSE.ts` allow-lists event kinds at `:31` and switches per
   kind at `:460`, so *rendering* a new event in the activity feed remains a `hub/ui/src` change.
   An event closes the recording gap, not the display gap.

Separately, and independently of charters: with no broadcast, a second open client's roster is not
told an agent was archived. The acting client self-invalidates in `useArchiveAgent`'s `onSuccess`;
nothing informs the others.

**R3 adds no task for this.** It is true today with no charter release at all, so it is a standing
defect of archival rather than something this change introduces or worsens — filed as **F391 (C)**.
Whether to fold it in is the operator's call, and it belongs beside the one decision this change
already carries, since it is the option that makes the rider's second half reachable *without* the
bundle refresh that decision is about.

### Decided by the operator, 2026-09-20, in session

**Folded in — the API line holds and the event is added.** Of the three shapes put to them (API
only as R3 left it; API plus this event; API plus a `hub/ui/src` bundle refresh), they chose the
middle one. The reasoning they were given and accepted: `persist_event` and `sse_manager.broadcast`
are both server-side, so the rider's *recording* half is discharged with nothing committed under
`hub/ui/src` and nothing reaching the live `:8000` app on its next reload — which is the constraint
that made the bundle-refresh option expensive in the first place. **Group 2b** carries it; the
`agent-configuration` delta gains one normative paragraph and three scenarios.

**What this decision does not do, stated so a later round does not over-read it:**

- **It does not close the display gap.** `useSSE.ts:31`/`:460` still do not know these kinds, so the
  operator sees nothing new. Group 2b says so in its own header and task 2b.6 forbids claiming
  otherwise when setting F391's status.
- **It does not reverse D2.** Remembering the binding in a column is still rejected; an event
  records that something happened, which is a different claim from something being bound.
- **It does not widen the change's blast radius beyond the API.** Task 2b.7 is the check.

**Group 5 (F390, `runners.py`) was not cut** — the operator was offered that trim and did not take
it, so `DIRECTION.md`'s three-file framing is knowingly exceeded by one file.

**The standing adversarial-Opus pass before approval was deliberately skipped**, at the operator's
explicit instruction on 2026-09-20, on the grounds that R1, R2 and R3 ran as three independent
processes and each corrected the last — unlike `a-loop-staffs-the-agent-it-names`, where two of
three rounds shared a session and a second adversarial pass then returned eight blocking findings.
Recorded here because the absence of that pass is otherwise indistinguishable from an oversight,
and because **this change's D10 itself is R3 work that nothing has re-derived.**

## D8 — what holds, and must keep holding

Named because a change that lists only defects describes a product that does not exist. Each was
read in the code this round:

- **The roster's filter is correct and is not touched.** `agents.py:359-369`, applied after every
  source, with the no-row-means-open rule.
- **Trigger already refuses an archived agent**, in both paths (`agent_trigger.py:661`, `:1370`).
  F181 is the probe disagreeing with that refusal, not the refusal being absent.
- **The bound-charter refusal is right for an open holder**, and its named repair works: `PATCH`
  `charter_id: null`, then `DELETE` returns `204`. Driven 2026-09-15, recorded in `FINDINGS.md`'s
  row-4 *what held* list. This change must not weaken it.
- **An agent with no charter is fully usable** and says so — *"No charter is assigned to this
  agent."* (`agent-charter`'s requirement *An agent is bound to at most one charter*). This is what
  makes releasing the binding safe: it lands the agent in a state the product already supports.
- **A dangling `charter_id` is survivable but not benign**: `agents.py:1572-1573` resolves it with
  `db.get(Charter, ...)` and tolerates `None`. That tolerance is why D1's rejected alternative
  would have failed quietly rather than loudly.
