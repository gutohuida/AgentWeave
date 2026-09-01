import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { RunnersPage } from '@/components/runners/RunnersPage'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

const createMutate = vi.fn()
const updateMutate = vi.fn()
const bindMutate = vi.fn()

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
    ],
    isLoading: false,
  }),
  useCreateRunner: () => ({ mutate: createMutate, isPending: false }),
  useUpdateRunner: () => ({ mutate: updateMutate, isPending: false }),
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
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

function optionsOf(select: HTMLElement): (string | null)[] {
  return [...select.querySelectorAll('option')].map((option) => option.textContent)
}

describe('runner management UI', () => {
  beforeEach(() => {
    createMutate.mockReset()
    updateMutate.mockReset()
    bindMutate.mockReset()
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
    expect(optionsOf(modelSelect)).toEqual(['Provider default', 'Opus 5', 'Sonnet 5', 'Haiku 4.5'])
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

  it('rebinds an agent to a different runner', async () => {
    const user = userEvent.setup()
    render(<AgentSettingsPage agent="claude" section="execution" />)

    await user.selectOptions(screen.getByLabelText('Runner for claude'), 'runner-opus')
    expect(bindMutate).toHaveBeenCalledWith({ agent: 'claude', runnerId: 'runner-opus' })
  })
})
