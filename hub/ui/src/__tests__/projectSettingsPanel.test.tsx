import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectSettingsPanel } from '@/components/environment/ProjectSettingsPanel'
import { describeThreshold } from '@/components/environment/describeThreshold'
import { useConfigStore } from '@/store/configStore'
import type { AgentSummary } from '@/api/agents'

const update = vi.fn()
const relocate = vi.fn()
const deleteProject = vi.fn()
const project = {
  id: 'proj-a', name: 'Website', working_directory: null, path_display: 'C:/missing/site',
  directory_state: 'missing', last_opened_at: null, last_seen_at: null, hop_budget: 12,
  turn_delivery_cap: 8, agent_budget: 4, token_budget: 10000, allow_agent_jobs: false, agents: [],
}

function makeSettings(): {
  name: string
  hop_budget: number
  turn_delivery_cap: number
  agent_budget: number
  token_budget: number
  allow_agent_jobs: boolean
  conversation_title_mode: 'truncate' | 'generate'
  conversation_title_runner_id: string | null
  checkpoint_mode: 'off' | 'offered' | 'automatic'
  checkpoint_threshold_mode: 'percent' | 'tokens'
  checkpoint_threshold_value: number
  checkpoint_notes_value: number
  checkpoint_runner_id: string | null
  checkpoint_model: string | null
} {
  return {
    name: 'Website',
    hop_budget: 12,
    turn_delivery_cap: 8,
    agent_budget: 4,
    token_budget: 10000,
    allow_agent_jobs: false,
    conversation_title_mode: 'generate',
    conversation_title_runner_id: 'runner-titles',
    checkpoint_mode: 'offered',
    checkpoint_threshold_mode: 'tokens',
    checkpoint_threshold_value: 150_000,
    checkpoint_notes_value: 120_000,
    checkpoint_runner_id: 'runner-haiku',
    checkpoint_model: 'claude-haiku-4-5-20251001',
  }
}

let settings = makeSettings()

let suggestion: { suggestion: string | null; chosen: string | null; is_repository: boolean } = {
  suggestion: 'master',
  chosen: null,
  is_repository: true,
}

/** `checkpoint_compaction_percent` lands at task 3.4 (design D10) -- not yet a field on
 *  `AgentSummary`. The panel does not call `useAgents` yet either (that call is this task's own
 *  work, D10 "Project settings"); the mock is in place ahead of it so 1.18(b)'s fixtures exist
 *  once it does. */
type AgentWithCompaction = AgentSummary & { checkpoint_compaction_percent?: number | null }
let projectAgents: AgentWithCompaction[] = []

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: projectAgents, isLoading: false }),
}))

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
  useRunners: () => ({
    data: [
      { id: 'runner-haiku', name: 'Haiku 4.5', cli: 'claude', model: null },
      { id: 'runner-titles', name: 'Titler', cli: 'claude', model: 'claude-opus-5' },
    ],
  }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({
    data: {
      providers: [{
        provider: 'claude',
        models: [
          { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5', aliases: ['haiku'], context_window: 200_000 },
          { id: 'claude-opus-5', label: 'Opus 5', aliases: ['opus'], context_window: 1_000_000 },
        ],
      }],
    },
  }),
}))

describe('phase 5 project settings and locate repair', () => {
  beforeEach(() => {
    update.mockReset()
    relocate.mockReset()
    suggestion = { suggestion: 'master', chosen: null, is_repository: true }
    settings = makeSettings()
    projectAgents = []
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

  it('reflects the stored conversation title mode', () => {
    render(<ProjectSettingsPanel />)
    expect(screen.getByLabelText('Conversation titles')).toHaveValue('generate')
  })

  it('changes the conversation title mode and saves it', () => {
    settings.conversation_title_mode = 'truncate'
    render(<ProjectSettingsPanel />)
    fireEvent.change(screen.getByLabelText('Conversation titles'), { target: { value: 'generate' } })
    fireEvent.click(screen.getByText('Save settings'))
    expect(update).toHaveBeenCalledWith(expect.objectContaining({
      conversation_title_mode: 'generate',
    }))
  })

  it('names each runner by its own model in the title-runner select (F268)', () => {
    render(<ProjectSettingsPanel />)
    const select = screen.getByLabelText('Conversation title runner')
    expect(within(select).getByRole('option', { name: 'Haiku 4.5 — Provider default (claude)' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'Titler — Opus 5 (claude)' })).toBeInTheDocument()
  })

  it("names the project's checkpoint model in the checkpoint-runner select, whatever each runner records (F268)", () => {
    render(<ProjectSettingsPanel />)
    const select = screen.getByLabelText('Checkpoint runner')
    expect(within(select).getByRole('option', { name: 'Haiku 4.5 — Haiku 4.5 (claude)' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'Titler — Haiku 4.5 (claude)' })).toBeInTheDocument()
  })

  it('names each runner by its own model in the checkpoint-runner select once checkpoint_model is cleared (F268)', () => {
    settings.checkpoint_model = null
    render(<ProjectSettingsPanel />)
    const select = screen.getByLabelText('Checkpoint runner')
    expect(within(select).getByRole('option', { name: 'Haiku 4.5 — Provider default (claude)' })).toBeInTheDocument()
    expect(within(select).getByRole('option', { name: 'Titler — Opus 5 (claude)' })).toBeInTheDocument()
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

/**
 * Task 1.18(b), design D10 ("Project settings"): a project percent threshold shown lowered for
 * any bound agent whose runner compacts below 95, naming that agent. The panel does not read
 * `useAgents` or compute this line yet, so every assertion here is expected to fail today --
 * confirming the gap -- through `queryByText`, not a crash.
 */
describe('project-level checkpoint-ceiling notice (task 1.18(b), design D10)', () => {
  beforeEach(() => {
    settings = makeSettings()
    settings.checkpoint_threshold_mode = 'percent'
    settings.checkpoint_threshold_value = 80
  })

  it('names an agent whose runner compacts below the configured threshold', () => {
    projectAgents = [
      { name: 'cop-1', status: 'idle', message_count: 0, active_task_count: 0, runner: 'copilot', checkpoint_compaction_percent: 80 },
    ]
    render(<ProjectSettingsPanel />)
    expect(screen.queryByText(/Lowered to 77%/)).toBeInTheDocument()
    expect(screen.queryByText(/cop-1/)).toBeInTheDocument()
  })

  it('shows nothing when every bound agent compacts at the C=95 default', () => {
    projectAgents = [
      { name: 'claude-1', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude', checkpoint_compaction_percent: 95 },
    ]
    render(<ProjectSettingsPanel />)
    expect(screen.queryByText(/Lowered to/)).not.toBeInTheDocument()
  })
})
