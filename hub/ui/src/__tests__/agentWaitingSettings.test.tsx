import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AgentInfoTab } from '@/components/agents/AgentInfoTab'
import type { AgentSummary } from '@/api/agents'

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

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgentSessions: () => ({ data: [], isLoading: false }) }
})

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

describe('per-agent waiting settings', () => {
  beforeEach(() => updateMutate.mockClear())

  it('shows the default as a placeholder when nothing is set', () => {
    // Not pre-filled with 240: a row storing today's number would keep saying it after the
    // default moved, and the operator could not tell "chosen" from "inherited".
    render(<AgentInfoTab agent={agent()} />)
    const input = questionWait()
    expect(input).toHaveValue(null)
    expect(input).toHaveAttribute('placeholder', '240')
    expect(screen.getByText(/Default \(240s\)/)).toBeInTheDocument()
  })

  it('shows a configured value', () => {
    render(<AgentInfoTab agent={agent({ question_timeout_seconds: 300 })} />)
    expect(questionWait()).toHaveValue(300)
  })

  it('saves on blur, not on every keystroke', () => {
    // Typing "45" over "240" passes through "4"; saving that would set a wait shorter than the
    // card takes to render.
    render(<AgentInfoTab agent={agent({ question_timeout_seconds: 240 })} />)
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
    render(<AgentInfoTab agent={agent({ question_timeout_seconds: 300 })} />)
    fireEvent.change(questionWait(), { target: { value: '' } })
    fireEvent.blur(questionWait())
    expect(updateMutate).toHaveBeenCalledWith({
      agent: 'codex-1',
      field: 'question_timeout_seconds',
      seconds: null,
    })
  })

  it.each([['5'], ['601'], ['0']])('refuses %s without saving', (value) => {
    render(<AgentInfoTab agent={agent()} />)
    fireEvent.change(questionWait(), { target: { value } })
    fireEvent.blur(questionWait())
    expect(updateMutate).not.toHaveBeenCalled()
    expect(screen.getByText(/Between 10 and 600 seconds/)).toBeInTheDocument()
  })

  it('does not save a value that has not changed', () => {
    render(<AgentInfoTab agent={agent({ question_timeout_seconds: 300 })} />)
    fireEvent.blur(questionWait())
    expect(updateMutate).not.toHaveBeenCalled()
  })

  it('offers both waits, and the bindings, as settings on the agent', () => {
    // The point of the change: these are durable per-agent settings, and they live here rather
    // than behind a gear or in the composer's per-conversation pills.
    render(<AgentInfoTab agent={agent()} />)
    expect(screen.getByLabelText(/Permission decision wait for codex-1/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Answer to a question wait for codex-1/)).toBeInTheDocument()
    expect(screen.getByLabelText('Runner for codex-1')).toBeInTheDocument()
    expect(screen.getByLabelText('Charter for codex-1')).toBeInTheDocument()
  })
})
