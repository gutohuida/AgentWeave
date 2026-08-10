import { useCallback, useRef } from 'react'

interface PaneResizerProps {
  /** Current width of the pane this divider sizes, in px. */
  width: number
  onChange: (width: number) => void
  /** Restored on double-click. */
  defaultWidth: number
  min: number
  max: number
  label?: string
  /**
   * The element the width is measured inside. Omitted, the width is measured from the viewport's
   * left edge — correct for the Hub rail, which starts there, and wrong for any pane that does
   * not. The specification workspace sits to the right of that rail, so its dividers pass the
   * workspace container and get a width that means the same thing whatever is left of it.
   */
  containerRef?: React.RefObject<HTMLElement | null>
  /**
   * Which side of the divider the sized pane is on. `left` is the default and grows rightward;
   * `right` grows leftward and is measured from the container's right edge, so a chat pane on
   * the far side reports its own width rather than everything to its left.
   */
  side?: 'left' | 'right'
}

/**
 * The boundary between two panes.
 *
 * The resizer owns the dividing line rather than either pane owning a border, for two reasons:
 * the panes then share one ground plane with a single separation signal, and hover feedback on
 * the boundary comes for free.
 *
 * The hit area is deliberately wider than the visible line — you should not
 * have to hit a 1px target. The line itself stays 1px and only changes colour,
 * so nothing reflows while you aim at it.
 */
export function PaneResizer({
  width,
  onChange,
  defaultWidth,
  min,
  max,
  label = 'Resize navigation',
  containerRef,
  side = 'left',
}: PaneResizerProps) {
  const dragging = useRef(false)

  const clamp = useCallback(
    (value: number) => Math.min(max, Math.max(min, value)),
    [min, max],
  )

  /** Pointer position -> the width of the pane this divider sizes. */
  const widthAt = useCallback(
    (clientX: number) => {
      const bounds = containerRef?.current?.getBoundingClientRect()
      if (!bounds) return clientX
      return side === 'right' ? bounds.right - clientX : clientX - bounds.left
    },
    [containerRef, side],
  )

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true
    // Pointer capture keeps the drag alive when the pointer outruns the 11px
    // strip. Guarded because it is absent in jsdom and in older engines, where
    // dragging still works — it just stops if the pointer leaves the element.
    try {
      e.currentTarget.setPointerCapture?.(e.pointerId)
    } catch {
      /* capture unavailable; drag degrades gracefully */
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return
    onChange(clamp(widthAt(e.clientX)))
  }

  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return
    dragging.current = false
    try {
      if (e.currentTarget.hasPointerCapture?.(e.pointerId)) {
        e.currentTarget.releasePointerCapture?.(e.pointerId)
      }
    } catch {
      /* nothing to release */
    }
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  // Keyboard resizing keeps the control operable without a pointer. The arrow keys move the
  // divider, not the number: on a pane that grows leftward, ArrowLeft makes it wider, so the
  // key and the thing on screen agree.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const step = (e.shiftKey ? 32 : 8) * (side === 'right' ? -1 : 1)
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      onChange(clamp(width - step))
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      onChange(clamp(width + step))
    } else if (e.key === 'Home') {
      e.preventDefault()
      onChange(defaultWidth)
    }
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      data-testid="pane-resizer"
      className="workspace-resizer group relative z-20 w-[11px] shrink-0 cursor-col-resize
                 focus-visible:outline-none"
      style={{ marginLeft: -5, marginRight: -5 }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={() => onChange(defaultWidth)}
      onKeyDown={handleKeyDown}
    >
      {/* The 1px line. Only its colour changes, so aiming at it shifts nothing. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-[5px] w-px
                   transition-colors duration-base ease-smooth
                   group-hover:bg-[var(--ring)] group-focus-visible:bg-[var(--ring)]"
        style={{ background: 'var(--border-region)' }}
      />
    </div>
  )
}
