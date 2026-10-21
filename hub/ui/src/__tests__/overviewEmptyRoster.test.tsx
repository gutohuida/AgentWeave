import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OverviewView } from '@/components/overview/OverviewView'

// F808: the empty roster told the operator to run `agentweave start`, a command the CLI refuses.
// Agents are added in the app.
describe('F808 — the Overview with no agents', () => {
  const view = (onAddAgent?: () => void) =>
    render(
      <OverviewView
        needs={[]}
        running={[]}
        finished={[]}
        agents={[]}
        spend={{ usd: 0, tokens: 0, period: 'so far' }}
        onOpenLedger={vi.fn()}
        onAddAgent={onAddAgent}
        now={new Date('2026-10-21T09:00:00Z')}
      />,
    )

  it('names no CLI command and offers Add agent', () => {
    const onAddAgent = vi.fn()
    const { container } = view(onAddAgent)
    expect(container.textContent).not.toContain('agentweave start')
    fireEvent.click(screen.getByRole('button', { name: /add agent/i }))
    expect(onAddAgent).toHaveBeenCalledTimes(1)
  })
})
