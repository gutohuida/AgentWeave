import * as React from 'react'
import { useTracesRequestStore, type TracesRequest } from '@/store/tracesRequestStore'
import { TracesPage } from './TracesPage'

/** The project-wide Traces view as Project settings › Traces hosts it (leaner-navigation FR-14).
 *  A run count elsewhere asks for its runs through the store; the request is taken into local
 *  state and cleared from the store at once, so leaving and coming back does not reopen the
 *  filtered list. `focus` is the address's run list (URL `focus`): the first run it names. */
export function TracesBrowser({ focus = null }: { focus?: string | null }) {
  const waiting = useTracesRequestStore((state) => state.request)
  const [applied, setApplied] = React.useState<(TracesRequest & { nonce: number }) | null>(() => {
    const run = focus?.split(',').find(Boolean)
    return run ? { run, label: `run ${run}`, nonce: 0 } : null
  })
  if (waiting && waiting.nonce !== applied?.nonce) setApplied(waiting)
  React.useEffect(() => {
    if (waiting) useTracesRequestStore.getState().clear()
  }, [waiting])
  return <TracesPage key={applied?.nonce ?? 0} request={applied} />
}
