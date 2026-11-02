import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import '@/styles/spec-notices.css'

/** One thing the document's page has to tell the operator: a refusal, a warning, a note, or
 *  something waiting on them (an amendment). The banner used to give each its own block of height;
 *  here every one is a single line, and its full text opens on demand (spec
 *  `the-spec-header-redesigned`, FR-3). */
export interface HeaderNotice {
  id: string
  tone: 'error' | 'warn' | 'info'
  /** One line: what it is. */
  summary: React.ReactNode
  /** The rest, shown when the notice is opened. */
  body?: React.ReactNode
  action?: { label: string; onClick: () => void }
}

const RANK: Record<HeaderNotice['tone'], number> = { error: 0, warn: 1, info: 2 }
const ICON: Record<HeaderNotice['tone'], string> = { error: 'error', warn: 'warning', info: 'info' }

export function byUrgency(notices: HeaderNotice[]): HeaderNotice[] {
  return [...notices].sort((a, b) => RANK[a.tone] - RANK[b.tone])
}

/** A: one line under the title: the most urgent notice, and "+N more" that opens them all. */
export function SpecNoticeLine({ notices }: { notices: HeaderNotice[] }) {
  const [open, setOpen] = React.useState(false)
  const sorted = byUrgency(notices)
  const first = sorted[0]
  if (!first) return null
  if (open) {
    return (
      <div className="aw-notices" data-testid="spec-notices" data-open="true">
        <NoticeList notices={sorted} />
        <button type="button" className="aw-notices-more" onClick={() => setOpen(false)}>
          <Icon name="expand_less" size={13} /> Fold
        </button>
      </div>
    )
  }
  return (
    <div className="aw-notices" data-testid="spec-notices" data-open="false">
      <NoticeRow notice={first} single onMore={sorted.length > 1 || first.body ? () => setOpen(true) : undefined} more={sorted.length - 1} />
    </div>
  )
}

/** B: a count in the header that opens every notice below it. */
export function SpecNoticeBadge({ notices }: { notices: HeaderNotice[] }) {
  const [open, setOpen] = React.useState(false)
  const root = React.useRef<HTMLSpanElement>(null)
  React.useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  const sorted = byUrgency(notices)
  const first = sorted[0]
  if (!first) return null
  return (
    <span className="aw-notice-badge-wrap" ref={root}>
      <button type="button" className="aw-notice-badge" data-tone={first.tone} aria-expanded={open} onClick={() => setOpen((o) => !o)} title="What this document has to tell you">
        <Icon name={ICON[first.tone]} size={13} />
        {sorted.length}
      </button>
      {open ? (
        <div className="aw-notice-pop aw-pop" data-state="open">
          <NoticeList notices={sorted} />
        </div>
      ) : null}
    </span>
  )
}

/** C: the notices as a stack of cards, for the page's right-hand column. */
export function SpecNoticeStack({ notices }: { notices: HeaderNotice[] }) {
  const sorted = byUrgency(notices)
  if (!sorted.length) return null
  return (
    <div className="aw-notice-stack" data-testid="spec-notices">
      <div className="aw-notice-stack-head">Needs a look · {sorted.length}</div>
      <NoticeList notices={sorted} />
    </div>
  )
}

function NoticeList({ notices }: { notices: HeaderNotice[] }) {
  return (
    <ul className="aw-notice-list">
      {notices.map((n) => (
        <li key={n.id}>
          <NoticeRow notice={n} />
        </li>
      ))}
    </ul>
  )
}

function NoticeRow({ notice, single, onMore, more = 0 }: { notice: HeaderNotice; single?: boolean; onMore?: () => void; more?: number }) {
  const [open, setOpen] = React.useState(false)
  const expandable = !single && Boolean(notice.body)
  return (
    <div className="aw-notice" data-tone={notice.tone} data-single={single ? 'true' : 'false'}>
      <div className="aw-notice-line">
        <Icon name={ICON[notice.tone]} size={13} className="aw-notice-icon" />
        {expandable ? (
          <button type="button" className="aw-notice-summary" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {notice.summary}
            <Icon name={open ? 'expand_less' : 'expand_more'} size={12} />
          </button>
        ) : (
          <span className="aw-notice-summary">{notice.summary}</span>
        )}
        {notice.action ? (
          <Button variant="ghost" size="xs" onClick={notice.action.onClick}>
            {notice.action.label}
          </Button>
        ) : null}
        {onMore ? (
          <button type="button" className="aw-notices-more" onClick={onMore}>
            {more > 0 ? `+${more} more` : 'Details'}
            <Icon name="expand_more" size={12} />
          </button>
        ) : null}
      </div>
      {expandable && open ? <div className="aw-notice-body">{notice.body}</div> : null}
    </div>
  )
}
