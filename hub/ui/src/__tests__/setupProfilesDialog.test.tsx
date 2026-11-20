import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SetupProfilesDialog } from '@/components/overview/SetupProfilesDialog'
import { describeSetupItem } from '@/components/overview/setupItems'
import type { ProjectSetupItem } from '@/api/projects'

// `profiles-threads-and-builds-everywhere` FR-8, criterion setup-offer-creates-two (dialog half):
// no charter is preselected, a runner is chosen for each, the same name twice is refused before
// anything is sent, and confirming sends both profiles in one request.

// The real hook and client, against a stubbed fetch: what reaches the Hub is the request itself.
const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>()
const requests = () =>
  fetchMock.mock.calls.map(([url, init]) => ({
    url,
    method: init.method,
    body: JSON.parse(String(init.body)),
  }))
let runners: { id: string; name: string }[] = []
vi.mock('@/api/runners', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/runners')>()
  return { ...actual, useRunners: () => ({ data: runners, isLoading: false, error: null, refetch: vi.fn() }) }
})
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
  runners = [
    { id: 'runner-haiku', name: 'Claude Code — Haiku' },
    { id: 'runner-sonnet', name: 'Claude Code — Sonnet' },
  ]
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('the setup offer', () => {
  it('preselects no charter and no runner, so Create both waits for a runner each', () => {
    renderDialog()
    for (const role of ['builder', 'checker']) {
      expect(screen.getByTestId(`setup-profiles-${role}-charter`)).toHaveTextContent('No charter')
      expect(screen.getByTestId(`setup-profiles-${role}-runner`)).toHaveTextContent('Choose a runner…')
    }
    expect(create()).toBeDisabled()
  })

  it('creates Builder with no charter and Checker with Verifier, one runner each, in one request', async () => {
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
    await choose(user, 'setup-profiles-builder-runner', 'Claude Code — Haiku')
    await choose(user, 'setup-profiles-checker-runner', 'Claude Code — Sonnet')
    await choose(user, 'setup-profiles-checker-charter', 'Verifier')
    expect(fetchMock).not.toHaveBeenCalled()
    await user.click(create())

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(requests()).toEqual([
      {
        url: expect.stringMatching(/\/api\/v1\/projects\/proj-a\/setup\/profiles$/),
        method: 'POST',
        body: {
          builder: { name: 'Builder', charter_id: null, runner_id: 'runner-haiku' },
          checker: { name: 'Checker', charter_id: 'charter-verifier', runner_id: 'runner-sonnet' },
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
    await choose(user, 'setup-profiles-builder-runner', 'Claude Code — Haiku')
    await choose(user, 'setup-profiles-checker-runner', 'Claude Code — Haiku')

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

    await choose(user, 'setup-profiles-builder-runner', 'Claude Code — Haiku')
    await choose(user, 'setup-profiles-checker-runner', 'Claude Code — Haiku')
    await user.click(create())

    expect(await screen.findByTestId('setup-profiles-error')).toHaveTextContent("Agent name 'Builder' already exists")
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  it('with no runners says so and points to where one is added', () => {
    runners = []
    renderDialog()
    expect(screen.getByTestId('setup-profiles-no-runners')).toHaveTextContent('no runners yet')
    expect(screen.getByRole('button', { name: 'Add a runner in Project settings' })).toBeInTheDocument()
    expect(create()).toBeDisabled()
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
