import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SetupProfilesDialog } from '@/components/overview/SetupProfilesDialog'
import { describeSetupItem } from '@/components/overview/setupItems'
import type { ProjectSetupItem } from '@/api/projects'

// `profiles-threads-and-builds-everywhere` FR-8, criterion setup-offer-creates-two (dialog half):
// no charter is preselected, a provider and model are chosen for each, the same name twice is
// refused before anything is sent, and confirming sends both profiles in one request. The models
// are the catalog's, not the project's runners (`a-profile-s-pool-and-a-new-chat-can-use-any-model-
// of-any-provider`, FR-9), so a model no runner uses is offered and sent by provider and model.

// The real hook and client, against a stubbed fetch: what reaches the Hub is the request itself.
const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>()
const requests = () =>
  fetchMock.mock.calls.map(([url, init]) => ({
    url,
    method: init.method,
    body: JSON.parse(String(init.body)),
  }))
const model = (id: string, label: string, isDefault = false) => ({ id, label, aliases: [], context_window: null, default: isDefault })
const CATALOG = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [model('claude-opus-5-5', 'Opus 5.5'), model('claude-sonnet-5-5', 'Sonnet 5.5', true), model('claude-haiku-5-5', 'Haiku 5.5')],
      controls: [],
    },
    { provider: 'codex', label: 'Codex', models: [model('gpt-6-luna', 'gpt-6-luna', true)], controls: [] },
    { provider: 'copilot', label: 'Copilot', models: [model('gpt-6', 'GPT-6', true)], controls: [] },
  ],
}
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: CATALOG, isLoading: false, error: null, refetch: vi.fn() }),
}))
vi.mock('@/api/runners', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/runners')>()),
  useProviderLaunchability: () => ({
    data: {
      providers: {
        claude: { runnable: true, present: true, authorized: true },
        codex: { runnable: true, present: true, authorized: true },
        copilot: { runnable: false, present: false, authorized: true, reason: 'Copilot is not installed' },
      },
    },
  }),
}))
vi.mock('@/api/charters', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/charters')>()
  return {
    ...actual,
    useCharters: () => ({
      data: [{ id: 'charter-verifier', name: 'Verifier' }, { id: 'charter-planner', name: 'Planner' }],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    }),
  }
})

function renderDialog(onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SetupProfilesDialog projectId="proj-a" open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  )
  return onOpenChange
}

async function choose(user: ReturnType<typeof userEvent.setup>, testId: string, option: string) {
  await user.click(screen.getByTestId(testId))
  await user.click(await screen.findByRole('menuitemradio', { name: option }))
}

async function rename(user: ReturnType<typeof userEvent.setup>, role: 'builder' | 'checker', name: string) {
  const field = within(screen.getByTestId(`setup-profiles-${role}`)).getByLabelText('Name')
  await user.clear(field)
  await user.type(field, name)
}

