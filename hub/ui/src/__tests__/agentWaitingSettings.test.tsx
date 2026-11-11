import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const updateMutate = vi.fn()

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useBindAgentModel: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useProviderLaunchability: () => ({ data: undefined }),
  useUpdateAgentWaiting: () => ({ mutate: updateMutate, isPending: false, isError: false }),
  MIN_WAITING_SECONDS: 10,
  MAX_WAITING_SECONDS: 600,
}))

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

let roster: AgentSummary[] = []

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgentLaunchability: () => ({ data: undefined }),
    useUpdateAgentReachGrants: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useAgents: () => ({ data: roster, isLoading: false }),
  }
})

/** The page resolves its agent from the roster, so a test supplies one and names it. */
function renderInteraction(summary: AgentSummary) {
  roster = [summary]
  return render(<QueryClientProvider client={new QueryClient()}><AgentSettingsPage agent={summary.name} section="running" onSelectSection={vi.fn()} onBack={vi.fn()} /></QueryClientProvider>)
}

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'codex-1',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    runner: 'codex',
    permission_timeout_seconds: null,
    question_timeout_seconds: null,
    ...overrides,
  }
}

const questionWait = () => screen.getByLabelText(/An answer to a question/)
const questionRow = () => questionWait().closest('.aw-settings-row') as HTMLElement
const WRITES = expect.any(Object)

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

describe('per-agent waiting settings', () => {
  beforeEach(() => updateMutate.mockClear())

  it('shows the built-in wait when nothing is set, with no reset offered', () => {
    renderInteraction(agent())
    expect(questionWait()).toHaveValue('240')
    expect(within(questionRow()).queryByRole('button', { name: 'Reset to default' })).not.toBeInTheDocument()
  })

  it('shows a configured value, marked as changed', () => {
    renderInteraction(agent({ question_timeout_seconds: 300 }))
    expect(questionWait()).toHaveValue('300')
    expect(within(questionRow()).getByRole('button', { name: 'Reset to default' })).toBeInTheDocument()
  })

  it('saves once when the field is left, not on every keystroke, with no Save button', () => {
    // Typing "45" over "240" passes through "4"; saving that would set a wait shorter than the
    // card takes to render. ac-no-save-buttons: the write is the whole interaction.
    renderInteraction(agent({ question_timeout_seconds: 240 }))
    const input = questionWait()
    fireEvent.change(input, { target: { value: '4' } })
    fireEvent.change(input, { target: { value: '45' } })
    expect(updateMutate).not.toHaveBeenCalled()

    fireEvent.blur(input)
    expect(updateMutate).toHaveBeenCalledTimes(1)
    expect(updateMutate).toHaveBeenCalledWith({ agent: 'codex-1', field: 'question_timeout_seconds', seconds: 45 }, WRITES)
    expect(screen.queryByRole('button', { name: /^Save/ })).not.toBeInTheDocument()
  })

  it('saves on Enter', () => {
    renderInteraction(agent())
    fireEvent.change(questionWait(), { target: { value: '90' } })
    fireEvent.keyDown(questionWait(), { key: 'Enter' })
    expect(updateMutate).toHaveBeenCalledTimes(1)
    expect(updateMutate).toHaveBeenCalledWith({ agent: 'codex-1', field: 'question_timeout_seconds', seconds: 90 }, WRITES)
  })

  it('goes back to the default through the reset', () => {
    renderInteraction(agent({ question_timeout_seconds: 300 }))
    fireEvent.click(within(questionRow()).getByRole('button', { name: 'Reset to default' }))
    expect(updateMutate).toHaveBeenCalledWith({ agent: 'codex-1', field: 'question_timeout_seconds', seconds: null }, WRITES)
  })

  it.each([['5', /At least 10/], ['601', /At most 600/], ['0', /At least 10/]])('refuses %s without saving', (value, why) => {
    renderInteraction(agent())
    fireEvent.change(questionWait(), { target: { value } })
    fireEvent.blur(questionWait())
    expect(updateMutate).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(why as RegExp)
  })

  it('does not save a value that has not changed', () => {
    renderInteraction(agent({ question_timeout_seconds: 300 }))
    fireEvent.blur(questionWait())
    expect(updateMutate).not.toHaveBeenCalled()
  })

  it('keeps both waits together under Running, and the other bindings elsewhere', () => {
    renderInteraction(agent())
    expect(screen.getByLabelText(/A permission decision/)).toBeInTheDocument()
    expect(screen.getByLabelText(/An answer to a question/)).toBeInTheDocument()
    expect(screen.getByLabelText('Model for codex-1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Charter for codex-1')).not.toBeInTheDocument()
  })

  it('puts each binding in its own section', () => {
    roster = [agent()]
    const { unmount } = render(<QueryClientProvider client={new QueryClient()}><AgentSettingsPage agent="codex-1" section="permissions" onSelectSection={vi.fn()} onBack={vi.fn()} /></QueryClientProvider>)
    expect(screen.getByLabelText('Default permissions for codex-1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Model for codex-1')).not.toBeInTheDocument()
    unmount()

    render(<QueryClientProvider client={new QueryClient()}><AgentSettingsPage agent="codex-1" section="agent" onSelectSection={vi.fn()} onBack={vi.fn()} /></QueryClientProvider>)
    expect(screen.getByLabelText('Charter for codex-1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Model for codex-1')).not.toBeInTheDocument()
  })

  it('says so when the agent is not in the roster, rather than rendering an empty page', () => {
    roster = []
    render(<QueryClientProvider client={new QueryClient()}><AgentSettingsPage agent="codex-1" section="running" onSelectSection={vi.fn()} onBack={vi.fn()} /></QueryClientProvider>)
    expect(screen.getByTestId('agent-settings-empty')).toHaveTextContent(/no longer in the roster/i)
  })
})
