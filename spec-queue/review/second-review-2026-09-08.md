# Second review — the four unapproved changes, 2026-09-08

**Written by an interactive session at the operator's instruction:** *"Before approving review the
work against the code."* The first verification round's record is `handoff-0114`'s
`## The verification round`; this round did **not** read it before starting, which was the point.
Every statement below was run against the tree at `5cdca4b`, not reasoned from a document.

**Verdict: none of the four needs another round.** Three need one-line editorial repairs before an
implementer picks them up. None of the repairs touches a requirement, a scenario, or a design
decision.

---

## Findings

### S-1 — F295 cites thirteen deleted probes, and two of them as *instructions*, not evidence

`V-1` reported one dead citation (`testbed/scratch/f295/probe_pool.py` at `tasks.md:16`). It is
**thirteen distinct scripts** across `proposal.md`, `design.md` and `tasks.md`; the 2026-09-07 clean
slate emptied `testbed/` to its two tracked files, and every one of them is gone.

For eleven of the thirteen this is bounded, and the change said so in advance: `tasks.md` 4.3 —
*"delete `testbed/scratch/f295/` or leave it, but do not commit it… the measurements it produced are
quoted in `proposal.md` and `design.md`, which are what the record needs."* A quoted result whose
script is gone is a weaker record, not a broken one.

**Two are different, because they are forward instructions rather than evidence.** `tasks.md` 3.1
tells the implementer to kill a worker thread *"by the real mechanism… which is what
`testbed/scratch/f295/probe_guard_lib.py:kill_worker` does"*, and 3.10 tells them to reuse 3.1's
mechanism. That instruction cannot be followed: the file does not exist. The mechanism itself is
still fully described in `design.md:5-12` (queue a `(future, function)` pair whose future belongs to
a closed loop, then join the thread), so the repair is to state it inline in 3.1 and stop pointing
at a deleted file.

`DEAD-ENDS.md` already carries the general lesson (*grep `openspec/changes/` for `testbed/` before
clearing it*). This finding is that the specific cost was under-counted by twelve.

### S-2 — the two aiosqlite line numbers drift, and each is cited twice

Confirmed against the installed **aiosqlite 0.22.1** (`~/AppData/Roaming/Python/Python311/site-packages/aiosqlite/core.py`):

| Cited | Actual | What is there |
|---|---|---|
| `core.py:199-201` | **`:202-203`** | `close()`'s `if self._connection is None: return` (`:199` is the `def`, `:200` the docstring) |
| `core.py:151-152` | **`:152-153`** | `_execute`'s `if not self._running or not self._connection: raise ValueError("Connection closed")` |

`V-2` reported this. What it did not say is that each appears in **two** places — `design.md:66` and
`:69`, and again in `tasks.md` 1.3, which is the task that tells the implementer to write these
exact line numbers into a source comment. Left alone, the drift is copied into `engine.py` and
outlives the change.

The mechanism is right in both cases. This is a citation repair, not a design one.

### S-3 — `ROADMAP.md` is wrong about which changes touch the bundle, and it bears on `ORDER:`

Stage 0.3 says *"Three of the four touch `hub/ui` and the committed bundle, so they cannot run
beside each other. Only one is bundle-free."* The Stage 0 table repeats it, marking
`an-agent-without-mcp-is-not-told-it-has-nothing` as touching UI/bundle.

**It does not.** That change names no `hub/ui` file anywhere in its four documents, and declares its
own exemption in its second paragraph: `tasks.md:7` — *"`hub/hub/static/ui` is not rebuilt and the
TypeScript lint set is not required."* Its file list is nine `hub/hub/*.py` modules plus
`docs/architecture/overview.md`.

So **two of the four are bundle-free**, not one. And the two that do touch the bundle share no
source file:

| Change | Source files | Bundle |
|---|---|---|
| `a-dead-connection` | `hub/hub/db/engine.py`, `hub/hub/main.py`, `hub/tests/conftest.py` | no |
| `an-agent-without-mcp` | 9 × `hub/hub/*.py`, `docs/` | no |
| `the-conversation-carries-its-own-run-facts` | `agent_chat.py`, `agentChat.ts`, `AgentOutputPanel.tsx`, `AgentTimeline.tsx` | **yes** |
| `clearing-instructions-asks-first` | `InstructionsPage.tsx`, new `ClearInstructionsDialog.tsx` | **yes** |

