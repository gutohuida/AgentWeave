import type { ReactNode } from 'react'

/** The six state tones (`styles/story.css`). Colour carries state and nothing else (vis-D8). */
export type Tone = 'green' | 'amber' | 'red' | 'blue' | 'purple' | 'neutral'

/**
 * A dot and a label on a tinted ground, in one of the six state tones.
 *
 * Keyed on its label by the caller's render, so a changed state pops in rather than swapping
 * silently. `live` pulses the dot for something still happening (a running turn).
 */
export function StatePill({
  tone,
  children,
  live = false,
  title,
  testId,
}: {
  tone: Tone
  children: ReactNode
  live?: boolean
  title?: string
  testId?: string
}) {
  return (
    <span
      className={`aw-pill tone-${tone}`}
      data-live={live ? 'true' : undefined}
      title={title}
      data-testid={testId}
    >
      {children}
    </span>
  )
}
