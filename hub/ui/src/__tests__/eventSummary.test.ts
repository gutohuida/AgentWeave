import { describe, it, expect } from 'vitest'

import { summaryForEvent } from '@/lib/eventSummary'

describe('summaryForEvent', () => {
  it('never prints undefined when compact task and question events omit optional identity fields', () => {
    expect(summaryForEvent('task_updated', { status: 'in_progress' })).toBe('in_progress')
    expect(summaryForEvent('question_asked', { question: 'Ready to approve?' })).toBe('Ready to approve?')
  })
  // `task_created` was listed twice — once under the Hub-side events and again under the
  // CLI-pushed ones. A `switch` takes the first match, so the second clause was unreachable and
  // its wording never rendered anywhere. esbuild warned on every single build; nothing failed,
  // so nothing was noticed. This pins which of the two survived.
  it('summarises task_created exactly once, with the Hub-side wording', () => {
    expect(summaryForEvent('task_created', { title: 'Ship it', assignee: 'builder' })).toBe(
      '"Ship it" assigned to builder'
    )
  })

  it('falls back to unassigned rather than rendering undefined', () => {
    expect(summaryForEvent('task_created', { title: 'Ship it' })).toBe(
      '"Ship it" assigned to unassigned'
    )
  })

  // A Codex agent declined by its own sandbox used to produce no event at all. Now it does, and
  // the method it was refused on is mapped to a readable name first — the timeline renders
  // "{agent} refused {tool_name}", where a JSON-RPC method reads as noise.
  it('renders a runtime-decided refusal as a sentence', () => {
    const summary = summaryForEvent('permission_denied', {
      agent: 'reviewer',
      tool_name: 'Write',
      reason: "outside reviewer's workspace",
      decided_by: 'runtime',
    })
    expect(summary).toBe("reviewer refused Write: outside reviewer's workspace")
  })

  it('still names the action when the runtime gave no reason', () => {
    const summary = summaryForEvent('permission_denied', { agent: 'reviewer', tool_name: 'Bash' })
    expect(summary).toBe('reviewer refused Bash')
  })

  it('still summarises the event types that follow the clause that was removed', () => {
    expect(summaryForEvent('task_status', { task_id: 't-1', prev: 'pending', status: 'assigned' }))
      .toBe('t-1: pending → assigned')
  })

  // `every-run-knows-its-task`, task 4.9: a kind the timeline had never rendered before this
  // change, registered here rather than left to the default branch's best-effort guess.
  it('names the task and the count when open divergences resolve', () => {
    expect(summaryForEvent('run_divergence_resolved', { task_id: 'task-1', count: 1 })).toBe(
      '1 open divergence on task-1 resolved'
    )
    expect(summaryForEvent('run_divergence_resolved', { task_id: 'task-1', count: 3 })).toBe(
      '3 open divergences on task-1 resolved'
    )
  })
  // F87. Every one of these carries its only readable detail in a field the default branch does
  // not look at, so before this they rendered as their own event name and nothing else — and
  // `queue_entry_abandoned` is the *only* durable record that an input was dropped.
  it('says what was lost when the Hub gives up on a queued message', () => {
    expect(
      summaryForEvent('queue_entry_abandoned', {
        entry_id: 'entry-1',
        agent: 'builder',
        run_id: null,
        attempts: 3,
        reason: 'delivery failed 3 times; the Hub stopped retrying',
      })
    ).toBe('builder never received a message — delivery failed 3 times; the Hub stopped retrying')
  })

  it('names the agent and the cause when a queue is paused', () => {
    expect(
      summaryForEvent('queue_agent_paused', {
        agent: 'author',
        reason: 'project workspace is unavailable: directory is missing',
        directory_state: 'missing',
      })
    ).toBe('author is paused: project workspace is unavailable: directory is missing')
  })

  it('records the depth a held chain was continued from', () => {
    expect(
      summaryForEvent('queue_entry_released', {
        entry_id: 'entry-2',
        agent: 'reviewer',
        released_from_depth: 7,
      })
    ).toBe("reviewer's held message was continued from hop 7")
  })

  // A context reading is one of the most frequent rows in a live timeline, and every field it
  // carries (`percent`, `context_tokens`, `limit_tokens`, `model`) is one the default branch does
  // not look at — so each one rendered as the bare string `context_warning`, twice over, with the
  // measurement nowhere. Observed live during two separate drive sessions before it was filed.
  it('renders the measurement a context reading carries, not its own event name', () => {
    expect(
      summaryForEvent('context_warning', {
        agent: 'coder',
        percent: 62.5,
        context_tokens: 125000,
        limit_tokens: 200000,
        model: 'gpt-5.4-mini',
        observed_at: 1756000000,
      })
    ).toBe('coder is at 62.5% of its context window, 125000 of 200000 tokens (gpt-5.4-mini)')
  })

  // A Claude sample whose model the catalog does not declare keeps `percent`/`limit_tokens` null
  // (`resolve_usage_limit` invents nothing) — the count it does carry is still worth reading.
  it('reports the raw token count when a context reading has no percentage', () => {
    expect(
      summaryForEvent('context_warning', { agent: 'builder', context_tokens: 48123, model: 'claude-x' })
    ).toBe('builder has used 48123 context tokens (claude-x)')
  })

  it('names the agent even when a context reading carries no measurement at all', () => {
    expect(summaryForEvent('context_warning', { agent: 'builder' })).toBe(
      'builder: a context reading with no measurement'
    )
  })

  // The failure family, F105. Every kind below is written to `event_logs` by the Hub's own code —
  // so it certainly reaches this timeline — and every one of them names its detail something the
  // default branch does not look at (`reason`, `error_summary`, `run_exit_status`), not `error`
  // or `message`. Each therefore rendered as its own event name and nothing else: an operator
  // scanning a red row learned only that a red row existed. Swept out of the emitters rather
  // than found one at a time, which is how the previous five families were each discovered.
  it('renders why a scheduled job failed, not the words job_run_failed', () => {
    expect(
      summaryForEvent('job_run_failed', {
        job_id: 'job-1',
        job_name: 'nightly review',
        agent: 'reviewer',
        trigger: 'schedule',
        run_id: 'run-9',
        error_summary: 'runner claude exited 1',
      })
    ).toBe('"nightly review" failed for reviewer: runner claude exited 1')
  })

  it('names the job even when a failure carries no summary', () => {
    expect(summaryForEvent('job_run_failed', { job_id: 'job-1', agent: 'reviewer' })).toBe(
      'job-1 failed for reviewer'
    )
  })

  it('renders which action the Hub refused and why', () => {
    expect(
      summaryForEvent('agent_action_rejected', {
        endpoint: 'POST /messages',
        reason: 'unknown_recipient',
        recipient: 'nobody',
      })
    ).toBe('POST /messages refused: unknown_recipient (nobody)')
  })

  it('renders a refusal that names no recipient', () => {
    expect(
      summaryForEvent('agent_action_rejected', { endpoint: 'POST /messages', reason: 'archived_agent' })
    ).toBe('POST /messages refused: archived_agent')
  })

  it('says which document a turn produced nothing against', () => {
    expect(
      summaryForEvent('turn_produced_nothing', {
        run_id: 'run-3',
        agent: 'coder',
        spec_document: 'spec/changes/x.md',
        document_phase: 'proposed',
        run_exit_status: 'completed',
      })
    ).toBe('coder ended (completed) without changing spec/changes/x.md')
  })

  it('says which review could not be staffed and why', () => {
    expect(
      summaryForEvent('review_unstaffed', {
        job_id: 'job-2',
        job_name: 'loop',
        loop_id: 'loop-1',
        task_id: 'task-7',
        reason: 'no eligible reviewer',
      })
    ).toBe('no agent could review task-7: no eligible reviewer')
  })

  it('says why a loop stopped', () => {
    expect(
      summaryForEvent('loop_stopped', { job_id: 'job-2', loop_id: 'loop-1', reason: 'queue_drained' })
    ).toBe('loop loop-1 stopped: queue_drained')
  })

  it('says a loop ran out of queued work', () => {
    expect(
      summaryForEvent('loop_queue_exhausted', {
        job_id: 'job-2',
        loop_id: 'loop-1',
        pending_request: null,
      })
    ).toBe('loop loop-1 has no queued work left')
  })

  it('says why a firing was skipped', () => {
    expect(
      summaryForEvent('job_run_skipped', {
        job_id: 'job-2',
        job_name: 'nightly review',
        agent: 'reviewer',
        reason: 'agent_busy',
      })
    ).toBe('"nightly review" skipped: agent_busy')
  })

  it('says what a crashed run was holding', () => {
    expect(
      summaryForEvent('run_interrupted', {
        agent: 'coder',
        run_id: 'run-4',
        pid: 1234,
        returned_entry_ids: ['e-1'],
        abandoned_entry_ids: ['e-2', 'e-3'],
      })
    ).toBe("coder's run was interrupted — 1 message requeued, 2 dropped")
  })

  it('names the hop budget a suspended chain hit', () => {
    expect(
      summaryForEvent('queue_chain_suspended', {
        entry_id: 'entry-9',
        agent: 'reviewer',
        hop_depth: 6,
        hop_budget: 5,
      })
    ).toBe('reviewer: chain suspended at hop 6 of a 5-hop budget')
  })

  it('says which worktree could not be released and why', () => {
    expect(
      summaryForEvent('task_worktree_release_failed', {
        task_id: 'task-7',
        reason: 'directory is locked',
      })
    ).toBe('task-7: worktree not released — directory is locked')
  })

  // The cut that keeps this finding honest: a kind whose payload does name its detail `error`
  // already renders through the default branch, and does not need a case. Asserted so a later
  // sweep does not add one for it and call that a fix.
  it('leaves a kind that already carries `error` to the default branch', () => {
    expect(
      summaryForEvent('conversation_binding_conflict', {
        agent: 'coder',
        run_id: 'run-1',
        conversation_id: 'conv-1',
        error: 'run is already bound to conv-2',
      })
    ).toBe('run is already bound to conv-2')
  })
  // Task 8.3 of `a-write-outside-the-workspace-is-recorded`: the label check. The event's payload
  // names nothing the default branch reads, so before this case the operator's notice rendered as
  // the bare string `agent_wrote_outside_workspace` — the F87 shape, in the change that added it.
  //
  // The wording is checked as well as the presence. The product records this write; it does not
  // prevent it, and a row that read "escaped" or "violation" would claim a wall that is not there.
  it("names where an outside write landed, and never calls it an escape", () => {
    const summary = summaryForEvent('agent_wrote_outside_workspace', {
      agent: 'alice',
      tool: 'Write',
      path: 'C:/checkouts/bob/notes.md',
      destination_kind: 'agent',
      destination_name: 'bob',
    })
    expect(summary).toBe("alice wrote outside its workspace, into bob's workspace: Write → C:/checkouts/bob/notes.md")
    for (const forbidden of ['escap', 'violat', 'breach', 'refus', 'denied', 'blocked']) {
      expect(summary.toLowerCase()).not.toContain(forbidden)
    }
  })

  // A destination with no name still reads as a sentence rather than as a kind.
  it('falls back to plain wording for a destination that names nothing', () => {
    expect(
      summaryForEvent('agent_wrote_outside_workspace', {
        agent: 'alice',
        tool: 'Edit',
        path: '/tmp/stray.txt',
        destination_kind: 'outside',
        destination_name: null,
      })
    ).toBe('alice wrote outside its workspace: Edit → /tmp/stray.txt')
  })
})
