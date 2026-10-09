import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, renderHook, screen, waitFor, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { ApiError } from '@/api/client'

/*
 * A retired requirement stays reachable from its document (F211;
 * `a-documents-rigor-history-and-retired-requirements-are-on-screen`, D3-D5).
 *
 * Coverage leaves retired requirements out, so without this list a retired requirement leaves every
 * screen while work still points at it. The list reads `GET /spec/requirements?document=`, the only
 * read that includes them; a row reads `GET /spec/requirements/{identifier}?document=`.
 *
 * Fixtures are in the order the routes return (F190):
 *  - the list is `order_by(SpecRequirement.identifier)`, a **string** sort, so FR-1, FR-10, FR-2
 *    (`test_the_requirement_list_includes_retired_rows_in_string_order`);
 *  - a detail's evidence is `produced_at, id` ascending, oldest first
 *    (`requirement_evidence.for_requirement`).
 */

let handler: ((event: { type: string; data: unknown }) => void) | null = null
vi.mock('@/hooks/useSSE', () => ({
  useSSE: (fn: (event: { type: string; data: unknown }) => void) => {
    handler = fn
  },
}))

// `getJson`/`postJson` only; `ApiError` and the error readers stay real.
const getJson = vi.fn()
const postJson = vi.fn()
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: (path: string) => getJson(path),
    postJson: (path: string, body?: unknown) => postJson(path, body),
  }
})

let requirementsResult: Record<string, unknown> = {}
const detailResults: Record<string, Record<string, unknown>> = {}
const useSpecRequirementSpy = vi.fn()

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecRequirements: () => requirementsResult,
    useSpecRequirement: (identifier: string, path: string) => {
      useSpecRequirementSpy(identifier, path)
      return detailResults[identifier] ?? { isLoading: true }
    },
  }
})

import { SpecRetiredRequirements } from '@/components/spec/SpecRetiredRequirements'
import { useSetSpecRigor, useSpecEvents } from '@/api/spec'

const PATH = 'spec/changes/demo/spec.json'

function requirement(identifier: string, key: string, state: 'active' | 'retired') {
  return {
    id: `req-${identifier}`,
    identifier,
    key,
    document_id: 'spdoc-1',
    state,
    digest: 'd',
    anchor: identifier,
  }
}

/** In the route's order: a string sort on the identifier. */
const ROUTE_ORDER = [
  requirement('FR-1', 'lists-due', 'active'),
  requirement('FR-10', 'exports-history', 'retired'),
  requirement('FR-2', 'records-watering', 'retired'),
]

function evidence(id: string, summary: string, producedAt: string, reason: string) {
  return {
    id,
    summary,
    kind: 'test',
    locator: null,
    actor_kind: 'agent',
    actor: 'builder',
    run_id: null,
    task_id: 'task-1',
    review_state: 'rejected',
    latest_review: { decision: 'rejected', reason, actor_kind: 'operator', actor: 'operator' },
    produced_at: producedAt,
    footprint: null,
  }
}

function mount(onOpenTasks = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <SpecRetiredRequirements path={PATH} onOpenTasks={onOpenTasks} />
    </QueryClientProvider>,
  )
  return onOpenTasks
}

beforeEach(() => {
  vi.clearAllMocks()
  handler = null
  requirementsResult = { data: { requirements: ROUTE_ORDER } }
  for (const key of Object.keys(detailResults)) delete detailResults[key]
  useConfigStore.setState({ selectedProjectId: 'proj-a', isConfigured: true })
})