The only collision between the last two is the generated `hub/hub/static/ui`. The ordering
constraint is therefore narrower than the roadmap states, and this is written into `APPROVALS.md`'s
`## 2026-09-08` section where the `ORDER:` line will be composed.

### S-4 — the run-facts change opens on a stale environment instruction, and it is the gate

`tasks.md` phase 0 is a hard gate: *"If phase 0 has not been recorded, do phase 0 and stop."* Its
first item, 0.1, reads: *"Trial Hub on **8011** — never `proj-5e960453` or `proj-18e5d4e0`, never
port 8000."*

Written 2026-09-05, and overtaken by the 2026-09-07 clean slate. `proj-5e960453` was deleted with
the `beta`/`trial`/`dev`/`drive8011` profiles; the trial Hub is now `:8010` serving
`~/.agentweave/hub/profiles/trial/agentweave.db`, and this repo is registered as
`proj-d85a82bf4216`. So the first instruction in the change's gating phase forbids two project IDs
that no longer exist and mandates a port whose profile was deleted.

Nothing here is dangerous — the `never :8000` half is the one that matters and is still right — but
an implementer reading 0.1 literally will look for a profile that is gone. The sibling change has
the durable form and should be copied: `clearing-instructions` 5.3 says *"a spare port… leave
`:8010` alone"*, which stays true across profile churn.

### S-5 — two cosmetic count discrepancies

- `F295`'s `tasks.md` numbering **skips 3.9**. The header explains it (R2's mutation-check was 3.9;
  R3 renumbered it to 3.12) and no task was lost — the file holds 24, which is what `ROADMAP.md`
  says. A reader counting task numbers rather than checkboxes will still stop on it.
- `APPROVALS.md`'s `## 2026-09-07` row calls that change **"23 tasks in 4 phases"**. It is 24, in 4
  phases — R3 added 1.5, 3.10 and 3.11 after the row was written. The row is otherwise accurate.

### S-6 — one truncated quotation

`an-agent-without-mcp`'s `proposal.md` introduces its blockquote as *"`launchability.py:325-330` is
the whole non-MCP branch"* and then drops the branch's final sentence — *"Inbound content is already
included in this turn; no retrieval is needed."* — with no ellipsis. The sentence is irrelevant to
the argument, which is why nobody noticed; the claim "the whole branch" is what makes it worth a
line.

---

## What was checked and found sound

Recorded because a review that reports only its findings hides how much of the work was confirmed.

**Versions match the documents exactly.** `aiosqlite 0.22.1`, `SQLAlchemy 2.0.50` — both cited, both
installed.

**F295 — the `close`-event siting is complete and consistent.** This was the first review's
highest-value target. `design.md` carries the supersession where the old arrangement is described
(`:95-101`, *"The neutralisation is right; where it is performed was wrong"*) and again in full in
`### What R3 established`. `tasks.md` carries it in five places that all agree: 1.2 replaced with
detect-only, 1.5 added as the `close` listener, 1.3 requiring the comment to say *why it is on
`close` and not inline*, 2.3 declaring *"Do not ship 2.3 without 1.5"*, and 3.3/3.10 pinning it with
mutation checks. **No residue of the inline arrangement survives anywhere in the change.**

**F295's private-attribute dependencies are real, read directly from the installed library.**
`_thread` is created at `core.py:90` (`Thread(target=_connection_worker_thread, …)`); `_running` at
`:85`; `_execute`'s guard tests **both** `_running` and `_connection`, which is what makes setting
both necessary; `close()` returns early on `_connection is None`. One thing no round stated and this
one checked: `_conn` is a property returning `self._connection` (`:133-137`), so clearing
`_connection` drops the last reference to the underlying `sqlite3.Connection` and refcounting closes
it. The neutralisation leaks no file handle — worth knowing precisely because `F292` is a locking
finding.

**F295's product citations resolve verbatim.** `main.py`'s lifespan is `yield` at `:356`,
`terminate_all_active_runs()` `:357`, `shutdown_scheduler()` `:358`, **no `engine.dispose()`** — the
gap the first requirement fills. `engine.py`'s `create_async_engine` is at `:34` with **no event
listeners of any kind**, so both listeners are new code. `_background_runs` is at
`agent_trigger.py:144`, the `create_task` at `:1190`, the registration at `:1230`. `conftest.py`'s
`:84` pragma listener, `:293` docstring, `:317-330` ordering comment, the settle loop, and the
`else: raise AssertionError` sitting **before** `await _REAL_ENGINE.dispose()` are all exactly as
task 3.8 describes.

