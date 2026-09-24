# Design — every event the Hub sends reaches the app

## Operator review, 2026-09-24

After the Opus adversarial review; citations re-checked at HEAD `c1c0fa4`.

- **Operator decisions confirmed.** B9-Q1: **no runtime allowlist**; the vocabulary is a generated
  type (D2 option B). B9-Q2: the bundle commit **waits for `:8000`'s restart** onto F335's fix
  (task 0.5). The two open questions below are therefore answered, not open.
- **The staleness test compared bytes across a line-ending conversion (Opus review).**
  `.gitattributes` sets `* text=auto eol=lf`, so the committed file is LF; `Path.write_text` on
  Windows writes CRLF, so a byte comparison would fail (or a regenerated file would churn) on this
  machine. The generator now writes with `newline="\n"`, and the test compares LF-normalised text
  (D3, tasks 1.3 and 2.3).
- **The generated file is linted (Opus review).** `hub/ui/eslint.config.js` ignores only `dist`,
  and `npm run lint` runs with `--max-warnings 0` (`hub/ui/package.json:10`), so the generated
  module must pass it as emitted; it is not added to `ignores` (D3, task 2.3).
- **D3 now says exactly how `connected` is excluded (Opus review).** `hub/hub/sse_events.py` defines
  `DISPATCHED_STREAM_FRAMES`, every entry of `STREAM_FRAMES` except `connected`, and the generator
  reads that tuple. F253's `stream_gap` (its task 2.3b) is then a one-line addition to
  `STREAM_FRAMES`; the generator needs no change. F253's text says the same.

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
lands) for frames the stream itself writes. 63 kinds at R1's scan. Beside them, derived and never
edited by hand:

```python
# Stream frames the app dispatches to listeners. `connected` is skipped by the read loop (D2).
DISPATCHED_STREAM_FRAMES = tuple(f for f in STREAM_FRAMES if f != "connected")
```

`hub/tests/test_sse_event_vocabulary.py` walks `hub/hub` with `ast`:

