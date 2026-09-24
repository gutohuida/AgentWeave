# Design — isolation does not change under held work

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B5-2026-09-24.md`, section 5: *approve with
fixes*) and the operator's decisions recorded there. What changed, and why:

- **D12-1 answered as recommended: refuse under held work.** D1 stands.
- **The helper compares the effective config, not `Agent.config` (review, MEDIUM).** Where an agent
  works is decided by `get_agent_config`'s merged dict, `{**agent_row.config, **session_meta}`, in
  which the synced session entry **wins** (`hub/hub/launchability.py:485-486`); every
  `is_writing_agent` caller that picks a workspace reads that dict (`agent_trigger.py:689`, `:718`,
  `:1442`; `api/v1/worktrees.py:316-317`). A helper comparing `Agent.config` alone refuses a PATCH
  that changes nothing effective (session meta pins `read_only`) and could miss one that does. D1
  now compares `is_writing_agent` over the effective config before and after, and the merge rule is
  extracted once (`effective_agent_config`) so the helper and `get_agent_config` cannot disagree.
  Tests 1.9 and 1.10.
- **A third door, `POST /session/sync`, is guarded (review, MEDIUM; operator decision 4: guard it).**
  The route replaces `ProjectSession.data` wholesale (`hub/hub/api/v1/session_sync.py:61-75`), and
  its `agents.<name>.read_only` outranks `Agent.config`. It now runs the same refusal for every agent
  in the new payload before it assigns `row.data`. Tests 1.11-1.13; spec delta widened from "stored
  configuration" to "the configuration the Hub reads for the agent, including synced session state".
  R2's round-log claim that `PATCH` and `register` are the only writers of `read_only` was wrong about
  this door.
- **B3's interaction stands**: `agents-no-longer-register-themselves` deletes `POST /agents/register`,
  and with it this change's guard there (task 1.4). B3 keeps `/session/sync` on purpose (its `design.md:107`) and leaves `PATCH` alone.
- No spec SHALL is contradicted: `openspec/specs/` states nothing about `/session/sync` or
  `read_only` (grep), so the delta stays one ADDED requirement.


**Built on the recommended answer to D12's first question** (F242: *may `read_only` flip
mid-task?*): **no — refused while the agent holds work, allowed otherwise.** If the operator answers
otherwise:

- **"Yes, and the flip takes effect at the next task"** — D1 is replaced by a pin: a task records
  its workspace scheme when its checkout is provisioned (`Task.workspace_scheme` already exists for
  the grandfathered case), and `resolve_turn_workspace` honours the pin over a later `read_only`.
  Larger: it changes task 4.7's precedence.
- **"Yes, freely"** — no change; F242 is closed as accepted behaviour and the settings-page comment
  is rewritten to say the API allows it.

## D12, first question — options

| Option | Releases | Breaks or leaves |
|---|---|---|
| **(a) refuse while the agent holds work** (recommended) | the UI comment's promise holds on every door; an operator is told what to finish first; no stored state changes meaning | an operator who wants to flip a busy agent must wait or reassign |
| (b) pin the scheme per task at provisioning | the flip is always accepted | changes `resolve_turn_workspace`'s precedence (task 4.7, "a task checkout it may not write to would be an empty gesture"); a read-only agent would then write in a task checkout — the opposite of what read-only means |
| (c) snapshot every held checkout at the flip, then allow | nothing is stranded at the moment of the flip | the next task-bound turn still writes uncommitted into the operator's checkout (F242 consequences 2 and 3 are untouched) |

**Interaction with D12's other questions.** None of substance. F165's spelling is about how a
footprint names a branch; F242 decides which directory a read-only agent's turn runs in. A
read-only agent's evidence is footprinted at its recorded directory, the project root
(`footprint_root`'s first answer), under either answer here. F141 does not touch agents.

## D1 — the rule

The setting that decides where a turn runs is the **effective** config: `get_agent_config` merges
the synced session entry over `Agent.config`, the session entry winning
(`launchability.py:485-486` — note its docstring at `:453-456` states the opposite order; the code is
what runs, and the build corrects the docstring). The rule compares that, before and after:

```python
# launchability.py — the merge rule, stated once; get_agent_config uses it too
def effective_agent_config(agent_config, session_meta) -> dict:
    return {**(agent_config or {}), **(session_meta or {})}

