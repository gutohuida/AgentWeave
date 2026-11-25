import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { checkMarker, type CheckState } from '@/lib/checkState'
import { TONE_COLOR } from '@/lib/taskStageVisual'
import '@/styles/check-state.css'

/** A task's latest check, as a glyph and a word in its tone (never colour alone, FR-12). Beside a
 *  check stage it says only the state ("Running"); beside any other stage it names the kind too
 *  ("Pre-review failed"). `glyphOnly` is for the dense surfaces (a build view row, a map node): the
 *  glyph alone, each state's distinct, with the whole sentence as its name and tooltip. Renders
 *  nothing for no check, or one that passed. */
export function CheckStateMarker({
  check,
  stage,
  size = 'sm',
  glyphOnly = false,
}: {
  check: CheckState | null | undefined
  stage: string | null | undefined
  size?: 'sm' | 'xs'
  glyphOnly?: boolean
}) {
  const marker = checkMarker(check, stage)
  if (!marker || !check) return null
  return (
    <span
      className="aw-check-marker"
      data-size={size}
      data-glyph-only={glyphOnly ? 'true' : undefined}
      role="img"
      data-check-kind={check.kind}
      data-check-state={check.state}
      data-moving={marker.moving ? 'true' : 'false'}
      title={marker.title}
      aria-label={marker.title}
      style={{ '--check-tone': TONE_COLOR[marker.tone] } as React.CSSProperties}
    >
      <Icon name={marker.glyph} size={size === 'xs' ? 10 : 11} />
      {glyphOnly ? null : <span>{marker.text}</span>}
    </span>
  )
}
