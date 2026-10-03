import { useState } from 'react'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { RunnersPage } from '@/components/runners/RunnersPage'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
import { overridesForRunner } from '@/lib/runnerProvider'
import { useConfigStore } from '@/store/configStore'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// `a-copilot-agent-uses-hooks-and-its-own-agents` test 1.14, the runner half (design D7, review
// 2026-09-28 finding 9): a Copilot runner's model provider in runner management and the composer.

const createMutate = vi.fn()
const updateMutate = vi.fn()
let refuseCreate: unknown = null

const PROVIDER = { type: 'anthropic', base_url: 'https://api.anthropic.com', api_key_var: 'MY_ANTHROPIC_KEY' }

// Shaped as `GET /runners` serves them (`RunnerResponse`): `provider_config` is present on every
// row, null when the runner has none.
const RUNNERS = [
  {
    id: 'runner-claude',
    project_id: 'proj-a',
    name: 'Claude Default',
    cli: 'claude',
    model: null,
    flags: null,
    provider_config: null,
    created_at: '2026-10-03T00:00:00Z',
    updated_at: '2026-10-03T00:00:00Z',
    model_unrecognised: false,
  },
  {
    id: 'runner-copilot',
    project_id: 'proj-a',
    name: 'Copilot Auto',
    cli: 'copilot',
    model: 'auto',
    flags: null,
    provider_config: null,
    created_at: '2026-10-03T00:00:00Z',
    updated_at: '2026-10-03T00:00:00Z',
    model_unrecognised: false,
  },
  {
    id: 'runner-byok',
    project_id: 'proj-a',
    name: 'Copilot on Anthropic',
    cli: 'copilot',
    model: 'claude-haiku-4-5-20251001',
    flags: null,
    provider_config: PROVIDER,
    created_at: '2026-10-03T00:00:00Z',
    updated_at: '2026-10-03T00:00:00Z',
    model_unrecognised: false,
  },
]

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: RUNNERS, isLoading: false }),
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
  useUpdateRunner: () => ({ mutate: updateMutate, isPending: false, error: null, reset: vi.fn() }),
  useDeleteRunner: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({
    data: [
      { name: 'byok', status: 'idle', message_count: 0, active_task_count: 0, color_index: 1, runner_id: 'runner-byok' },
      { name: 'plain', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2, runner_id: 'runner-copilot' },
    ],
  }),
}))
vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE, isLoading: false }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const CLAUDE_IDS = ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5-20251001']

/** The options the operator can pick: the placeholder a provider runner shows is disabled. */
function choosable(select: HTMLElement): string[] {
  return [...select.querySelectorAll('option')].filter((o) => !o.disabled).map((o) => o.value)
}

async function openNewCopilotRunner(user: ReturnType<typeof userEvent.setup>) {
  render(<RunnersPage />)
  await user.click(screen.getByRole('button', { name: 'New Runner' }))
  await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), 'Haiku on Anthropic')
  await user.selectOptions(screen.getByLabelText('CLI'), 'copilot')
}

