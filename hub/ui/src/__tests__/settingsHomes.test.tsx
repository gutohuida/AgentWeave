/**
 * leaner-navigation D3: what Activity and the Jobs tab held now lives in Project settings. Logs
 * hosts the raw event stream (FR-5), Jobs the jobs view opened on the job the address names
 * (FR-6, FR-7), Traces the project-wide traces view under its settings with no 'Browse traces'
 * button (FR-14), and Budgets the project's ledger below its limits (FR-15).
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectSettingsScreen } from '@/components/settings/ProjectSettingsScreen'
import { useConfigStore } from '@/store/configStore'

const seen: { jobsFocus?: string | null; tracesFocus?: string | null } = {}

vi.mock('@/components/logs/LogsView', () => ({ LogsView: () => <div data-testid="logs-view" /> }))
vi.mock('@/components/jobs/JobsScreen', () => ({
  JobsScreen: ({ focus }: { focus?: string | null }) => {
    seen.jobsFocus = focus
    return <div data-testid="jobs-view" />
  },
}))
vi.mock('@/components/traces/TracesBrowser', () => ({
  TracesBrowser: ({ focus }: { focus?: string | null }) => {
    seen.tracesFocus = focus
    return <div data-testid="traces-browser" />
  },
}))
vi.mock('@/components/settings/sections/TracesSection', () => ({ TracesSection: () => <div data-testid="traces-settings" /> }))
vi.mock('@/components/settings/sections/BudgetsSection', () => ({ BudgetsSection: () => <div data-testid="budget-limits" /> }))
vi.mock('@/components/activity/ProjectLedger', () => ({
  ProjectLedger: ({ onOpenTask }: { onOpenTask: (id: string) => void }) => (
    <button data-testid="ledger" onClick={() => onOpenTask('task-7')}>ledger</button>
  ),
}))
vi.mock('@/components/overview/ProjectSetupList', () => ({ ProjectSetupList: () => null }))
vi.mock('@/api/projects', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/projects')>()),
  useProjects: () => ({ data: [{ id: 'proj-a', name: 'Website' }] }),
  useProjectSettings: () => ({ data: undefined }),
}))
vi.mock('@/api/traces', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/traces')>()),
  useTraceSettings: () => ({ data: undefined }),
}))
vi.mock('@/api/charters', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/charters')>()),
  useCharters: () => ({ data: [] }),
}))
vi.mock('@/api/manager', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/manager')>()),
  useManagerJobs: () => ({ data: [] }),
}))

beforeEach(() => {
  useConfigStore.setState({ selectedProjectId: 'proj-a' })
  delete seen.jobsFocus
  delete seen.tracesFocus
})
afterEach(cleanup)

describe('Project settings hosts what Activity and Jobs held', () => {
  it('settings-logs: Logs shows the raw event stream', () => {
    render(<ProjectSettingsScreen section="logs" onSelectSection={vi.fn()} />)
    expect(screen.getByTestId('logs-view')).toBeInTheDocument()
  })

  it('lists Jobs and Logs among its sections, and selecting one asks for it', () => {
    const onSelectSection = vi.fn()
    render(<ProjectSettingsScreen section="logs" onSelectSection={onSelectSection} />)
    fireEvent.click(screen.getByRole('button', { name: /^Logs/ }))
    fireEvent.click(screen.getByRole('button', { name: /^Jobs/ }))
    expect(onSelectSection.mock.calls).toEqual([['logs'], ['jobs']])
  })

  it('running-job-link: Jobs opens the job the address names', () => {
    render(<ProjectSettingsScreen section="jobs" focus="job-9" onSelectSection={vi.fn()} />)
    expect(screen.getByTestId('jobs-view')).toBeInTheDocument()
    expect(seen.jobsFocus).toBe('job-9')
  })

  it('settings-traces: Traces holds the traces view under its settings, with no Browse traces button', () => {
    render(<ProjectSettingsScreen section="traces" focus="run-1" onSelectSection={vi.fn()} />)
    const settings = screen.getByTestId('traces-settings')
    const view = screen.getByTestId('traces-browser')
    expect(settings.compareDocumentPosition(view) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(seen.tracesFocus).toBe('run-1')
    expect(screen.queryByTestId('open-traces-view')).toBeNull()
    expect(screen.queryByRole('button', { name: /browse traces/i })).toBeNull()
  })

  it('budgets-ledger: Budgets shows the ledger below the limits, and a ledger row opens its task', () => {
    const onOpenTask = vi.fn()
    render(<ProjectSettingsScreen section="budgets" onSelectSection={vi.fn()} onOpenTask={onOpenTask} />)
    const limits = screen.getByTestId('budget-limits')
    const ledger = screen.getByTestId('ledger')
    expect(limits.compareDocumentPosition(ledger) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    fireEvent.click(ledger)
    expect(onOpenTask).toHaveBeenCalledExactlyOnceWith('task-7')
  })
})
