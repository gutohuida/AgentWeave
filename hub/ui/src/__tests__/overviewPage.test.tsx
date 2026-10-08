import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OverviewPage } from '@/components/overview/OverviewPage'
import type { AgentSummary } from '@/api/agents'

const agents: AgentSummary[] = [
  { name: 'claude-stalled', status: 'stalled', message_count: 1, active_task_count: 0 },
  { name: 'claude-idle', status: 'idle', message_count: 1, active_task_count: 0 },
  { name: 'claude-running', status: 'running', message_count: 1, active_task_count: 0 },
]

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: agents, isLoading: false }),
}))
vi.mock('@/api/questions', () => ({ useQuestions: () => ({ data: [] }) }))
vi.mock('@/api/tasks', () => ({ useTasks: () => ({ data: [] }) }))
vi.mock('@/api/status', () => ({ useStatus: () => ({ data: { project_name: 'AgentWeave' } }) }))
vi.mock('@/hooks/useSSE', () => ({ getBufferedEvents: () => [] }))
vi.mock('@/components/overview/OverviewBudgetSummary', () => ({ OverviewBudgetSummary: () => null }))
vi.mock('@/components/overview/CollaborationSummary', () => ({
  CollaborationSummary: () => <div data-testid="collab-summary-stub" />,
}))
vi.mock('@/components/overview/AgentPostureChips', () => ({
  AgentPostureChips: ({ agent }: { agent: AgentSummary }) => <div data-testid={`posture-${agent.name}`} />,
}))

describe('Gap 6 — OverviewPage agent health grid', () => {
  it('colors a stalled agent the same amber as waiting, not the same gray as idle', () => {
    const { container } = render(<OverviewPage onNavigate={vi.fn()} />)
    const buttons = Array.from(container.querySelectorAll('button')).filter((b) =>
      agents.some((a) => b.textContent?.includes(a.name))
    )
    const dotFor = (name: string) => {
      const btn = buttons.find((b) => b.textContent?.includes(name))
      return btn?.querySelector('span[style]') as HTMLElement
    }

    const stalledDot = dotFor('claude-stalled')
    const idleDot = dotFor('claude-idle')
    const runningDot = dotFor('claude-running')

    expect(stalledDot.style.background).toBe('var(--amber)')
    expect(idleDot.style.background).toBe('var(--text-3)')
    expect(runningDot.style.background).toBe('var(--green)')
    expect(stalledDot.style.background).not.toBe(idleDot.style.background)
  })

  it('only glows the dot for a pulsing status (running), not stalled', () => {
    const { container } = render(<OverviewPage onNavigate={vi.fn()} />)
    const buttons = Array.from(container.querySelectorAll('button')).filter((b) =>
      agents.some((a) => b.textContent?.includes(a.name))
    )
    const dotFor = (name: string) => {
      const btn = buttons.find((b) => b.textContent?.includes(name))
      return btn?.querySelector('span[style]') as HTMLElement
    }

    expect(dotFor('claude-running').style.boxShadow).toContain('var(--green)')
    expect(dotFor('claude-stalled').style.boxShadow).toBe('')
  })

  it('gives each agent card a status-bearing accessible name', () => {
    render(<OverviewPage onNavigate={vi.fn()} />)
    expect(document.querySelector('button[aria-label="Open claude-stalled, Stalled"]')).not.toBeNull()
    expect(document.querySelector('button[aria-label="Open claude-running, Running"]')).not.toBeNull()
  })

  // the-settings-that-gate-collaboration-are-on-the-project-page FR-1, FR-4.
  it('mounts the Collaboration block above Attention', () => {
    render(<OverviewPage onNavigate={vi.fn()} />)
    const block = screen.getByTestId('collab-summary-stub')
    const attention = screen.getByRole('heading', { name: 'Attention' })
    expect(block.compareDocumentPosition(attention) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("puts each agent's posture on its card, outside the button that opens the agent", () => {
    const onNavigate = vi.fn()
    render(<OverviewPage onNavigate={onNavigate} />)
    const posture = screen.getByTestId('posture-claude-idle')
    expect(posture.closest('button')).toBeNull()
    expect(posture.closest('[data-testid="agent-card-claude-idle"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Open claude-idle, Idle' }))
    expect(onNavigate).toHaveBeenCalledWith('agent:claude-idle')
  })
})
