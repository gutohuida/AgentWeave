import { useState } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { RunnersPage } from '@/components/runners/RunnersPage'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const createMutate = vi.fn()
const updateMutate = vi.fn()
const bindMutate = vi.fn()

// Armed by a test to make the next save fail. The save mutations are mocked with real `useState`
// rather than a bare `vi.fn`, because the refusal surface is *read off the mutation* — a plain spy
// has no `error` to render and no `reset()` to clear, which is the whole of section 3.
let refuseCreate: unknown = null
let refuseUpdate: unknown = null

// Armed by a test to swap in a catalog with a different Codex `source`
// (`the-codex-models-offered-are-the-ones-its-cli-lists`, design test 9).
let catalogOverride: ModelCatalogResponse | null = null

vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [
      {
        id: 'runner-default',
        project_id: 'proj-test',
        name: 'Claude Default',
        cli: 'claude',
        model: null,
        flags: null,
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
        model_unrecognised: false,
      },
      {
        id: 'runner-opus',
        project_id: 'proj-test',
        name: 'Claude Opus',
        cli: 'claude',
        model: 'claude-opus-5',
        flags: null,
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
        model_unrecognised: false,
      },
      {
        // A runner from before the catalog existed. Whether a model is recognised is the API's
        // decision (`RunnerResponse._flag_unrecognised_model`), never recomputed in the browser.
        id: 'runner-legacy',
        project_id: 'proj-test',
        name: 'Claude Legacy',
        cli: 'claude',
        model: 'claude-3-legacy-9',
        flags: null,
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
        model_unrecognised: true,
      },
      {
        // A declared alias, stored as written (a-model-alias-is-a-model-choice). The API already
        // reads this as recognised (`ProviderDescriptor.model` resolves aliases).
        id: 'runner-alias',
        project_id: 'proj-test',
        name: 'Claude Code — opus (latest)',
        cli: 'claude',
        model: 'opus',
        flags: null,
        created_at: '2026-08-03T00:00:00Z',
        updated_at: '2026-08-03T00:00:00Z',
        model_unrecognised: false,
      },
    ],
    isLoading: false,
  }),
  useCreateRunner: () => {
    const [error, setError] = useState<unknown>(null)
    return {
      mutate: (values: unknown, options: unknown) => {
        createMutate(values, options)
        setError(refuseCreate)
      },
      isPending: false,
      error,
      reset: () => setError(null),
    }
  },
  useUpdateRunner: () => {
    const [error, setError] = useState<unknown>(null)
    return {
      mutate: (values: unknown, options: unknown) => {
        updateMutate(values, options)
        setError(refuseUpdate)
      },
      isPending: false,
      error,
      reset: () => setError(null),
    }
  },
  useDeleteRunner: () => ({ mutate: vi.fn(), isPending: false }),
  useBindAgentRunner: () => ({ mutate: bindMutate, isPending: false, isError: false }),
  useUpdateAgentWaiting: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  MIN_WAITING_SECONDS: 10,
  MAX_WAITING_SECONDS: 600,
}))

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
    useAgentLaunchability: () => ({ data: undefined }),
    useUpdateAgentPermissionDefault: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
    useAgents: () => ({
      data: [
        { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, runner_id: 'runner-default' },
      ],
      isLoading: false,
    }),
  }
})

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return {
    ...actual,
    useModelCatalog: () => ({ data: catalogOverride ?? MODEL_CATALOG_FIXTURE, isLoading: false }),
  }
})

function optionsOf(select: HTMLElement): (string | null)[] {
  return [...select.querySelectorAll('option')].map((option) => option.textContent)
}