1. Every `.broadcast(` / `.publish(` / `defer_broadcast(` call whose kind argument is a string
   literal names a key of `EVENT_KINDS`. The kind is positional argument 1 of `broadcast` and
   `publish` (`project_id, event_type, data`) but argument 2 of `defer_broadcast` (`session,
   project_id, event_type, data`); the walk reads each by its own position, or by the
   `event_type=` keyword. Fails today for all 63 (the registry does not exist); after
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
SSE_EVENT_KINDS)[number]`. The array is exactly `sorted(set(EVENT_KINDS) |
set(DISPATCHED_STREAM_FRAMES))` (D1): the registry's kinds **plus every stream frame the app
dispatches to listeners** — `stream_gap` once `a-live-view-that-fell-behind-is-told-and-catches-up`
has landed (R2: that change's `ActivityLog` compares `event.type === 'stream_gap'`, which is TS2367
if the union lacks it). `connected` is excluded by `DISPATCHED_STREAM_FRAMES`'s definition, because
the read loop skips it before dispatch (D2); the generator has no exclusion of its own. So F253's
task 2.3b is one line — add `"stream_gap"` to `STREAM_FRAMES` — plus a regeneration.

**Line endings and lint (Opus review).** The repository checks text out as LF (`.gitattributes`:
`* text=auto eol=lf`), but `Path.write_text` on Windows translates `\n` to CRLF. The generator
therefore writes with `path.write_text(text, encoding="utf-8", newline="\n")`, and
`test_sse_event_vocabulary.py::test_the_generated_vocabulary_is_current` regenerates into memory
and compares **LF-normalised text** (`committed.replace("\r\n", "\n") == generated`), so neither a
CRLF working copy nor git's conversion makes it flaky; its failure message names the command to
run. The emitted module must pass `npm run lint` as written (`--max-warnings 0`,
`hub/ui/package.json:10`; `eslint.config.js` ignores only `dist`): no trailing whitespace, a final
newline, and no `eslint-disable` comment. No `npm` step runs Python: the generated file is
committed like the bundle.

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
| `run_diverged`, `run_divergence_resolved` | `tasks`, `status` | The card's divergence badge reads `task.has_open_divergence` from the tasks list (`TaskCard.tsx:396`); `run_diverged` may restaff, and `run_divergence_resolved` rides a move to `under_review` that the scheduler path announces with no `task_updated` (only `tasks.py:1472` and `spec.py:1634` broadcast that kind). `['project', pid, 'divergences', …]` (`useDivergences`, `api/tasks.ts:447`) is **not** invalidated: no component mounts it |
| `review_unstaffed` | `loops`, `loops/<loop_id>` | R2: it writes nothing but its own event row (`_emit_review_unstaffed`, `scheduler.py:2427-2478`: "It does not touch the job"), so no task or status query changes. The surface that names an unstaffable review is the loop card's stall reason (`decide_firing`, `scheduler.py:2070-2086`); the payload carries `loop_id` |
| `queue_agent_held`, `queue_agent_paused` | `agents`, `queue/<agent>` | As the queue family (`:499-510`) |
| `worktree_released` | `worktrees`, `worktree-conflicts` | As F250's cases (`:441-443`) |
| `checkpoint_ready`, `conversation_cut_over` | — | `useCheckpoints` (`api/checkpoints.ts:45-51`) |
| `conversation_updated`, `checkpoint_due`, `checkpoint_warning_dismissed` | — | `useProjectConversations` (`api/agentChat.ts:184-190`) refreshes on any payload with a `conversation_id` |
| `new_session_request` | — | Sent beside `message_created` (`agents.py:3039-3040`), which already invalidates |

## D5 — the feed

Admitting 18 kinds puts them in `eventBuffer` and in the Activity feed. Each either has a sentence
already (six do) or renders through the default branch. No new sentences are in scope.

**R2 checked the default branch.** `EventRow` renders the kind name as the row's title
(`components/activity/EventRow.tsx:81`) and prints a summary only when it differs from that name
(`:82`). The default branch (`eventSummary.ts:164-168`) returns the first of `error`, `message`,
`summary`, `title` in the payload, else the kind name. `checkpoint_due` (`checkpoint_trigger.py:222`,
`:280`: `conversation_id`, `agent`, threshold fields) and `agent_requested` (`agents.py:2242-2250`:
`agent`, `template`, `requester`, …) carry none of those, so each renders as its actor plus the bare
kind label, like every other kind without a sentence. Legible; whether it is enough is the
human-only check's question, and a "no" there is a new finding about a sentence, not a reason to
drop the kind. (`conversation_updated` carries `title`, so its row shows the conversation's title.)

## What each route returns when what it calls raises

No route changes. `publish`'s new warning is a `logger.warning` call and cannot raise.

## A bundle ahead of its Hub (R3) — B9-Q2

Prerequisite 0.4 checks F335 on the **tree**. The operator's `:8000` does not run the tree; it runs
the Hub process it last started from the tree, and serves `hub/hub/static/ui` from disk
(`StaticFiles`, `hub/hub/main.py:19`), so **a committed bundle reaches `:8000` on the next reload,
before any restart**. `/health`'s `ui_stale` does not see this skew: it compares the bundle with
`hub/ui/src` (`main.py:199-255`), not with the running process.

| Skew | What the operator sees |
|---|---|
| New bundle, `:8000` process older than F335 | Every one of the 18 kinds is now admitted, including `run_divergence_resolved`, which the old process still sends falsely when a review is refused at delivery. The Activity feed shows *"1 open divergence on T resolved"* for a divergence that is still open. The board stays true: the same frame's `tasks`/`status` invalidation refetches real state (D4). Every other admitted kind is a true event and is safe |
| New bundle, `:8000` process has F335 but not this change's registry | Safe. The registry has no runtime effect in the app (the generated module is a type), and the old process sends the same 63 kinds |
| New Hub, old bundle still open in a tab | Today's behaviour (the old allowlist drops the 18) until the tab reloads |

So the only hazard is F335's false line, for as long as `:8000` runs a process older than F335
while the new bundle is loaded. **B9-Q2:** gate the bundle commit on the operator's restart
(task 0.5, recommended), or accept the window. The builder cannot verify a restart itself, since
`:8000` may not be called.

## Open questions

Both answered by the operator on 2026-09-24 as recommended (B9-Q1: B; B9-Q2: yes, task 0.5 stands).
Kept below for the reasoning.

- **B9-Q2 (for the operator):** before this change's bundle is committed, must `:8000` have been
  restarted onto F335's fix? **Recommended: yes** (task 0.5). It costs one restart the operator
  would make anyway to pick up F335, and one question from the builder. Answering "accept the
  window" drops 0.5; until the next restart a refused review on `:8000` can put one false
  "divergence resolved" line in the feed while the board shows the truth.
- **B9-Q1 (for the operator):** keep a runtime allowlist generated from the registry (option A), or
  drop the runtime filter and keep the vocabulary as a type (option B)? **Recommended: B**, for the
  stale-bundle reason in D2.
