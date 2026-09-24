# Proposal — every event the Hub sends reaches the app

**Round 1, 2026-09-24** (bundle B9, spec track S4). Finding: **F251 (B)**. Re-measured on HEAD
`ce086b6` (= `404c7d5` for every `hub/` and `hub/ui/` file). **Nothing here is implemented yet.**

**Must land after `an-event-is-announced-only-once-its-write-is-committed` (F335)**, or in the same
commit. This change admits `run_divergence_resolved` to the app; until F335 is fixed, a review
refused at delivery broadcasts that kind falsely, and the Activity feed would render *"1 open
divergence on T resolved"* for a divergence that is still open.

**And its bundle waits for `:8000`'s restart (R3, B9-Q2).** A committed bundle reaches the
operator's `:8000` on the next reload, before the Hub process restarts; F335's fix reaches it only at
the restart. Until then the new bundle would show F335's false line there (design, "A bundle ahead
of its Hub"). Task 0.5 gates the bundle commit on the operator's restart.

## Why

`useSSE.ts:337` dispatches a frame only if its name is in `SSE_EVENT_TYPES` (`:21-68`), a
hand-written array. Every other frame is read off the socket and discarded before any listener,
buffer or cache invalidation sees it. The array duplicates a server-side fact with nothing keeping
it true.

**Re-measured by AST** over every `.broadcast(` call in `hub/hub` (R1 scan; the finding's grep
counted 57 kinds and 44 allowlisted names): the Hub broadcasts **63** kinds — 59 as literals plus
`run_started`/`run_completed`/`run_failed`/`run_stopped` through the one non-literal site,
`_broadcast_run_lifecycle` (`hub/hub/api/v1/agent_trigger.py:1916`, bounded by
`_RUN_LIFECYCLE_EVENTS` at `:1878`). The allowlist holds **46**. **18** are dropped — the finding's
17 plus one added since it was filed:

```
agent_requested        agents.py:2251         checkpoint_due          checkpoint_trigger.py:222,280
checkpoint_ready       checkpoint_trigger.py:331,341; checkpoint_handover.py:278; checkpoints.py:195
checkpoint_warning_dismissed  checkpoints.py:263                conversation_cut_over  checkpoint_trigger.py:335; checkpoints.py:403
conversation_updated   agent_chat.py:467       job_archived            jobs.py:1290
new_session_request    agents.py:3039          project_deleted         projects.py:641
question_declined      questions.py:592        queue_agent_held (new)  agent_trigger.py:2547
queue_agent_paused     turn_scheduler.py:497   review_unstaffed        scheduler.py:2478
run_diverged           run_divergence.py:869   run_divergence_resolved run_divergence.py:104
task_blocked           run_task_binding.py:800 task_unblocked          questions.py:506,603
worktree_released      session_sync.py:159
```

And the mirror image, which the finding did not list: **`job_deleted` is allowlisted and handled**
(`useSSE.ts:40`, `:523`) **but no code in `hub/hub` broadcasts it** — archiving a job broadcasts
`job_archived`, which is dropped. So the jobs list the invalidation at `:521-529` was written to
refresh never refreshes on archive, and `useSSE.test.tsx:128` tests a kind the Hub never emits.

Code already written for the dropped kinds, and never run: `useCheckpoints`' subscription
(`hub/ui/src/api/checkpoints.ts:45-51`, `checkpoint_ready`/`conversation_cut_over`), the rail's
conversation refresh (`hub/ui/src/api/agentChat.ts:184-190`, `conversation_updated`, and any payload
with a `conversation_id` — which also covers `checkpoint_due` and `checkpoint_warning_dismissed`),
and six feed sentences in `hub/ui/src/lib/eventSummary.ts` (`queue_agent_paused` `:26`,
`review_unstaffed` `:79`, `run_diverged` `:138`, `task_blocked` `:145`, `run_divergence_resolved`
`:149`, `task_unblocked` `:150`). The checkpoint offer banner (`AgentOutputPanel.tsx:605-618`)
reads `useCheckpoints`, so a context-pressure checkpoint still appears only on reload.

This has been patched name by name twice (`useSSE.ts:538-540` for six loop events; the
`permission_denied` test at `useSSE.test.tsx:313`). Each patch left the next name to be dropped by
default.

## What changes

- The Hub declares its event vocabulary once, in `hub/hub/sse_events.py`. A test fails when any
  broadcast names a kind the registry lacks, and when the registry names a kind nothing broadcasts.
- The app stops filtering by name. It dispatches every named frame except `connected`. A generated
  TypeScript module (`hub/ui/src/lib/sseEventKinds.generated.ts`) carries the vocabulary as a type,
  so a handler written for a kind the Hub does not send fails `tsc`. A test fails when the
  generated file is stale.
- The central invalidation switch gains cases for the admitted kinds that change server state, and
  `job_deleted` is replaced by `job_archived`.

## What does not change

- The wire format, the operator stream's project stamping, and every payload.
- `summaryForEvent` keeps taking `type: string`: it also renders persisted history kinds that are
  never broadcast (`job_run_failed`, the `watchdog_*` family).

## Impact

- `hub/hub/sse_events.py` (new), `hub/hub/sse.py` (a warning for an unregistered kind),
  `scripts/generate_sse_event_kinds.py` (new), `hub/ui/src/lib/sseEventKinds.generated.ts` (new),
  `hub/ui/src/hooks/useSSE.ts`, tests, and the committed UI bundle.
- Spec: `local-project-workspace` gains *"The app receives every event kind the Hub broadcasts"*.
