import { create } from 'zustand'
import { projectDestination, goTo } from '@/lib/navigation'

/** What a screen outside the traces view asks it to open filtered to: the runs of a build, of a
 *  task, of an agent since a day. Only the fields given narrow the list. */
export interface TracesRequest {
  build?: string
  task?: string
  agent?: string
  /** An ISO date-time; runs that started at or after it. */
  since?: string
  /** What the filtered list is called while it is in force ("Build 2", "task AW-5"). */
  label?: string
}

interface TracesRequestState {
  /** Set by a run count elsewhere, read by Activity → Traces when it mounts. `nonce` makes two
   *  identical requests in a row still count as two, so the view re-reads the second one. */
  request: (TracesRequest & { nonce: number }) | null
  ask: (request: TracesRequest) => void
  clear: () => void
}

let nonce = 0

export const useTracesRequestStore = create<TracesRequestState>((set) => ({
  request: null,
  ask: (request) => set({ request: { ...request, nonce: ++nonce } }),
  clear: () => set({ request: null }),
}))

/** Follow a run count: ask the traces view for those runs, then go to Activity (which opens on
 *  Traces while a request is waiting). */
export function openTraces(projectId: string, request: TracesRequest): void {
  useTracesRequestStore.getState().ask(request)
  goTo(projectDestination(projectId, 'activity'))
}
