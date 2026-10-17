import { useLayoutEffect, useRef, type ReactNode } from 'react'

/**
 * Content that opens by animating its height (grid rows 0fr -> 1fr), so a panel of any size opens
 * without a measured jump. While closed it is `inert` and hidden from screen readers, so nothing
 * inside it can take the keyboard. (`inert` is set through the DOM: React 18 has no typed prop.)
 */
export function Expander({
  open,
  id,
  children,
}: {
  open: boolean
  id?: string
  children: ReactNode
}) {
  const inner = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const node = inner.current
    if (!node) return
    if (open) node.removeAttribute('inert')
    else node.setAttribute('inert', '')
  }, [open])
  return (
    <div className="aw-expander" data-open={open ? 'true' : 'false'} id={id} aria-hidden={!open}>
      <div ref={inner}>{children}</div>
    </div>
  )
}
