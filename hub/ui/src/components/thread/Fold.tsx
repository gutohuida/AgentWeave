import { Icon } from '@/components/common/Icon'
import { KNOT_GLYPH } from '@/lib/threadKnots'
import type { ThreadKnot } from '@/api/thread'
import { formatDateTime } from '@/lib/format'
import '@/styles/thread.css'

interface FoldProps {
  knot: ThreadKnot
  open: boolean
  now: Date
  onToggle: () => void
  /** The id of the region this fold controls. */
  regionId: string
}

/** Routine knots gathered into one ("6 runs"). It is a knot: the same head, the same keys; what
 *  sets it apart is the stacked bead and that it names a count instead of a single thing. */
export function Fold({ knot, open, now, onToggle, regionId }: FoldProps) {
  const start = formatDateTime(knot.start, now)
  const end = formatDateTime(knot.end, now)
  return (
    <button
      type="button"
      data-slot="knot-head"
      data-knot-head=""
      className="aw-knot-head aw-knot-head-fold"
      aria-expanded={open}
      aria-controls={regionId}
      onClick={onToggle}
    >
      <span className="aw-knot-kind">
        <Icon name={KNOT_GLYPH[knot.fold_of && knot.fold_of !== 'group' ? knot.fold_of : 'fold']} size={14} />
        <span className="aw-knot-word">{knot.word}</span>
      </span>
      <span className="aw-knot-title">{knot.title}</span>
      <span className="aw-knot-meta">
        <span>{start === end ? start : `${start} – ${end}`}</span>
        {knot.actors.length > 0 ? <span>{knot.actors.join(', ')}</span> : null}
      </span>
      <span className="aw-knot-chevron" aria-hidden="true">
        <Icon name="chevron_right" size={14} />
      </span>
    </button>
  )
}