describe('runner management UI', () => {
  beforeEach(() => {
    createMutate.mockReset()
    updateMutate.mockReset()
    bindMutate.mockReset()
    refuseCreate = null
    refuseUpdate = null
    catalogOverride = null
  })

  it('offers copilot as a runner CLI (a-copilot-agent-runs-over-acp task 1.19)', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    expect(optionsOf(screen.getByLabelText('CLI'))).toEqual(['claude', 'codex', 'copilot'])
  })

  it('names the built-in fallback under the Codex model select when no cache was read (design test 9)', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.selectOptions(screen.getByLabelText('CLI'), 'codex')

    expect(screen.getByText('Built-in list: no Codex model cache')).toBeInTheDocument()
  })

  it('names the installed Codex CLI and fetch date under the model select when a cache was read (design test 9)', async () => {
    const user = userEvent.setup()
    catalogOverride = {
      providers: MODEL_CATALOG_FIXTURE.providers.map((p) =>
        p.provider === 'codex'
          ? {
              ...p,
              source: {
                kind: 'cli_cache' as const,
                fetched_at: '2026-09-23T10:10:51Z',
                client_version: '0.146.0',
                reason: null,
              },
            }
          : p,
      ),
    }
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.selectOptions(screen.getByLabelText('CLI'), 'codex')

    expect(
      screen.getByText('As listed by your installed Codex CLI (0.146.0, fetched 23 Sep)'),
    ).toBeInTheDocument()
  })

  it('shows no Codex source line for the Claude CLI', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    // Claude is the default CLI when the dialog opens.
    expect(screen.queryByText(/Built-in list|As listed by your installed Codex CLI/)).not.toBeInTheDocument()
  })

  it('creates a custom runner variant without replacing the existing runner', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    expect(screen.getByText('Claude Default')).toBeInTheDocument()
    expect(screen.getByText('Claude Opus')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    // 'e.g. Claude Opus' is the *Name* field, not the model: Save is disabled on an empty name.
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'Claude Sonnet')

    // The model is chosen from the catalog — the unset choice plus exactly what claude declares,
    // and no free-typed model field anywhere on screen.
    const modelSelect = screen.getByLabelText('Model')
    expect(optionsOf(modelSelect)).toEqual([
      'Provider default',
      'Opus 5',
      'Sonnet 5',
      'Haiku 4.5',
      'opus — latest (now Opus 5)',
      'sonnet — latest (now Sonnet 5)',
      'haiku — latest (now Haiku 4.5)',
    ])
    expect(screen.queryByPlaceholderText('e.g. claude-sonnet-5')).not.toBeInTheDocument()

    await user.selectOptions(modelSelect, 'claude-sonnet-5')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(createMutate).toHaveBeenCalledWith(
      { name: 'Claude Sonnet', cli: 'claude', model: 'claude-sonnet-5' },
      expect.any(Object),
    )
  })

  it('creates a runner with no model when the operator leaves Provider default', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'Claude Plain')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // Omitted, not null: an absent model on create is what "the provider's own default" means.
    expect(createMutate).toHaveBeenCalledWith(
      { name: 'Claude Plain', cli: 'claude', model: undefined },
      expect.any(Object),
    )
  })

  it('resets the model to Provider default when the CLI changes while creating', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.selectOptions(screen.getByLabelText('Model'), 'claude-opus-5')
    expect((screen.getByLabelText('Model') as HTMLSelectElement).value).toBe('claude-opus-5')

    await user.selectOptions(screen.getByLabelText('CLI'), 'codex')

    // Unset — *not* codex's own default model. A runner must not have one chosen on its behalf.
    const modelSelect = screen.getByLabelText('Model') as HTMLSelectElement
    expect(modelSelect.value).toBe('')
    expect(optionsOf(modelSelect)).toEqual(['Provider default', 'GPT-5.6-Sol', 'GPT-5.4-Mini'])
  })

  it('offers and keeps a runner whose model the catalog does not declare', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    // The list says which runners need attention without opening each one.
    expect(screen.getByText('claude-3-legacy-9')).toBeInTheDocument()
    expect(screen.getByText('Unrecognised')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit Claude Legacy' }))
    const modelSelect = screen.getByLabelText('Model') as HTMLSelectElement
    expect(modelSelect.value).toBe('claude-3-legacy-9')
    expect(optionsOf(modelSelect)).toEqual([
      'Provider default',
      'claude-3-legacy-9 — unrecognised',
      'Opus 5',
      'Sonnet 5',
      'Haiku 4.5',
      'opus — latest (now Opus 5)',
      'sonnet — latest (now Sonnet 5)',
      'haiku — latest (now Haiku 4.5)',
    ])

    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateMutate).toHaveBeenCalledWith(
      { id: 'runner-legacy', updates: { name: 'Claude Legacy', model: 'claude-3-legacy-9' } },
      expect.any(Object),
    )
  })

  it('sends an explicit null when a runner is moved back to Provider default', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'Edit Claude Opus' }))
    expect((screen.getByLabelText('Model') as HTMLSelectElement).value).toBe('claude-opus-5')

    await user.selectOptions(screen.getByLabelText('Model'), '')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // `undefined` would be dropped by JSON.stringify and read by the Hub as "leave it alone".
    expect(updateMutate).toHaveBeenCalledWith(
      { id: 'runner-opus', updates: { name: 'Claude Opus', model: null } },
      expect.any(Object),
    )
  })

  it('reads the Hub refusal inside the dialog, which keeps what was entered', async () => {
    const user = userEvent.setup()
    // The exact body F173 was reported against.
    refuseCreate = new ApiError(400, JSON.stringify({ detail: "'opus' is not a model 'claude' declares" }))
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'Claude Opus 5')
    await user.selectOptions(screen.getByLabelText('Model'), 'claude-opus-5')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent("'opus' is not a model 'claude' declares")
    // The dialog stays open holding the values that were refused, so the operator edits rather
    // than retypes.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect((screen.getByPlaceholderText('e.g. Claude Opus') as HTMLInputElement).value).toBe('Claude Opus 5')
    expect((screen.getByLabelText('Model') as HTMLSelectElement).value).toBe('claude-opus-5')
  })

  it('reads a Pydantic refusal, which the deleted local helper could not', async () => {
    const user = userEvent.setup()
    refuseCreate = new ApiError(
      422,
      JSON.stringify({ detail: [{ type: 'value_error', loc: ['body', 'name'], msg: 'Value error, A runner name may not be blank.' }] }),
    )
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('A runner name may not be blank.')
  })

  it('does not show the previous refusal when New Runner is reopened', async () => {
    const user = userEvent.setup()
    refuseCreate = new ApiError(400, JSON.stringify({ detail: "'opus' is not a model 'claude' declares" }))
    render(<RunnersPage />)

    await user.click(screen.getByRole('button', { name: 'New Runner' }))
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'Claude Opus 5')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'New Runner' }))

    // The mutation outlives the dialog, so without a reset the refusal is on screen before
    // anything has been submitted.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('opens a runner stored as a declared alias with the alias option selected and no unrecognised marker (design test 6)', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)

    const row = screen.getByText('Claude Code — opus (latest)').closest('.row-group') as HTMLElement
    expect(within(row).queryByText('Unrecognised')).not.toBeInTheDocument()

    await user.click(within(row).getByRole('button', { name: 'Edit Claude Code — opus (latest)' }))
    const modelSelect = screen.getByLabelText('Model') as HTMLSelectElement
    expect(modelSelect.value).toBe('opus')
    expect(optionsOf(modelSelect)).not.toContain('opus — unrecognised')
  })

  it('rebinds an agent to a different runner', async () => {
    const user = userEvent.setup()
    render(<AgentSettingsPage agent="claude" section="execution" />)

    await user.selectOptions(screen.getByLabelText('Runner for claude'), 'runner-opus')
    expect(bindMutate).toHaveBeenCalledWith({ agent: 'claude', runnerId: 'runner-opus' })
  })
})
