import { describe, it, expect } from 'vitest'
import { eventBelongsToTimeline } from '@/api/agents'

describe('eventBelongsToTimeline — timeline live-update matching (previously: no SSE coverage, pure 5s poll)', () => {
  it('matches message_created where the agent sent it', () => {
    expect(
      eventBelongsToTimeline({ type: 'message_created', data: { from: 'claude', to: 'ops' }, timestamp: '' }, 'claude')
    ).toBe(true)
  })

  it('matches message_created where the agent received it (either "to" or "recipient" key)', () => {
    expect(
      eventBelongsToTimeline({ type: 'message_created', data: { to: 'claude' }, timestamp: '' }, 'claude')
    ).toBe(true)
    expect(
      eventBelongsToTimeline({ type: 'message_created', data: { recipient: 'claude' }, timestamp: '' }, 'claude')
    ).toBe(true)
  })

  it('matches log_event and agent_heartbeat via the "agent" key', () => {
    expect(
      eventBelongsToTimeline({ type: 'log_event', data: { agent: 'claude' }, timestamp: '' }, 'claude')
    ).toBe(true)
    expect(
      eventBelongsToTimeline({ type: 'agent_heartbeat', data: { agent: 'claude' }, timestamp: '' }, 'claude')
    ).toBe(true)
  })

  it('does not match a different agent', () => {
    expect(
      eventBelongsToTimeline({ type: 'agent_heartbeat', data: { agent: 'codex' }, timestamp: '' }, 'claude')
    ).toBe(false)
  })

  it('does not match an unrelated event type', () => {
    expect(
      eventBelongsToTimeline({ type: 'task_updated', data: { agent: 'claude' }, timestamp: '' }, 'claude')
    ).toBe(false)
  })
})
