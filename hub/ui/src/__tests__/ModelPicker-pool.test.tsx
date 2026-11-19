import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ComposerModelControls } from '@/components/agents/ComposerModelControls'
import { chatChoiceOverrides, chatEntry, chatStartedOn } from '@/components/agents/pool/poolModel'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

/**
 * The chat composer under a pool (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-
 * pool`, FR-9, criterion chat-picker-bounded): the model choice lists only the profile's entries,
 * the Effort pill is gone because an entry carries its effort, and once a chat has a turn the
 * entries on another CLI are listed but not choosable. The pool is in the order the agents route
 * returns it, the operator's order.
 */

const CATALOG: ModelCatalogResponse = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [
        { id: 'claude-haiku-5-5', label: 'Haiku 5.5', aliases: ['haiku'], context_window: null, default: false },
        { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5', aliases: ['sonnet'], context_window: null, default: true },
        { id: 'claude-opus-5-5', label: 'Opus 5.5', aliases: ['opus'], context_window: null, default: false },
      ],
      controls: [
        {
          id: 'effort',
          label: 'Effort',
          kind: 'enum',
          values: [
            { id: 'medium', label: 'Medium' },
            { id: 'high', label: 'High' },
          ],
          default: 'medium',
          apply: { style: 'flag', template: '--effort {value}' },
        },
        {
          id: 'permission_mode',
          label: 'Permissions',
          kind: 'enum',
          values: [
            { id: 'default', label: 'Ask' },
            { id: 'acceptEdits', label: 'Edit files' },
          ],
          default: 'default',
          apply: { style: 'flag', template: '--permission-mode {value}' },
        },
      ],
    },
    {
      provider: 'codex',
      label: 'Codex',
      models: [{ id: 'gpt-6.1-sol', label: 'GPT-6.1-Sol', aliases: [], context_window: null, default: true }],
      controls: [],
    },
  ],
}

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: CATALOG }) }
})

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const HAIKU: AgentPoolEntry = {
  id: 'pool-haiku',
  runner_id: 'runner-haiku',
  runner_name: 'Haiku',
  cli: 'claude',
  model: 'haiku',
  effort: null,
  default: true,
}
const SONNET: AgentPoolEntry = {
  id: 'pool-sonnet',
  runner_id: 'runner-sonnet',
  runner_name: 'Sonnet',
  cli: 'claude',
  model: 'sonnet',
  effort: 'high',
  default: false,
}
const CODEX: AgentPoolEntry = {
  id: 'pool-codex',
  runner_id: 'runner-codex',
  runner_name: 'Codex',
  cli: 'codex',
  model: 'gpt-6.1-sol',
  effort: null,
  default: false,
}

function renderControls(pool: AgentPoolEntry[], overrides: Record<string, string> = {}, startedOn: string | null = null) {
  const onChooseEntry = vi.fn()
  render(
    <ComposerModelControls
      runner="claude"
      effectiveModel={null}
      effectiveControls={overrides}
      onChangeModel={vi.fn()}
      onChangeControl={vi.fn()}
      pool={pool}
      agentName="Builder"
      currentEntry={chatEntry(pool, overrides)}
      poolStartedOn={startedOn}
      onChooseEntry={onChooseEntry}
    />,
    { wrapper },
  )
  return { onChooseEntry }
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /^Model:/ }))
  return screen.getByRole('listbox', { name: 'Models Builder may run on' })
}

