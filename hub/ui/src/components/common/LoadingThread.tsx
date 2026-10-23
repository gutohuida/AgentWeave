import { useId, type CSSProperties } from 'react'

/** The two drawings of the loop (brand/identity-record.md §4): master for 48px and up, small for
 *  16–32px. Path A runs from the left end up into the loop; path B runs out of it to the right end. */
const DRAWINGS = {
  master: {
    stroke: 5.5,
    gap: 9.5,
    a: 'M9 15 L21 50 L34 21 C38.6 12.5 37.6 6 32 6',
    b: 'M32 6 C26.4 6 25.4 12.5 30 21 L43 50 L55 15',
  },
  small: {
    stroke: 8,
    gap: 16,
    a: 'M7 18 L19 54 L33.5 25 C40 14 39.5 6 32 6',
    b: 'M32 6 C24.5 6 24 14 30.5 25 L45 54 L57 18',
  },
} as const

const SIZES = { panel: 64, inline: 24, control: 16 } as const

// Written out in full: Tailwind keeps a layered class only if it finds the whole name in the source,
// so a class assembled from the size at runtime is dropped from the build.
const SIZE_CLASS = {
  panel: 'aw-loading-thread--panel',
  inline: 'aw-loading-thread--inline',
  control: 'aw-loading-thread--control',
} as const

export type LoadingThreadSize = keyof typeof SIZES

/**
 * The brand's loading motion: the loop's thread weaves through — it draws in from the left end,
 * through the loop, to the right end, then its tail follows it out (`aw-weave-a`/`aw-weave-b` in
 * index.css; the operator's pick, the-thread-is-how-agentweave-shows-it-is-loading). The crossing
 * cut runs with path B, so the gap opens only once B reaches it.
 *
 * - `panel` (default): 64px master drawing centred in the space the content will take; pass
 *   `minHeight` so the layout keeps its shape while it waits.
 * - `inline`: 24px small drawing followed by the label as text.
 * - `control`: 16px small drawing in `currentColor`, for inside a button.
 *
 * Held invisible for 300ms by `.aw-delayed`, so a fast load shows nothing; still and fully drawn
 * under reduced motion.
 */
export function LoadingThread({
  label,
  size = 'panel',
  minHeight,
  className,
}: {
  label: string
  size?: LoadingThreadSize
  minHeight?: number | string
  className?: string
}) {
  const cut = `aw-thread-cut-${useId().replace(/:/g, '')}`
  const px = SIZES[size]
  const kind = size === 'panel' ? 'master' : 'small'
  const d = DRAWINGS[kind]
  const style: CSSProperties | undefined = minHeight != null ? { minHeight } : undefined
  return (
    <div
      role="status"
      aria-label={label}
      className={`aw-loading-thread ${SIZE_CLASS[size]} aw-delayed${className ? ` ${className}` : ''}`}
      style={style}
    >
      <svg
        width={px}
        height={px}
        viewBox="0 0 64 64"
        aria-hidden="true"
        focusable="false"
        data-loading-thread=""
        data-drawing={kind}
      >
        {/* Mask luminance, not colour: white keeps the under-thread, black cuts the crossing gap. */}
        <defs>
          <mask id={cut} maskUnits="userSpaceOnUse" x="-8" y="-8" width="80" height="80">
            <rect x="-8" y="-8" width="80" height="80" fill="white" />
            <path
              className="aw-thread-b"
              pathLength={1}
              d={d.b}
              fill="none"
              stroke="black"
              strokeWidth={d.gap}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </mask>
        </defs>
        <g className="aw-thread" fill="none" strokeWidth={d.stroke} strokeLinejoin="round" strokeLinecap="round">
          <path className="aw-thread-a" pathLength={1} d={d.a} mask={`url(#${cut})`} />
          <path className="aw-thread-b" pathLength={1} d={d.b} />
        </g>
      </svg>
      {size === 'inline' ? <span className="aw-loading-thread-label">{label}</span> : null}
    </div>
  )
}
