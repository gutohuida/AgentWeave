import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** A built roadmap slice whose next slice's drafting is offered (`hub/hub/slice_drafting.py`, D6):
 *  derived on read, so it is listed until the operator takes or declines it, or a document claims
 *  the next slice. Nothing is queued until it is taken. */
export interface NextSliceOffer {
  /** The slice document's path. */
  document: string
  document_id: string
  title: string
  roadmap: string
  roadmap_title: string
  approved_slice: { key: string; title?: string | null }
  next_slice: { key: string; title?: string | null; intent?: string | null; done?: string | null }
  /** The document's author, preselected as the agent that drafts it; null when none wrote it. */
  agent: string | null
  conversation_id: string | null
  /** Recorded as an approval-time request before offers replaced it. */
  requested: boolean
  tasks: string[]
}

/** Every offer in the project. SSE (`next_slice_offered`, `next_slice_answered`) invalidates it. */
export function useNextSliceOffers() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<NextSliceOffer[]>({
    queryKey: ['project', projectId, 'nextSliceOffers'],
    queryFn: async () =>
      (await getJson<{ offers: NextSliceOffer[] }>(`/api/v1/projects/${projectId}/project/next-slice-offers`))
        .offers,
    enabled: isConfigured && !!projectId,
  })
}

function useOfferAnswer<TArgs extends { path: string }>(
  call: (projectId: string, args: TArgs) => Promise<unknown>,
) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (args: TArgs) => call(projectId ?? '', args),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'nextSliceOffers'] }),
  })
}

/** Draft: queue the drafting turn to the chosen agent. */
export function useTakeNextSliceOffer() {
  return useOfferAnswer<{ path: string; agent: string }>((projectId, { path, agent }) =>
    postJson(
      `/api/v1/projects/${projectId}/project/documents/next-slice/take?path=${encodeURIComponent(path)}`,
      { agent },
    ),
  )
}

/** Not now: hide the offer for that slice. */
export function useDeclineNextSliceOffer() {
  return useOfferAnswer<{ path: string }>((projectId, { path }) =>
    postJson(
      `/api/v1/projects/${projectId}/project/documents/next-slice/decline?path=${encodeURIComponent(path)}`,
      {},
    ),
  )
}

/** What the offer reads as, in one line. */
export function offerTitle(offer: NextSliceOffer): string {
  const next = offer.next_slice.title || offer.next_slice.key
  return `Slice ${offer.approved_slice.key} is built: draft ${next}?`
}
