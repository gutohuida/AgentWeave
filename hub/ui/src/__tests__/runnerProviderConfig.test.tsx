import { useState } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
import { overridesForRunner } from '@/lib/runnerProvider'
import { useConfigStore } from '@/store/configStore'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

// `a-copilot-agent-uses-hooks-and-its-own-agents` test 1.14, the runner half (design D7, review
// 2026-09-28 finding 9): a Copilot runner's model provider in runner management and the composer.

const createMutate = vi.fn()
const updateMutate = vi.fn()
const refuseCreate: unknown = null

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

// The list counts what uses each runner; the manager's jobs are one of those, not what these test.
vi.mock('@/api/manager', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/manager')>()),
  useManagerJobs: () => ({ data: [] }),
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