async def isolation_change_refusal(session, project_id, agent_name, before, after) -> Optional[dict]:
    # before/after: effective configs (effective_agent_config over the stored and the proposed state)
    if worktrees.is_writing_agent(before) == worktrees.is_writing_agent(after):
        return None
    live = [run for run in <agent's Run rows whose id is in run_liveness.live_run_ids()>]
    held = [task for task in <Task where project_id, assignee == agent, status not in TERMINAL_STATUSES>]
    if not live and not held:
        return None
    return {"code": "isolation_change_under_held_work", "message": …, "held": {...}}
```

It lives beside `get_agent_config` in `launchability.py` (which already imports models lazily,
`:267`, `:469`) because two routers call it and neither should import the other.

- **Both directions.** Turning isolation **on** mid-task strands the other way: the previous turns'
  uncommitted edits sit in the operator's checkout while the next turn provisions a fresh task
  checkout from the base and does not see them.
- **Assigned, not provisioned.** A pending or assigned task may have no checkout yet, and counting it
  is stricter than necessary. It is also what the operator can see and act on without reading the
  disk, and the remedy is the same. **R2 keeps "assigned" — narrowing to "provisioned" would miss a
  real case.** Isolation turned **on** for a read-only agent is exactly the direction where no task
  checkout exists: its earlier task-bound turns ran in the operator's checkout
  (`resolve_turn_workspace` → `resolve_agent_workspace`, `worktrees.py:776-822`), their edits are
  uncommitted there (nothing snapshots a turn without an isolated workspace,
  `agent_trigger.py:1033`, `:1341`), and the next turn would provision a fresh task checkout that
  cannot see them. "Provisioned" answers no there; "assigned and not terminal" answers yes. And in the
  other direction the flip's harm does not depend on a live edit either: a task checkout's work is
  committed at each turn end (`snapshot_worktree`), so what is stranded is the task branch the next
  turn no longer runs on.
- **The per-agent worktree** needs no separate check. Its uncommitted work exists only during a turn
  — `snapshot_worktree` commits it when each turn ends — so the live-run check covers it.
- **A review is not held work.** A reviewer is not the task's assignee, and its review checkout is
  detached and per-agent; a live review is covered by the live-run check.

Where it runs — three doors, each computing `before` from the stored state and `after` from the
state it is about to write, and refusing before it mutates anything:

- `patch_agent`, before the config merge is assigned (`agents.py:2648-2659`): `after` is the merged
  or cleared `Agent.config` under the **current** session entry, so `config: null` (which clears
  `read_only`) is covered, and a PATCH that the session entry overrides is not a change.
- `register_agent`'s re-registration branch (`:2300-2308`), the same way.
- `sync_session` (`api/v1/session_sync.py:46-75`), before `row.data = body.data` (`:67`): for each
  agent named in the new payload that has an `Agent` row, `before` is its effective config under the
  old session data and `after` is `effective_agent_config(row.config, body.data["agents"][name])`.
  The first refusal raises 409; the payload is refused whole. An agent the payload **omits** is
  deleted, not re-isolated — removal keeps today's behaviour (its own checkout released, its task
  checkouts left alone, `session_sync.py:117-127`), and is not this rule's question.

## What the routes return when what they call raises

The helper reads the registry (in-memory) and one `Task` and one `Run` query. A database error
propagates as today's 500 from any of the three routes, with nothing assigned — the check runs before
the row is mutated. The refusal is raised before `session.commit()` (`session_sync.py:115` for the
sync route), and `get_session` never commits on exit (`db/engine.py:166-169`), so a refused body
changes **no** field — not only `config`: on `PATCH` the same "refused whole" rule the route already
states for unknown fields (`agents.py:2548-2553`); on `/session/sync` neither `ProjectSession.data`
nor any roster row (no agent added, none deleted, no worktree released — the release runs after the
commit).

## Cross-bundle

`agents-no-longer-register-themselves` (bundle B3) deletes `POST /agents/register`. If it lands
first, this change's guard on that route and its task 1.4 are dropped; if this lands first, B3
deletes the guard with the route. B3's design already records this (its *Cross-bundle* list). The
`PATCH` and `/session/sync` doors are untouched by B3.

## Open questions

1. **A read-only agent created that way and assigned a writing task** (R1 finding, not F242's
   door). Options: (a) refuse assigning a task to a read-only agent; (b) give a task-bound turn its
   task checkout even for a read-only agent (reverses task 4.7); (c) snapshot the project checkout
   after a read-only agent's task-bound turn — writes a commit onto the operator's branch; (d) file it
   and leave it. R1 recommends (d) now — nothing in the app sets `read_only` — and (a) if the app ever
   offers it. **R2 agrees with (d)**, and routes it to the orchestrator as a candidate finding (the
   bundle record's *Noticed* list, item 1): it is the same harm as F242's consequences 2-3 reached
   without any flip, and only (a) closes it.

## Round log

- **R1, 2026-09-24.** Re-verified F242 against `404c7d5`; found the second door (`POST /register`)
  and the flip-independent residual; wrote D1 and the options.
- **R2, 2026-09-24.** Re-derived both doors (`agents.py:2300-2308`, `:2648-2659`); the only other
  writers of `Agent.config` are row creation (`:737`, `:2205`) and the posture's `yolo` mirror
  (`:2489`), none of which touches `read_only`. Kept "assigned" over "provisioned" (the turn-on
  direction has no checkout to count). Open Question 1: (d), routed as a candidate finding. No
  claim disagreed with the code.
- **R3, 2026-09-24.** Re-derived: `patch_agent` merges `config` before any check (`agents.py:2648-2659`);
  `get_session` never commits on exit (`db/engine.py:166-169`), so raising before `session.commit()`
  refuses the body whole even though earlier fields were already set on the row; `is_writing_agent`
  (`worktrees.py:226-230`), `run_liveness.live_run_ids` (`:64`) and `TERMINAL_STATUSES`
  (`task_transition_service.py:736`) exist as the helper assumes; `takes_task_workspace` gives
  `read_only` precedence over the task (`worktrees.py:763-773`). No claim disagreed; nothing changed.
- **Operator review, 2026-09-24.** Two fixes from `spec-queue/tracks/reviews/B5-2026-09-24.md` §5,
  re-verified at HEAD `d0da83d`: the effective-config merge (`launchability.py:485-486`; workspace
  callers read it via `get_agent_config`, `agent_trigger.py:689`, `:718`, `:1442`,
  `api/v1/worktrees.py:316-317`) and the third door, `POST /session/sync`
  (`session_sync.py:46-75`, commit `:115`), guarded per operator decision 4. Seeding fixtures that
  sync `read_only` (`test_agent_trigger.py:488`, `test_project_scoped_runtime.py:103`) seed the roster
  at setup, which holds no work; control 1.14 runs every suite that calls `/session/sync` to prove it.
