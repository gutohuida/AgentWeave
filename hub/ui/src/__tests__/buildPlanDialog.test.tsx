/**
 * The Build dialog (`the-build-dialog-redesigned`, FR-1 to FR-8), rendered through the container
 * (`SpecPhaseBar` → `useSpecPhaseControls`), fed the document read's real payload: the declared
 * tasks ride in the page's `aw-spec-payload` block, the recommendation in `recommended_build`, and
 * what the dialog sends is read off the body the mocked build route receives.
 */
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { useConfigStore } from '@/store/configStore'
import type { SpecRecommendedBuild } from '@/api/spec'

const PATH = 'spec/changes/demo/spec.json'
const posts: Array<{ path: string; body: Record<string, unknown> }> = []
let recommended: SpecRecommendedBuild

const TASKS = [
  { key: 'alpha-key', title: 'Alpha thing' },
  { key: 'beta-key', title: 'Beta thing' },
  { key: 'gamma-key', title: 'Gamma thing' },
]

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
    task_builders: { 'alpha-key': 'dev', 'beta-key': 'ops', 'gamma-key': 'dev' },
    task_checkers: { 'alpha-key': 'qa', 'beta-key': 'qa', 'gamma-key': 'ops' },
    task_reasons: {
      'alpha-key': { builder: 'dev knows the module.', checker: 'qa reviewed the last slice.' },
      'beta-key': { builder: 'ops owns the deploy.' },
      'gamma-key': {},
    },
    reasons: {},
  }
}

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  const payload = JSON.stringify({
    title: 'Demo',
    tasks: [
      { key: 'alpha-key', title: 'Alpha thing' },
      { key: 'beta-key', title: 'Beta thing' },
      { key: 'gamma-key', title: 'Gamma thing' },
    ],
  })
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/loops')) return []
      if (path.includes('/project/spec?')) {
        return {
          path: 'spec/changes/demo/spec.json',
          content: `<script id="aw-spec-payload" type="application/json">${payload}</script>`,
          updated_at: '2026-11-03T00:00:00Z',
          content_version: 'v1',
          recommended_build: (globalThis as { __recommended?: unknown }).__recommended,
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
              updated_at: '2026-11-03T00:00:00Z',
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
  // `ghost` is archived: the Hub lists open agents only.
  useAgents: () => ({
    data: [
      { name: 'dev', color_index: 0, context_usage: { model: 'sonnet-5-5' } },
      { name: 'qa', color_index: 1 },
      { name: 'ops', color_index: 2 },
    ],
    isError: false,
  }),
}))

