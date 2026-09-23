# Design — `run_id` in an event always names a run

**Built on the recommended answer to D1, second half** (rename the key, outright). If the operator
answers otherwise:

- *emit both keys for a period*: add `job_run_id` beside `run_id` at every site, and file a follow-up
  to delete `run_id`. The requirement below then needs a transitional clause;
- *keep `run_id` and document it*: this change is withdrawn, and F149 is closed as by-design with
  the timeline reader (`api/v1/agents.py:883-891`) left to miss silently;
- *give `JobRun` ids their own prefix* (`jobrun-`): complementary rather than alternative. It makes
  the value self-describing even in rows persisted before the rename, but it changes nothing a reader
  keys on. Not recommended on its own; not needed with the rename.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

What each reader of these events reads, at HEAD:

| Reader | Where | Keys read | Affected by the rename? |
|---|---|---|---|
| SSE dispatch | `hub/ui/src/hooks/useSSE.ts:524-535` | `id` | no |
| Event summary | `hub/ui/src/lib/eventSummary.ts:57-65` | `job_name`, `job_id`, `agent`, `error_summary`, `reason` | no |
| Agent timeline run facts | `hub/hub/api/v1/agents.py:883-891` | `run_id` of **every** event returned | yes: it stops looking up `JobRun` ids as runs |
| SSE tests | `hub/ui/src/__tests__/useSSE.test.tsx:128-144`, `:198-225` | frame type and `id` | no |
| Event summary tests | `hub/ui/src/__tests__/eventSummary.test.ts:154-168`, `:231` | as above | no |
| Hub tests | `grep -rn run_id hub/tests` near job events | none found in R1 | no |

`JobRun.requested_by_run_id` (`db/models.py:1421`) holds a real `Run` id and keeps its name.

## Decisions

### D1 — Rename, no dual emission

Nothing reads the key, and the one generic reader is better off without it. A transition period
protects readers that do not exist, and leaves a second meaning of `run_id` in the stream for as long
as it lasts.

### D2 — Stored events are not rewritten

Rewriting `event_log.data` in a migration would touch the operator's real history on their next
`:8000` restart, for a key nobody reads. Old rows keep `run_id`; the timeline reader already treats
an id that names no run as absent (`agents.py:886-891`).

### D3 — The rule is stated once, for every event

The requirement is written against all events, not these three, because the failure is a *second*
meaning for a shared key. The next event with a second kind of id is the case it exists for.

## Risks / Trade-offs

- **An external script reading `run_id` from `job_fired`** breaks. The drive harnesses under
  `scripts/drive/` are the only such scripts in the repo; R1's `grep` found none reading it. R2 should
  re-check.
- **An agent that read `run_id` from `run_job`'s MCP result** sees `job_run_id` instead. No MCP tool
  accepts a `JobRun` id, so there is nothing the agent could have done with it.

## Migration Plan

None. No schema change; stored events untouched (D2).

## Open Questions

None beyond the decision itself.
