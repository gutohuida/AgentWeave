import { describe, it, expect } from 'vitest'
import { summaryForEvent } from '@/lib/eventSummary'

describe('summaryForEvent — stream_gap', () => {
  it('says how many events were not delivered and that views were refreshed', () => {
    const line = summaryForEvent('stream_gap', { dropped: 10, severity: 'warn' })
    expect(line).toContain('10 events were not delivered')
    expect(line).toContain('Views were refreshed')
  })
})
