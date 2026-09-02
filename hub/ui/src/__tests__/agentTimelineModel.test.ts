import { describe, expect, it } from 'vitest'
import type { TimelineEntry } from '@/api/agentChat'
import type { TurnUsage } from '@/api/accounting'
import {
  entryCategory,
  findPairedResult,
  groupIntoTurns,
  isSuccessCompletionEntry,
  reduceTurnBlocks,
  tokensByRunId,
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

function turnUsage(overrides: Partial<TurnUsage>): TurnUsage {
  return {
    id: 'tu-1',
    run_id: 'run-1',
    agent: 'claude',
    status: 'measured',
    runner: 'claude',
    model: 'claude-sonnet-5',
    input_tokens: 100,
    output_tokens: 200,
    total_tokens: 300,
    cache_read_tokens: null,
    cache_write_tokens: null,
    reasoning_tokens: null,
    api_equivalent_usd_micros: null,
    allowance: null,
    observed_at: '2026-08-02T00:00:00Z',
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

describe('isSuccessCompletionEntry', () => {
  it('matches runner_parsing.py\'s status_event("completed", ...) sentinel', () => {
    expect(
      isSuccessCompletionEntry(
        entry({ kind: 'agent_output', output_kind: 'status', payload: { phase: 'completed' } }),
      ),
    ).toBe(true)
  })

  it('leaves a non-terminal status phase (e.g. a plan) alone', () => {
    expect(
      isSuccessCompletionEntry(
        entry({ kind: 'agent_output', output_kind: 'status', payload: { phase: 'plan' } }),
      ),
    ).toBe(false)
  })

  it('ignores entries of any other kind or output_kind', () => {
    expect(isSuccessCompletionEntry(entry({ kind: 'operator_input' }))).toBe(false)
    expect(
      isSuccessCompletionEntry(
        entry({ kind: 'agent_output', output_kind: 'diagnostic', payload: { phase: 'completed' } }),
      ),
    ).toBe(false)
    // A failed run's error_event (runner_parsing.py's is_error branch) is kind='error', never
    // 'status' — it must keep rendering regardless of this helper.
    expect(
      isSuccessCompletionEntry(entry({ kind: 'agent_output', output_kind: 'error' })),
    ).toBe(false)
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

describe('reduceTurnBlocks (2026-08-04-hub-charcoal-visual-refresh)', () => {
  it('produces blocks in execution order, never hoisting work ahead of preceding text', () => {
    const entries = [
      entry({ id: 'text_a', output_kind: 'text' }),
      entry({ id: 'tool_1', output_kind: 'tool_use', payload: { call_id: 'c1' } }),
      entry({ id: 'text_b', output_kind: 'text' }),
      entry({ id: 'tool_2', output_kind: 'tool_use', payload: { call_id: 'c2' } }),
      entry({ id: 'result', output_kind: 'status' }),
    ]
    const blocks = reduceTurnBlocks(entries)
    expect(blocks.map((b) => (b.kind === 'work' ? `work:${b.entries.map((e) => e.id).join(',')}` : `entry:${b.entry.id}`)))
      .toEqual(['entry:text_a', 'work:tool_1', 'entry:text_b', 'work:tool_2', 'entry:result'])
  })

  it('collapses consecutive work entries into one block', () => {
    const entries = [
      entry({ id: 'thinking', output_kind: 'thinking' }),
      entry({ id: 'tool_1', output_kind: 'tool_use', payload: { call_id: 'c1' } }),
      entry({ id: 'tool_result_1', output_kind: 'tool_result', payload: { call_id: 'c1' } }),
    ]
    const blocks = reduceTurnBlocks(entries)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind).toBe('work')
    expect(blocks[0].kind === 'work' && blocks[0].entries.map((e) => e.id)).toEqual([
      'thinking', 'tool_1', 'tool_result_1',
    ])
  })

  it('leaves a work-only turn as a single block, unchanged in substance', () => {
    const entries = [
      entry({ id: 'tool_1', output_kind: 'tool_use' }),
      entry({ id: 'tool_2', output_kind: 'tool_use' }),
    ]
    const blocks = reduceTurnBlocks(entries)
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind).toBe('work')
  })

  it('gives each work block a distinct, stable id derived from its first entry', () => {
    const entries = [
      entry({ id: 'text_a', output_kind: 'text' }),
      entry({ id: 'tool_1', output_kind: 'tool_use' }),
      entry({ id: 'text_b', output_kind: 'text' }),
      entry({ id: 'tool_2', output_kind: 'tool_use' }),
    ]
    const blocks = reduceTurnBlocks(entries)
    const workBlockIds = blocks.filter((b) => b.kind === 'work').map((b) => b.id)
    expect(new Set(workBlockIds).size).toBe(workBlockIds.length)
  })
})

describe('tokensByRunId', () => {
  it('maps a measured turn to its total token count', () => {
    const result = tokensByRunId([turnUsage({ run_id: 'run-1', total_tokens: 4200 })])
    expect(result['run-1']).toBe(4200)
  })

  it('omits an unavailable turn rather than showing 0 tokens', () => {
    const result = tokensByRunId([
      turnUsage({ run_id: 'run-1', status: 'unavailable', total_tokens: null }),
    ])
    expect(result['run-1']).toBeUndefined()
  })

  it('omits a measured turn with no total (partial usage payload)', () => {
    const result = tokensByRunId([turnUsage({ run_id: 'run-1', total_tokens: null })])
    expect(result['run-1']).toBeUndefined()
  })

  it('keys by run_id, not turn id, so multiple entries for the same run resolve to one figure', () => {
    const result = tokensByRunId([
      turnUsage({ id: 'tu-1', run_id: 'run-1', total_tokens: 100 }),
      turnUsage({ id: 'tu-2', run_id: 'run-2', total_tokens: 250 }),
    ])
    expect(result).toEqual({ 'run-1': 100, 'run-2': 250 })
  })
})