**Run-facts copies a convention that genuinely ships.** `agents.py:830-841` builds `RunFacts` with
the `running`→`started` rename and `outside_workspace_writes` passed through undefaulted, with
comments explaining both — task 1.5 asks for that construction and nothing else.
`ChatHistoryResponse` at `agent_chat.py:173` has no such field. The ordering task 1.4 depends on is
real: `get_recent_chat` sorts, truncates at `:697`, **then** extends with queued entries — so
"after, not before" is a meaningful distinction and test 4.4 pins the right thing. `useAgentTimeline`
is called at `AgentOutputPanel.tsx:332` and **nowhere else** in the file, so task 2.2's claim that
the hook becomes dead holds. `eventTargetsAgent` (`agentChat.ts:284`) today matches only
`message_created`, `agent_output` and the queue events, so task 3.1 is an extension rather than a
rewrite. `useSSE.ts:404-412` really is an unfiltered `queryClient.invalidateQueries()` on reconnect,
from `useSSE()` mounted at `App.tsx:216` — so task 3.4's *"write nothing"* is correct and 4.9 is
guarding the only thing that makes it correct.

**Clearing-instructions' dependencies all exist and its one ticked task is real evidence.**
`ArchiveConfirmDialog.tsx` and `useDialogFocus.ts` both present. `handleSave` at
`InstructionsPage.tsx:54-56`, the `actions={data ? … : undefined}` structural gate at `:62`, and the
2000 ms success flash at `:46-52` — the three the tasks turn on. The pre-change drive harness
`scripts/drive/t_d8_clearing_instructions_prechange.py` **exists and is committed** (`3078843`),
which is what makes task 5.2's `[x]` legitimate rather than a plan marking itself done.
`t_d4_instructions_failed_load.py:316` really does query role `button` where the control is a
combobox, so 5.5's scope refusal names a real thing.

**Agent-without-mcp's decisive asymmetry is exactly as claimed.** `mcp_server.py:815` calls
`_ask_operator` before archiving, unconditionally. `agent_actions.py:764-777` — the route that tool
then calls — resolves the actor and delegates straight to `archive_job` with no confirmation of any
kind. The non-MCP notice at `launchability.py:325-330` and its prepending at
`agent_trigger.py:1006-1007` are verbatim. And its scoped-out finding is confirmed: the shipped
`agent-capability-plane` spec still carries *"A turn that ends on an unasked question is surfaced to
the operator"* (`:140`) and *"The operator can convert an unasked question into a real one"*
(`:178`) — requirements for a feature `CLAUDE.md` forbids reintroducing.

**Spec deltas are structurally sound.** All four pass `openspec validate --strict`. Every `MODIFIED`
requirement name matches a requirement that exists in the shipped spec by exactly that name:
*A run's terminal outcome is visible* (`agent-stream-events:299`), *Hub UI provides instructions
editor* (`project-instructions:34`), *Save cannot write instructions that were never read*
(`:118`), *HTTP and MCP access have equal capability* (`agent-capability-plane:107`).

---

## What this review did not do

- **Built nothing.** No change was implemented, no test was written, no suite was run — not
  `pytest`, not `ruff`, `black` or `mypy`. Nothing here says any of the four *works*.
- **Drove nothing.** No agent turn, no browser, no screenshot. The two Hubs were checked for health
  and otherwise untouched.
- **Did not re-run the probes.** They no longer exist (S-1). The one that mattered most —
  the aiosqlite attribute chain — was re-derived on 2026-09-08 and is in `DEAD-ENDS.md`; this round
  re-read the library source instead, which is a stronger check of the same claim.
- **Did not verify the competitor or upstream claims** in the harness exploration. Out of scope.
- **Did not check every one of the 73 citations.** The first round did that and found 73/73. This
  round re-derived the load-bearing ones from the code and checked classes of claim the first round
  did not look at: environment instructions, task numbering, bundle scope, and forward instructions
  pointing at deleted files. Three of the six findings came from those classes.
