import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ComposerModelControls } from '@/components/agents/ComposerModelControls'
import { chatChoice, chatEffortOverrides, chatPickOverrides, chatStartedOn } from '@/components/agents/pool/poolModel'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

/**
 * The chat composer's model choice (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-
 * provider`, FR-3, FR-6, FR-11; it reverses FR-9 of the pool change, which bounded a chat to its
 * pool): the profile's pool first under its name, then every other catalog model by provider,
 * always a picker, with the effort as its own pill. Once a chat has a turn, another CLI's models
 * are listed but not choosable. The pool is in the order the agents route returns it.
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

/** The project's runners as the runners route returns them: one the Hub made for a chat on Opus. */
const RUNNERS = [{ id: 'runner-opus-chat', cli: 'claude' as const, model: 'claude-opus-5-5' }]

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
  const onChange = vi.fn()
  render(
    <ComposerModelControls
      runner="claude"
      effectiveModel={null}
      effectiveControls={overrides}
      onChangeModel={vi.fn()}
      onChangeControl={vi.fn()}
      pool={pool}
      agentName="Builder"
      chatOverrides={overrides}
      poolStartedOn={startedOn}
      onChangeChatOverrides={onChange}
      runners={RUNNERS}
    />,
    { wrapper },
  )
  return { onChange }
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /^Model:/ }))
  return screen.getByRole('listbox', { name: 'Models for this chat with Builder' })
}

function groups(listbox: HTMLElement) {
  return within(listbox)
    .getAllByRole('group')
    .map((group) => [
      group.getAttribute('aria-label'),
      within(group)
        .getAllByRole('option')
        .map((option) => option.getAttribute('aria-label')),
    ])
}

