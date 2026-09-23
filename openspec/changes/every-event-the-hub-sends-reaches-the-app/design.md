# Design — every event the Hub sends reaches the app

**Built on the recommended answer to B9-Q1 (design D2: the app dispatches every named frame, and
the generated vocabulary is a type, not a runtime filter).** If the operator answers otherwise
(keep a runtime allowlist, generated), D2 option A applies instead: tasks 2.4-2.5 keep the
`includes` test at `useSSE.ts:337` against the generated array, task 1.6 inverts to assert an
unknown kind is dropped, and option A's stale-bundle risk (D2) is accepted. Everything else stands.

Ordering: after `an-event-is-announced-only-once-its-write-is-committed` (F335). If
`a-live-view-that-fell-behind-is-told-and-catches-up` (F253) has landed, `stream_gap` joins the
registry's stream-frame section (D1); if not, it is simply absent.

## D1 — one registry on the server

`hub/hub/sse_events.py` holds `EVENT_KINDS: dict[str, str]`, each broadcast kind mapped to one
line saying what it announces, and `STREAM_FRAMES = ("connected",)` (plus `"stream_gap"` once F253
lands) for frames the stream itself writes. 63 kinds at R1's scan.

`hub/tests/test_sse_event_vocabulary.py` walks `hub/hub` with `ast`:

1. Every `.broadcast(` / `.publish(` / `defer_broadcast(` call whose kind argument is a string
   literal names a key of `EVENT_KINDS`. Fails today for all 63 (the registry does not exist); after
   the fix, a typo'd or new unregistered kind fails naming file and line.
2. A call whose kind is **not** a literal is allowed only at a declared site. Today there is one:
   `_broadcast_run_lifecycle` (`agent_trigger.py:1916`), which asserts `event_type in
   _RUN_LIFECYCLE_EVENTS` (`:1897`). The test imports that tuple and asserts it is a subset of the
   registry. Any other non-literal site fails.
3. Every key of `EVENT_KINDS` is broadcast by some site (literal or declared tuple). This is the
   check that would have caught `job_deleted`, and it keeps the registry from accreting dead names.

At runtime `SSEManager.publish`/`broadcast` logs a **warning** for an unregistered kind and still
sends it. It must not raise: broadcasts run after the write they announce has committed (and, after
F335, a deferred one runs inside `commit()`), so a raise would answer 500 for a write that landed.

## D2 — what the app does with a kind (B9-Q1)

| Option | Runtime | Keeps the fact in one place? | Failure it leaves |
|---|---|---|---|
| A. Generated allowlist | Keep `SSE_EVENT_TYPES.includes(...)`, list generated from the registry | Yes, at build time | **A stale bundle re-drops new kinds.** The bundle is a committed artefact (`hub/hub/static/ui`) refreshed separately from Hub code; `/health` reports `ui_stale` exactly because the two drift (`.claude/rules/hub-ui.md`). Every Hub kind added without a bundle refresh is F251 again, silently. |
| **B. No runtime filter; generated type (recommended)** | Dispatch every named frame except `connected`; `SSEEvent.type` is typed as the generated `SseEventKind` union | Yes | A stale bundle still dispatches a new kind; it renders with `summaryForEvent`'s default branch and invalidates nothing until a case is written — visible, not silent. |
| C. No filter, no generation | Dispatch everything; `type: string` | Yes (no client copy) | Nothing stops a handler for a kind the Hub never sends — `job_deleted`'s case (`useSSE.ts:523`) is exactly that, and it is why archiving a job never refreshed the list. |

B is the smallest thing that removes both failure directions: the app cannot drop a kind by
omission (no filter), and cannot handle a kind that does not exist without `tsc` failing
(`npm run build` is `tsc && vite build`, `hub/ui/package.json:8`). TypeScript rejects a `case`
label or `===` comparison whose literal is not in the union (TS2678 / TS2367).

The one cost: under skew (a bundle older than its Hub), `event.type` can hold a string outside the
union at runtime. That is safe — it reaches the switch's fall-through and `summaryForEvent(type:
string)` — and it is stated in a comment where the type is declared.

**What the filter was for, and what replaces it.** The only frames on the wire that are not events
are `connected` (`sse.py:108-114`, `event: connected`, `data: connected`) and `: ping` comments,
which `feedSSEChunk` never emits as frames (no `data:` line). `connected` is skipped explicitly, next
to the existing `message` skip at `useSSE.ts:333-336`.

## D3 — the generated module

`scripts/generate_sse_event_kinds.py` imports `hub.sse_events` and writes
`hub/ui/src/lib/sseEventKinds.generated.ts`: a header saying it is generated and from what, then
`export const SSE_EVENT_KINDS = [...] as const` (sorted) and `export type SseEventKind = (typeof
SSE_EVENT_KINDS)[number]`. `test_sse_event_vocabulary.py::test_the_generated_vocabulary_is_current`
regenerates into memory and compares byte for byte with the committed file; its failure message
names the command to run. No `npm` step runs Python: the generated file is committed like the
bundle.

## D4 — the admitted kinds that change server state

Each case uses the event's server-stamped `project_id` (`pid`), as every existing case does
(`useSSE.ts:418-424`). Kinds already served by a component's own listener get no central case.

| Kind | Central invalidation | Why |
|---|---|---|
| `job_archived` (replaces dead `job_deleted`) | `jobs`, `jobs/<id>`, `loops` | The job list and a loop whose job was archived |
| `project_deleted` | `['projects']` | The rail |
| `agent_requested` | `agents`, `['projects']` | A new agent is on the roster (the rail reads agents from `['projects']`, `useSSE.ts:571-573`) |
| `question_declined` | `questions`, `status` | As `question_answered` (`:460-464`) |
| `task_blocked`, `task_unblocked` | `tasks`, `status`, `questions` | Board and the waiting-on-you surfaces |
| `run_diverged`, `run_divergence_resolved`, `review_unstaffed` | `tasks`, `status` | Task cards and the drawer show divergences (`TaskCard.tsx`, `TaskDetailDrawer.tsx`); a divergence may restaff |
| `queue_agent_held`, `queue_agent_paused` | `agents`, `queue/<agent>` | As the queue family (`:499-510`) |
| `worktree_released` | `worktrees`, `worktree-conflicts` | As F250's cases (`:441-443`) |
| `checkpoint_ready`, `conversation_cut_over` | — | `useCheckpoints` (`api/checkpoints.ts:45-51`) |
| `conversation_updated`, `checkpoint_due`, `checkpoint_warning_dismissed` | — | `useProjectConversations` (`api/agentChat.ts:184-190`) refreshes on any payload with a `conversation_id` |
| `new_session_request` | — | Sent beside `message_created` (`agents.py:3039-3040`), which already invalidates |

## D5 — the feed

Admitting 18 kinds puts them in `eventBuffer` and in the Activity feed. Each either has a sentence
already (six do) or renders through the default branch. No new sentences are in scope; R2 should
look at whether `checkpoint_due` and `agent_requested` read acceptably through the default branch
(`eventSummary.ts:164-168`, which falls back to the kind's name).

## What each route returns when what it calls raises

No route changes. `publish`'s new warning is a `logger.warning` call and cannot raise.

## Open questions

- **B9-Q1 (for the operator):** keep a runtime allowlist generated from the registry (option A), or
  drop the runtime filter and keep the vocabulary as a type (option B)? **Recommended: B**, for the
  stale-bundle reason in D2.
