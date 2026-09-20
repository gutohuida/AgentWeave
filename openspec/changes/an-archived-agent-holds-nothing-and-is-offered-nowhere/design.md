# Design — an archived agent holds nothing and is offered nowhere

## Round 1, 2026-09-20

Written by the day window's first spec round. The remedy was already decided
(`spec-queue/DECISIONS.md:637`, *"clear an archived agent's bindings at source"*), so this round
explored **where** that lands in the code and **what it costs**, and did not re-open **whether**.
Everything below was read in the working tree at `1fdfc4d`; each claim names the file and line it
came from so R2 and R3 can re-derive it against the code rather than against this file.

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
`archive_agent_row` (`agents.py:18`). Verified 2026-09-20 — `grep -rn "agent_lifecycle" hub/hub/`
returns three import lines in `agents.py` and nothing else. No MCP tool archives an agent
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
  that states the rule and the current state: *"No charter is bound. Archiving releases an agent's
  charter, so bind one before this agent's next turn."*

(c)'s sentence is true for an agent that never had a charter, which is why it is worded as the rule
plus the state rather than as a claim about this agent's history. That is the property to attack in
R2: a sentence that reads as *"your charter was removed"* would be false for a never-bound agent,
and this one must not drift into that.

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

**The distinction this rests on, stated so R2 can reject it:** a charter is *instruction for turns
the agent will take* — and nothing runs an archived agent, so it governs nothing and keeping it
bound only walls off the charter's deletion. A runner is *the record of what this agent ran with* —
still true of an archived agent, and still displayed. If R2 finds that reasoning wrong, the change
that follows is small and local: add one line to `archive()` and extend D4's refusal test.

## D4 — the third site: `runners.py`, closed by naming rather than by releasing

`runners.py:175-183` is the same query and the same sentence as `charters.py:95-98`:

```python
select(Agent.name).where(Agent.project_id == project_id, Agent.runner_id == runner_id)
```

Since D3 keeps `runner_id` bound, this refusal **can** still name an agent the default roster does
not show — F185's exact wall, one route over, filed by this round as **F390 (C)**. It is answered the other way:
the refusal states that the holder is archived and where to reach it, so the operator can act on
the name instead of hunting for it.

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

`get_agents_launchability` has two sources — `_get_session_data`'s `agents` map and the `Agent`
rows (`agents.py:186-191`) — and the same hazard. So the filter goes in the same place, with the
same *"an agent with no row cannot have been archived, so it counts as open"* rule, and **before**
the per-name loop, which does a `get_agent_config` and a `Runner` lookup per agent.

**Signature:** the same `lifecycle: Literal["open", "archived", "all"] = Query("open")` the roster
takes, rather than an unconditional exclusion. Two reasons: the agent's own settings page is
entitled to probe an agent it can display, and a caller that copies the roster's call shape gets
the roster's behaviour. The default is what closes F181 — every existing caller passes nothing.

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
