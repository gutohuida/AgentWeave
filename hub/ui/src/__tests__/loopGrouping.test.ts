/**
 * Collapsing consecutive firings — the ordering rules that make it safe.
 *
 * The list is sorted by recency, and that order *is* information: a firing that happened between
 * two things the operator did belongs between them. So grouping is strictly consecutive, never
 * global, and never reorders.
 */
import { describe, expect, it } from 'vitest'
import type { AgentConversation } from '@/api/agentChat'
import {
  capRows,
  conversationsOf,
  groupConsecutiveFirings,
  MIN_FIRINGS_TO_GROUP,
} from '@/lib/loopGrouping'

function conv(id: string, loop?: { id: string; label: string }): AgentConversation {
  return {
    id,
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title: id,
    title_set_by_operator: false,
    origin: loop ? 'job' : 'operator',
    loop: loop ?? null,
    attention: 'idle',
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
  }
}

const SWEEP = { id: 'loop-1', label: 'nightly sweep' }
const OTHER = { id: 'loop-2', label: 'hourly ping' }

describe('groupConsecutiveFirings', () => {
  it('leaves a list with no loops exactly as it was', () => {
    const rows = groupConsecutiveFirings([conv('a'), conv('b'), conv('c')])

    expect(rows.map((r) => r.kind)).toEqual(['conversation', 'conversation', 'conversation'])
  })

  it('collapses a run of firings of one loop into a single row', () => {
    const rows = groupConsecutiveFirings([
      conv('f1', SWEEP),
      conv('f2', SWEEP),
      conv('f3', SWEEP),
    ])

    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ kind: 'loopGroup', loopId: 'loop-1', label: 'nightly sweep' })
    expect(conversationsOf(rows[0]).map((c) => c.id)).toEqual(['f1', 'f2', 'f3'])
  })

  it('leaves a lone firing as a plain row', () => {
    // Collapsing one conversation hides it behind a click and saves no space; the marker on the
    // row already says which loop it came from.
    expect(MIN_FIRINGS_TO_GROUP).toBe(2)
    const rows = groupConsecutiveFirings([conv('a'), conv('f1', SWEEP), conv('b')])

    expect(rows.map((r) => r.kind)).toEqual(['conversation', 'conversation', 'conversation'])
  })

  it('does not join two runs of the same loop separated by something else', () => {
    // Grouping globally would move the operator's conversation, and the order is the information.
    const rows = groupConsecutiveFirings([
      conv('f1', SWEEP),
      conv('f2', SWEEP),
      conv('typed'),
      conv('f3', SWEEP),
      conv('f4', SWEEP),
    ])

    expect(rows.map((r) => r.kind)).toEqual(['loopGroup', 'conversation', 'loopGroup'])
    expect(conversationsOf(rows[0]).map((c) => c.id)).toEqual(['f1', 'f2'])
    expect(conversationsOf(rows[2]).map((c) => c.id)).toEqual(['f3', 'f4'])
  })

  it('breaks a run on a different loop', () => {
    const rows = groupConsecutiveFirings([
      conv('a1', SWEEP),
      conv('a2', SWEEP),
      conv('b1', OTHER),
      conv('b2', OTHER),
    ])

    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({ loopId: 'loop-1' })
    expect(rows[1]).toMatchObject({ loopId: 'loop-2' })
  })

  it('preserves order and loses nothing', () => {
    const input = [
      conv('a'),
      conv('f1', SWEEP),
      conv('f2', SWEEP),
      conv('b'),
      conv('f3', OTHER),
      conv('c'),
    ]

    const flattened = groupConsecutiveFirings(input).flatMap(conversationsOf)

    expect(flattened.map((c) => c.id)).toEqual(input.map((c) => c.id))
  })
})

describe('capRows', () => {
  it('counts hidden conversations, not hidden rows', () => {
    // The operator is being told how many conversations are hidden; a collapsed group of five
    // standing behind "Show 1 more" would be a lie.
    const rows = groupConsecutiveFirings([
      conv('a'),
      conv('f1', SWEEP),
      conv('f2', SWEEP),
      conv('f3', SWEEP),
    ])

    expect(capRows(rows, 1).hiddenConversations).toBe(3)
  })

  it('never splits a group, because it caps rows', () => {
    const rows = groupConsecutiveFirings([conv('f1', SWEEP), conv('f2', SWEEP), conv('b')])
    const { visible } = capRows(rows, 1)

    expect(visible).toHaveLength(1)
    expect(conversationsOf(visible[0])).toHaveLength(2)
  })

  it('hides nothing when everything fits', () => {
    const rows = groupConsecutiveFirings([conv('a'), conv('b')])

    expect(capRows(rows, 7)).toEqual({ visible: rows, hiddenConversations: 0 })
  })
})
