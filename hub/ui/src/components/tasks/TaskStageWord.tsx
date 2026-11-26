import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import type { CheckState } from '@/lib/checkState'
import { TONE_COLOR, stageVisual } from '@/lib/taskStageVisual'
import { CheckStateMarker } from './CheckStateMarker'
import '@/styles/check-state.css'

/** A task's stage as the board words it, a glyph and a word in its tone, then its check marker
 *  (`task-stages-in-the-build-view-and-dependency-map` FR-11, FR-12): for every surface that is
 *  not the board card or a map node, so each words one task alike. `glyphOnly` draws the marker
 *  as its glyph alone, for a row too dense for its words. */
export function TaskStageWord({
  stage,
  check,
  glyphOnly = false,
  size = 'sm',
}: {
  stage: string
  check?: CheckState | null
  glyphOnly?: boolean
  size?: 'sm' | 'xs'
}) {
  const visual = stageVisual(stage)
  return (
    <span
      className="aw-stage-word"
      data-size={size}
      data-stage={stage}
      style={{ '--stage-tone': TONE_COLOR[visual.tone] } as React.CSSProperties}
    >
      <Icon name={visual.glyph} size={size === 'xs' ? 11 : 12} />
      <span className="aw-stage-word-text">{visual.word}</span>
      <CheckStateMarker check={check} stage={stage} size="xs" glyphOnly={glyphOnly} />
    </span>
  )
}
