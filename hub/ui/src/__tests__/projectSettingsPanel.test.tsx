import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectSettingsPanel, describeThreshold } from '@/components/environment/ProjectSettingsPanel'
import { useConfigStore } from '@/store/configStore'

const update = vi.fn()
const relocate = vi.fn()
const deleteProject = vi.fn()
const project = {
  id: 'proj-a', name: 'Website', working_directory: null, path_display: 'C:/missing/site',
  directory_state: 'missing', last_opened_at: null, last_seen_at: null, hop_budget: 12,
  turn_delivery_cap: 8, agent_budget: 4, token_budget: 10000, allow_agent_jobs: false, agents: [],
}

const settings = {
  name: 'Website',
  hop_budget: 12,
  turn_delivery_cap: 8,
  agent_budget: 4,
  token_budget: 10000,
  allow_agent_jobs: false,
  conversation_title_mode: 'generate' as const,
  conversation_title_runner_id: 'runner-titles',
  checkpoint_mode: 'offered' as const,
  checkpoint_threshold_mode: 'tokens' as const,
  checkpoint_threshold_value: 150_000,
  checkpoint_notes_value: 120_000,
  checkpoint_runner_id: 'runner-haiku',
  checkpoint_model: 'claude-haiku-4-5-20251001',
}

let suggestion: { suggestion: string | null; chosen: string | null; is_repository: boolean } = {
  suggestion: 'master',
  chosen: null,
  is_repository: true,
}

vi.mock('@/api/projects', () => ({
  useProjects: () => ({ data: [project] }),
  useProjectSettings: () => ({ data: settings }),
  useMainBranchSuggestion: () => ({ data: suggestion }),
  useUpdateProjectSettings: () => ({ mutate: update, isPending: false, error: null }),
  useRelocateProject: () => ({ mutate: relocate, isPending: false, error: null }),
  useDeleteProject: () => ({
    mutate: deleteProject, isPending: false, error: null, isSuccess: false, reset: vi.fn(),
  }),
}))

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [{ id: 'runner-haiku', name: 'Haiku 4.5', cli: 'claude', model: null }] }),
}))

vi.mock('@/api/modelCatalog', () => ({
  useModelCatalog: () => ({
    data: {
      providers: [{
        provider: 'claude',
        models: [{ id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5', context_window: 200_000 }],
      }],
    },
  }),
}))

describe('phase 5 project settings and locate repair', () => {
  beforeEach(() => {
    update.mockReset()
    relocate.mockReset()
    suggestion = { suggestion: 'master', chosen: null, is_repository: true }
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  /**
   * An unmerged task tells the operator to "choose one in the project's settings". Until this
   * control existed that was a closed loop: told what to do, given no way to do it, and the only
   * way to set the branch was a hand-written PUT.
   */
  it('offers the branch approval merges into, where the integration note sends you', () => {
    render(<ProjectSettingsPanel />)
    fireEvent.change(screen.getByLabelText('Main branch'), { target: { value: 'trunk' } })
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ main_branch: 'trunk' }))
  })

  it('offers the detected branch without choosing it', () => {
    render(<ProjectSettingsPanel />)
    // A suggestion is safe for a report and unsafe for a write, so it is a placeholder and a
    // button — not a value already sitting in the field.
    expect(screen.getByLabelText('Main branch')).toHaveValue('')
    fireEvent.click(screen.getByText('Use “master”'))
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ main_branch: 'master' }))
  })

  it('clears the choice back to nothing merging', () => {
    render(<ProjectSettingsPanel />)
    fireEvent.change(screen.getByLabelText('Main branch'), { target: { value: '   ' } })
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({ main_branch: null }))
  })

  it('does not offer a branch for a project that is not a repository', () => {
    suggestion = { suggestion: null, chosen: null, is_repository: false }
    render(<ProjectSettingsPanel />)
    expect(screen.getByLabelText('Main branch')).toBeDisabled()
    expect(screen.queryByText(/^Use “/)).not.toBeInTheDocument()
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

  it('submits every setting it was given, including ones it does not edit', () => {
    // The defect this replaced: the panel held a six-field `Pick` of `ProjectSummary` and the
    // endpoint replaces what it receives, so renaming a project silently cleared its whole
    // checkpoint configuration — and its title mode with it. Observed live, HTTP 200.
    render(<ProjectSettingsPanel />)
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByText('Save settings'))

    expect(update).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Renamed',
      checkpoint_mode: 'offered',
      checkpoint_threshold_mode: 'tokens',
      checkpoint_threshold_value: 150_000,
      checkpoint_notes_value: 120_000,
      checkpoint_runner_id: 'runner-haiku',
      checkpoint_model: 'claude-haiku-4-5-20251001',
      conversation_title_mode: 'generate',
      conversation_title_runner_id: 'runner-titles',
    }))
  })

  it('collects a token threshold in thousands and stores it canonically', () => {
    render(<ProjectSettingsPanel />)
    // Stored as 150000, shown as 150 — the unit an operator thinks in.
    expect(screen.getByLabelText('Checkpoint threshold')).toHaveValue(150)

    fireEvent.change(screen.getByLabelText('Checkpoint threshold'), { target: { value: '120' } })
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({
      checkpoint_threshold_mode: 'tokens',
      checkpoint_threshold_value: 120_000,
    }))
  })

  it('shows the threshold in both readings when the window is known', () => {
    render(<ProjectSettingsPanel />)
    expect(screen.getByText(/150k — 75% of 200k/)).toBeInTheDocument()
  })

  it('clears the whole threshold when the value is emptied, never half of it', () => {
    // A mode with no value is not a partial setting to be completed from elsewhere — it would
    // read as a number in a unit nobody chose.
    render(<ProjectSettingsPanel />)
    fireEvent.change(screen.getByLabelText('Checkpoint threshold'), { target: { value: '' } })
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({
      checkpoint_threshold_mode: null,
      checkpoint_threshold_value: null,
      checkpoint_notes_value: null,
    }))
  })
})

describe('threshold readings', () => {
  it('matches checkpoint_policy.describe_threshold on the same examples', () => {
    // Restated in TypeScript rather than fetched, so this pins the two against each other.
    expect(describeThreshold('tokens', 150_000, 200_000)).toBe('150k — 75% of 200k')
    expect(describeThreshold('percent', 75, 200_000)).toBe('75% — 150k of 200k')
    expect(describeThreshold('tokens', 150_000, null)).toBe('150k')
    expect(describeThreshold('percent', 80, null)).toBe('80%')
  })
})
