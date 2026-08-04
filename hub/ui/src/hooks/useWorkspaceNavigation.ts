import { useCallback, useEffect, useState } from 'react'
import {
  parseDestination,
  resolveDestination,
  serializeDestination,
  type ResolveDestinationOptions,
  type WorkspaceDestination,
} from '@/lib/navigation'

function currentSearch(): string {
  return typeof window === 'undefined' ? '' : window.location.search
}

function resolveFromLocation(options: ResolveDestinationOptions): WorkspaceDestination {
  return resolveDestination(parseDestination(currentSearch()), options)
}

/** Drives `WorkspaceDestination` from `window.location`'s search parameters
 * using `history.pushState`/`popstate` (design.md decision 9) — no routing
 * dependency. A destination whose project turns out not to be registered is
 * corrected via `replaceState` (not a new history entry) as soon as the
 * collection is known. */
export function useWorkspaceNavigation(options: ResolveDestinationOptions) {
  const { availableProjectIds, lastOpenedProjectId } = options
  const [destination, setDestination] = useState<WorkspaceDestination>(() =>
    resolveFromLocation(options),
  )

  useEffect(() => {
    // Compare against the actual URL, not the previous state value: fallback
    // resolution is deterministic, so a state value already computed via
    // resolveFromLocation always equals a freshly recomputed one even when
    // the URL itself still holds the unresolved (invalid) request.
    const resolved = resolveFromLocation({ availableProjectIds, lastOpenedProjectId })
    const target = serializeDestination(resolved)
    if (target !== currentSearch()) {
      window.history.replaceState(null, '', target || window.location.pathname)
    }
    setDestination((current) =>
      JSON.stringify(current) === JSON.stringify(resolved) ? current : resolved,
    )
    // availableProjectIds is compared by content, not identity, since callers
    // typically pass a fresh array each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableProjectIds === null ? null : availableProjectIds.join(','), lastOpenedProjectId])

  useEffect(() => {
    const onPopState = () => {
      setDestination(resolveFromLocation({ availableProjectIds, lastOpenedProjectId }))
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableProjectIds === null ? null : availableProjectIds.join(','), lastOpenedProjectId])

  const navigate = useCallback(
    (next: WorkspaceDestination) => {
      const resolved = resolveDestination(next, { availableProjectIds, lastOpenedProjectId })
      const target = serializeDestination(resolved)
      window.history.pushState(null, '', target || window.location.pathname)
      setDestination(resolved)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [availableProjectIds === null ? null : availableProjectIds.join(','), lastOpenedProjectId],
  )

  return { destination, navigate }
}