describe('ComposerModelControls under a pool (FR-9)', () => {
  it('chat-picker-bounded: the picker lists only the pool’s Haiku and Sonnet', () => {
    renderControls([HAIKU, SONNET])
    const listbox = open()
    const labels = within(listbox)
      .getAllByRole('option')
      .map((option) => option.getAttribute('aria-label'))
    expect(labels).toEqual(['Haiku 5.5, the default', 'Sonnet 5.5 · High'])
    expect(within(listbox).queryByText(/Opus/)).toBeNull()
    // The pill reads the default entry before anything is chosen.
    expect(screen.getByRole('button', { name: /^Model:/ })).toHaveTextContent('Haiku 5.5')
  })

  it('replaces the Effort pill, keeping the CLI’s other controls', () => {
    renderControls([HAIKU, SONNET])
    expect(screen.queryByTitle(/^Effort:/)).toBeNull()
    expect(screen.getByTitle(/^Permissions:/)).toBeInTheDocument()
  })

  it('choosing an entry hands it back, and its overrides name its runner and effort', () => {
    const { onChooseEntry } = renderControls([HAIKU, SONNET], { permission_mode: 'acceptEdits', model: 'opus' })
    fireEvent.click(within(open()).getByRole('option', { name: 'Sonnet 5.5 · High' }))
    expect(onChooseEntry).toHaveBeenCalledWith(SONNET)
    expect(chatChoiceOverrides({ permission_mode: 'acceptEdits', model: 'opus' }, SONNET)).toEqual({
      permission_mode: 'acceptEdits',
      runner_id: 'runner-sonnet',
      effort: 'high',
    })
    // Back to the default: its effort is none, so none is sent.
    expect(chatChoiceOverrides({ runner_id: 'runner-sonnet', effort: 'high' }, HAIKU)).toEqual({
      runner_id: 'runner-haiku',
    })
  })

  it('shows the chosen entry, read from the overrides the conversation stores', () => {
    renderControls([HAIKU, SONNET], { runner_id: 'runner-sonnet', effort: 'high' })
    expect(screen.getByRole('button', { name: /^Model:/ })).toHaveTextContent('Sonnet 5.5 · High')
  })

  it('a started chat lists another CLI’s entries as not choosable, saying a new chat is needed', () => {
    const { onChooseEntry } = renderControls([HAIKU, SONNET, CODEX], {}, 'claude')
    const listbox = open()
    const codex = within(listbox).getByRole('option', { name: 'GPT-6.1-Sol' })
    expect(codex).toHaveAttribute('aria-disabled', 'true')
    expect(codex).toHaveTextContent('This chat runs on Claude Code; start a new chat for Codex')
    fireEvent.click(codex)
    expect(onChooseEntry).not.toHaveBeenCalled()
    // Before its first turn every entry is choosable.
    expect(within(listbox).getByRole('option', { name: 'Sonnet 5.5 · High' })).not.toHaveAttribute('aria-disabled')
  })

  it('a new chat may choose an entry on any CLI', () => {
    const { onChooseEntry } = renderControls([HAIKU, SONNET, CODEX], {}, null)
    const codex = within(open()).getByRole('option', { name: 'GPT-6.1-Sol' })
    expect(codex).not.toHaveAttribute('aria-disabled')
    fireEvent.click(codex)
    expect(onChooseEntry).toHaveBeenCalledWith(CODEX)
  })

  it('reads the CLI a chat started on from the conversation the route returns', () => {
    const pool = [HAIKU, CODEX]
    expect(chatStartedOn(pool, undefined)).toBeNull()
    expect(chatStartedOn(pool, { started_cli: null, provider_session_id: null })).toBeNull()
    expect(chatStartedOn(pool, { started_cli: 'codex', provider_session_id: 's' })).toBe('codex')
    // A session from before runs recorded their runner ran on the default.
    expect(chatStartedOn(pool, { started_cli: null, provider_session_id: 's' })).toBe('claude')
  })

  it('without a pool, the model picker and the Effort pill are as before', () => {
    render(
      <ComposerModelControls
        runner="claude"
        effectiveModel={null}
        effectiveControls={{}}
        onChangeModel={vi.fn()}
        onChangeControl={vi.fn()}
      />,
      { wrapper },
    )
    expect(screen.getByTitle(/^Effort:/)).toBeInTheDocument()
    expect(screen.getByTitle(/^Model:/)).toHaveTextContent('Sonnet 5.5')
  })
})
