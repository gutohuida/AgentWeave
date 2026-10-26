import { ApiError } from '@/api/client'

/** What a many-key read answers: each found key's body, and the keys it does not have. */
export interface ManyAnswer<V> {
  found: Record<string, V>
  missing: string[]
}

/**
 * Per-key reads issued in the same tick, sent as one request.
 *
 * Each caller still reads one key, under its own query key, with its own invalidation and refetch;
 * only the transport is shared. The rail mounts one conversation listing per registered project in
 * one commit, so opening the app sent one request per project (25 on the trial Hub, queued six at a
 * time behind each other). Now those reads leave together.
 *
 * A key read alone — an event refreshing one project's listing — goes to the single-key route, as
 * it did before, and so does every key when the many-key request fails. A key the many-key route
 * reports missing is refused as the single-key route refuses it, with a 404, so callers cannot
 * tell the two transports apart.
 */
export function coalescedReads<V>(
  readOne: (key: string) => Promise<V>,
  readMany: (keys: string[]) => Promise<ManyAnswer<V>>,
  missingDetail: (key: string) => string,
): (key: string) => Promise<V> {
  let waiting: Map<string, Array<{ resolve: (value: V) => void; reject: (error: unknown) => void }>> | null = null

  const flush = () => {
    const batch = waiting
    waiting = null
    if (!batch) return
    const keys = [...batch.keys()]
    const settle = (key: string, outcome: { value: V } | { error: unknown }) => {
      for (const caller of batch.get(key) ?? []) {
        if ('value' in outcome) caller.resolve(outcome.value)
        else caller.reject(outcome.error)
      }
    }
    if (keys.length === 1) {
      readOne(keys[0]).then(
        (value) => settle(keys[0], { value }),
        (error) => settle(keys[0], { error }),
      )
      return
    }
    readMany(keys).then(
      (answer) => {
        // An answer without the expected shape is read key by key below, never taken as "none".
        const found = answer?.found ?? {}
        const missing = answer?.missing ?? []
        for (const key of keys) {
          if (Object.prototype.hasOwnProperty.call(found, key)) settle(key, { value: found[key] })
          else if (missing.includes(key)) {
            settle(key, { error: new ApiError(404, JSON.stringify({ detail: missingDetail(key) })) })
          } else {
            // Not answered either way: read it on its own rather than invent an answer.
            readOne(key).then(
              (value) => settle(key, { value }),
              (error) => settle(key, { error }),
            )
          }
        }
      },
      // A Hub without the many-key route (a bundle reloaded before its Hub restarted onto the code
      // that serves it) still answers every key from its own route, as before.
      () =>
        keys.forEach((key) =>
          readOne(key).then(
            (value) => settle(key, { value }),
            (error) => settle(key, { error }),
          ),
        ),
    )
  }

  return (key: string) =>
    new Promise<V>((resolve, reject) => {
      if (!waiting) {
        waiting = new Map()
        // A macrotask, not a microtask: the reads one render mounts start across several effects,
        // and all of them have run before the next task.
        setTimeout(flush, 0)
      }
      const callers = waiting.get(key) ?? []
      callers.push({ resolve, reject })
      waiting.set(key, callers)
    })
}

/** One coalescer per group (a lifecycle, a project), created on first use. */
export function coalescedReadsByGroup<V>(
  make: (group: string) => (key: string) => Promise<V>,
): (group: string, key: string) => Promise<V> {
  const groups = new Map<string, (key: string) => Promise<V>>()
  return (group, key) => {
    let read = groups.get(group)
    if (!read) {
      read = make(group)
      groups.set(group, read)
    }
    return read(key)
  }
}
