# Design — agents no longer register themselves

**Built on the recommended answer to D3**: self-registration leaves the product, as the operator
already decided on 2026-08-29, so no "third sentence keyed on `contact_mode`" is written and
`contact_mode` goes with the population it described. **If the operator answers otherwise** (keep
self-registration), this change is withdrawn and replaced by one that keeps the route, drops only
`watchdog-spawn` from the vocabulary, and adds a launchability reason keyed on `contact_mode`
(`poll`: *"manages its own execution; the Hub does not start it"*); F136's guard would then be
replaced, not deleted. The measurements below are what that alternative would have to argue against.

## Context — re-verified on HEAD `404c7d5`

| Finding | Still open? | Evidence |
|---|---|---|
| F111 | open | `POST /agents/register` live at `hub/hub/api/v1/agents.py:2261`; the guard at `launchability.py:507` still reads `elif not agent_row.self_registered and "runner" not in meta` |
| F136 | open, same root | the same clause; the defending comment at `launchability.py:508-514` still cites `collaboration_ready`, which F136 measured as `null` for this case |
| F3 | open | literal `contact_mode="watchdog-spawn"` at `agents.py:735` (create) and `:2203` (`request_agent`); `_CONTACT_MODES` at `:84` still lists it; `hub/tests/test_operator_agent_creation.py:56` pins it in a whole-body equality |

`git log -S 'contact_mode="watchdog-spawn"'` finds no commit removing either literal since F3 was
filed. The DEAD blocks added 2026-09-20 (`agents.py:77-83`, `db/models.py:208-218`,
`src/agentweave/constants.py:315`) already record that nothing acts on these fields.

## D1 — Delete, do not reword

Three options were on the table for D3:

