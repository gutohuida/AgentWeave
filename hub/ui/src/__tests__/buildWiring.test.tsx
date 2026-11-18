import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { OpenInBuild } from '@/components/overview/OpenInBuild'
import { BuildViewContainer } from '@/components/builds/BuildViewContainer'
import { summaryOf, taskStateOf, type BuildRead, type BuildRunRead, type BuildTaskRead } from '@/components/builds/buildViewModel'
import { buildDestination, buildHref, parseDestination, serializeDestination } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'

const state = vi.hoisted(() => ({ read: null as unknown, reads: 0 }))

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/builds/build-1/tasks')) {
        state.reads += 1
        return state.read
      }
      if (path.endsWith('/project/builds')) return { builds: [{ id: 'build-1', state: 'running' }, { id: 'build-2', state: 'finished' }] }
      if (path.includes('/traces') || path.includes('/runs/')) return { spans: [], events: [] }
      return []
    }),
  }
})

function run(id: string, over: Partial<BuildRunRead> = {}): BuildRunRead {
  return {
    id,
    role: 'build',
    agent: 'Developer',
    model: 'claude-sonnet-5',
    conversation_id: `conv-${id}`,
    started_at: '2026-11-17T09:00:00Z',
    ended_at: '2026-11-17T09:10:00Z',
    status: 'completed',
    cost_state: 'measured',
    cost_usd_micros: 1_000_000,
    tokens: null,
    moves: [{ from: 'in_progress', to: 'completed' }],
    mend: null,
    ...over,
  }
}

function task(id: string, over: Partial<BuildTaskRead> = {}): BuildTaskRead {
  return {
    id,
    ref: id.toUpperCase(),
    title: `Task ${id}`,
    status: 'in_progress',
    declared: true,
    builder: 'Developer',
    checker: 'QA',
    last_change_at: '2026-11-17T11:00:00Z',
    needs_operator: null,
    requirements: [],
    runs: [],
    send_backs: [],
    ...over,
  }
}

function read(over: Partial<BuildTaskRead> = {}): BuildRead {
  return {
    build: { id: 'build-1', document_id: 'doc-1', document_title: 'A build', document_path: null, state: 'running', level: 'reviewed', created_at: '2026-11-17T08:00:00Z', stopped_at: null, stop_reason: null },
    tasks: [task('a-1'), task('b-2', { runs: [run('r1'), run('r2')], ...over })],
    build_runs: [],
    as_of: '2026-11-17T12:00:00Z',
  }
}

describe('the build view address', () => {
  it('round-trips build, task, run and filter, so a copied address reopens the same view', () => {
    const destination = buildDestination('proj-1', 'build-1', { task: 'B-2', run: 'r2', filter: 'needs-you' })
    const search = serializeDestination(destination)
    expect(search).toContain('view=build')
    expect(parseDestination(search)).toEqual(destination)
  })

  it('leaves out what the address does not name, and falls back to the Spec tab for a bad build id', () => {
    expect(serializeDestination(buildDestination('proj-1', 'build-1'))).toBe('?project=proj-1&tab=spec&view=build&focus=build-1')
    expect(buildDestination('proj-1', 'not a build/id')).toEqual({ kind: 'project', projectId: 'proj-1', tab: 'spec' })
  })

  it('links a summary task to the view at that task', () => {
    expect(buildHref('proj-1', 'build-1', 'B-2')).toContain('view=build&focus=build-1&task=B-2')
  })
})

describe('BuildViewContainer', () => {
  let client: QueryClient
  beforeEach(() => {
    state.reads = 0
    state.read = read()
    useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1' } as never)
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  })
  afterEach(() => vi.restoreAllMocks())

  function mount(address = { task: null as string | null, run: null as string | null, filter: 'all' as const }, onNavigate = vi.fn()) {
    render(
      <QueryClientProvider client={client}>
        <BuildViewContainer projectId="proj-1" buildId="build-1" address={address} onNavigate={onNavigate} />
      </QueryClientProvider>,
    )
    return onNavigate
  }

  it('reads the build from the Hub and lists its tasks once each, in order', async () => {
    mount()
    const section = await screen.findByRole('region', { name: 'Tasks' })
    expect(section).toBeTruthy()
    const buttons = await screen.findAllByRole('button', { name: /^Open runs of/ })
    expect(buttons.map((b) => b.getAttribute('aria-label'))).toEqual(['Open runs of A-1', 'Open runs of B-2'])
  })

  it('expands the task its address names', async () => {
    mount({ task: 'B-2', run: null, filter: 'all' })
    expect(await screen.findByRole('button', { name: /Open trace: Build 1/ })).toBeTruthy()
  })

  it('writes an expanded task to the address by replacing the entry, and a run by adding one', async () => {
    const onNavigate = mount({ task: 'B-2', run: null, filter: 'all' })
    await userEvent.click(await screen.findByRole('button', { name: /Open trace: Build 1/ }))
    expect(onNavigate).toHaveBeenCalledWith(buildDestination('proj-1', 'build-1', { task: 'B-2', run: 'r1' }), { replace: false })
  })

  it('shows a task that moves on the next read without a reload', async () => {
    mount()
    await screen.findAllByRole('button', { name: /^Open runs of/ })
    state.read = read({ status: 'completed' })
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['project', 'proj-1', 'builds'] })
    })
    await waitFor(() => expect(state.reads).toBeGreaterThan(1))
    expect(screen.getAllByText(taskStateOf('completed').label).length).toBeGreaterThan(0)
  })

  it('draws the summary from the same read, so its figures equal the view', () => {
    const r = read()
    const s = summaryOf(r, new Date('2026-11-17T12:00:00Z'))
    expect(s.totals.tasks).toBe(r.tasks.length)
  })
})

describe('Open in its build', () => {
  beforeEach(() => useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1' } as never))

  function link(buildId: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <OpenInBuild projectId="proj-1" buildId={buildId} task="B-2" />
      </QueryClientProvider>,
    )
  }

  it('is offered for a running build and opens its view at the task', async () => {
    link('build-1')
    const anchor = await screen.findByRole('link', { name: /Open in its build/ })
    expect(anchor.getAttribute('href')).toContain('view=build&focus=build-1&task=B-2')
  })

  it('is not offered once the build is finished', async () => {
    link('build-2')
    await waitFor(() => expect(screen.queryByRole('link', { name: /Open in its build/ })).toBeNull())
  })
})
