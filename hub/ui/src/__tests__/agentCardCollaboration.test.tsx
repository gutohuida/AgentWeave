import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AgentCard } from '@/components/agents/AgentCard'
import type { AgentSummary } from '@/api/agents'

/**
 * The composer's target-agent picker was the only place `collaboration_ready` was ever
 * shown. `2026-08-06-hub-collaboration-and-conversation-fixes` removed that picker, so the
 * indicator moved here — the place an operator looks to understand an agent's configuration
 * rather than a control they only see while composing.
 */
const agent: AgentSummary = {
  name: 'codex-mini-1',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'codex',
  display_model: 'gpt-5.4-mini',
}

describe('AgentCard — collaboration readiness', () => {
  it('flags an agent that will run but cannot call AgentWeave tools', () => {
    render(
      <AgentCard
        agent={agent}
        selected={false}
        onClick={() => undefined}
        launchability={{
          present: true,
          authorized: true,
          runnable: true,
          collaboration_ready: false,
          collaboration_reason: 'opted out of the app-server transport',
        }}
      />,
    )
    const badge = screen.getByText('CANNOT COLLABORATE')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveAttribute('title', 'opted out of the app-server transport')
  })

  it('does not flag a ready agent', () => {
    render(
      <AgentCard
        agent={agent}
        selected={false}
        onClick={() => undefined}
        launchability={{
          present: true,
          authorized: true,
          runnable: true,
          collaboration_ready: true,
          collaboration_reason: null,
        }}
      />,
    )
    expect(screen.queryByText('CANNOT COLLABORATE')).not.toBeInTheDocument()
  })

  it('does not flag an agent whose readiness is unknown', () => {
    // `collaboration_ready` is null for an unbound agent — "not applicable", not "broken".
    render(<AgentCard agent={agent} selected={false} onClick={() => undefined} />)
    expect(screen.queryByText('CANNOT COLLABORATE')).not.toBeInTheDocument()
  })
})