describe('SpecRetiredRequirements', () => {
  // 1.6 (D3). The component sorts numerically on purpose; a component that kept the route's
  // string order would list FR-10 first.
  it('counts the retired requirements and lists them in numeric order', async () => {
    mount()

    const toggle = screen.getByTestId('spec-retired-toggle')
    expect(toggle).toHaveTextContent('2 retired requirements')
    expect(screen.queryByTestId('spec-retired-row-FR-2')).not.toBeInTheDocument()

    await userEvent.click(toggle)

    const rows = within(screen.getByTestId('spec-retired-list')).getAllByTestId(/^spec-retired-row-/)
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'spec-retired-row-FR-2',
      'spec-retired-row-FR-10',
    ])
    expect(rows[0]).toHaveTextContent('records-watering')
    expect(rows[1]).toHaveTextContent('exports-history')
    // The active one is not listed here; coverage already shows it.
    expect(screen.queryByTestId('spec-retired-row-FR-1')).not.toBeInTheDocument()
  })

  it('renders nothing when the document has retired nothing', () => {
    requirementsResult = { data: { requirements: [requirement('FR-1', 'lists-due', 'active')] } }
    const client = new QueryClient()
    const { container } = render(
      <QueryClientProvider client={client}>
        <SpecRetiredRequirements path={PATH} />
      </QueryClientProvider>,
    )
    expect(container).toBeEmptyDOMElement()
  })

  // 1.7 (D3). Expanding a row reads its detail, with `document` always passed.
  it('shows the tasks and evidence still pointing at a retired requirement', async () => {
    detailResults['FR-2'] = {
      data: {
        requirement: requirement('FR-2', 'records-watering', 'retired'),
        tasks: [{ id: 'task-1', title: 'Build the watering log', status: 'in_progress', assignee: 'builder' }],
        // Oldest first, as the route returns them; shown in that order, not reversed.
        evidence: [
          evidence('ev-1', 'first run of the suite', '2026-09-20T10:00:00+00:00', 'wrong branch'),
          evidence('ev-2', 'second run of the suite', '2026-09-21T10:00:00+00:00', 'still failing'),
        ],
        coverage: {
          identifier: 'FR-2',
          requirement_id: 'req-FR-2',
          document_id: 'spdoc-1',
          // What `requirement_coverage._state` reports for this detail: its current-digest
          // evidence is all rejected, and that is decided before retirement is looked at.
          // `retired` is only ever the state of a retired requirement nothing serves (below).
          state: 'rejected',
          integration: 'not_applicable',
          evidence_count: 2,
          accepted_count: 0,
          linked_task_ids: ['task-1'],
        },
      },
    }
    const onOpenTasks = mount()

    await userEvent.click(screen.getByTestId('spec-retired-toggle'))
    expect(useSpecRequirementSpy).not.toHaveBeenCalled()
    await userEvent.click(screen.getByTestId('spec-retired-expand-FR-2'))

    expect(useSpecRequirementSpy).toHaveBeenCalledWith('FR-2', PATH)
    expect(useSpecRequirementSpy).not.toHaveBeenCalledWith('FR-10', PATH)

    const detail = screen.getByTestId('spec-retired-detail-FR-2')
    const task = within(detail).getByTestId('spec-retired-task-task-1')
    expect(task).toHaveTextContent('Build the watering log')
    expect(task).toHaveTextContent('in_progress')
    expect(task).toHaveTextContent('builder')

    const pieces = within(detail).getAllByTestId(/^spec-retired-evidence-/)
    expect(pieces.map((piece) => piece.getAttribute('data-testid'))).toEqual([
      'spec-retired-evidence-ev-1',
      'spec-retired-evidence-ev-2',
    ])
    expect(pieces[0]).toHaveTextContent('first run of the suite')
    expect(pieces[0]).toHaveTextContent('rejected')
    expect(pieces[0]).toHaveTextContent('wrong branch')

    // Shown as reported (the spec's "as reported for that requirement"), not overwritten.
    expect(within(detail).getByTestId('spec-retired-coverage-FR-2')).toHaveTextContent(
      'Coverage: rejected',
    )

    await userEvent.click(task.querySelector('button')!)
    expect(onOpenTasks).toHaveBeenCalledWith(['task-1'])
  })

  // The route's other answer for a retired requirement: nothing links to it and nothing proves it
  // (`test_a_retired_requirement_nobody_serves_is_retired_not_unserved`).
  it('shows a retired requirement nothing serves as retired, with no work', async () => {
    detailResults['FR-2'] = {
      data: {
        requirement: requirement('FR-2', 'records-watering', 'retired'),
        tasks: [],
        evidence: [],
        coverage: {
          identifier: 'FR-2',
          requirement_id: 'req-FR-2',
          document_id: 'spdoc-1',
          state: 'retired',
          integration: 'not_applicable',
          evidence_count: 0,
          accepted_count: 0,
          linked_task_ids: [],
        },
      },
    }
    mount()

    await userEvent.click(screen.getByTestId('spec-retired-toggle'))
    await userEvent.click(screen.getByTestId('spec-retired-expand-FR-2'))

    const detail = screen.getByTestId('spec-retired-detail-FR-2')
    expect(within(detail).getByTestId('spec-retired-coverage-FR-2')).toHaveTextContent(
      'Coverage: retired',
    )
    expect(detail).toHaveTextContent('No tasks link to it.')
  })

  // 1.8 (D5, the F197 shape). A failed read says so, with the Hub's words, and never spins.
  it('says the detail could not be loaded, with the body, instead of a skeleton', async () => {
    detailResults['FR-2'] = {
      isError: true,
      error: new ApiError(500, 'database is locked'),
    }
    mount()

    await userEvent.click(screen.getByTestId('spec-retired-toggle'))
    await userEvent.click(screen.getByTestId('spec-retired-expand-FR-2'))

    const detail = screen.getByTestId('spec-retired-detail-FR-2')
    expect(detail).toHaveTextContent('Could not load FR-2')
    expect(detail).toHaveTextContent('database is locked')
    expect(detail.querySelector('.skeleton')).toBeNull()
  })

  it('says the list could not be loaded when the requirements read fails', () => {
    requirementsResult = { isError: true, error: new ApiError(500, 'database is locked') }
    mount()

    const failure = screen.getByTestId('spec-retired-error')
    expect(failure).toHaveTextContent('Could not load')
    expect(failure).toHaveTextContent('database is locked')
  })
})

