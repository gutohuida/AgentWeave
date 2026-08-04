import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectSettingsPanel } from '@/components/environment/ProjectSettingsPanel'
import { useConfigStore } from '@/store/configStore'

const update = vi.fn()
const relocate = vi.fn()
const project = {
  id: 'proj-a', name: 'Website', working_directory: null, path_display: 'C:/missing/site',
  directory_state: 'missing', last_opened_at: null, last_seen_at: null, hop_budget: 12,
  turn_delivery_cap: 8, agent_budget: 4, token_budget: 10000, allow_agent_jobs: false, agents: [],
}

vi.mock('@/api/projects', () => ({
  useProjects: () => ({ data: [project] }),
  useUpdateProjectSettings: () => ({ mutate: update, isPending: false, error: null }),
  useRelocateProject: () => ({ mutate: relocate, isPending: false, error: null }),
}))

describe('phase 5 project settings and locate repair', () => {
  beforeEach(() => {
    update.mockReset()
    relocate.mockReset()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('edits all validated settings as one resource', () => {
    render(<ProjectSettingsPanel />)
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Storefront' } })
    fireEvent.change(screen.getByLabelText('Hop budget'), { target: { value: '15' } })
    fireEvent.click(screen.getByLabelText('Allow agent jobs'))
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Storefront', hop_budget: 15, turn_delivery_cap: 8, agent_budget: 4,
      token_budget: 10000, allow_agent_jobs: true,
    }))
  })

  it('keeps directory repair as a distinct Locate action', () => {
    render(<ProjectSettingsPanel />)
    expect(screen.getByText('Directory unavailable')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New directory path'), { target: { value: 'D:/restored/site' } })
    fireEvent.click(screen.getByText('Locate project'))
    expect(relocate).toHaveBeenCalledWith({ path: 'D:/restored/site' })
    expect(update).not.toHaveBeenCalled()
  })
})
