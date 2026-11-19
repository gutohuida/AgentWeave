/**
 * The Build dialog's model per task (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-
 * its-pool`, FR-6, criterion build-prefills-recommendation), rendered through the container
 * (`SpecPhaseBar` → `useSpecPhaseControls`) so the pools come from the agents read, the runners
 * read and the catalog as the app fetches them, and what the dialog sends is read off the body the
 * mocked build route receives.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { useConfigStore } from '@/store/configStore'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { SpecRecommendedBuild } from '@/api/spec'

const PATH = 'spec/changes/demo/spec.json'
const posts: Array<{ path: string; body: Record<string, unknown> }> = []

const RUNNERS = [
  { id: 'r-haiku', name: 'Claude Haiku', cli: 'claude', model: 'claude-haiku-5-5' },
  { id: 'r-sonnet', name: 'Claude Sonnet', cli: 'claude', model: 'claude-sonnet-5-5' },
  { id: 'r-opus', name: 'Claude Opus', cli: 'claude', model: 'claude-opus-5-5' },
]

const CATALOG = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [
        { id: 'claude-haiku-5-5', label: 'Haiku 5.5', aliases: [] },
        { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5', aliases: [] },
        { id: 'claude-opus-5-5', label: 'Opus 5.5', aliases: [] },
      ],
      controls: [
        {
          id: 'effort',
          label: 'Effort',
          values: [
            { id: 'medium', label: 'Medium' },
            { id: 'high', label: 'High' },
          ],
        },
      ],
    },
  ],
}

function entry(id: string, runner: (typeof RUNNERS)[number], effort: string | null, isDefault: boolean): AgentPoolEntry {
  return { id, runner_id: runner.id, runner_name: runner.name, cli: 'claude', model: runner.model, effort, default: isDefault }
}

// dev may run on Haiku (default) and Sonnet high; qa on Sonnet only. Neither holds Opus.
const DEV_POOL = [entry('p-1', RUNNERS[0]!, null, true), entry('p-2', RUNNERS[1]!, 'high', false)]
const QA_POOL = [entry('p-3', RUNNERS[1]!, null, true)]

function recommendation(): SpecRecommendedBuild {
  return {
    mode: 'flow',
    agent: 'dev',
    reviewer: 'qa',
    tester: null,
    cron: '*/10 * * * *',
    stop_when_queue_empties: true,
    stop_at: null,
    driver: 'flow',
    level: 'reviewed',
    builders: [],
    reviewers: [],
    lead: null,
    budget_cap_usd: null,
    landing: 'main',
    builder: 'dev',
    checker: 'qa',
    task_builders: { 'in-pool': 'dev', 'out-of-pool': 'dev' },
    task_checkers: { 'in-pool': 'qa', 'out-of-pool': 'qa' },
    task_reasons: { 'in-pool': {}, 'out-of-pool': {} },
    // The first recommends an entry dev's pool holds; the second one it does not.
    task_builder_entries: {
      'in-pool': { runner_id: 'r-sonnet', effort: 'high' },
      'out-of-pool': { runner_id: 'r-opus', effort: null },
    },
    task_checker_entries: { 'in-pool': null, 'out-of-pool': null },
    reasons: {},
  }
}

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  const payload = JSON.stringify({
    title: 'Demo',
    tasks: [
      { key: 'in-pool', title: 'In pool' },
      { key: 'out-of-pool', title: 'Out of pool' },
    ],
  })
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      const g = globalThis as { __runners?: unknown; __catalog?: unknown; __recommended?: unknown }
      if (path.includes('/loops')) return []
      if (path.endsWith('/runners')) return g.__runners
      if (path.includes('/model-catalog')) return g.__catalog
      if (path.includes('/project/spec?')) {
        return {
          path: 'spec/changes/demo/spec.json',
          content: `<script id="aw-spec-payload" type="application/json">${payload}</script>`,
          updated_at: '2026-11-19T00:00:00Z',
          content_version: 'v1',
          recommended_build: g.__recommended,
        }
      }
      if (path.includes('/documents')) {
        return {
          documents: [
            {
              id: 'spdoc-1',
              path: 'spec/changes/demo/spec.json',
              title: 'Demo',
              kind: 'change-spec',
              phase: 'approved',
              rigor: 'contract',
              content_digest: null,
              explore_closed: true,
              updated_at: '2026-11-19T00:00:00Z',
            },
          ],
        }
      }
      return []
    }),
    postJson: vi.fn(async (path: string, body: Record<string, unknown>) => {
      ;(globalThis as { __posts?: unknown[] }).__posts?.push({ path, body })
      return { id: 'job-new', build_outcome: { flow: { state: 'created', messages: [] } } }
    }),
  }
})
vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [
      { name: 'dev', color_index: 0, pool: DEV_POOL },
      { name: 'qa', color_index: 1, pool: QA_POOL },
    ],
    isError: false,
  }),
}))

