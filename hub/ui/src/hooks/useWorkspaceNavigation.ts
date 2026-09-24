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

/** The address as it actually reads today: pathname plus search. A destination is always
 *  serialized against the root (`canonicalUrl` below), so any other pathname — a deep link whose
 *  shape this app doesn't parse, or one left over from before this canonicalisation existed — is
 *  itself part of what makes the address non-canonical, not just its query. */
function currentAddress(): string {
  return typeof window === 'undefined' ? '' : `${window.location.pathname}${window.location.search}`
}

function resolveFromLocation(options: ResolveDestinationOptions): WorkspaceDestination {
  return resolveDestination(parseDestination(currentSearch()), options)
}

/** The one shape a destination is ever written to the address bar as: `/` plus its query, dropping
 *  any pathname the request arrived with. The app has no router dependency (design.md decision 9)
 *  — `main.py` serves `index.html` for any path — so a pathname is never meaningful state, only
 *  ever a leftover that would otherwise survive a `replaceState` targeting a bare `?…` query. */
function canonicalUrl(destination: WorkspaceDestination): string {
  return `/${serializeDestination(destination)}`
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
    const target = canonicalUrl(resolved)
    if (target !== currentAddress()) {
      window.history.replaceState(null, '', target)
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

  /** `replace` is for a destination the operator did not ask for — resolving "this agent" to its
   *  most recent conversation, say. Pushing that would put the same conversation behind Back. */
  const navigate = useCallback(
    (next: WorkspaceDestination, options?: { replace?: boolean }) => {
      const resolved = resolveDestination(next, { availableProjectIds, lastOpenedProjectId })
      const url = canonicalUrl(resolved)
      if (options?.replace) window.history.replaceState(null, '', url)
      else window.history.pushState(null, '', url)
      setDestination(resolved)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [availableProjectIds === null ? null : availableProjectIds.join(','), lastOpenedProjectId],
  )

  return { destination, navigate }
}