describe('runner management: a Copilot runner on a model provider', () => {
  beforeEach(() => {
    createMutate.mockReset()
    updateMutate.mockReset()
    refuseCreate = null
  })

  it('offers provider fields for a copilot runner only', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)
    await user.click(screen.getByRole('button', { name: 'New Runner' }))

    for (const cli of ['claude', 'codex']) {
      await user.selectOptions(screen.getByLabelText('CLI'), cli)
      expect(screen.queryByLabelText(/model provider/)).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Key variable name')).not.toBeInTheDocument()
    }

    await user.selectOptions(screen.getByLabelText('CLI'), 'copilot')
    await user.click(screen.getByLabelText(/model provider/))
    expect(screen.getByLabelText('Provider')).toHaveValue('anthropic')
    expect(screen.getByLabelText('Base URL')).toHaveAttribute('placeholder', 'https://api.anthropic.com')
    expect(screen.getByLabelText('Key variable name')).toBeInTheDocument()

    // Leaving copilot hides them again, and nothing of the provider is sent.
    await user.selectOptions(screen.getByLabelText('CLI'), 'claude')
    expect(screen.queryByLabelText('Key variable name')).not.toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('e.g. Claude Opus'), '!')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(createMutate.mock.calls[0][0].provider_config).toBeUndefined()
  })

  it('states that the provider takes an API key and a Claude Max subscription cannot be used', async () => {
    const user = userEvent.setup()
    await openNewCopilotRunner(user)
    await user.click(screen.getByLabelText(/model provider/))

    const key = screen.getByLabelText('Key variable name')
    const note = document.getElementById(key.getAttribute('aria-describedby')!.split(' ')[0])!
    expect(note).toHaveTextContent(/API key/)
    expect(note).toHaveTextContent(/A Claude Max subscription cannot be used/)
    expect(note).toHaveTextContent(/Put the key in the Hub's environment and name that variable here/)
  })

  it("offers the claude catalog's ids only once a provider is set, and clears the model on each toggle", async () => {
    const user = userEvent.setup()
    await openNewCopilotRunner(user)
    const model = () => screen.getByLabelText('Model') as HTMLSelectElement

    // Without a provider: Copilot's own models and the unset choice.
    expect(choosable(model())).toEqual(['', 'auto', 'claude-haiku-4.5'])
    await user.selectOptions(model(), 'auto')

    await user.click(screen.getByLabelText(/model provider/))
    expect(model().value).toBe('')
    // Exactly the ids: no "Provider default", no "Latest" alias group, no Copilot model.
    expect(choosable(model())).toEqual(CLAUDE_IDS)
    expect(model().querySelector('optgroup')).toBeNull()
    expect(within(model()).queryByText('Provider default')).not.toBeInTheDocument()

    await user.selectOptions(model(), 'claude-haiku-4-5-20251001')
    await user.click(screen.getByLabelText(/model provider/))
    expect(model().value).toBe('')
    expect(choosable(model())).toEqual(['', 'auto', 'claude-haiku-4.5'])
  })

  it('creates the runner with the provider, its key variable and a Claude API id', async () => {
    const user = userEvent.setup()
    await openNewCopilotRunner(user)
    await user.click(screen.getByLabelText(/model provider/))

    // Save waits for the two things the Hub would refuse without.
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    await user.type(screen.getByLabelText('Key variable name'), 'MY_ANTHROPIC_KEY')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('Model'), 'claude-haiku-4-5-20251001')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // No base_url when left blank: the Hub stores its default address.
    expect(createMutate).toHaveBeenCalledWith(
      {
        name: 'Haiku on Anthropic',
        cli: 'copilot',
        model: 'claude-haiku-4-5-20251001',
        provider_config: { type: 'anthropic', api_key_var: 'MY_ANTHROPIC_KEY' },
      },
      expect.any(Object),
    )
  })

  it("reads the Hub's refusal beside the key field", async () => {
    const user = userEvent.setup()
    // `POST /runners` checks the provider before the model (`_checked_provider`), so a pasted key
    // is refused with this sentence, verbatim from `runner_provider.provider_config_problem`, and
    // as a 400 with a string `detail`.
    const sentence =
      "api_key_var must be the name of an environment variable (capital letters, digits and " +
      "underscores, such as MY_ANTHROPIC_KEY), not the key itself. Put the key in the Hub's " +
      'environment and name that variable here.'
    refuseCreate = new ApiError(400, JSON.stringify({ detail: sentence }))
    await openNewCopilotRunner(user)
    await user.click(screen.getByLabelText(/model provider/))
    await user.type(screen.getByLabelText('Key variable name'), 'sk-ant-not-a-name')
    await user.selectOptions(screen.getByLabelText('Model'), 'claude-haiku-4-5-20251001')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    const alerts = await screen.findAllByRole('alert')
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toHaveTextContent(sentence)
    const key = screen.getByLabelText('Key variable name')
    // Beside the field: described by it, and in the same field group.
    expect(key.getAttribute('aria-describedby')!.split(' ')).toContain(alerts[0].id)
    expect(key.parentElement).toContainElement(alerts[0])
    // The dialog keeps what was entered.
    expect(key).toHaveValue('sk-ant-not-a-name')
  })

  it('opens a provider runner with its provider, and sends null when the provider is turned off', async () => {
    const user = userEvent.setup()
    render(<RunnersPage />)
    await user.click(screen.getByRole('button', { name: 'Edit Copilot on Anthropic' }))

    expect(screen.getByLabelText(/model provider/)).toBeChecked()
    expect(screen.getByLabelText('Key variable name')).toHaveValue('MY_ANTHROPIC_KEY')
    expect(screen.getByLabelText('Base URL')).toHaveValue('https://api.anthropic.com')
    expect(screen.getByLabelText('Model')).toHaveValue('claude-haiku-4-5-20251001')

    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateMutate.mock.calls[0][0]).toEqual({
      id: 'runner-byok',
      updates: {
        name: 'Copilot on Anthropic',
        model: 'claude-haiku-4-5-20251001',
        provider_config: { type: 'anthropic', base_url: 'https://api.anthropic.com', api_key_var: 'MY_ANTHROPIC_KEY' },
      },
    })

    await user.click(screen.getByLabelText(/model provider/))
    await user.selectOptions(screen.getByLabelText('Model'), 'auto')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateMutate.mock.calls[1][0].updates).toEqual({
      name: 'Copilot on Anthropic',
      model: 'auto',
      provider_config: null,
    })
  })

  it('marks a provider runner in the list', () => {
    render(<RunnersPage />)
    const rows = screen.getAllByText(/^(Copilot Auto|Copilot on Anthropic)$/)
    expect(rows).toHaveLength(2)
    expect(screen.getAllByText('Anthropic API')).toHaveLength(1)
    expect(screen.getByText('Anthropic API')).toHaveAttribute(
      'title',
      'Runs go to https://api.anthropic.com with the key in $MY_ANTHROPIC_KEY',
    )
  })
})

