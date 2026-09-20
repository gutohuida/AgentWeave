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
`usage_accounting.record_turn_usage`, and archival does not touch it. `Run` itself carries no
runner or model column at all (`models.py:1105-1229`) — R2 checked, because R1's sentence implied
one.

Structurally the two bindings are the *same* kind of thing, not different kinds:

- adjacent, identically-shaped branches in `patch_agent` — each validates that the referenced row
  exists in the project, then assigns (`agents.py:2461-2470` and `:2472-2478`);
- adjacent fields on the same response model (`AgentSummary`, `agents.py:568`, `:569`);
- each walls a `DELETE` with the same sentence, one word apart (`charters.py:95-98`,
  `runners.py:175-183`).

So there is no principle separating them. **What actually separates them is a display dependency,
and it is real and measured:** `list_agents` derives the runner and display model from the live
binding **and from nothing else** — `runners_by_id.get(agent_row.runner_id)` at `agents.py:517-524`
— and never reads `TurnUsage`. Clearing `runner_id` would therefore drop an archived agent's row to
the `"native"` / `"Native"` fall-through that the comment at `:512-515` exists to prevent, on the
one screen that still shows that agent, with no fallback to recover it from.

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
`/agents/launchability` (that is F178's subject). The parameter serves no caller that exists today.

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
