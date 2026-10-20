import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GeneralSection } from '@/components/settings/sections/GeneralSection'
import { describeThreshold } from '@/components/environment/describeThreshold'
import { useConfigStore } from '@/store/configStore'
import type { AgentSummary } from '@/api/agents'
import { ApiError } from '@/api/client'
import { chooseMenuOption, menuSelect, openMenuSelect } from './support/menuSelect'

/** Each change is its own save: `update` receives the patch alone, and the options that let the
 *  section answer it. Tests that need an answer call `answer(...)` on the last call. */
const update = vi.fn()
function lastPatch(): Record<string, unknown> {
  return update.mock.calls[update.mock.calls.length - 1][0]
}
function answer(result: { warnings?: string[] } | { error: unknown }) {
  const options = update.mock.calls[update.mock.calls.length - 1][1]
  if ('error' in result) options.onError(result.error)
  else options.onSuccess({ ...settings, ...lastPatch(), warnings: result.warnings })
  options.onSettled?.()
}
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
  checkpoint_auto_continue: boolean
  main_branch: string | null
  checks: Array<{ name: string; command: string; timeout_seconds: number }> | null
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
    checkpoint_auto_continue: false,
    main_branch: null,
    checks: null,
  }
}

let settings = makeSettings()
let settingsError: Error | null = null
const refetchSettings = vi.fn()

let suggestion: { suggestion: string | null; chosen: string | null; is_repository: boolean } = {
  suggestion: 'master',
  chosen: null,
  is_repository: true,
}

type AgentWithCompaction = AgentSummary & { checkpoint_compaction_percent?: number | null }
let projectAgents: AgentWithCompaction[] = []
let projectAgentsFailed = false
let projectsError: Error | null = null
let runnersError: Error | null = null

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: projectAgents, isLoading: false, isError: projectAgentsFailed }),
}))

vi.mock('@/api/projects', () => ({
  useProjects: () => (projectsError ? { data: undefined, error: projectsError, refetch: vi.fn() } : { data: [project], error: null, refetch: vi.fn() }),
  useProjectSettings: () => ({
    data: settingsError ? undefined : settings, error: settingsError, isError: settingsError !== null, refetch: refetchSettings,
  }),
  useMainBranchSuggestion: () => ({ data: suggestion }),
  useUpdateProjectSettings: () => ({ mutate: update, isPending: false, error: null }),
  useRelocateProject: () => ({ mutate: relocate, isPending: false, error: null, isError: false }),
  useDeleteProject: () => ({
    mutate: deleteProject, isPending: false, error: null, isSuccess: false, reset: vi.fn(),
  }),
}))

