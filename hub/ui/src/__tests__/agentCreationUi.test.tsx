import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentCreateDialog } from '@/components/agents/AgentCreateDialog'
import { ProjectHeader } from '@/components/layout/ProjectHeader'

const mutate = vi.fn()
let mutationError: Error | null = null

vi.mock('@/api/agents', () => ({
  useCreateAgent: () => ({ mutate, isPending: false, error: mutationError, reset: vi.fn() }),
}))
vi.mock('@/api/runners', () => ({
  useProviderLaunchability: () => ({ data: { providers: {
    codex: { runnable: true, present: true, authorized: true },
    claude: { runnable: false, present: false, authorized: true, reason: 'CLI unavailable' },
  } } }),
}))
vi.mock('@/api/modelCatalog', () => ({
  useModelCatalog: () => ({ data: { providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [{ id: 'claude-sonnet-5', label: 'Sonnet 5', aliases: [], context_window: 1_000_000, default: true }],
      controls: [],
    },
    {
      provider: 'codex',
      label: 'Codex CLI',
      models: [{ id: 'gpt-5.6-sol', label: 'GPT-5.6-Sol', aliases: [], context_window: 272_000, default: true }],
      controls: [],
    },
  ] } }),
}))
vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [{ id: 'charter-reviewer', name: 'Code Reviewer' }], isLoading: false }),
}))

describe('operator agent creation dialog', () => {
  beforeEach(() => {
    mutate.mockReset()
    mutationError = null
  })

  it('keeps agent creation out of the project header', () => {
    render(<ProjectHeader projectName="Website" directoryAvailable onOpenSetup={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Add agent' })).not.toBeInTheDocument()
  })

  it('collects a name, launchable provider and model, and optional charter', () => {
    const onCreated = vi.fn()
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={onCreated} />)
    expect(screen.getByRole('option', { name: /Claude Code/ })).toBeDisabled()
    expect(screen.getByText(/CLI unavailable/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'codex-gamma' } })
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'codex' } })
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'gpt-5.6-sol' } })
    fireEvent.change(screen.getByLabelText('Charter'), { target: { value: 'charter-reviewer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create agent' }))
    expect(mutate).toHaveBeenCalledWith(
      { name: 'codex-gamma', provider: 'codex', model: 'gpt-5.6-sol', charter_id: 'charter-reviewer' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
    mutate.mock.calls[0][1].onSuccess({ name: 'codex-gamma' })
    expect(onCreated).toHaveBeenCalledWith('codex-gamma')
  })

  it('selects the catalog default model when the provider changes', () => {
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'codex' } })
    expect(screen.getByLabelText('Model')).toHaveValue('gpt-5.6-sol')
  })

  it('does not offer a model select before a provider is chosen', () => {
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    expect(screen.queryByLabelText('Model')).not.toBeInTheDocument()
  })

  it('preserves fields and shows a typed API failure inline', () => {
    mutationError = new Error('{"detail":"Agent name already exists"}')
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'duplicate' } })
    expect(screen.getByDisplayValue('duplicate')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Agent name already exists')
  })

  it('traps keyboard focus and closes on Escape', () => {
    const onClose = vi.fn()
    render(<AgentCreateDialog open onClose={onClose} onCreated={vi.fn()} />)
    const cancel = screen.getByRole('button', { name: 'Cancel' })
    cancel.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(screen.getByLabelText('Agent name')).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })
})
