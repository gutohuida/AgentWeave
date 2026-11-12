import * as React from 'react'
import { THREAD_KNOTS, TONE_COLOR, stageVisual } from '@/lib/taskStageVisual'

/** A task's thread: five knots from built to on main, filled as far as the task has come
 *  (`task-card-and-story-redesign`, FR-2). The brand's red thread, drawn in the app's own tones: the
 *  stage's tone runs up to the knot it has reached, and a landing that did not happen cuts it there.
 *
 *  `compact` is the card's hairline with no labels; the drawer draws it labelled. The fill animates
 *  when the stage changes (FR-7, styles in task-redesign.css), and stands still under reduced motion.
 *  The stage word always sits beside it, so the thread is never the only telling (FR-9). */
export function StageThread({ stage, compact }: { stage: string | null | undefined; compact?: boolean }) {
  const visual = stageVisual(stage)
  const reached = visual.knot
  const last = THREAD_KNOTS.length - 1
  // A stage still moving fills halfway toward the knot it is heading for, so work under way always
  // shows some thread; a stage that has arrived fills to its knot.
  // A cut thread stops at the knot before the break.
  const fill =
    reached < 0 ? 0 : visual.cut ? ((reached - 1) / last) * 100 : visual.moving ? Math.max(5, ((reached - 0.5) / last) * 100) : (reached / last) * 100
  const style = { '--thread-tone': TONE_COLOR[visual.tone], '--thread-fill': `${fill}%` } as React.CSSProperties
  return (
    <div
      className="aw-thread"
      data-compact={compact ? 'true' : 'false'}
      data-cut={visual.cut ? 'true' : 'false'}
      data-moving={visual.moving ? 'true' : 'false'}
      style={style}
      role={compact ? undefined : 'img'}
      aria-hidden={compact ? true : undefined}
      aria-label={compact ? undefined : `${visual.word}: ${reached < 0 ? 'not built yet' : `reached ${THREAD_KNOTS[reached].toLowerCase()}`}`}
    >
      <span className="aw-thread-line" />
      <span className="aw-thread-fill" />
      {THREAD_KNOTS.map((label, index) => (
        <span
          key={label}
          className="aw-thread-knot"
          data-state={index < reached || (index === reached && !visual.moving) ? 'passed' : index === reached ? 'here' : 'ahead'}
          data-cut-here={visual.cut && index === reached ? 'true' : 'false'}
          style={{ left: `${(index / last) * 100}%` }}
        >
          {compact ? null : <span className="aw-thread-label">{label}</span>}
        </span>
      ))}
    </div>
  )
}