describe('the composer for an agent on a provider runner', () => {
  beforeEach(() => {
    cleanup()
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-fresh' }), { status: 200 }),
    )
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  function surface(agent: string) {
    render(
      <NewConversationSurface
        projectId="proj-a"
        projectName="Website"
        agent={agent}
        onChooseAgent={vi.fn()}
        onStarted={vi.fn()}
      />,
    )
  }

  it("offers no model choice and shows the runner's model", () => {
    surface('byok')
    const shown = screen.getByTitle(/^Model: Haiku 4\.5\./)
    expect(shown.tagName).not.toBe('BUTTON')
    expect(shown).toHaveTextContent('Haiku 4.5')
    expect(screen.queryByRole('button', { name: /Model:/ })).not.toBeInTheDocument()
    // Copilot's own controls are still offered.
    expect(screen.getByTitle(/^Permissions:/)).toBeInTheDocument()
  })

  it('still offers the model picker for an agent on a plain Copilot runner', () => {
    surface('plain')
    expect(screen.getByRole('button', { name: /Model:/ })).toHaveTextContent('Auto')
  })

})

describe('overridesForRunner', () => {
  it("drops a stored model on a provider runner, which the Hub would refuse, and keeps the rest", () => {
    const stored = { model: 'auto', permission_mode: 'manual' }
    expect(overridesForRunner(stored, { provider_config: PROVIDER as never })).toEqual({ permission_mode: 'manual' })
    expect(overridesForRunner(stored, { provider_config: null })).toBe(stored)
    expect(overridesForRunner(stored, undefined)).toBe(stored)
  })
})
