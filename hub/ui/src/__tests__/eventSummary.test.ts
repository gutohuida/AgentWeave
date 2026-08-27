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
})
