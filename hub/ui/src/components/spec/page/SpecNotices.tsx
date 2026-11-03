import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import '@/styles/spec-notices.css'

/** One thing the document's page has to tell the operator: a refusal, a warning, a note, or
 *  something waiting on them (an amendment). The banner used to give each its own block of height;
 *  here every one is a single line behind the header's count, and its full text and controls open
 *  on demand (spec `the-spec-header-redesigned`, FR-7). */
export interface HeaderNotice {
  id: string
  tone: 'error' | 'warn' | 'info'
  /** One line: what it is. */
  summary: React.ReactNode
  /** The rest, shown when the notice is opened: its full text and any controls it carries. */
  body?: React.ReactNode
  /** Opened as soon as the list is: a control the operator came for (the journey step and size). */
  defaultOpen?: boolean
  action?: { label: string; onClick: () => void; disabled?: boolean }
  testId?: string
}

const RANK: Record<HeaderNotice['tone'], number> = { error: 0, warn: 1, info: 2 }
const ICON: Record<HeaderNotice['tone'], string> = { error: 'error', warn: 'warning', info: 'info' }

function byUrgency(notices: HeaderNotice[]): HeaderNotice[] {
  return [...notices].sort((a, b) => RANK[a.tone] - RANK[b.tone])
}

/** The count in the header, in the tone of the most urgent notice, that opens every notice. Adds
 *  no height: the list floats over the body. Renders nothing when there is nothing to tell. */
export function SpecNoticeBadge({ notices }: { notices: HeaderNotice[] }) {
  const [open, setOpen] = React.useState(false)
  const root = React.useRef<HTMLSpanElement>(null)
  React.useEffect(() => {
    if (!open) return
    // A dialog or menu a notice opened is portalled outside the list: a click there keeps it open.
    const onDown = (e: MouseEvent) => {
      const target = e.target as Element | null
      if (!root.current || root.current.contains(target)) return
      if (target?.closest?.('[role="dialog"], [role="menu"], [role="listbox"]')) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  const sorted = byUrgency(notices)
  const first = sorted[0]
  if (!first) return null
  const label = `${sorted.length} ${sorted.length === 1 ? 'message' : 'messages'}`
  return (
    <span className="aw-notice-badge-wrap" ref={root}>
      <button
        type="button"
        className="aw-notice-badge"
        data-testid="spec-notice-count"
        data-tone={first.tone}
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((o) => !o)}
        title="What this document has to tell you"
      >
        <Icon name={ICON[first.tone]} size={13} />
        {sorted.length}
      </button>
      {open ? (
        <div className="aw-notice-pop aw-pop" data-state="open" data-testid="spec-notices" role="region" aria-label={label}>
          <NoticeList notices={sorted} />
        </div>
      ) : null}
    </span>
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

function NoticeRow({ notice }: { notice: HeaderNotice }) {
  const [open, setOpen] = React.useState(notice.defaultOpen === true)
  const expandable = Boolean(notice.body)
  return (
    <div className="aw-notice" data-tone={notice.tone} data-testid={notice.testId ?? `spec-notice-${notice.id}`}>
      <div className="aw-notice-line">
        <Icon name={ICON[notice.tone]} size={13} className="aw-notice-icon" />
        {expandable ? (
          <button type="button" className="aw-notice-summary" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            <span className="aw-notice-summary-text">{notice.summary}</span>
            <Icon name={open ? 'expand_less' : 'expand_more'} size={12} />
          </button>
        ) : (
          <span className="aw-notice-summary">
            <span className="aw-notice-summary-text">{notice.summary}</span>
          </span>
        )}
        {notice.action ? (
          <Button variant="ghost" size="xs" disabled={notice.action.disabled} onClick={notice.action.onClick}>
            {notice.action.label}
          </Button>
        ) : null}
      </div>
      {expandable && open ? <div className="aw-notice-body">{notice.body}</div> : null}
    </div>
  )
}
