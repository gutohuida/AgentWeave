# Proposal — an undelivered message says how its last attempt ended

**Round 1, 2026-09-24** (bundle B2, decision D11). Findings: **F291 (C)**, changed shape since it was
filed, and **F273 (B)**, whose premise is obsolete; both re-verified against HEAD `ce086b6`.
Taken together because D11's answer to both is the same sentence: *a run's own row is the record of
how that attempt ended, and the conversation reads it from there.* **Nothing here is implemented
yet.**

## Why

### F291 — where a pre-spawn failure shows

A run that fails before its process spawns writes no output row (the pre-spawn `except`,
`agent_trigger.py:2173-2213`, calls `record_agent_output` nowhere). Its input is retried up to
`DELIVERY_ATTEMPT_LIMIT = 3` and then abandoned (`inbound_queue.py:280-290`), keeping
`delivered_in_run_id` as *"the operator's breadcrumb from a dropped message to the run that ate it"*
(`:286-288`).

What has changed since F291 was filed:

- the chat response now carries the facts of every run its entries name, including an abandoned
  entry's (`api/v1/agent_chat.py:296-345`, `_queued_entries_for` → `_run_facts_for`; F274);
- `run_failed` is in the chat hooks' refresh predicate (`hub/ui/src/api/agentChat.ts:314-319`);
- an abandoned message is its own one-entry turn at the time it arrived, with its *not delivered*
  chip and the Hub's reason (`hub/ui/src/lib/agentTimelineModel.ts:54-60`, F275;
  `AgentTimeline.tsx:261-272`).

What has not: **the run's own outcome never reaches the screen.** The abandoned turn is rendered by
`MessageEntry` with `runId: null` (`agentTimelineModel.ts:59`), so nothing reads
`runs[entry.run_id]`, and `RunFacts` (`hub/hub/schemas/agents.py:140-169`) carries no error even if
something did. The operator reads *"delivery failed 3 times; the Hub stopped retrying"* and not
*why*: *"%1 is not a valid Win32 application"* is on the run row (`Run.error`, written at
`agent_trigger.py:2178`) and in the `run_failed` broadcast (`_transport_failure_fields`, `:1828-1846`),
and nowhere the conversation shows.

One small gap F291 also recorded is still open: `queue_entry_abandoned` is not in the chat hooks'
`QUEUE_EVENT_TYPES` (`agentChat.ts:284-290`). On the run-end path `run_failed` covers it (broadcast
after the abandonment commits, `agent_trigger.py:2195-2204`). On the scheduler's give-up path, which
has no run (`turn_scheduler.py:639-655`, `run_id: None`), nothing the chat hooks hear fires.

### F273 — what a run says when its own terminal-status write fails

F273 argued that the persisted status line (`Run {status} (exit {code}).`) is *"the only settled
signal a stopped, failed or binding-conflicted run has … and the only carrier of the exit code once
the SSE stream has ended"*, so its silent loss mattered. **Both halves are no longer true:**

- the run's status and exit code are on its row (`agent_trigger.py:2450-2452`, `:3125`) and are
  served to the conversation by the run facts map (`RunFacts.status`, `.exit_code`), which
  `AgentTimeline` reads as the authoritative outcome (`AgentTimeline.tsx:130-161`: the status line is
  the fast signal, the run row the backstop);
- on the process path the status-line write is now `_record_observation` on its own session
  (`agent_trigger.py:2611-2625`, F359): a lock is retried and then dropped with a warning naming the
  run (`:1939-1956`), and any other error propagates to the catch-all, which logs it naming the run
  and leaves the terminal status alone (`_record_run_failure_tail`, `:2025-2031`). **R2: the Codex
  path does not use `_record_observation`.** It writes the line on the finalize block's own session
  after that block's commit (`agent_trigger.py:3206-3216`), so any error there, a lock included, goes
  straight to the same catch-all: logged naming the run, the committed terminal status untouched,
  and the re-drain still run by the tail. The amended requirement holds on both paths; only the
  retry is process-path only.

So the outcome F273 feared (*"the row that was supposed to say how it ended is silently absent"*)
now costs a refresh's latency, not the fact. What is still wrong is the spec, which requires the line
as though it were the record (`agent-stream-events`, *A run's terminal status line is persisted*,
`openspec/specs/agent-stream-events/spec.md:405-429`).

## What Changes

- `RunFacts` gains `error`: the run row's `Run.error`, fitted to a bound, `None` where the run
  recorded none. Both constructions carry it (`agent_chat.py:341`, `agents.py:894`).
- An abandoned message's turn reads its run's facts: where `runs[entry.run_id]` exists, the block
  says how the last attempt ended, beneath the Hub's reason: *"Last attempt failed: %1 is not a
  valid Win32 application."* (wording in design D2).
- `queue_entry_abandoned` joins the chat hooks' refresh predicate.
- `agent-stream-events`' requirement on the status line is amended: the line is persisted where it
  can be; a failure to write it is logged naming the run; the run's outcome and exit code are carried
  by the run's row and its facts either way. No product code changes for F273.

## Capabilities

### Modified Capabilities

- `agent-stream-events`: *A run's terminal status line is persisted* (modified); *A conversation
  carries the facts of the runs it renders* is unchanged, and `error` is added under it by an added
  requirement.
- `agent-conversation-workspace`: adds *An undelivered message says how its last attempt ended*.

## Impact

- `hub/hub/schemas/agents.py`, `hub/hub/api/v1/agent_chat.py`, `hub/hub/api/v1/agents.py`,
  `hub/ui/src/api/agents.ts`, `hub/ui/src/api/agentChat.ts`, `hub/ui/src/components/agents/AgentTimeline.tsx`;
  a UI bundle refresh (commit `hub/ui/src` and `hub/hub/static/ui` together; it reaches the
  operator's live `:8000` on their next reload).
- Routes changed: the two chat routes and the agent timeline gain one nullable field per run. No
  new call that can raise: the value is a column already loaded by the same query.
- Not in scope: rendering a retried-then-successful attempt's failure. The retry's turn already tells
  the agent (`agent-conversation-workspace`, *A re-delivered turn says the earlier attempt was cut
  off*); the operator sees the successful turn.
