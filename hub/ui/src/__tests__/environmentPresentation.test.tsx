import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DiagnosticsPanel } from '@/components/environment/DiagnosticsPanel'
import { SettingsSection } from '@/components/environment/SettingsSection'
import { WorktreesPanel } from '@/components/environment/WorktreesPanel'

const writeText = vi.fn()

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

  it('states the reachable worktree surface honestly when there is no activity API data', () => {
    render(<WorktreesPanel />)
    expect(screen.getByText('No worktree activity')).toBeInTheDocument()
    expect(screen.getByText(/appear here when an agent starts work/)).toBeInTheDocument()
  })
})
