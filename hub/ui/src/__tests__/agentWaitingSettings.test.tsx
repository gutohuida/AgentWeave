import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import type { AgentSummary } from '@/api/agents'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const updateMutate = vi.fn()

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
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
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useAgents: () => ({ data: roster, isLoading: false }),
  }
})

/** The page resolves its agent from the roster, so a test supplies one and names it. */
function renderInteraction(summary: AgentSummary) {
  roster = [summary]
  return render(<AgentSettingsPage agent={summary.name} section="interaction" />)
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

const questionWait = () => screen.getByLabelText(/Answer to a question wait for codex-1/)

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

describe('per-agent waiting settings', () => {
  beforeEach(() => updateMutate.mockClear())

  it('shows the default as a placeholder when nothing is set', () => {
    // Not pre-filled with 240: a row storing today's number would keep saying it after the
    // default moved, and the operator could not tell "chosen" from "inherited".
    renderInteraction(agent())
    const input = questionWait()
    expect(input).toHaveValue(null)
    expect(input).toHaveAttribute('placeholder', '240')
    expect(screen.getByText(/Default \(240s\)/)).toBeInTheDocument()
  })

  it('shows a configured value', () => {
    renderInteraction(agent({ question_timeout_seconds: 300 }))
    expect(questionWait()).toHaveValue(300)
  })

  it('saves on blur, not on every keystroke', () => {
    // Typing "45" over "240" passes through "4"; saving that would set a wait shorter than the
    // card takes to render.
    renderInteraction(agent({ question_timeout_seconds: 240 }))
    const input = questionWait()
    fireEvent.change(input, { target: { value: '4' } })
    fireEvent.change(input, { target: { value: '45' } })
    expect(updateMutate).not.toHaveBeenCalled()

    fireEvent.blur(input)
    expect(updateMutate).toHaveBeenCalledWith({
      agent: 'codex-1',
      field: 'question_timeout_seconds',
      seconds: 45,
    })
  })

  it('clears back to the default when emptied', () => {
    renderInteraction(agent({ question_timeout_seconds: 300 }))
    fireEvent.change(questionWait(), { target: { value: '' } })
    fireEvent.blur(questionWait())
    expect(updateMutate).toHaveBeenCalledWith({
      agent: 'codex-1',
      field: 'question_timeout_seconds',
      seconds: null,
    })
  })

  it.each([['5'], ['601'], ['0']])('refuses %s without saving', (value) => {
    renderInteraction(agent())
    fireEvent.change(questionWait(), { target: { value } })
    fireEvent.blur(questionWait())
    expect(updateMutate).not.toHaveBeenCalled()
    expect(screen.getByText(/Between 10 and 600 seconds/)).toBeInTheDocument()
  })

  it('does not save a value that has not changed', () => {
    renderInteraction(agent({ question_timeout_seconds: 300 }))
    fireEvent.blur(questionWait())
    expect(updateMutate).not.toHaveBeenCalled()
  })

  it('keeps both waits together under Interaction, and the bindings elsewhere', () => {
    // These are durable per-agent settings, and they live on the agent rather than behind a gear
    // or in the composer's per-conversation pills. What changed with the configuration page is
    // that they no longer share one scrolling panel with the bindings: a section is a claim about
    // what the operator came to do, and "how long it waits for me" is not "what it runs as".
    renderInteraction(agent())
    expect(screen.getByLabelText(/Permission decision wait for codex-1/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Answer to a question wait for codex-1/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Runner for codex-1')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Charter for codex-1')).not.toBeInTheDocument()
  })

  it('puts each binding in its own section', () => {
    roster = [agent()]
    const { unmount } = render(<AgentSettingsPage agent="codex-1" section="execution" />)
    expect(screen.getByLabelText('Runner for codex-1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Charter for codex-1')).not.toBeInTheDocument()
    unmount()

    render(<AgentSettingsPage agent="codex-1" section="charter" />)
    expect(screen.getByLabelText('Charter for codex-1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Runner for codex-1')).not.toBeInTheDocument()
  })

  it('says so when the agent is not in the roster, rather than rendering an empty page', () => {
    roster = []
    render(<AgentSettingsPage agent="codex-1" section="interaction" />)
    expect(screen.getByTestId('agent-settings-empty')).toHaveTextContent(/no longer in the roster/i)
  })
})
