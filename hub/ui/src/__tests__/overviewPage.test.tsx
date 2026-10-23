import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OverviewScreen } from '@/components/overview/OverviewScreen'
import type { AgentSummary } from '@/api/agents'
// @ts-expect-error Vitest runs in Node; the browser bundle never includes this test.
import { readFileSync } from 'node:fs'

/** The Overview's agent list (formerly the agent health grid; re-targeted to the wired
 *  `OverviewScreen` in ui-finesse). Identity colour is on the dot, state is on the row's words. */

const agents: AgentSummary[] = [
  { name: 'claude-stalled', status: 'stalled', message_count: 1, active_task_count: 0, runner_id: 'r1' },
  { name: 'claude-idle', status: 'idle', message_count: 1, active_task_count: 0, runner_id: 'r1' },
  { name: 'claude-running', status: 'running', message_count: 1, active_task_count: 0, runner_id: 'r1' },
]

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: agents, isLoading: false }),
}))
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutate: vi.fn() }),
}))
vi.mock('@/api/tasks', () => ({ useTasks: () => ({ data: { tasks: [], total: 0, has_more: false } }) }))
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: { conversations: [] } }) }
})
vi.mock('@/api/ledger', () => ({ useProjectLedger: () => ({ data: undefined }) }))
vi.mock('@/api/queue', () => ({ useQueueStatuses: () => [] }))
vi.mock('@/api/stalls', () => ({ useOpenStalls: () => ({ data: [] }), useEndStall: () => ({ mutate: vi.fn() }) }))
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: undefined }) }))
vi.mock('@/components/overview/AgentPostureChips', () => ({
  AgentPostureChips: ({ agent }: { agent: AgentSummary }) => <div data-testid={`posture-${agent.name}`} />,
}))

const rowFor = (name: string) => screen.getByTestId(`agent-card-${name}`).querySelector('[data-slot="agent-row"]') as HTMLElement

const overviewCss = readFileSync('src/styles/overview.css', 'utf8')

/** The colour `.aw-ov-row-detail[data-state="<state>"]` declares in the stylesheet. */
function stateColour(state: string): string | null {
  const match = new RegExp(`\\.aw-ov-row-detail\\[data-state="${state}"\\]\\s*\\{[^}]*color:\\s*([^;]+);`).exec(overviewCss)
  return match ? match[1].trim() : null
}

describe('Gap 6 — the Overview agent list', () => {
  it('colors a stalled agent the same amber as waiting, not the same gray as idle', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(rowFor('claude-stalled').dataset.state).toBe('stalled')
    expect(rowFor('claude-idle').dataset.state).toBe('idle')
    expect(rowFor('claude-running').dataset.state).toBe('running')
    expect(stateColour('stalled')).toBe('var(--amber)')
    expect(stateColour('stalled')).toBe(stateColour('waiting'))
    expect(stateColour('idle')).not.toBe('var(--amber)')
  })

  it('only pulses the dot for a running agent, not a stalled one', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(rowFor('claude-running').querySelector('.aw-agent-dot')!.classList.contains('aw-pulse')).toBe(true)
    expect(rowFor('claude-stalled').querySelector('.aw-agent-dot')!.classList.contains('aw-pulse')).toBe(false)
  })

  it('gives each agent row a status-bearing accessible name', () => {
    render(<OverviewScreen onNavigate={vi.fn()} />)
    expect(document.querySelector('button[aria-label="Open claude-stalled, Stalled"]')).not.toBeNull()
    expect(document.querySelector('button[aria-label="Open claude-running, Running"]')).not.toBeNull()
  })

  // the-settings-that-gate-collaboration-are-on-the-project-page FR-1, FR-4.
  it('reaches questions and permission decisions with no question open (F636)', () => {
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('overview-questions-link'))
    expect(onNavigate).toHaveBeenCalledWith('questions')
  })

  it("puts each agent's posture beside its row, outside the button that opens the agent", () => {
    const onNavigate = vi.fn()
    render(<OverviewScreen onNavigate={onNavigate} />)
    const posture = screen.getByTestId('posture-claude-idle')
    expect(posture.closest('button')).toBeNull()
    expect(posture.closest('[data-testid="agent-card-claude-idle"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Open claude-idle, Idle' }))
    expect(onNavigate).toHaveBeenCalledWith('agent:claude-idle')
  })
})
