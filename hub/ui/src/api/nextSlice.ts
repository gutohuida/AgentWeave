import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** A built roadmap slice whose next slice's drafting is offered (`hub/hub/slice_drafting.py`, D6):
 *  derived on read, so it is listed until the operator takes or declines it, or a document claims
 *  the next slice. Nothing is queued until it is taken. */
export interface NextSliceOffer {
  /** The document of the last slice this one builds after; null when it builds after none. */
  document: string | null
  document_id: string | null
  title: string | null
  roadmap: string
  roadmap_title: string
  /** The last slice it builds after; null when it builds after none. */
  approved_slice: { key: string; title?: string | null } | null
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
      (await getJson<{ offers: NextSliceOffer[] }>(`/api/v1/projects/${projectId}/project/next-slice-offers`, { background: true }))
        .offers,
    enabled: isConfigured && !!projectId,
  })
}

/** What a take or decline names: the roadmap and the slice offered (an offer may build after no
 *  slice, or after one that is not adjacent, so a document path cannot address it). */
export interface OfferTarget {
  roadmap: string
  slice: string
}

export function offerTarget(offer: NextSliceOffer): OfferTarget {
  return { roadmap: offer.roadmap, slice: offer.next_slice.key }
}

/** Stable key for one offer. */
export function offerKey(offer: NextSliceOffer): string {
  return `${offer.roadmap}#${offer.next_slice.key}`
}

function useOfferAnswer<TArgs extends OfferTarget, TResult = unknown>(
  call: (projectId: string, args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (args: TArgs) => call(projectId ?? '', args),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'nextSliceOffers'] }),
  })
}

/** What a take answers: the slice's change document, created before the turn was queued, and the
 *  conversation the drafting turn runs in (`every-spec-entry-point-leads-into-the-journey`, FR-1). */
export interface TakenOffer {
  state: string
  agent: string
  conversation_id: string | null
  entry_id: string
  document: string
}

/** Draft: create the slice's document and queue the drafting turn to the chosen agent. */
export function useTakeNextSliceOffer() {
  return useOfferAnswer<OfferTarget & { agent: string }, TakenOffer>((projectId, { roadmap, slice, agent }) =>
    postJson<TakenOffer>(`/api/v1/projects/${projectId}/project/documents/next-slice/take`, {
      path: roadmap,
      slice,
      agent,
    }),
  )
}

/** Not now: hide the offer for that slice. */
export function useDeclineNextSliceOffer() {
  return useOfferAnswer<OfferTarget>((projectId, { roadmap, slice }) =>
    postJson(`/api/v1/projects/${projectId}/project/documents/next-slice/decline`, {
      path: roadmap,
      slice,
    }),
  )
}

/** What the offer reads as, in one line. */
export function offerTitle(offer: NextSliceOffer): string {
  const next = offer.next_slice.title || offer.next_slice.key
  return offer.approved_slice
    ? `Slice ${offer.approved_slice.key} is built: draft ${next}?`
    : `Draft ${next}?`
}
