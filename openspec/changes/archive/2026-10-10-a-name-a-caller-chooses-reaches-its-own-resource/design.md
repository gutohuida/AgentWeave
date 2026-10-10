# Design — a name a caller chooses reaches its own resource

**Built on the recommended answer to B11's F248 question** (ROUNDS.md D13, *"`/worktrees/conflicts`
shadows an agent named 'conflicts'"*): **reserve the shadowed words, and let a route-table test catch
the next one.** If the operator prefers to move the routes (D3, option b), D1 is replaced by route
moves with aliases and D2 is kept unchanged.

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| Literal before parameter, same depth, caller-named parameter | the proposal's table |
| Reserved agent names, with a reason each, checked case-insensitively | `hub/hub/worktrees.py:73-80`, `:148-150` |
| The CLI's copy of the set | `src/agentweave/constants.py:77-79` |
| Agent creation validates through `validate_agent_name` | `worktrees.py:141-150` (R2: confirm every create door reaches it) |
| Task ids are caller-choosable | `hub/hub/schemas/tasks.py:17`, `:72-79` |
| F248's own write-up: "the repair is a namespace, not a reordering" | `scripts/drive/FINDINGS.md` F248 status line |

## D1 — Reserve the words, each with the route it would lose to

```python
_RESERVED_AGENT_NAMES = {
    "user": ...,
    "operator": ...,
    "conflicts": "GET /worktrees/conflicts would answer for it instead of its workspace",
    "settings": "GET /queue/settings would answer for it instead of its queue",
    "sessions": "GET /agent/sessions/{agent} would answer for its chat and conversation list",  # R3
}
```

`RESERVED_AGENT_NAMES` in the CLI gains the same three. Task ids: one shared function in
`schemas/tasks.py` (beside `_TASK_ID_RE`), called by **both** `TaskCreate._validate_id_shape` and
`AgentTaskCreate.validate_id` (`agent_actions.py:127-132`, the agent door MCP `create_task` posts
through), refuses
`board` and `boards` (case-insensitively, since the route match is exact but the reserved-name check
is not, and consistency with agents costs nothing) with *"'board' is a route under /tasks; choose
another id"*.

## D2 — The route table is the source of the words

`hub/tests/test_a_chosen_name_is_not_a_route.py` builds the app, walks `app.routes`, and for **every**
route with a `{param}` segment collects the literal routes registered before it, with a shared
method, that match it segment for segment (R2: keyed on the match, not on the names `{agent}` /
`{task_id}`, so a new route spelling its parameter `{agent_name}` is caught too). A pair whose
parameter is Hub-minted sits in an explicit allowlist in the test (today only `{runner_id}`:
`launchability`, `launchability-by-provider`); every other pair must have its word refused by the
validator for that parameter's resource. It asserts `validate_agent_name(word)` or the task-id validator raises for each
literal found. Today that list is exactly `conflicts`, `settings`, `sessions`, `board`, `boards`.
**(R3)** The walk must match a whole path, not one differing segment: `/agent/sessions/{agent}` and
`/agent/{agent}/chat` differ in two segments, each a literal against a parameter, and both match
`/agent/sessions/chat`. The earlier-registered route wins, so the victim is the later route's
parameter (`{agent}` = `sessions`). R2's list missed this pair.

This is what makes the fix durable. F248 was filed on 2026-09-01; the queue collision next to it
existed then and nobody saw it, because nothing asked.

## D3 — The options

| Option | What it would break | What it releases |
|---|---|---|
| **(a) Reserve the words + D2 (this change)** | Nothing on `:8000` (no such names today). An install elsewhere with an agent already called `conflicts` keeps it, still unreadable at those two routes, and cannot create another. | Every shadowed name, and the next one by test. |
| (b) Move the literal routes (`/worktree-conflicts`, `/queue-settings`, `/task-board(s)`) | Every UI caller of the moved routes, and `:8000`'s live app if the bundle lands before the backend restarts, unless the old paths stay as aliases for a release. | The names, without a reserved list. |
| (c) Move the parameter routes under a segment (`/worktrees/agents/{agent}`) | Not possible for `/tasks/{task_id}` without moving the most-used route in the API, including MCP's `get_task`. | Two of the three. |
| (d) Reorder | Swaps which resource is unreachable. | Nothing. |

(b) is the structurally cleaner end state, since it removes the coupling between route names and
naming rules. (a) is recommended because it costs no route migration, and D2 keeps the coupling
checked rather than remembered.

## D4 — What the routes return when the new code raises

`validate_agent_name` already raises `ValueError`, and every agent-create door already turns that
into a 400 or 409 (the `user`/`operator` path, F415). The task-id validator is a Pydantic validator,
so a reserved id answers 422 naming `id` **at each door's own request model**.

**R2 correction: the agent door.** `POST /agent/tasks` parses `AgentTaskCreate` (its own id
validator) and then builds `TaskCreate(**body.model_dump(), …)` *inside* the handler
(`agent_actions.py:233`). If only `TaskCreate` refused `board`, the agent door would accept the body
and then raise a Pydantic `ValidationError` from handler code, which FastAPI answers **500**, not 422.
Hence one shared check called by both models (D1); task 1.4 covers both doors. `create_job`'s
`initial_tasks` builds `TaskCreate` inside a `try` that already answers 422 (`jobs.py:661-669`).

## Open questions

None beyond the decision this is built on.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: collision table rebuilt independently from the built app's `app.routes` (not
  R1's source scan), both orders checked: literal-before-parameter pairs are exactly
  `worktrees/conflicts`, `queue/settings`, `tasks/board`, `tasks/boards` (caller-chosen) and two
  `runners/launchability*` (Hub-minted `runner_id`); no parameter route hides a later literal. R1's
  `charter-…`/`job-…` pairs do not exist; corrected. Every agent-create door reaches
  `validate_agent_name` (`agents.py:666, 2153, 2278`, `agent_roster.py:36`, `agent_trigger.py:654,
  1416`, `session_sync.py:84`). **Disagreed:** the agent task door has its own id validator
  (`AgentTaskCreate`, `agent_actions.py:127-132`) and re-validates through `TaskCreate` inside the
  handler, so a `TaskCreate`-only fix answers 500 there; D1, D4 and tasks 1.4, 2.2 now use one
  shared check. D2's walk re-keyed on segment match plus a minted-parameter allowlist. `:8000`
  (`mode=ro`, 2026-09-24): no agent `conflicts`/`settings`, no task `board`/`boards`.
- R3 2026-09-24: re-walked the built app's `app.routes` with a whole-path matcher (every pair of
  routes with a shared method and equal depth whose segments are pairwise equal or literal-vs-
  parameter). **Disagreed (1):** a fifth word. `GET /agent/sessions/{agent}`
  (`agent_trigger.py:3257`) is registered before `GET /agent/{agent}/chat` and
  `GET /agent/{agent}/conversations`, so an agent named `sessions` loses its chat history and
  conversation list, both read by the UI (`api/agentChat.ts:167`, `:381`). `sessions` added to D1,
  D2's list, the proposal and tasks 1.2 and 1.6; D2 now states the whole-path rule. The other four
  rows and the `{runner_id}` allowlist held. `:8000` (`mode=ro`): no agent named `sessions`.
