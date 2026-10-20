import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { EventLogEntry } from '@/api/logs'
import { ActivityScreen } from '@/components/activity/ActivityScreen'

/** The wired Activity tab: Ledger leads (F718), the digest reads the project's own log, Logs stays
 *  reachable, and the palette's "logs" opens Logs even while the tab is mounted. */

let entries: EventLogEntry[] = []
const logsOpts: unknown[] = []
let tasksError: Error | null = null

vi.mock('@/api/logs', () => ({
  useLogs: (opts: unknown) => {
    logsOpts.push(opts)
    return { data: entries, isLoading: false, error: null, hasOlder: false, loadOlder: vi.fn(), isLoadingOlder: false }
  },
}))
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: { recent_turns: [] } }) }))
vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [{ name: 'builder', color_index: 1 }] }) }))
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: { conversations: [] } }) }
})
vi.mock('@/api/tasks', () => ({
  useTasks: () => (tasksError ? { data: undefined, error: tasksError } : { data: { tasks: [{ id: 'task-1', title: 'Fix the parser' }] } }),
}))
vi.mock('@/components/activity/ProjectLedger', () => ({ ProjectLedger: () => <div data-testid="ledger-stub" /> }))
vi.mock('@/components/logs/LogsView', () => ({ LogsView: () => <div data-testid="logs-stub" /> }))

function entry(id: string, event_type: string, data: Record<string, unknown>, timestamp = '2026-10-20T10:00:00Z'): EventLogEntry {
  return { id, project_id: 'proj-1', event_type, agent: 'builder', data, severity: 'info', timestamp }
}

describe('the Activity tab', () => {
  it('opens on the Ledger', () => {
    render(<ActivityScreen onOpenTask={vi.fn()} />)
    expect(screen.getByTestId('ledger-stub')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Ledger' })).toHaveAttribute('aria-checked', 'true')
  })

  it('shows the digest of the live project log under Activity', () => {
    entries = [entry('e1', 'task_updated', { task_id: 'task-1', status: 'approved', agent: 'builder' })]
    render(<ActivityScreen onOpenTask={vi.fn()} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Activity' }))
    expect(screen.queryByTestId('ledger-stub')).toBeNull()
    expect(screen.getByText(/The last 1 events/)).toBeInTheDocument()
    // The digest refreshes as events arrive.
    expect(logsOpts[logsOpts.length - 1]).toMatchObject({ live: true })
  })

  it('keeps Logs reachable, and opens on it when asked', () => {
    const { rerender } = render(<ActivityScreen onOpenTask={vi.fn()} />)
    fireEvent.click(screen.getByRole('radio', { name: 'Logs' }))
    expect(screen.getByTestId('logs-stub')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: 'Ledger' }))
    rerender(<ActivityScreen onOpenTask={vi.fn()} initialView="logs" />)
    expect(screen.getByTestId('logs-stub')).toBeInTheDocument()
  })

  it('says which lookups the Hub did not answer, so unnamed sentences are explained', () => {
    tasksError = new Error('500')
    try {
      render(<ActivityScreen onOpenTask={vi.fn()} initialView="activity" />)
      expect(screen.getByTestId('query-error-notice')).toHaveTextContent('Couldn’t read the tasks from the Hub')
    } finally {
      tasksError = null
    }
  })
})
