import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { KNOT_GLYPH, LINK_LABEL } from '@/lib/threadKnots'
import { formatDateTime } from '@/lib/format'
import type { KnotLink, ThreadKnot } from '@/api/thread'
import { Fold } from './Fold'
import '@/styles/thread.css'

interface KnotProps {
  knot: ThreadKnot
  open: boolean
  now: Date
  /** The knot an address or a jump points at: drawn marked. */
  current?: boolean
  onToggle: () => void
  onOpenLink: (link: KnotLink) => void
  /** The opened thread, rendered by the parent so the recursion stays in one place. */
  children?: React.ReactNode
}

function when(knot: ThreadKnot, now: Date): string {
  const start = formatDateTime(knot.start, now)
  const end = formatDateTime(knot.end, now)
  return start === end ? start : `${start} – ${end}`
}

function KnotFace({ knot, now }: { knot: ThreadKnot; now: Date }) {
  return (
    <>
      <span className="aw-knot-kind">
        <Icon name={KNOT_GLYPH[knot.kind]} size={14} />
        <span className="aw-knot-word">{knot.word}</span>
      </span>
      <span className="aw-knot-title">{knot.title}</span>
      {knot.summary ? <span className="aw-knot-summary">{knot.summary}</span> : null}
      <span className="aw-knot-meta">
        <span>{when(knot, now)}</span>
        {knot.actors.length > 0 ? <span>{knot.actors.join(', ')}</span> : null}
        {knot.child_count > 0 ? (
          <span>
            {knot.child_count} {knot.child_count === 1 ? 'knot' : 'knots'}
          </span>
        ) : null}
      </span>
    </>
  )
}

/** One knot on the thread: glyph and word, title, when, who, how many it holds. A knot that holds
 *  others opens in place (Enter or Space) into its own thread, passed as `children`. */
export const Knot = React.memo(function Knot({ knot, open, now, current, onToggle, onOpenLink, children }: KnotProps) {
  const holds = knot.child_count > 0
  const regionId = `thread-${knot.key.replace(/[^a-zA-Z0-9_-]/g, '_')}`
  return (
    <li className="aw-knot" data-kind={knot.kind} data-open={open ? 'true' : 'false'} data-current={current ? 'true' : undefined} data-knot-key={knot.key}>
      <span className="aw-knot-bead" aria-hidden="true" />
      {knot.kind === 'fold' ? (
        <Fold knot={knot} open={open} now={now} onToggle={onToggle} regionId={regionId} />
      ) : holds ? (
        <button
          type="button"
          data-slot="knot-head"
          data-knot-head=""
          className="aw-knot-head"
          aria-expanded={open}
          aria-controls={regionId}
          onClick={onToggle}
        >
          <KnotFace knot={knot} now={now} />
          <span className="aw-knot-chevron" aria-hidden="true">
            <Icon name="chevron_right" size={14} />
          </span>
        </button>
      ) : (
        <div className="aw-knot-head" data-knot-head="" tabIndex={0}>
          <KnotFace knot={knot} now={now} />
        </div>
      )}
      {knot.link ? (
        <button
          type="button"
          data-slot="knot-link"
          className="aw-knot-link"
          aria-label={`${LINK_LABEL[knot.link.object] ?? 'Open'}: ${knot.title}`}
          title={LINK_LABEL[knot.link.object] ?? 'Open'}
          onClick={() => onOpenLink(knot.link!)}
        >
          <Icon name="move_up" size={14} />
        </button>
      ) : null}
      {holds ? (
        <div className="aw-knot-opened" id={regionId} role="region" aria-label={`Inside: ${knot.title}`} hidden={!open}>
          <div className="aw-knot-opened-inner">{open ? children : null}</div>
        </div>
      ) : null}
    </li>
  )
})