beforeEach(() => {
  posts.length = 0
  const g = globalThis as { __posts?: unknown[]; __runners?: unknown; __catalog?: unknown; __recommended?: unknown }
  g.__posts = posts
  g.__runners = RUNNERS
  g.__catalog = CATALOG
  g.__recommended = recommendation()
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})
afterEach(cleanup)

async function openDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={PATH} />
    </QueryClientProvider>,
  )
  await userEvent.click(await screen.findByRole('button', { name: 'Build…' }))
  const dialog = await screen.findByRole('dialog')
  // The pools arrive with the agents, runners and catalog reads.
  await within(dialog).findByRole('button', { name: 'In pool: builder’s model' })
  return dialog
}

const row = (dialog: HTMLElement, title: string) =>
  within(dialog).getByText(title).closest('[role="row"]') as HTMLElement

async function options(dialog: HTMLElement, name: string): Promise<string[]> {
  await userEvent.click(within(dialog).getByRole('button', { name }))
  const listed = screen.getAllByRole('menuitemradio').map((item) => item.textContent ?? '')
  await userEvent.keyboard('{Escape}')
  return listed
}

describe('the Build dialog’s model per task', () => {
  it('prefills the recommendation in the pool, and the default for one outside it', async () => {
    const dialog = await openDialog()

    expect(within(dialog).getByRole('button', { name: 'In pool: builder’s model' })).toHaveTextContent('Sonnet 5.5 · High')
    expect(within(dialog).getByRole('button', { name: 'Out of pool: builder’s model' })).toHaveTextContent('Haiku 5.5')
    expect(row(dialog, 'Out of pool')).toHaveTextContent('Recommended Opus 5.5 is not one of dev’s models; it runs on the default.')
    expect(row(dialog, 'In pool')).not.toHaveTextContent('is not one of')
  })

  it('each dropdown lists exactly its profile’s pool', async () => {
    const dialog = await openDialog()

    for (const name of ['In pool: builder’s model', 'Out of pool: builder’s model']) {
      const listed = await options(dialog, name)
      expect(listed).toHaveLength(DEV_POOL.length)
      expect(listed[0]).toMatch(/^Haiku 5\.5/)
      expect(listed[1]).toMatch(/^Sonnet 5\.5 · High/)
      expect(listed.join(' ')).not.toMatch(/Opus/)
    }
    // qa's pool is one entry: shown as a fact, not a choice.
    expect(within(dialog).queryByRole('button', { name: 'In pool: checker’s model' })).not.toBeInTheDocument()
    expect(row(dialog, 'In pool')).toHaveTextContent('Sonnet 5.5')
  })

  it('sends every task’s entry, as shown', async () => {
    const dialog = await openDialog()
    await userEvent.click(within(dialog).getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(1))

    expect(posts[0]!.body.task_builder_entries).toEqual({
      'in-pool': { runner_id: 'r-sonnet', effort: 'high' },
      'out-of-pool': { runner_id: 'r-haiku', effort: null },
    })
    expect(posts[0]!.body.task_checker_entries).toEqual({
      'in-pool': { runner_id: 'r-sonnet', effort: null },
      'out-of-pool': { runner_id: 'r-sonnet', effort: null },
    })
  })

  it('a pick replaces the recommendation and can be put back', async () => {
    const dialog = await openDialog()
    await userEvent.click(within(dialog).getByRole('button', { name: 'In pool: builder’s model' }))
    await userEvent.click(screen.getByRole('menuitemradio', { name: /^Haiku 5\.5/ }))

    expect(row(dialog, 'In pool')).toHaveTextContent('Recommended Sonnet 5.5 · High')
    await userEvent.click(within(row(dialog, 'In pool')).getByRole('button', { name: 'Put back' }))
    expect(within(dialog).getByRole('button', { name: 'In pool: builder’s model' })).toHaveTextContent('Sonnet 5.5 · High')
  })

  it('an older Hub with no pools names agents only and sends no entries', async () => {
    const agents = await import('@/api/agents')
    vi.spyOn(agents, 'useAgents').mockReturnValue({
      data: [{ name: 'dev', color_index: 0 }, { name: 'qa', color_index: 1 }],
      isError: false,
    } as unknown as ReturnType<typeof agents.useAgents>)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SpecPhaseBar path={PATH} />
      </QueryClientProvider>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Build…' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByRole('button', { name: /model$/ })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.body).not.toHaveProperty('task_builder_entries')
  })
})
