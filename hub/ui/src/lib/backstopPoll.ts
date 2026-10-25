import type { Query } from '@tanstack/react-query'

/** How often a query that the stream keeps fresh retries after a failed read. */
export const BACKSTOP_MS = 30_000

/** `refetchInterval` for data the stream already reports: no polling while reads succeed, one
 *  retry every `BACKSTOP_MS` once a read has failed, until one succeeds. The stream's own reconnect
 *  invalidates every query, so a dropped event is healed there rather than by a steady poll. */
export function backstopAfterFailure(query: Pick<Query, 'state'>): number | false {
  return query.state.status === 'error' ? BACKSTOP_MS : false
}
