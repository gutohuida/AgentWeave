import { useId } from 'react'

/**
 * The AgentWeave loop — the brand mark, in its small drawing (16–32px): one madder thread draws
 * the W and loops back over itself at the centre. The gap where the thread crosses itself is a real
 * cut-out (an SVG mask), so the mark sits on any ground. The master drawing for 48px and up, the
 * colours and the usage rules live in the identity kit (docs/assets, and the AgentWeave design
 * system artifact). Decoration beside the name, so it carries no accessible name of its own.
 */
export function BrandLoop({ size = 16, testId }: { size?: number; testId?: string }) {
  const cut = `aw-loop-cut-${useId().replace(/:/g, '')}`
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
      data-testid={testId}
      className="aw-brand-loop"
    >
      {/* Mask luminance, not colour: white keeps the under-thread, black cuts the crossing gap. */}
      <defs>
        <mask id={cut} maskUnits="userSpaceOnUse" x="-8" y="-8" width="80" height="80">
          <rect x="-8" y="-8" width="80" height="80" fill="white" />
          <path
            d="M32 6 C24.5 6 24 14 30.5 25 L45 54 L57 18"
            fill="none"
            stroke="black"
            strokeWidth="16"
            strokeLinejoin="round"
          />
        </mask>
      </defs>
      <g fill="none" stroke="var(--brand-madder)" strokeWidth="8" strokeLinejoin="round" strokeLinecap="round">
        <path d="M7 18 L19 54 L33.5 25 C40 14 39.5 6 32 6" mask={`url(#${cut})`} />
        <path d="M32 6 C24.5 6 24 14 30.5 25 L45 54 L57 18" />
      </g>
    </svg>
  )
}
