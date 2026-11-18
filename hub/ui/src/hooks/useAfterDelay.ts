import { useEffect, useState } from 'react'

/** True once `ms` has passed since mount. A spec page's first reads share the browser's few
 *  connections to the Hub with every other read it fires, so work the open page does not draw at
 *  first is started after the page's own reads (the build strip) have had their turn. */
export function useAfterDelay(ms: number): boolean {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const t = window.setTimeout(() => setReady(true), ms)
    return () => window.clearTimeout(t)
  }, [ms])
  return ready
}

/** How long the open spec page's own reads go first, before background reads start. */
export const BACKGROUND_READ_DELAY_MS = 3000
