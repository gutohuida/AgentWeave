# Proposal — a name a caller chooses reaches its own resource

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Finding: **F248 (C)**. Re-verified
on `ce086b6`, and R1 found it is one instance of three. **Nothing here is implemented yet.**

## Why

FastAPI matches routes in declaration order, so a literal segment declared before a `{param}` at the
same depth claims that word for good. Where the parameter is a name a caller chose, the resource
under that name can never be read at its own address. R1 listed every such pair in `hub/hub/api/v1`
(a script over every `@router.<method>("…")`, grouping by method and depth):

| Route with a caller-chosen name | Shadowed by | Declared at | Who chooses the name |
|---|---|---|---|
| `GET /worktrees/{agent}` | `GET /worktrees/conflicts` | `worktrees.py:178` before `:293` | anyone creating an agent; `AGENT_NAME_RE` accepts `conflicts` |
| `GET /queue/{agent}` | `GET /queue/settings` | `inbound_queue.py:80` before `:199` | the same; accepts `settings` |
| `GET /tasks/{task_id}` | `GET /tasks/board`, `GET /tasks/boards` | `tasks.py:943`, `:1009` before `:1234` | a task creator: `TaskCreate.id` accepts `^[a-zA-Z][a-zA-Z0-9_-]{0,63}$` (`schemas/tasks.py:17`, `:72-79`) |

The other literal-beside-parameter pairs the script found are under Hub-minted ids (`runner-…`,
`charter-…`, `job-…`), which cannot collide. F248 measured the first row (`GET
/worktrees/conflicts` answers `200 []` for an agent named `conflicts`,
`t_sweep_row15_worktrees.py` leg 2). The other two are read from declaration order, not measured.

The UI calls both `/queue/${agent}` (`hub/ui/src/api/queue.ts:40`) and `/worktrees/${agent}`
(`api/workspace.ts:84`), so an agent named `settings` has an unreadable queue panel and one named
`conflicts` an unreadable workspace panel.

## What Changes

- **The shadowed words are refused as names** (design D1): agent names `conflicts` and `settings`
  join the reserved names, each with a reason naming the route it would lose to; task ids `board`
  and `boards` are refused the same way.
- **A test makes the next collision fail** (design D2): it walks the app's routes, finds every literal
  sibling of a caller-named parameter, and asserts the matching validator refuses that word. A new
  literal route beside `{agent}` or `{task_id}` then fails the suite until its word is reserved.
- The reserved agent names change in both places CLAUDE.md names (`src/agentweave/constants.py`,
  `hub/hub/worktrees.py`).

No route moves, so no UI bundle and no backend/bundle ordering on `:8000`. No migration: `:8000`
has no agent named `conflicts` or `settings` and no task with id `board` or `boards` (measured,
`mode=ro`, 2026-09-24).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `hub-api-request-contract`: a new requirement, *A name a caller chooses reaches its own
  resource*.

## Impact

- `hub/hub/worktrees.py` (`_RESERVED_AGENT_NAMES`), `src/agentweave/constants.py`
  (`RESERVED_AGENT_NAMES`), `hub/hub/schemas/tasks.py` (the id validator).
- `hub/tests/`: a new `test_a_chosen_name_is_not_a_route.py`; `tests/` for the CLI constant if a test
  pins the set.
