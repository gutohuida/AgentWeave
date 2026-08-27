import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DiagnosticsPanel } from '@/components/environment/DiagnosticsPanel'
import { SettingsSection } from '@/components/environment/SettingsSection'
import { WorktreesPanel } from '@/components/environment/WorktreesPanel'

const writeText = vi.fn()

// The shape a disabled query has: no project is selected in this presentation-only test, so the
// hook never runs and there is no answer yet. Mocked rather than wrapped in a QueryClientProvider,
// matching how this file already stands in for `@/api/status`.
vi.mock('@/api/workspace', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/workspace')>()
  return { ...actual, useWorktrees: () => ({ data: undefined, isLoading: false, error: null }) }
})

vi.mock('@/api/status', () => ({
  useStatus: () => ({
    data: { status: 'ok', project_name: 'Website', agents: 3 },
    isLoading: false,
  }),
}))

describe('configuration surface presentation', () => {
  beforeEach(() => {
    writeText.mockReset()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
  })

  it('keeps every configuration page in one labelled project hierarchy', () => {
    render(
      <SettingsSection title="Settings" description="Project controls">
        <div>Rows</div>
      </SettingsSection>,
    )

    expect(screen.getByRole('region', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByText('Project configuration')).toBeInTheDocument()
    expect(screen.getByText('Project controls')).toBeInTheDocument()
  })

  it('makes raw diagnostics keyboard-readable and directly copyable', async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    render(<DiagnosticsPanel />)

    const rawStatus = screen.getByText(/"project_name": "Website"/)
    expect(rawStatus.tagName).toBe('PRE')
    expect(rawStatus).toHaveAttribute('tabindex', '0')

    await user.click(screen.getByRole('button', { name: 'Copy status' }))
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"agents": 3'))
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('says nothing about worktree activity until it has been told (task 6.4b)', () => {
    // This panel used to be a stub that rendered "No worktree activity" unconditionally — the
    // same answer for a project with a dozen checkouts as for one with none. It reads
    // `GET /worktrees` now, so with no project selected the query never runs and the honest
    // answer is "not yet", not an empty project and not a failure.
    render(<WorktreesPanel />)
    expect(screen.getByLabelText('Loading worktrees')).toBeInTheDocument()
    expect(screen.queryByText('No worktree activity')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
