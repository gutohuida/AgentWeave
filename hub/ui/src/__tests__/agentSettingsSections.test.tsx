import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { AGENT_SETTINGS_SECTIONS, type AgentSettingsSection } from '@/lib/navigation'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'
import { menuSelect, openMenuSelect } from './support/menuSelect'

// `settings-in-the-app-s-style-where-you-expect-them` FR-4, FR-5, FR-8 and FR-9 on an agent's
// settings: five sections, no Save button and no native control in any, and a model chosen directly.

const bindModel = vi.fn()
let roster: AgentSummary[] = []
let runners: Array<{ id: string; name: string; cli: string; model: string | null }> = []
let providers: Record<string, { present: boolean }> = { claude: { present: true }, codex: { present: true }, copilot: { present: false } }

vi.mock('@/api/runners', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/runners')>()),
  useRunners: () => ({ data: runners, isLoading: false, error: null }),
  useProviderLaunchability: () => ({ data: { providers } }),
  useBindAgentModel: () => ({ mutate: bindModel, isPending: false, isError: false }),
  useUpdateAgentWaiting: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))
vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))
vi.mock('@/api/workspace', () => ({
  useAgentWorkspace: () => ({
    data: { working_dir: '/repo', isolated: true, branch: 'agentweave/worker', provisioned: true, unavailable_reason: null, task_checkouts: [] },
    isLoading: false,
  }),
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }),
}))
vi.mock('@/api/projects', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/projects')>()),
  useProjectSettings: () => ({ data: { checkpoint_mode: 'offered', checkpoint_threshold_mode: null, checkpoint_threshold_value: null }, isError: false }),
}))
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: roster, isLoading: false }),
  useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
  useAgentLaunchability: () => ({ data: undefined }),
  useArchiveAgent: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useUpdateAgentDescription: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentReachGrants: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentGrant: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentCheckpointMode: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentCheckpointOverride: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentReviewAgents: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAgentGithubMcp: () => ({ mutate: vi.fn(), isPending: false }),
}))

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return { name: 'worker', status: 'idle', message_count: 0, active_task_count: 0, lifecycle: 'open', runner: 'claude', runner_id: 'runner-sonnet', ...overrides } as AgentSummary
}

function open(section: AgentSettingsSection) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AgentSettingsPage agent="worker" section={section} onSelectSection={vi.fn()} onBack={vi.fn()} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  bindModel.mockReset()
  roster = [agent()]
  runners = [{ id: 'runner-sonnet', name: 'Claude Code — Sonnet 5', cli: 'claude', model: 'claude-sonnet-5' }]
  providers = { claude: { present: true }, codex: { present: true }, copilot: { present: false } }
})

describe('an agent settings page has five sections (FR-8)', () => {
  it('lists exactly Agent, Running, Permissions, Checkpoints and Workspace', () => {
    open('agent')
    const wanted = ['Agent', 'Running', 'Permissions', 'Checkpoints', 'Workspace']
    const nav = screen.getByRole('navigation')
    const listed = within(nav)
      .getAllByRole('button')
      .map((b) => b.textContent?.trim() ?? '')
      .filter((text) => wanted.includes(text))
    expect(listed).toEqual(wanted)
  })

  it.each(AGENT_SETTINGS_SECTIONS)('%s has no Save button, native checkbox, date input or select (FR-4, FR-5)', (section) => {
    roster = [agent({ runner: 'copilot' })]
    const { container } = open(section)
    expect(screen.queryByRole('button', { name: /^Save/ })).not.toBeInTheDocument()
    expect(container.querySelector('input[type=checkbox], input[type=date], select')).toBeNull()
  })
})

describe('choosing a model directly (FR-9)', () => {
  it('lists every model of an installed provider and its default, and leaves out one that is not installed', async () => {
    const user = userEvent.setup()
    open('running')
    const labels = (await openMenuSelect(user, 'Model for worker')).map((o) => o.textContent ?? '')
    expect(labels.some((l) => l.startsWith('claude · its default'))).toBe(true)
    for (const name of ['Opus 5', 'Sonnet 5', 'Haiku 4.5']) expect(labels.some((l) => l.startsWith(`claude · ${name}`))).toBe(true)
    expect(labels.some((l) => l.startsWith('codex'))).toBe(true)
    expect(labels.some((l) => l.includes('copilot'))).toBe(false)
  })

  it('shows the model it runs on now', () => {
    open('running')
    expect(menuSelect('Model for worker')).toHaveTextContent('claude · Sonnet 5')
  })

  it('binds the provider and model chosen, in one write, with no runner named (ac-model-new)', async () => {
    const user = userEvent.setup()
    open('running')
    const options = await openMenuSelect(user, 'Model for worker')
    await user.click(options.find((o) => o.textContent?.startsWith('claude · Haiku 4.5'))!)
    expect(bindModel).toHaveBeenCalledTimes(1)
    expect(bindModel).toHaveBeenCalledWith({ agent: 'worker', provider: 'claude', model: 'claude-haiku-4-5-20251001' }, expect.any(Object))
  })

  it('binds a provider’s own default as a null model', async () => {
    const user = userEvent.setup()
    open('running')
    const options = await openMenuSelect(user, 'Model for worker')
    await user.click(options.find((o) => o.textContent?.startsWith('codex · its default'))!)
    expect(bindModel).toHaveBeenCalledWith({ agent: 'worker', provider: 'codex', model: null }, expect.any(Object))
  })

  it('keeps the model it runs on in the menu even when its provider is not installed', async () => {
    const user = userEvent.setup()
    providers = { claude: { present: false }, codex: { present: true }, copilot: { present: false } }
    open('running')
    const labels = (await openMenuSelect(user, 'Model for worker')).map((o) => o.textContent ?? '')
    expect(labels.some((l) => l.startsWith('claude · Sonnet 5'))).toBe(true)
  })
})
