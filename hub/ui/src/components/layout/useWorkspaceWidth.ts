import { useEffect, useState } from 'react'

/**
 * The measured width of a container, or `null` before the first real measurement.
 *
 * Measured rather than taken from the viewport: the Hub rail and any other chrome already consume
 * viewport width, so a media query would report "wide" while the content is actually being
 * crushed. The same measurement decides the layout mode and budgets the pane widths.
 *
 * A zero width means "not laid out yet", not "narrow". Acting on it would flash the overlay before
 * anything has been measured, so it is ignored rather than recorded.
 *
 * Lived in `components/spec/SpecWorkspace.tsx` until the three-column specification workspace was
 * replaced by a conversation with a document panel. The hook outlived the layout that needed it.
 */
export function useWorkspaceWidth(ref: React.RefObject<HTMLElement | null>): number | null {
  const [width, setWidth] = useState<number | null>(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const apply = (measured: number) => {
      if (measured <= 0) return
      setWidth(measured)
    }

    apply(element.getBoundingClientRect().width)

    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) apply(entry.contentRect.width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  return width
}
