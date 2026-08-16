import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { DeleteProjectDialog } from '@/components/environment/DeleteProjectDialog'

const mutate = vi.fn()
const reset = vi.fn()
let mutationState: { isPending: boolean; error: unknown } = { isPending: false, error: null }

vi.mock('@/api/projects', () => ({
  useDeleteProject: () => ({ mutate, reset, ...mutationState }),
}))

const project = {
  id: 'proj-a', name: 'Website', working_directory: 'C:/work/site', path_display: 'C:/work/site',
  directory_state: 'available', last_opened_at: null, last_seen_at: null, hop_budget: 12,
  turn_delivery_cap: 8, agent_budget: 4, token_budget: 10000, allow_agent_jobs: false, agents: [],
}

describe('DeleteProjectDialog — 5.1 type-to-confirm gating', () => {
  beforeEach(() => {
    mutate.mockReset()
    reset.mockReset()
    mutationState = { isPending: false, error: null }
  })

  it('stays disabled until the typed name matches exactly, then calls the mutation exactly once', () => {
    const onDeleted = vi.fn()
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={onDeleted} />)
    const deleteButton = screen.getByText('Delete project')
    expect(deleteButton).toBeDisabled()

    const input = screen.getByLabelText('Project name to confirm')
    fireEvent.change(input, { target: { value: 'Website' } })
    expect(deleteButton).toBeEnabled()

    fireEvent.click(deleteButton)
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate).toHaveBeenCalledWith(undefined, { onSuccess: onDeleted })
  })

  it('rejects a partial or case-mismatched name — D7 is case-sensitive', () => {
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={vi.fn()} />)
    const deleteButton = screen.getByText('Delete project')
    const input = screen.getByLabelText('Project name to confirm')

    fireEvent.change(input, { target: { value: 'website' } })
    expect(deleteButton).toBeDisabled()

    fireEvent.change(input, { target: { value: 'Web' } })
    expect(deleteButton).toBeDisabled()

    fireEvent.click(deleteButton)
    expect(mutate).not.toHaveBeenCalled()
  })

  it('accepts the name with only leading/trailing whitespace trimmed', () => {
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={vi.fn()} />)
    const deleteButton = screen.getByText('Delete project')
    fireEvent.change(screen.getByLabelText('Project name to confirm'), { target: { value: '  Website  ' } })
    expect(deleteButton).toBeEnabled()
  })
})

describe('DeleteProjectDialog — 5.2 the 409 active-run reason', () => {
  beforeEach(() => {
    mutate.mockReset()
    reset.mockReset()
  })

  it('renders the active-run reason from a 409, not a generic failure message', () => {
    mutationState = {
      isPending: false,
      error: new ApiError(409, JSON.stringify({
        detail: { code: 'project_has_active_run', message: 'project cannot be deleted while a run is active' },
      })),
    }
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('project cannot be deleted while a run is active')
    expect(screen.queryByText('The project could not be deleted.')).not.toBeInTheDocument()
  })

  it('falls back to a generic message for an unstructured error', () => {
    mutationState = { isPending: false, error: new ApiError(500, 'boom') }
    render(<DeleteProjectDialog project={project} onClose={vi.fn()} onDeleted={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
  })
})
