/**
 * The Build dialog's settings (`a-build-has-a-driver-a-level-and-its-people`, criterion
 * `build-dialog-prefilled`): each setting is filled in from the recommendation, each task shows its
 * declared builder, and submitting sends exactly the shown settings.
 *
 * `RECOMMENDED` is the document read's real payload: `recommended_build` as `GET /project/spec`
 * returned it for a document recommending a lead-driven Fast build (captured from the Hub's own
 * route, `_recommended_build`, not hand-shaped -- F190), and the header's build strip reads
 * `builds[0]` as that read lists them.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuildDialog } from '@/components/spec/BuildDialog'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { useConfigStore } from '@/store/configStore'
import type { BuildChoices, SpecBuild, SpecRecommendedBuild } from '@/api/spec'

/** `recommended_build`, as the route answered it. */
const RECOMMENDED: SpecRecommendedBuild = {
  mode: 'flow',
  agent: 'dev',
  reviewer: 'qa',
  tester: null,
  cron: '*/10 * * * *',
  stop_when_queue_empties: true,
  stop_at: null,
  driver: 'lead',
  level: 'fast',
  builders: ['dev'],
  reviewers: ['qa'],
  lead: 'lead',
  budget_cap_usd: 5.0,
  landing: 'main',
  task_builders: { t1: 'dev', t2: null },
  reasons: { lead: 'lead knows this code.', level: 'A small change, low risk.' },
}

const RUNNING: SpecBuild = {
  id: 'build-1',
  state: 'running',
  driver: 'lead',
  level: 'fast',
  builders: ['dev'],
  reviewers: ['qa'],
  lead: 'lead',
  budget_cap_usd: 5,
  spent_usd: 1.2,
  unpriced_turns: 0,
  window_start: null,
  window_end: null,
  landing: 'main',
  loop_id: 'loop-1',
  stop_reason: null,
  created_at: '2026-10-27T10:00:00+00:00',
  stopped_at: null,
}

const posts: Array<{ path: string; body: unknown }> = []
const patches: Array<{ path: string; body: unknown }> = []
let builds: SpecBuild[] = []

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/loops')) return []
      if (path.includes('/project/spec?')) {
        return {
          path: 'spec/changes/demo/spec.json',
          content: '<html></html>',
          updated_at: '2026-10-27T00:00:00Z',
          content_version: 'v1',
          recommended_build: RECOMMENDED,
          builds,
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
              rigor: 'sketch',
              content_digest: null,
              explore_closed: true,
              updated_at: '2026-10-27T00:00:00Z',
            },
          ],
        }
      }
      return []
    }),
    postJson: vi.fn(async (path: string, body: unknown) => {
      posts.push({ path, body })
      return { build_outcome: { flow: { state: 'created', messages: ['started'] } } }
    }),
    patchJson: vi.fn(async (path: string, body: unknown) => {
      patches.push({ path, body })
      return RUNNING
    }),
  }
})
vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [{ name: 'dev' }, { name: 'lead' }, { name: 'qa' }],
    isError: false,
  }),
}))

beforeEach(() => {
  posts.length = 0
  patches.length = 0
  builds = []
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})
afterEach(cleanup)

function renderDialog(onConfirm: (choices: BuildChoices) => void) {
  return render(
    <BuildDialog
      title="Demo"
      approve={false}
      recommended={RECOMMENDED}
      openAgents={['dev', 'lead', 'qa']}
      isPending={false}
      error={null}
      onCancel={() => {}}
      onConfirm={onConfirm}
    />,
  )
}

