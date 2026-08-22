import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
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
vi.mock('@/components/accounting/AccountingPanel', () => ({ AccountingPanel: () => null }))

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
})