vi.mock('@/api/runners', () => ({
  useRunners: () => runnersError ? { data: undefined, error: runnersError } : ({
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

/** Types into a committed field and leaves it, which is what saves it. */
function commit(label: string, value: string) {
  const field = screen.getByLabelText(label)
  fireEvent.change(field, { target: { value } })
  fireEvent.blur(field)
}

describe('Project settings → General, applied on change', () => {
  beforeEach(() => {
    update.mockReset()
    relocate.mockReset()
    suggestion = { suggestion: 'master', chosen: null, is_repository: true }
    settings = makeSettings()
    settingsError = null
    refetchSettings.mockReset()
    projectAgents = []
    projectAgentsFailed = false
    projectsError = null
    runnersError = null
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('says the project could not be read, rather than waiting on a skeleton for it', () => {
    projectsError = new Error('500')
    render(<GeneralSection />)
    expect(screen.queryByLabelText('Loading project settings')).toBeNull()
    expect(screen.getByRole('alert')).toHaveTextContent("This project's settings could not be loaded.")
  })

  it('warns that the checkpoint runner menu is incomplete when the runners cannot be read', () => {
    runnersError = new Error('500')
    render(<GeneralSection />)
    expect(screen.getByTestId('settings-runners-error')).toHaveTextContent("This project's runners could not be read.")
  })

  it('says the agent-jobs switch covers jobs, flows and loops, as the refusal does (F639)', () => {
    render(<GeneralSection />)
    expect(screen.getByRole('switch', { name: 'Agents may start jobs, flows and loops' })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText(/asking to start a job, flow or loop is refused/)).toBeInTheDocument()
  })

  it('offers the branch approval merges into, where the integration note sends you', () => {
    render(<GeneralSection />)
    commit('Main branch', 'trunk')
    expect(update).toHaveBeenCalledTimes(1)
    expect(lastPatch()).toEqual({ main_branch: 'trunk' })
  })

  it('adds a check, and saves none as null when the last is removed', async () => {
    const user = userEvent.setup()
    const { unmount } = render(<GeneralSection />)
    await user.click(screen.getByRole('button', { name: /Add check/ }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Name'), 'tests')
    await user.type(within(dialog).getByLabelText('Command'), 'pytest -q')
    await user.click(within(dialog).getByRole('button', { name: 'Add check' }))
    expect(lastPatch()).toEqual({ checks: [{ name: 'tests', command: 'pytest -q', timeout_seconds: 900 }] })
    unmount()

    settings = { ...makeSettings(), checks: [{ name: 'tests', command: 'pytest -q', timeout_seconds: 900 }] }
    update.mockReset()
    render(<GeneralSection />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove tests' }))
    expect(lastPatch()).toEqual({ checks: null })
  })

  it('shows the saved checks in order and reorders them', () => {
    settings = {
      ...makeSettings(),
      checks: [
        { name: 'lint', command: 'ruff check .', timeout_seconds: 120 },
        { name: 'tests', command: 'pytest -q', timeout_seconds: 900 },
      ],
    }
    render(<GeneralSection />)
    expect(screen.getByTestId('project-check-0')).toHaveTextContent('lint')
    expect(screen.getByTestId('project-check-1')).toHaveTextContent('tests')
    expect(screen.getByRole('button', { name: 'Move lint up' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Move tests up' }))
    expect((lastPatch().checks as Array<{ name: string }>).map((check) => check.name)).toEqual(['tests', 'lint'])
  })

  it('edits a saved check in place', async () => {
    const user = userEvent.setup()
    settings = { ...makeSettings(), checks: [{ name: 'lint', command: 'ruff check .', timeout_seconds: 120 }] }
    render(<GeneralSection />)
    await user.click(screen.getByRole('button', { name: 'Edit lint' }))
    const dialog = await screen.findByRole('dialog')
    const command = within(dialog).getByLabelText('Command')
    expect(command).toHaveValue('ruff check .')
    await user.clear(command)
    await user.type(command, 'ruff check src')
    await user.click(within(dialog).getByRole('button', { name: 'Save check' }))
    expect(lastPatch()).toEqual({ checks: [{ name: 'lint', command: 'ruff check src', timeout_seconds: 120 }] })
  })

  it('offers the detected branch without choosing it', () => {
    render(<GeneralSection />)
    // A suggestion is safe for a report and unsafe for a write, so it is a placeholder and a
    // button — not a value already sitting in the field.
    expect(screen.getByLabelText('Main branch')).toHaveValue('')
    expect(screen.getByLabelText('Main branch')).toHaveAttribute('placeholder', 'master')
    expect(update).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Use “master”'))
    expect(lastPatch()).toEqual({ main_branch: 'master' })
  })

  it('clears the choice back to nothing merging', () => {
    settings = { ...makeSettings(), main_branch: 'main' }
    render(<GeneralSection />)
    commit('Main branch', '   ')
    expect(lastPatch()).toEqual({ main_branch: null })
  })

  it('does not offer a branch for a project that is not a repository', () => {
    suggestion = { suggestion: null, chosen: null, is_repository: false }
    render(<GeneralSection />)
    expect(screen.getByLabelText('Main branch')).toBeDisabled()
    expect(screen.queryByText(/^Use “/)).not.toBeInTheDocument()
    expect(screen.getByText(/not a git repository/)).toBeInTheDocument()
  })

  it('saves each setting on its own, sending only what changed', () => {
    render(<GeneralSection />)
    commit('Name', 'Storefront')
    expect(lastPatch()).toEqual({ name: 'Storefront' })
    commit('Hop budget', '15')
    expect(lastPatch()).toEqual({ hop_budget: 15 })
    fireEvent.click(screen.getByRole('switch', { name: 'Agents may start jobs, flows and loops' }))
    expect(lastPatch()).toEqual({ allow_agent_jobs: true })
    expect(update).toHaveBeenCalledTimes(3)
  })

  it('refuses a value outside its range on the field, and never sends it', () => {
    render(<GeneralSection />)
    commit('Hop budget', '0')
    expect(screen.getByLabelText('Hop budget')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('At least 1.')
    expect(update).not.toHaveBeenCalled()
  })

  it('saves once when Enter commits and the field then loses focus', () => {
    render(<GeneralSection />)
    const field = screen.getByLabelText('Hop budget')
    fireEvent.change(field, { target: { value: '20' } })
    fireEvent.keyDown(field, { key: 'Enter' })
    fireEvent.blur(field)
    expect(update).toHaveBeenCalledTimes(1)
  })

  it('groups its rows under headings, Collaboration first and Project last', () => {
    render(<GeneralSection />)
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Collaboration', 'Reach', 'Integration', 'Checkpointing', 'Project', 'Delete project',
    ])
  })

  it('leaves the token limit to Budgets: no field here, and a way there', () => {
    const onNavigate = vi.fn()
    render(<GeneralSection onNavigate={onNavigate} />)
    expect(screen.queryByLabelText(/token budget/i)).toBeNull()
    commit('Hop budget', '9')
    expect(lastPatch()).toEqual({ hop_budget: 9 })
    fireEvent.click(screen.getByRole('button', { name: 'Open Budgets' }))
    expect(onNavigate).toHaveBeenCalledWith('budgets')
  })

  it('says agent budget caps agents an agent asks for, not agents running at once', () => {
    render(<GeneralSection />)
    const row = screen.getByLabelText('Agent budget').closest('.aw-settings-row') as HTMLElement
    expect(row.textContent).toMatch(/an agent asking for another is refused/i)
    expect(row.textContent).toMatch(/Adding one yourself is never limited/)
    expect(row.textContent).not.toMatch(/at the same time/i)
  })

  it('keeps directory repair as a distinct Locate action', () => {
    render(<GeneralSection />)
    expect(screen.getByText('Missing')).toBeInTheDocument()
    expect(screen.getByText('C:/missing/site')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New directory path'), { target: { value: 'D:/restored/site' } })
    fireEvent.click(screen.getByText('Locate project'))
    expect(relocate).toHaveBeenCalledWith({ path: 'D:/restored/site' }, expect.anything())
    expect(update).not.toHaveBeenCalled()
  })

  it('opens the type-to-confirm dialog to delete the project', () => {
    render(<GeneralSection />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete project…' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deleteProject).not.toHaveBeenCalled()
  })

  it('never sends a field it was not asked to change (the title fields stay with Manager)', () => {
    // The defect a whole-form save kept re-creating: a copy loaded earlier writing back over a
    // change made in another section since. A patch cannot carry what it did not change.
    render(<GeneralSection />)
    commit('Name', 'Renamed')
    const sent = lastPatch()
    expect(sent).toEqual({ name: 'Renamed' })
    expect(sent).not.toHaveProperty('conversation_title_mode')
    expect(sent).not.toHaveProperty('token_budget')
  })

  it('collects a token threshold in thousands and stores it canonically', () => {
    render(<GeneralSection />)
    // Stored as 150000, shown as 150 — the unit an operator thinks in.
    expect(screen.getByLabelText('Checkpoint at')).toHaveValue('150')
    expect(menuSelect('Threshold unit')).toHaveTextContent('K tokens')
    commit('Checkpoint at', '120')
    expect(lastPatch()).toEqual({ checkpoint_threshold_mode: 'tokens', checkpoint_threshold_value: 120_000 })
  })

  it('collects the notes point in the threshold’s own unit', () => {
    render(<GeneralSection />)
    expect(screen.getByLabelText('Ask for notes at')).toHaveValue('120')
    commit('Ask for notes at', '100')
    expect(lastPatch()).toEqual({ checkpoint_notes_value: 100_000 })
  })

  it('shows the threshold in both readings when the window is known', () => {
    render(<GeneralSection />)
    expect(screen.getByText(/150k — 75% of 200k/)).toBeInTheDocument()
  })

  it('clears the whole threshold when the value is emptied, never half of it', () => {
    // A mode with no value would read as a number in a unit nobody chose.
    render(<GeneralSection />)
    commit('Checkpoint at', '')
    expect(lastPatch()).toEqual({
      checkpoint_threshold_mode: null,
      checkpoint_threshold_value: null,
      checkpoint_notes_value: null,
    })
  })

  it('clears a stored threshold when its unit changes, rather than reading it in the other', async () => {
    const user = userEvent.setup()
    render(<GeneralSection />)
    await chooseMenuOption(user, 'Threshold unit', /% of window/)
    expect(lastPatch()).toEqual({
      checkpoint_threshold_mode: null,
      checkpoint_threshold_value: null,
      checkpoint_notes_value: null,
    })
  })

  it('shows no conversation title controls: they moved to Manager', () => {
    render(<GeneralSection />)
    expect(screen.queryByLabelText('Conversation titles')).toBeNull()
    expect(screen.queryByLabelText('Conversation title runner')).toBeNull()
  })

  it("names the project's checkpoint model on every checkpoint-runner choice, whatever each runner records (F268)", async () => {
    const user = userEvent.setup()
    render(<GeneralSection />)
    const options = await openMenuSelect(user, 'Checkpoint runner')
    const haiku = options.find((o) => o.textContent?.startsWith('Haiku 4.5'))
    const titler = options.find((o) => o.textContent?.startsWith('Titler'))
    expect(haiku).toHaveTextContent('Haiku 4.5 · claude')
    expect(titler).toHaveTextContent('Haiku 4.5 · claude')
  })

  it('names each runner by its own model once checkpoint_model is cleared (F268)', async () => {
    const user = userEvent.setup()
    settings.checkpoint_model = null
    render(<GeneralSection />)
    const options = await openMenuSelect(user, 'Checkpoint runner')
    expect(options.find((o) => o.textContent?.startsWith('Haiku 4.5'))).toHaveTextContent('Provider default · claude')
    expect(options.find((o) => o.textContent?.startsWith('Titler'))).toHaveTextContent('Opus 5 · claude')
  })

  it('offers a model alias as a choice of its own, naming what it now points at', async () => {
    const user = userEvent.setup()
    render(<GeneralSection />)
    const options = await openMenuSelect(user, 'Checkpoint model')
    expect(options.map((o) => o.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('haiku, the latest'), expect.stringContaining('Now Opus 5')]),
    )
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

/** Task 1.18(b), design D10: a project percent threshold shown lowered for any bound agent whose
 *  runner compacts below 95, naming that agent. */
describe('project-level checkpoint-ceiling notice (task 1.18(b), design D10)', () => {
  beforeEach(() => {
    settings = makeSettings()
    settings.checkpoint_threshold_mode = 'percent'
    settings.checkpoint_threshold_value = 80
    settings.checkpoint_notes_value = 70
    projectAgentsFailed = false
    settingsError = null
  })

  it('says so when the project agents could not be read', () => {
    projectAgents = []
    projectAgentsFailed = true
    render(<GeneralSection />)
    expect(screen.queryByText(/agents could not be read/)).toBeInTheDocument()
  })

  it('names an agent whose runner compacts below the configured threshold', () => {
    projectAgents = [
      { name: 'cop-1', status: 'idle', message_count: 0, active_task_count: 0, runner: 'copilot', checkpoint_compaction_percent: 80 },
    ]
    render(<GeneralSection />)
    expect(screen.getByTestId('ceiling-note')).toHaveTextContent(/Lowered to 77%/)
    expect(screen.getByTestId('ceiling-note')).toHaveTextContent(/cop-1/)
  })

  it('shows nothing when every bound agent compacts at the C=95 default', () => {
    projectAgents = [
      { name: 'claude-1', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude', checkpoint_compaction_percent: 95 },
    ]
    render(<GeneralSection />)
    expect(screen.queryByText(/Lowered to/)).not.toBeInTheDocument()
  })
})

describe('F197 a failed settings query', () => {
  beforeEach(() => {
    settingsError = new ApiError(500, JSON.stringify({ detail: 'settings route is down' }))
    refetchSettings.mockReset()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('names the failure with a Retry instead of a skeleton that never ends, and shows no rows', () => {
    render(<GeneralSection />)
    expect(screen.getByRole('alert')).toHaveTextContent(/settings could not be loaded/i)
    expect(screen.getByRole('alert')).toHaveTextContent('settings route is down')
    expect(screen.queryByLabelText('Loading project settings')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Hop budget')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetchSettings).toHaveBeenCalledTimes(1)
  })
})

describe('F728 a save answers warnings, and the page shows them', () => {
  beforeEach(() => {
    settings = makeSettings()
    settingsError = null
    update.mockReset()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('lists what the Hub warned of after the save', async () => {
    const warning = 'The agent budget is now 2, but 3 agents are open.'
    render(<GeneralSection />)
    commit('Agent budget', '2')
    answer({ warnings: [warning] })
    expect(await screen.findByTestId('settings-save-warnings')).toHaveTextContent(warning)
  })

  it('shows no warning list for a save that warned of nothing', () => {
    render(<GeneralSection />)
    commit('Agent budget', '6')
    answer({ warnings: [] })
    expect(screen.queryByTestId('settings-save-warnings')).not.toBeInTheDocument()
  })

  it('names a refused save in the page, with the Hub’s reason', async () => {
    render(<GeneralSection />)
    commit('Agent budget', '6')
    answer({ error: new ApiError(422, JSON.stringify({ detail: 'notes must sit below the threshold' })) })
    expect(await screen.findByTestId('settings-save-refusal')).toHaveTextContent('notes must sit below the threshold')
  })
})