describe('BuildDialog', () => {
  it('opens with every setting the recommendation names, and each task with its builder', () => {
    renderDialog(() => {})

    expect(screen.getByTestId('build-driver')).toHaveValue('lead')
    expect(screen.getByTestId('build-lead')).toHaveValue('lead')
    expect(screen.getByTestId('build-level')).toHaveValue('fast')
    expect(screen.getByTestId('build-builders-dev')).toBeChecked()
    expect(screen.getByTestId('build-builders-qa')).not.toBeChecked()
    expect(screen.getByTestId('build-reviewers-qa')).toBeChecked()
    expect(screen.getByTestId('build-cap')).toHaveValue('5')
    expect(screen.getByTestId('build-landing')).toHaveValue('main')
    expect(screen.getByTestId('build-task-builder-t1')).toHaveValue('dev')
    expect(screen.getByTestId('build-task-builder-t2')).toHaveValue('')
    expect(screen.getByTestId('build-reason-level')).toHaveTextContent('low risk')
    expect(screen.getByTestId('build-reason-lead')).toHaveTextContent('lead knows this code.')
  })

  it('sends exactly the settings shown', () => {
    const onConfirm = vi.fn()
    renderDialog(onConfirm)

    fireEvent.click(screen.getByTestId('build-confirm'))

    expect(onConfirm).toHaveBeenCalledWith({
      driver: 'lead',
      lead: 'lead',
      level: 'fast',
      builders: ['dev'],
      reviewers: ['qa'],
      budget_cap_usd: 5,
      landing: 'main',
      task_builders: { t1: 'dev', t2: '' },
    })
  })

  it('sends what the operator changed: a level, a builder, a task builder, the cap and landing', () => {
    const onConfirm = vi.fn()
    renderDialog(onConfirm)

    fireEvent.change(screen.getByTestId('build-driver'), { target: { value: 'flow' } })
    fireEvent.change(screen.getByTestId('build-level'), { target: { value: 'gated' } })
    fireEvent.click(screen.getByTestId('build-builders-qa'))
    fireEvent.change(screen.getByTestId('build-task-builder-t2'), { target: { value: 'qa' } })
    fireEvent.change(screen.getByTestId('build-cap'), { target: { value: '12.5' } })
    fireEvent.change(screen.getByTestId('build-landing'), { target: { value: 'nowhere' } })
    fireEvent.click(screen.getByTestId('build-confirm'))

    expect(onConfirm).toHaveBeenCalledWith({
      driver: 'flow',
      level: 'gated',
      builders: ['dev', 'qa'],
      reviewers: ['qa'],
      budget_cap_usd: 12.5,
      landing: 'nowhere',
      task_builders: { t1: 'dev', t2: 'qa' },
    })
  })

  it('refuses to send a lead build with no lead, or a cap that is not a number', () => {
    renderDialog(() => {})
    fireEvent.change(screen.getByTestId('build-lead'), { target: { value: '' } })
    expect(screen.getByTestId('build-confirm')).toBeDisabled()
    fireEvent.change(screen.getByTestId('build-lead'), { target: { value: 'lead' } })
    fireEvent.change(screen.getByTestId('build-cap'), { target: { value: 'lots' } })
    expect(screen.getByTestId('build-confirm')).toBeDisabled()
  })
})

function renderPhaseBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path="spec/changes/demo/spec.json" />
    </QueryClientProvider>,
  )
}

describe('Build on the spec header', () => {
  it('posts the settings the dialog showed to the build route', async () => {
    renderPhaseBar()

    fireEvent.click(await screen.findByRole('button', { name: 'Build…' }))
    const dialog = await screen.findByTestId('build-dialog')
    await waitFor(() => expect(within(dialog).getByTestId('build-driver')).toHaveValue('lead'))
    fireEvent.click(within(dialog).getByTestId('build-confirm'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].path).toContain('/documents/build?')
    expect(posts[0].body).toEqual({
      driver: 'lead',
      lead: 'lead',
      level: 'fast',
      builders: ['dev'],
      reviewers: ['qa'],
      budget_cap_usd: 5,
      landing: 'main',
      task_builders: { t1: 'dev', t2: '' },
    })
  })

  it('shows the running build, its spend of its cap, and raises the cap', async () => {
    builds = [RUNNING]
    renderPhaseBar()

    const strip = await screen.findByTestId('spec-build-status')
    expect(strip).toHaveTextContent('driven by a lead')
    expect(strip).toHaveTextContent('fast')
    expect(within(strip).getByTestId('spec-build-spend')).toHaveTextContent('$1.20 of $5.00')
    fireEvent.click(within(strip).getByTestId('spec-build-raise'))
    fireEvent.change(within(strip).getByTestId('spec-build-cap'), { target: { value: '10' } })
    fireEvent.click(within(strip).getByTestId('spec-build-cap-save'))

    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].path).toContain('/project/builds/build-1')
    expect(patches[0].body).toEqual({ budget_cap_usd: 10 })
    fireEvent.click(within(strip).getByTestId('spec-build-stop'))
    await waitFor(() => expect(posts.some((post) => post.path.endsWith('/builds/build-1/stop'))).toBe(true))
  })
})
