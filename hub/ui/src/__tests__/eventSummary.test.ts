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
})
