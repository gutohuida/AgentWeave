import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  offerKey,
  offerTarget,
  offerTitle,
  useDeclineNextSliceOffer,
  useTakeNextSliceOffer,
  type NextSliceOffer,
} from '@/api/nextSlice'

/**
 * `a-roadmap-that-is-recognisably-a-roadmap`: an offer is for a slice of a roadmap, so the take and
 * decline the Overview sends name the roadmap and the slice (`hub/tests/test_slice_progress.py`
 * answers that body). An offer with no builds-after has no document and no approved slice.
 */
const postJson = vi.fn()

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  postJson: (...args: unknown[]) => postJson(...args),
}))
vi.mock('@/store/configStore', () => ({
  useConfigStore: () => ({ isConfigured: true, selectedProjectId: 'proj-1' }),
}))

const ROADMAP = 'spec/changes/the-plan/spec.json'

function offer(over: Partial<NextSliceOffer>): NextSliceOffer {
  return {
    document: 'spec/changes/one/spec.json',
    document_id: 'spdoc-1',
    title: 'One',
    roadmap: ROADMAP,
    roadmap_title: 'The plan',
    approved_slice: { key: 's1', title: 'One' },
    next_slice: { key: 's3', title: 'Three' },
    agent: 'architect',
    conversation_id: null,
    requested: false,
    tasks: [],
    ...over,
  }
}

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
}

beforeEach(() => {
  postJson.mockReset()
  postJson.mockResolvedValue({})
})

describe('answering a next-slice offer', () => {
  it('takes a non-adjacent slice by roadmap and slice', async () => {
    const { result } = renderHook(() => useTakeNextSliceOffer(), { wrapper })
    result.current.mutate({ ...offerTarget(offer({})), agent: 'builder' })
    await waitFor(() => expect(postJson).toHaveBeenCalled())
    expect(postJson).toHaveBeenCalledWith(
      '/api/v1/projects/proj-1/project/documents/next-slice/take',
      { path: ROADMAP, slice: 's3', agent: 'builder' },
    )
  })

  it('declines a slice that builds after nothing without reading its missing document', async () => {
    const free = offer({
      document: null,
      document_id: null,
      title: null,
      approved_slice: null,
      next_slice: { key: 's5', title: 'Five' },
    })
    expect(offerTitle(free)).toBe('Draft Five?')
    const { result } = renderHook(() => useDeclineNextSliceOffer(), { wrapper })
    result.current.mutate(offerTarget(free))
    await waitFor(() => expect(postJson).toHaveBeenCalled())
    expect(postJson).toHaveBeenCalledWith(
      '/api/v1/projects/proj-1/project/documents/next-slice/decline',
      { path: ROADMAP, slice: 's5' },
    )
  })

  it('keys two offers of one roadmap apart', () => {
    expect(offerKey(offer({}))).not.toBe(offerKey(offer({ next_slice: { key: 's5' } })))
  })
})
