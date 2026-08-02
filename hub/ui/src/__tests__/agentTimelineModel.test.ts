import { describe, expect, it } from 'vitest'
import type { TimelineEntry } from '@/api/agentChat'
import {
  entryCategory,
  findPairedResult,
  groupIntoTurns,
  runStatusByRunId,
} from '@/lib/agentTimelineModel'

function entry(overrides: Partial<TimelineEntry>): TimelineEntry {
  return {
    id: 'e1',
    kind: 'agent_output',
    content: 'hello',
    timestamp: '2026-08-02T00:00:00Z',
    delivery_state: 'delivered',
    ...overrides,
  }
}

describe('entryCategory', () => {
  it('classifies operator/peer entries and plain agent text as conversational', () => {
    expect(entryCategory(entry({ kind: 'operator_input' }))).toBe('message')
    expect(entryCategory(entry({ kind: 'inbound_peer' }))).toBe('message')
    expect(entryCategory(entry({ kind: 'outbound_peer' }))).toBe('message')
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'text' }))).toBe('message')
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'error' }))).toBe('message')
  })

  it('classifies thinking/tool_use/tool_result as intermediate work', () => {
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'thinking' }))).toBe('work')
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'tool_use' }))).toBe('work')
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'tool_result' }))).toBe('work')
  })

  it('classifies status/diagnostic as a structured result', () => {
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'status' }))).toBe('result')
    expect(entryCategory(entry({ kind: 'agent_output', output_kind: 'diagnostic' }))).toBe('result')
  })
})

describe('groupIntoTurns', () => {
  it('groups delivered entries by run_id, preserving arrival order', () => {
    const entries = [
      entry({ id: 'a', run_id: 'run-1', timestamp: '2026-08-02T00:00:00Z' }),
      entry({ id: 'b', run_id: 'run-2', timestamp: '2026-08-02T00:01:00Z' }),
      entry({ id: 'c', run_id: 'run-1', timestamp: '2026-08-02T00:02:00Z' }),
    ]
    const { turns } = groupIntoTurns(entries)
    expect(turns).toHaveLength(2)
    expect(turns[0].runId).toBe('run-1')
    expect(turns[0].entries.map((e) => e.id)).toEqual(['a', 'c'])
    expect(turns[1].runId).toBe('run-2')
  })

  it('separates still-queued entries into pending, not a turn', () => {
    const entries = [
      entry({ id: 'delivered', run_id: 'run-1', delivery_state: 'delivered' }),
      entry({ id: 'queued', delivery_state: 'queued' }),
    ]
    const { turns, pending } = groupIntoTurns(entries)
    expect(turns).toHaveLength(1)
    expect(pending.map((e) => e.id)).toEqual(['queued'])
  })
})

describe('findPairedResult', () => {
  it('pairs a tool_use with its tool_result by call_id', () => {
    const use = entry({
      id: 'use-1',
      output_kind: 'tool_use',
      payload: { call_id: 'c1' },
    })
    const result = entry({
      id: 'result-1',
      output_kind: 'tool_result',
      payload: { call_id: 'c1' },
    })
    expect(findPairedResult([use, result], use)?.id).toBe('result-1')
  })

  it('returns undefined when no matching result exists yet', () => {
    const use = entry({ id: 'use-2', output_kind: 'tool_use', payload: { call_id: 'c2' } })
    expect(findPairedResult([use], use)).toBeUndefined()
  })
})

describe('runStatusByRunId', () => {
  it('maps run lifecycle events to their run_id, keeping only recognized types', () => {
    const events = [
      { event_type: 'run_started', data: { run_id: 'run-1' } },
      { event_type: 'run_completed', data: { run_id: 'run-1' } },
      { event_type: 'run_stopped', data: { run_id: 'run-2' } },
      { event_type: 'message', data: { run_id: 'run-3' } },
    ]
    const result = runStatusByRunId(events)
    expect(result['run-1']).toBe('completed')
    expect(result['run-2']).toBe('stopped')
    expect(result['run-3']).toBeUndefined()
  })
})
