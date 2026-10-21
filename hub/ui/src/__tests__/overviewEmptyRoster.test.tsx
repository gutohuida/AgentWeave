import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OverviewPage } from '@/components/overview/OverviewPage'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [], isLoading: false }),
}))
vi.mock('@/api/questions', () => ({ useQuestions: () => ({ data: [] }) }))
vi.mock('@/api/tasks', () => ({ useTasks: () => ({ data: [] }) }))
vi.mock('@/api/status', () => ({ useStatus: () => ({ data: { project_name: 'AgentWeave' } }) }))
vi.mock('@/hooks/useSSE', () => ({ getBufferedEvents: () => [] }))
vi.mock('@/components/overview/OverviewBudgetSummary', () => ({ OverviewBudgetSummary: () => null }))
vi.mock('@/components/overview/CollaborationSummary', () => ({ CollaborationSummary: () => null }))

// F808: the empty roster told the operator to run `agentweave start`, a command the CLI refuses.
// Agents are added in the app.
describe('F808 — OverviewPage with no agents', () => {
  it('names no CLI command and offers Add agent', () => {
    const onAddAgent = vi.fn()
    const { container } = render(<OverviewPage onNavigate={vi.fn()} onAddAgent={onAddAgent} />)
    expect(container.textContent).not.toContain('agentweave start')
    fireEvent.click(screen.getByRole('button', { name: /add agent/i }))
    expect(onAddAgent).toHaveBeenCalledTimes(1)
  })
})
