import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SettingsSection } from '@/components/environment/SettingsSection'
import { ProjectSettingsScreen } from '@/components/settings/ProjectSettingsScreen'
import { DiagnosticsSection } from '@/components/settings/sections/DiagnosticsSection'
import { WorktreesSection } from '@/components/settings/sections/WorktreesSection'
import { useToastStore } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'

const writeText = vi.fn()

// The shape a disabled query has: no project is selected in this presentation-only test, so the
// hook never runs and there is no answer yet.
vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return {
    ...actual,
    useWorktrees: () => ({ data: undefined, isLoading: false, error: null }),
    useWorktreeConflicts: () => ({ data: undefined, error: null }),
  }
})

let statusError: Error | null = null
vi.mock('@/api/status', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/status')>()),
  useStatus: () =>
    statusError
      ? { data: undefined, isLoading: false, error: statusError, refetch: vi.fn() }
      : { data: { status: 'ok', project_name: 'Website', agents: 3 }, isLoading: false, error: null, refetch: vi.fn() },
}))

vi.mock('@/api/projects', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/projects')>()),
  useProjects: () => ({ data: [{ id: 'proj-a', name: 'Website' }] }),
}))
vi.mock('@/api/runners', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/runners')>()),
  useRunners: () => ({ data: [{ id: 'r1' }, { id: 'r2' }] }),
}))
vi.mock('@/api/charters', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/charters')>()),
  useCharters: () => ({ data: [{ id: 'c1' }] }),
}))
vi.mock('@/api/manager', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/manager')>()),
  useManagerJobs: () => ({ data: [{ key: 'a', enabled: true }, { key: 'b', enabled: false }] }),
}))

describe('configuration surface presentation', () => {
  beforeEach(() => {
    writeText.mockReset()
    useToastStore.setState({ items: [] })
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
  })

  it('keeps every configuration page in one labelled project hierarchy, under one name', async () => {
    const user = userEvent.setup()
    const onSelectSection = vi.fn()
    render(<ProjectSettingsScreen section="worktrees" onSelectSection={onSelectSection} />)

    const nav = screen.getByRole('navigation', { name: 'Project settings' })
    expect(within(nav).getByText('Website')).toBeInTheDocument()
    expect(within(nav).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'General', 'Manager1 on', 'Runners2', 'Charters1', 'Instructions', 'Budgets', 'Quality', 'Worktrees', 'Diagnostics',
    ])
    expect(within(nav).getByRole('button', { name: /Worktrees/ })).toHaveAttribute('aria-current', 'page')
    // The words the old rail used for the same place are gone.
    expect(screen.queryByText('Configuration')).toBeNull()
    expect(screen.queryByText('Environment')).toBeNull()
    expect(screen.queryByText('Project configuration')).toBeNull()

    await user.click(within(nav).getByRole('button', { name: /Runners/ }))
    expect(onSelectSection).toHaveBeenCalledWith('runners')
  })

  it('frames an unconverted section as a labelled page, without the old eyebrow', () => {
    render(
      <SettingsSection title="Settings" description="Project controls">
        <div>Rows</div>
      </SettingsSection>,
    )

    expect(screen.getByRole('region', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.queryByText('Project configuration')).toBeNull()
    expect(screen.getByText('Project controls')).toBeInTheDocument()
  })

  it('says the status could not be read, rather than waiting on a skeleton or printing {}', () => {
    statusError = new Error('500')
    try {
      render(<DiagnosticsSection />)
      expect(screen.queryByLabelText('Loading diagnostics')).toBeNull()
      expect(screen.getByRole('alert')).toHaveTextContent("The Hub's status could not be read.")
    } finally {
      statusError = null
    }
  })

  it('makes raw diagnostics keyboard-readable and directly copyable', async () => {
    const user = userEvent.setup()
    // After `setup()`, which installs a clipboard of its own.
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    render(<DiagnosticsSection />)

    const rawStatus = screen.getByText(/"project_name": "Website"/)
    expect(rawStatus.tagName).toBe('PRE')
    expect(rawStatus).toHaveAttribute('tabindex', '0')

    await user.click(screen.getByRole('button', { name: 'Copy status' }))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"agents": 3'))
    expect(useToastStore.getState().items.map((item) => item.title)).toContain('Status copied')
  })

  it('says nothing about worktree activity until it has been told (task 6.4b)', () => {
    // This panel used to be a stub that rendered "No worktree activity" unconditionally. It reads
    // `GET /worktrees` now, so with no answer yet the honest one is "not yet", not an empty
    // project and not a failure.
    render(<WorktreesSection />)
    expect(screen.getByLabelText('Loading worktrees')).toBeInTheDocument()
    expect(screen.queryByText('No checkouts right now')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
