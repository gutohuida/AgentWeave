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
}
```

`RESERVED_AGENT_NAMES` in the CLI gains the same two. Task ids: the `TaskCreate.id` validator refuses
`board` and `boards` (case-insensitively, since the route match is exact but the reserved-name check
is not, and consistency with agents costs nothing) with *"'board' is a route under /tasks; choose
another id"*.

## D2 — The route table is the source of the words

`hub/tests/test_a_chosen_name_is_not_a_route.py` builds the app, walks `app.routes`, and for each
route whose last segment is `{agent}` or `{task_id}` collects the literal routes with the same
method and prefix. It asserts `validate_agent_name(word)` or the task-id validator raises for each
literal found. Today that list is exactly `conflicts`, `settings`, `board`, `boards`.

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
so a reserved id answers 422 naming `id`. No new exception path.

## Open questions

None beyond the decision this is built on.

## Round log

- R1 2026-09-24: written.
