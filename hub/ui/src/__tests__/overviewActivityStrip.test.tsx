import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OverviewPage } from '@/components/overview/OverviewPage'
import { useConfigStore } from '@/store/configStore'
import type { SSEEvent } from '@/hooks/useSSE'

// F419: the strip read the instance-wide buffer, so project B's events showed on project A's
// Overview, and its amber dot tested 'warning' where the Hub writes 'warn'.
let buffer: SSEEvent[] = []

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [], isLoading: false }) }))
vi.mock('@/api/questions', () => ({ useQuestions: () => ({ data: [] }) }))
vi.mock('@/api/tasks', () => ({ useTasks: () => ({ data: [] }) }))
vi.mock('@/api/status', () => ({ useStatus: () => ({ data: { project_name: 'AgentWeave' } }) }))
vi.mock('@/hooks/useSSE', () => ({ getBufferedEvents: () => buffer }))
vi.mock('@/components/overview/OverviewBudgetSummary', () => ({ OverviewBudgetSummary: () => null }))
vi.mock('@/components/overview/CollaborationSummary', () => ({ CollaborationSummary: () => null }))
vi.mock('@/components/overview/AgentPostureChips', () => ({ AgentPostureChips: () => null }))

function event(type: string, projectId: string, severity?: string): SSEEvent {
  return { type, data: { project_id: projectId, agent: `agent-of-${projectId}` }, timestamp: new Date().toISOString(), severity }
}

describe('F419 - Overview activity strip', () => {
  beforeEach(() => {
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it("does not show another project's events", () => {
    buffer = [event('task_created', 'proj-b'), event('task_updated', 'proj-a')]
    render(<OverviewPage onNavigate={vi.fn()} />)
    expect(screen.queryByText('agent-of-proj-b')).toBeNull()
    expect(screen.getByText('agent-of-proj-a')).toBeTruthy()
  })

  it('shows no strip when only another project has events', () => {
    buffer = [event('task_created', 'proj-b')]
    render(<OverviewPage onNavigate={vi.fn()} />)
    expect(screen.queryByRole('heading', { name: 'Activity' })).toBeNull()
  })

  it("paints the dot amber for the Hub's 'warn' severity, green otherwise", () => {
    buffer = [event('task_updated', 'proj-a', 'info'), event('run_slow', 'proj-a', 'warn')]
    const { container } = render(<OverviewPage onNavigate={vi.fn()} />)
    const dots = Array.from(container.querySelectorAll('.overview-activity-pill > span:first-child')) as HTMLElement[]
    expect(dots).toHaveLength(2)
    // newest first: the 'warn' event leads
    expect(dots[0].style.background).toBe('var(--amber)')
    expect(dots[1].style.background).toBe('var(--green)')
  })
})