beforeEach(() => {
  posts.length = 0
  ;(globalThis as { __posts?: unknown[] }).__posts = posts
  recommended = recommendation()
  ;(globalThis as { __recommended?: unknown }).__recommended = recommended
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
  return screen.findByRole('dialog')
}

const trigger = (dialog: HTMLElement, name: string) => within(dialog).getByRole('button', { name })
const row = (dialog: HTMLElement, title: string) =>
  within(dialog).getByText(title).closest('[role="row"]') as HTMLElement

async function pick(dialog: HTMLElement, name: string, agent: string) {
  await userEvent.click(trigger(dialog, name))
  await userEvent.click(screen.getByRole('menuitemradio', { name: new RegExp(`^${agent}`) }))
}

describe('the Build dialog', () => {
  it('one row per declared task, by title', async () => {
    const dialog = await openDialog()
    expect(within(dialog).getByRole('heading', { name: 'How it runs' })).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'Who builds and checks' })).toBeInTheDocument()
    for (const task of TASKS) {
      const line = row(dialog, task.title)
      expect(within(line).getByRole('button', { name: `${task.title}: builder` })).toBeInTheDocument()
      expect(within(line).getByRole('button', { name: `${task.title}: checker` })).toBeInTheDocument()
      expect(within(dialog).queryByText(task.key)).not.toBeInTheDocument()
    }
    expect(within(dialog).getAllByRole('row')).toHaveLength(1 + TASKS.length)
  })

  it('opens on the recommendation with its reasons', async () => {
    const dialog = await openDialog()
    expect(trigger(dialog, 'Alpha thing: builder')).toHaveTextContent('dev')
    expect(trigger(dialog, 'Beta thing: builder')).toHaveTextContent('ops')
    expect(trigger(dialog, 'Gamma thing: checker')).toHaveTextContent('ops')
    expect(within(dialog).getByText('dev knows the module.')).toBeInTheDocument()
    expect(within(dialog).getByText('qa reviewed the last slice.')).toBeInTheDocument()
    expect(within(dialog).getByText('ops owns the deploy.')).toBeInTheDocument()
    // Beta's checker and both of Gamma's picks are recommended without a reason.
    expect(within(dialog).getAllByText(/No reason given/)).toHaveLength(3)
  })

  it('a changed pick names the recommendation and puts it back', async () => {
    const dialog = await openDialog()
    expect(within(dialog).getByText('As the document recommends.')).toBeInTheDocument()

    await pick(dialog, 'Alpha thing: builder', 'ops')

    const alpha = row(dialog, 'Alpha thing')
    expect(alpha).toHaveTextContent('Recommended dev')
    expect(trigger(dialog, 'Alpha thing: builder')).toHaveTextContent('ops')
    expect(within(dialog).getByText('One task differs from the recommendation.')).toBeInTheDocument()

    await userEvent.click(within(alpha).getByRole('button', { name: 'Put back' }))
    expect(trigger(dialog, 'Alpha thing: builder')).toHaveTextContent('dev')
    expect(within(dialog).getByText('As the document recommends.')).toBeInTheDocument()
  })

  it('a recommended agent that is not open is not chosen', async () => {
    recommended.task_builders = { ...recommended.task_builders, 'gamma-key': 'ghost' }
    const dialog = await openDialog()

    expect(trigger(dialog, 'Gamma thing: builder')).toHaveTextContent('Default (dev)')
    expect(row(dialog, 'Gamma thing')).toHaveTextContent('Recommended ghost is not an open agent here.')

    await userEvent.click(within(dialog).getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect((posts[0]!.body.task_builders as Record<string, string>)['gamma-key']).toBe('')
  })

  it('a task cannot check its own work', async () => {
    const dialog = await openDialog()
    const confirm = within(dialog).getByTestId('build-confirm')
    expect(confirm).toBeEnabled()

    await pick(dialog, 'Alpha thing: checker', 'dev')

    expect(row(dialog, 'Alpha thing')).toHaveTextContent('Checks its own work')
    expect(within(dialog).getByText(/One task has the same agent building and checking/)).toBeInTheDocument()
    expect(confirm).toBeDisabled()

    await pick(dialog, 'Alpha thing: checker', 'qa')
    expect(row(dialog, 'Alpha thing')).not.toHaveTextContent('Checks its own work')
    expect(confirm).toBeEnabled()
  })

  it('confirming unchanged sends the recommendation', async () => {
    const dialog = await openDialog()
    await userEvent.click(within(dialog).getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.path).toContain('/documents/build?')
    expect(posts[0]!.body).toEqual({
      driver: 'flow',
      level: 'reviewed',
      builders: ['dev', 'ops'],
      builder: 'dev',
      checker: 'qa',
      landing: 'main',
      task_builders: { 'alpha-key': 'dev', 'beta-key': 'ops', 'gamma-key': 'dev' },
      task_checkers: { 'alpha-key': 'qa', 'beta-key': 'qa', 'gamma-key': 'ops' },
    })
    expect(posts[0]!.body).not.toHaveProperty('delivery_agent')
  })

  it('Fast hides the checkers', async () => {
    const dialog = await openDialog()
    expect(trigger(dialog, 'Default checker')).toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('radio', { name: 'Fast' }))

    expect(within(dialog).queryByRole('button', { name: 'Default checker' })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: /: checker$/ })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('columnheader', { name: 'Checker' })).not.toBeInTheDocument()

    await userEvent.click(within(dialog).getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0]!.body.level).toBe('fast')
    expect(posts[0]!.body.checker).toBe('')
    expect(posts[0]!.body.task_checkers).toEqual({})
  })

  it('themed controls only', async () => {
    const dialog = await openDialog()
    expect(
      dialog.querySelectorAll('select, input[type="checkbox"], input[type="date"], input[type="datetime-local"]'),
    ).toHaveLength(0)

    await userEvent.click(trigger(dialog, 'Default builder'))
    const options = screen.getAllByRole('menuitemradio')
    const agents = options.filter((option) => /^(dev|qa|ops)/.test(option.textContent ?? ''))
    expect(agents).toHaveLength(3)
    for (const option of agents) expect(option.querySelector('.aw-bp-dot')).not.toBeNull()
    expect(options.find((option) => /^dev/.test(option.textContent ?? ''))).toHaveTextContent('sonnet-5-5')
  })
})