describe('the chat model picker: the pool first, then the catalog (FR-3)', () => {
  it('ac-picker-single-pool: a pool of one entry still opens a picker, its entry under the profile, then every other model', () => {
    renderControls([HAIKU])
    const listbox = open()
    expect(groups(listbox)).toEqual([
      ['Builder', ['Haiku 5.5, the default']],
      ['Claude Code', ['Sonnet 5.5', 'Opus 5.5']],
      ['Codex', ['GPT-6.1-Sol']],
    ])
    expect(screen.getByText(/This choice is for this chat only/)).toHaveTextContent(
      'This choice is for this chat only. Tasks and reviews run on Builder’s own models and do not follow it.',
    )
    // The pill reads the pool's default before anything is chosen.
    expect(screen.getByRole('button', { name: /^Model:/ })).toHaveTextContent('Haiku 5.5')
  })

  it('a model the pool holds is listed once, under the profile', () => {
    renderControls([HAIKU, SONNET])
    expect(groups(open())[1]).toEqual(['Claude Code', ['Opus 5.5']])
  })

  it('choosing a catalog model sends its provider and model; choosing an entry its runner and effort', () => {
    const { onChange } = renderControls([HAIKU, SONNET], { permission_mode: 'acceptEdits', effort: 'high' })
    fireEvent.click(within(open()).getByRole('option', { name: 'Opus 5.5' }))
    expect(onChange).toHaveBeenLastCalledWith({ permission_mode: 'acceptEdits', provider: 'claude', model: 'claude-opus-5-5', effort: 'high' })

    fireEvent.click(within(open()).getByRole('option', { name: 'Sonnet 5.5 · High' }))
    expect(onChange).toHaveBeenLastCalledWith({ permission_mode: 'acceptEdits', runner_id: 'runner-sonnet', effort: 'high' })
    // Back to the default: its effort is none, so none is sent.
    expect(chatPickOverrides(CATALOG, { runner_id: 'runner-sonnet', effort: 'high' }, { kind: 'entry', entry: HAIKU })).toEqual({
      runner_id: 'runner-haiku',
    })
    // An effort the chosen provider does not offer is dropped.
    expect(chatPickOverrides(CATALOG, { effort: 'high' }, { kind: 'model', provider: 'codex', model: 'gpt-6.1-sol' })).toEqual({
      provider: 'codex',
      model: 'gpt-6.1-sol',
    })
  })

  it('shows a stored choice outside the pool by the runner the Hub made for it', () => {
    renderControls([HAIKU], { runner_id: 'runner-opus-chat' })
    expect(screen.getByRole('button', { name: /^Model:/ })).toHaveTextContent('Opus 5.5')
    const opus = within(open()).getByRole('option', { name: 'Opus 5.5' })
    expect(opus).toHaveAttribute('aria-selected', 'true')
  })

  it('ac-other-cli-refused: a started chat lists another CLI’s models as not choosable, saying a new chat is needed', () => {
    const { onChange } = renderControls([HAIKU, SONNET, CODEX], {}, 'claude')
    const listbox = open()
    const codex = within(listbox).getByRole('option', { name: 'GPT-6.1-Sol' })
    expect(codex).toHaveAttribute('aria-disabled', 'true')
    expect(codex).toHaveTextContent('This chat runs on Claude Code; start a new chat for Codex')
    fireEvent.click(codex)
    expect(onChange).not.toHaveBeenCalled()
    // Its own CLI's models stay choosable, in the pool or not.
    const opus = within(listbox).getByRole('option', { name: 'Opus 5.5' })
    expect(opus).not.toHaveAttribute('aria-disabled')
    fireEvent.click(opus)
    expect(onChange).toHaveBeenCalledWith({ provider: 'claude', model: 'claude-opus-5-5' })
  })

  it('a new chat may choose a model on any CLI', () => {
    const { onChange } = renderControls([HAIKU], {}, null)
    const codex = within(open()).getByRole('option', { name: 'GPT-6.1-Sol' })
    expect(codex).not.toHaveAttribute('aria-disabled')
    fireEvent.click(codex)
    expect(onChange).toHaveBeenCalledWith({ provider: 'codex', model: 'gpt-6.1-sol' })
  })

  it('the filter narrows the list, and the keyboard chooses', () => {
    const { onChange } = renderControls([HAIKU])
    open()
    const input = screen.getByRole('combobox', { name: 'Find a model' })
    fireEvent.change(input, { target: { value: 'opus' } })
    expect(groups(screen.getByRole('listbox'))).toEqual([['Claude Code', ['Opus 5.5']]])
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith({ provider: 'claude', model: 'claude-opus-5-5' })
  })

  it('reads the CLI a chat started on from the conversation the route returns', () => {
    const pool = [HAIKU, CODEX]
    expect(chatStartedOn(pool, undefined)).toBeNull()
    expect(chatStartedOn(pool, { started_cli: null, provider_session_id: null })).toBeNull()
    expect(chatStartedOn(pool, { started_cli: 'codex', provider_session_id: 's' })).toBe('codex')
    // A session from before runs recorded their runner ran on the default.
    expect(chatStartedOn(pool, { started_cli: null, provider_session_id: 's' })).toBe('claude')
  })
})

describe('the chat effort is its own control (FR-6)', () => {
  it('offers the usual effort and the provider’s efforts, preselected with the entry’s', () => {
    renderControls([HAIKU, SONNET], { runner_id: 'runner-sonnet', effort: 'high' })
    fireEvent.click(screen.getByRole('button', { name: 'Effort: High' }))
    const options = within(screen.getByRole('listbox', { name: 'Effort' })).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['Usual', 'Medium', 'High'])
    expect(screen.getByTitle(/^Permissions:/)).toBeInTheDocument()
  })

  it('ac-effort-changes: changing it keeps the runner, and Usual clears it', () => {
    const { onChange } = renderControls([HAIKU], { runner_id: 'runner-opus-chat' }, 'claude')
    fireEvent.click(screen.getByRole('button', { name: 'Effort: Usual' }))
    fireEvent.click(screen.getByRole('option', { name: 'High' }))
    expect(onChange).toHaveBeenCalledWith({ runner_id: 'runner-opus-chat', effort: 'high' })
    expect(chatEffortOverrides({ runner_id: 'r', effort: 'high' }, null)).toEqual({ runner_id: 'r' })
  })

  it('reads the default entry’s effort when the chat chose none', () => {
    const highDefault = { ...HAIKU, effort: 'high' }
    expect(chatChoice(CATALOG, [highDefault], {})?.effort).toBe('high')
    expect(chatChoice(CATALOG, [highDefault], { effort: 'medium' })?.effort).toBe('medium')
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
