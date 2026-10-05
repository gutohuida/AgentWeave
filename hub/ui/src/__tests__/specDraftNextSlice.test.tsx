/**
 * "Draft the next slice" beside Approve (`a-spec-is-written-one-slice-at-a-time`, task 6.3).
 *
 * Fed through the real `useSpec`/`useSpecDocuments`/`useSetSpecPhase` hooks with `getJson`/`postJson`
 * mocked by path, as `specApprovalDelivery.test.tsx` does. `roadmap_slice` is what `GET /spec`
 * returns for a document that names a roadmap slice, and is absent on every other document.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { useConfigStore } from '@/store/configStore'

const PATH = 'spec/changes/slice-one/spec.html'
const posts: Array<{ path: string; body: Record<string, unknown> }> = []
let roadmapSlice: { document: string; slice: string } | undefined
let approveResponse: Record<string, unknown> = {}

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/loops')) return []
      if (path.includes('/project/spec?')) {
        return {
          path: PATH,
          content: '<html></html>',
          updated_at: '2026-10-05T00:00:00Z',
          ...(roadmapSlice ? { roadmap_slice: roadmapSlice } : {}),
        }
      }
      if (path.includes('/documents')) {
        return {
          documents: [
            {
              id: 'spdoc-1',
              path: PATH,
              title: 'Slice one',
              kind: 'change-spec',
              phase: 'proposed',
              rigor: 'sketch',
              content_digest: null,
              explore_closed: true,
              updated_at: '2026-10-05T00:00:00Z',
            },
          ],
        }
      }
      return []
    }),
    postJson: vi.fn(async (path: string, body: Record<string, unknown>) => {
      posts.push({ path, body })
      return approveResponse
    }),
  }
})
vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'planner' }], isError: false }),
}))

function renderPhaseBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={PATH} />
    </QueryClientProvider>,
  )
}

function approvals() {
  return posts.filter((post) => post.path.includes('/documents/phase') && post.path.includes('to=approved'))
}

beforeEach(() => {
  posts.length = 0
  roadmapSlice = undefined
  approveResponse = {}
  useConfigStore.setState({ selectedProjectId: 'proj-test', isConfigured: true } as never)
})

afterEach(() => cleanup())

describe('Draft the next slice', () => {
  it('is offered, on by default, for a document that names a roadmap slice, and travels with Approve', async () => {
    roadmapSlice = { document: 'spec/changes/the-plan/spec.html', slice: 's1' }
    renderPhaseBar()

    const box = (await screen.findByLabelText('Draft the next slice')) as HTMLInputElement
    expect(box.checked).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(approvals()).toHaveLength(1))
    expect(approvals()[0].body.draft_next_slice).toBe(true)
  })

  it('sends false when the operator unticks it', async () => {
    roadmapSlice = { document: 'spec/changes/the-plan/spec.html', slice: 's1' }
    renderPhaseBar()

    fireEvent.click(await screen.findByLabelText('Draft the next slice'))
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(approvals()).toHaveLength(1))
    expect(approvals()[0].body.draft_next_slice).toBe(false)
  })

  it('is absent, and never sent, for a document that names no roadmap slice', async () => {
    renderPhaseBar()

    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(approvals()).toHaveLength(1))
    expect(screen.queryByLabelText('Draft the next slice')).toBeNull()
    expect('draft_next_slice' in approvals()[0].body).toBe(false)
  })

  it('says what the approval did about the next slice', async () => {
    roadmapSlice = { document: 'spec/changes/the-plan/spec.html', slice: 's1' }
    approveResponse = { next_slice: { state: 'queued', slice: 's2', agent: 'planner' } }
    renderPhaseBar()

    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))

    expect(await screen.findByTestId('next-slice-outcome')).toHaveTextContent(
      'Asked @planner to draft slice s2.',
    )
  })

  it('says the next slice waits for the open tasks', async () => {
    roadmapSlice = { document: 'spec/changes/the-plan/spec.html', slice: 's1' }
    approveResponse = {
      next_slice: { state: 'waiting', slice: 's2', agent: 'planner', open_tasks: 2 },
    }
    renderPhaseBar()

    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))

    expect(await screen.findByTestId('next-slice-outcome')).toHaveTextContent(
      "@planner will be asked to draft slice s2 once this slice's 2 open tasks are approved or rejected.",
    )
  })
})