describe('the new keys refresh', () => {
  function wrapperFor(client: QueryClient) {
    return ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
  }

  // 1.9 (D4). The rigor route and a save that retires a requirement both broadcast `spec_updated`.
  it('invalidates the history, the requirement list and a requirement on spec_updated', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    renderHook(() => useSpecEvents(), { wrapper: wrapperFor(client) })

    handler!({ type: 'spec_updated', data: { path: PATH, rigor: 'gate', project_id: 'proj-a' } })

    const keys = spy.mock.calls.map((c) =>
      JSON.stringify((c[0] as { queryKey: unknown[] }).queryKey),
    )
    expect(keys).toContain(JSON.stringify(['project', 'proj-a', 'specRigorHistory']))
    expect(keys).toContain(JSON.stringify(['project', 'proj-a', 'specRequirements']))
    expect(keys).toContain(JSON.stringify(['project', 'proj-a', 'specRequirement']))
  })

  // 1.10 (D4, operator review LOW). The tab that pressed Confirm does not wait for the broadcast:
  // no SSE event is dispatched here, and the history query still refetches.
  it('refetches the history of the path it changed once a rigor change succeeds', async () => {
    const historyUrl = `/api/v1/projects/proj-a/project/documents/${PATH}/rigor-history`
    getJson.mockImplementation(async () => ({ events: [] }))
    postJson.mockResolvedValue({ path: PATH, rigor: 'gate' })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const { result } = renderHook(
      () => {
        // The history query as the app keys it, read straight from the route.
        useQuery({
          queryKey: ['project', 'proj-a', 'specRigorHistory', PATH],
          queryFn: () => getJson(historyUrl),
        })
        return useSetSpecRigor()
      },
      { wrapper: wrapperFor(client) },
    )

    await waitFor(() => expect(getJson).toHaveBeenCalledTimes(1))

    await act(async () => {
      await result.current.mutateAsync({ path: PATH, rigor: 'gate', reason: 'ready', expectedDigest: 'abc' })
    })

    // Nothing dispatched a `spec_updated`: only the mutation itself can have caused a refetch.
    await waitFor(() => expect(getJson).toHaveBeenCalledTimes(2))
    expect(getJson).toHaveBeenLastCalledWith(historyUrl)
  })
})