const create = () => screen.getByRole('button', { name: 'Create both' })

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('the setup offer', () => {
  it('preselects no charter and no provider, so Create both waits for a model each', () => {
    renderDialog()
    for (const role of ['builder', 'checker']) {
      expect(screen.getByTestId(`setup-profiles-${role}-charter`)).toHaveTextContent('No charter')
      expect(screen.getByTestId(`setup-profiles-${role}-provider`)).toHaveTextContent('Choose a provider…')
      expect(screen.getByTestId(`setup-profiles-${role}-model`)).toBeDisabled()
    }
    expect(create()).toBeDisabled()
  })

  it('uses themed menus only: a provider with its mark, then its catalog models, and a fitting placeholder', async () => {
    const user = userEvent.setup()
    renderDialog()
    expect(document.querySelector('select')).toBeNull()

    await choose(user, 'setup-profiles-builder-provider', 'Claude Code')
    const builder = within(screen.getByTestId('setup-profiles-builder'))
    expect(builder.getByLabelText('Name')).toHaveAttribute('placeholder', 'claude-builder')
    expect(screen.getByTestId('setup-profiles-builder-provider').querySelector('[title="Claude Code"]')).not.toBeNull()
    // The catalog default is chosen with the provider.
    expect(screen.getByTestId('setup-profiles-builder-model')).toHaveTextContent('Sonnet 5.5')
    await user.click(screen.getByTestId('setup-profiles-builder-model'))
    expect(screen.getAllByRole('menuitemradio').map((item) => item.textContent)).toEqual(['Opus 5.5', 'Sonnet 5.5', 'Haiku 5.5'])
    await user.keyboard('{Escape}')

    await choose(user, 'setup-profiles-builder-provider', 'Codex')
    expect(builder.getByLabelText('Name')).toHaveAttribute('placeholder', 'codex-builder')
    expect(screen.getByTestId('setup-profiles-builder-model')).toHaveTextContent('gpt-6-luna')

    // A provider whose CLI cannot run here is listed, not choosable, saying why.
    await user.click(screen.getByTestId('setup-profiles-builder-provider'))
    expect(screen.getByRole('menuitemradio', { name: /Copilot/ })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('Copilot is not installed')).toBeInTheDocument()
  })

  it('creates Builder on Opus 5.5 and Checker on Sonnet 5.5 with Verifier, by model, in one request', async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          builder: { id: 'agent-1', name: 'Builder', runner_id: 'runner-haiku', charter_id: null, color_index: 0 },
          checker: { id: 'agent-2', name: 'Checker', runner_id: 'runner-sonnet', charter_id: 'charter-verifier', color_index: 1 },
        }),
        { status: 201 },
      ),
    )
    const onOpenChange = renderDialog()

    await rename(user, 'builder', 'Builder')
    await rename(user, 'checker', 'Checker')
    await choose(user, 'setup-profiles-builder-provider', 'Claude Code')
    await choose(user, 'setup-profiles-builder-model', 'Opus 5.5')
    await choose(user, 'setup-profiles-checker-provider', 'Claude Code')
    await choose(user, 'setup-profiles-checker-model', 'Sonnet 5.5')
    await choose(user, 'setup-profiles-checker-charter', 'Verifier')
    expect(fetchMock).not.toHaveBeenCalled()
    await user.click(create())

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(requests()).toEqual([
      {
        url: expect.stringMatching(/\/api\/v1\/projects\/proj-a\/setup\/profiles$/),
        method: 'POST',
        body: {
          builder: { name: 'Builder', charter_id: null, provider: 'claude', model: 'claude-opus-5-5' },
          checker: { name: 'Checker', charter_id: 'charter-verifier', provider: 'claude', model: 'claude-sonnet-5-5' },
        },
      },
    ])
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('refuses the same name for both before sending anything', async () => {
    const user = userEvent.setup()
    renderDialog()

    await rename(user, 'builder', 'Solo')
    await rename(user, 'checker', 'solo')
    await choose(user, 'setup-profiles-builder-provider', 'Claude Code')
    await choose(user, 'setup-profiles-checker-provider', 'Claude Code')

    expect(screen.getByText('The builder already has this name.')).toBeInTheDocument()
    expect(create()).toBeDisabled()
    await user.click(create())
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows the Hub’s refusal and stays open', async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "The builder: Agent name 'Builder' already exists in this project" }), {
        status: 409,
      }),
    )
    const onOpenChange = renderDialog()

    await choose(user, 'setup-profiles-builder-provider', 'Claude Code')
    await choose(user, 'setup-profiles-checker-provider', 'Claude Code')
    await user.click(create())

    expect(await screen.findByTestId('setup-profiles-error')).toHaveTextContent("Agent name 'Builder' already exists")
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })
})

describe('the profiles setup item', () => {
  it('can be dismissed and opens the offer', () => {
    const onOffer = vi.fn()
    const item: ProjectSetupItem = {
      id: 'profiles',
      key: 'profiles',
      dismissable: true,
      agent: null,
      provider: null,
      reason: null,
      detail: null,
    }
    const described = describeSetupItem(item, 'proj-a', onOffer)
    expect(described.dismissable).toBe(true)
    expect(described.title).toBe('Add a builder and a checker')
    described.action.onClick()
    expect(onOffer).toHaveBeenCalledTimes(1)
  })
})