1. **Delete self-registration** (recommended; the operator's 2026-08-29 decision). No shipped client
   calls the route; the real database holds zero self-registered agents and zero `project_sessions`
   rows (read `mode=ro` 2026-09-24). Deleting the population removes the sentence and the column
   vocabulary together.
2. **Keep it, key a third launchability reason on `contact_mode`** (F136's sketch). Needs a public
   naming decision for the operator-created case (none of `poll`/`mcp-push`/`watchdog-spawn` is
   true of an agent the Hub spawns — F3's "gate, run and failed"), keeps four write-only columns,
   and preserves a population no client produces.
3. **Drop only the `self_registered` guard** (F136's measured one-liner). Measured by F136 to break
   no test, but tells a hypothetical polling agent to bind a runner it does not want; F111 records
   why that is also false.

Option 1 is the only one where every remaining sentence is true of an agent that can exist. It does
reach one shipped requirement: `runner-registry`'s scenario *"A self-registered agent with a runner
bound"* is quantified over the population, so that requirement is modified here rather than left
unreachable (F3's condition 1).

## D2 — The columns go in one migration

`contact_mode`, `self_registered`, `mcp_endpoint`, `spawn_cmd` (`db/models.py:206-220`). SQLite
needs `batch_alter_table` to drop columns; follow `.claude/rules/db-migrations.md` (guard for a
missing table, bump the head assertions in `test_migrations.py` and
`test_project_persistence.py`). The downgrade re-adds them nullable (`self_registered` with
`server_default='0'`), and does not restore values — there are none worth restoring (measured).

Keeping the columns and only deleting the route was considered and rejected: the response fields
would then echo constants forever, which is F3 in a different spelling.

## D3 — What else reads the population, and what happens to it

| Site | Today | After |
|---|---|---|
| `scheduler._job_agent_skip_reason` (`:229-252`), called at `:3078` | skips a job whose agent is a self-registered `poll` agent | deleted with its call. (`an-agent-can-be-paused-and-keeps-its-input` does not need this hook: a pause is read as a hold, which the loop busy guard and the plain-job coalesce already consult) |
| `launchability.py:507` | exempts self-registered agents from `RUNNER_UNBOUND` | `elif "runner" not in meta:` |
| `agents.py:567-577` liveness | `online`/`offline` only for self-registered agents; `None` otherwise | the field is removed from `AgentSummary`; heartbeat rows still feed `effective_heartbeat_status` unchanged |
| `agents.py:2289-2294` reserved-name check against `session_data` | only in `register_agent` | goes with the route |
| `test_request_strictness.py:49` `NO_CONTRACT_BY_DESIGN` entry for `register_agent` | exempts the untyped `body: dict` route | the entry is removed (the route no longer exists, and the test enumerates live routes) |
| `POST /agents/{name}/heartbeat` (`agents.py:2908`) | accepted from anyone with a project key | **unchanged** — heartbeats are not self-registration; whether the route still has a writer is out of scope |

## D4 — How a test makes an agent when no runner CLI exists

F3 names this as the question to answer first: `POST /projects/{p}/agents` probes the runner CLI and
answers 409 without one, and CI runners have no `claude` on PATH (memory: *local suite green because
claude is on PATH*). The register route became the fast fixture for that reason.

**Answer: a shared `add_agent` fixture in `hub/tests/conftest.py` that inserts an `Agent` row through
`async_session_factory`**, taking `name` and optional column overrides, exactly as
`test_a_task_waits_while_its_run_waits.py:71` and `test_a_late_answer_is_delivered.py:50` already do
locally. It performs no probe, so it is PATH-independent; `bind_runner` (`conftest.py:885`) keeps
working on top of it because it PATCHes the row the fixture created. Tests that read the register
route's returned `context` (`test_charter_context.py`, `test_instructions.py`,
`test_spec_document_context.py`, `test_workspace_posture_context.py`) read
`GET /agents/agent-context?agent=` instead, which renders the same `_render_hub_agent_context`.

The name rule is not changed: the fixture writes names tests choose; production creation still goes
through `AGENT_NAME_RE` and the Hub's restatements (`agents.py:75`, `worktrees.py`), which this change
does not touch.

## D5 — Routes and what they return when the call raises

- `POST /agents/register` — gone; a caller gets FastAPI's 404/405. No shim: nothing ships that calls it.
- `PATCH /agents/{name}` with `contact_mode`/`mcp_endpoint`/`spawn_cmd` — refused by the existing
  `_PATCH_AGENT_FIELDS` allowlist (the "fails in this direction" comment at `:2515`), i.e. the same
  400 an unknown key already gets. No new raise path.
- `GET /agents`, `POST /agents` (create), `GET /agents/{name}` — only lose fields; a raise inside
  them is unchanged by this change.

## Interaction with other open changes

- `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` (B10) deletes `AgentCard.tsx`; if it
  lands first, task 2.9's badge edit is moot.
- `isolation-does-not-change-under-held-work` (B5) plans a test (its task 1.4) and a guard on
  `POST /agents/register`'s config merge (its proposal, citing `agents.py:2300-2308`). If this change
  lands first, that half of B5 has no route to guard and its task 1.4 is dropped; if B5 lands first,
  this change deletes that guard with the route. R2 of both should record which.

## Open questions for the operator

1. **Confirm D3's answer** (delete). The recommendation is to record the 2026-08-29 decision in
   `DECISIONS.md`, where it is not yet written — it lives only inside FINDINGS F111.
2. **`project_sessions` / `POST /session/sync`** stay. They are the last watchdog-era input
   (0 rows on both Hubs; only writer is the dead CLI `push_session`, itself marked DEAD). Retiring
   them would also retire the `"runner" in meta` branch of launchability and `_get_session_data`'s
   four readers. Recommended: a separate follow-on, not folded in here.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): every site in D3's table re-derived by `grep` and confirmed (`scheduler.py:250`
  is the only behavioural reader; `_job_agent_skip_reason`'s one call is `:3078`). Test footprint
  confirmed at 31 sites in 19 files plus the 24 in `test_agents_self_registered.py`; drive callers
  are **9**, not 8. The 2026-08-29 decision is sourced (proposal *Why*). Task 1.3 corrected: after the
  migration it cannot set `self_registered`, so it is a control, and the guard's return is prevented by
  the column's absence (1.6) plus a source assertion. B5's final text
  (`isolation-does-not-change-under-held-work` design *Cross-bundle*) agrees with the interaction
  recorded here; B10's final text deletes `AgentCard.tsx`, so task 2.9's badge edit is moot if B10
  lands first. **Follow-on noted, not in scope:** `jobs._check_agent_exists` (`jobs.py:181-200`)
  exempts a project with an empty roster on the argument that a job may be created *"before the
  watchdog first syncs"*; with self-registration gone that bootstrap order no longer exists, and that
  exemption is the last producer of F276's no-such-agent firing.
- R3 (2026-09-24): every reader of the four columns re-derived by `grep` over `hub/hub`, `src/` and `hub/ui/src` (matches D3's table and task 2.x's sites exactly); `get_agent_registration` and `CONTACT_MODES` have no caller. Launchability's `"runner" in meta` also reads `Agent.config` (merged at `launchability.py:485-486`), so the unbound verdict after the change is "no runner row and no `runner` key anywhere" — as D3 says. Migration number: see the B3 record (three B3 changes and four others name or need `0106`). No change to the proposal.
