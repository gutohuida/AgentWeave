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
    'future-cli': { runnable: true, present: true, authorized: true },
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
    // A provider ProviderMark has no brand SVG for — exercises the initials fallback
    // and confirms a missing mark never blocks selection (task 4.7).
    {
      provider: 'future-cli',
      label: 'Future CLI',
      models: [{ id: 'future-1', label: 'Future One', aliases: [], context_window: null, default: true }],
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
    fireEvent.click(screen.getByRole('button', { name: 'Provider' }))
    expect(screen.getByRole('option', { name: /Claude Code/ })).toBeDisabled()
    expect(screen.getByText(/CLI unavailable/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: /Codex CLI/ }))

    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'codex-gamma' } })
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

  it('offers only the settings the first turn depends on', () => {
    // The creation-time boundary, as a test rather than a comment: a setting belongs here only
    // if the agent's *first turn* would be materially different without it. Thresholds, timeouts
    // and access grants all have workable defaults and can be changed before they matter, so
    // putting them here is friction at exactly the wrong moment.
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)

    expect(screen.getByLabelText('Agent name')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Provider' })).toBeInTheDocument()
    expect(screen.getByLabelText('Charter')).toBeInTheDocument()

    for (const absent of [/timeout/i, /threshold/i, /permission/i, /access/i, /checkpoint/i, /worktree/i]) {
      expect(screen.queryByLabelText(absent)).not.toBeInTheDocument()
    }
  })

  it('never requires a charter', () => {
    // `operator-agent-creation` states a charter "MAY be selected but MUST NOT be required" and
    // defines a no-charter contract. The configuration page must not tighten that.
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Provider' }))
    fireEvent.click(screen.getByRole('option', { name: /Codex CLI/ }))
    fireEvent.change(screen.getByLabelText('Agent name'), { target: { value: 'no-charter' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create agent' }))

    // The key is omitted rather than sent as null — "no charter" is the absence of a binding,
    // not a binding to nothing.
    expect(mutate).toHaveBeenCalledWith(
      { name: 'no-charter', provider: 'codex', model: 'gpt-5.6-sol' },
      expect.anything(),
    )
    expect(mutate.mock.calls[0][0]).not.toHaveProperty('charter_id')
  })

  it('selects the catalog default model when the provider changes', () => {
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Provider' }))
    fireEvent.click(screen.getByRole('option', { name: /Codex CLI/ }))
    expect(screen.getByLabelText('Model')).toHaveValue('gpt-5.6-sol')
  })

  it('shows the selected provider as the trigger label and closes the picker on choice', () => {
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Provider' }))
    fireEvent.click(screen.getByRole('option', { name: /Codex CLI/ }))
    expect(screen.getByRole('button', { name: 'Provider' })).toHaveTextContent('Codex CLI')
    expect(screen.queryByRole('listbox', { name: 'Provider' })).not.toBeInTheDocument()
  })

  it('a launchable provider with no brand mark is still selectable', () => {
    render(<AgentCreateDialog open onClose={vi.fn()} onCreated={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Provider' }))
    const option = screen.getByRole('option', { name: /Future CLI/ })
    expect(option).not.toBeDisabled()
    fireEvent.click(option)
    expect(screen.getByRole('button', { name: 'Provider' })).toHaveTextContent('Future CLI')
    expect(screen.getByLabelText('Model')).toHaveValue('future-1')
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
