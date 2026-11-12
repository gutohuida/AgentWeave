import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import type { StoryEvent } from '@/api/tasks'
import { formatAgo, formatDateTime } from '@/lib/format'
import { TONE_COLOR } from '@/lib/taskStageVisual'
import { timeline, type TimelineEntry } from '@/lib/taskTimeline'
import '@/styles/task-redesign.css'

/** A task's story as a timeline (`task-card-and-story-redesign`, FR-6): one row per event, each a
 *  glyph, a short label, who and when; milestones stand out, routine runs fold into one row that
 *  opens, and any row opens to its full text. Presentational: the drawer passes the `/story`
 *  route's events in the order the route returns them (oldest first). */
export function TaskTimeline({ events, now }: { events: StoryEvent[]; now?: Date }) {
  const items = React.useMemo(() => timeline(events), [events])
  const [open, setOpen] = React.useState<ReadonlySet<string>>(new Set())
  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  return (
    <ol className="aw-tl" data-testid="task-timeline">
      {items.map((item) =>
        item.kind === 'entry' ? (
          <Row key={item.entry.id} entry={item.entry} now={now} open={open.has(item.entry.id)} onToggle={() => toggle(item.entry.id)} />
        ) : open.has(item.fold.id) ? (
          <React.Fragment key={item.fold.id}>
            <li className="aw-tl-row aw-tl-unfold">
              <button type="button" data-slot="timeline-fold" className="aw-tl-fold-button" onClick={() => toggle(item.fold.id)}>
                <Icon name="unfold_less" size={12} />
                Fold {item.fold.folded.length} routine steps
              </button>
            </li>
            {item.fold.folded.map((entry) => (
              <Row key={entry.id} entry={entry} now={now} open={open.has(entry.id)} onToggle={() => toggle(entry.id)} />
            ))}
          </React.Fragment>
        ) : (
          <li key={item.fold.id} className="aw-tl-row aw-tl-fold">
            <span className="aw-tl-node" aria-hidden="true">
              <Icon name="more_horiz" size={12} />
            </span>
            <button type="button" data-slot="timeline-fold" className="aw-tl-fold-button" aria-expanded={false} onClick={() => toggle(item.fold.id)}>
              {item.fold.folded.length} routine steps
              <span className="aw-tl-fold-who">{foldSummary(item.fold.folded)}</span>
            </button>
          </li>
        ),
      )}
    </ol>
  )
}

function foldSummary(entries: TimelineEntry[]): string {
  const actors = Array.from(new Set(entries.map((e) => e.actor).filter(Boolean)))
  return actors.length ? actors.slice(0, 3).join(', ') + (actors.length > 3 ? '…' : '') : ''
}

function Row({ entry, now, open, onToggle }: { entry: TimelineEntry; now?: Date; open: boolean; onToggle: () => void }) {
  const tone = TONE_COLOR[entry.tone]
  const expandable = Boolean(entry.detail)
  return (
    <li
      className="aw-tl-row"
      data-milestone={entry.milestone ? 'true' : 'false'}
      data-tone={entry.tone}
      style={{ '--entry-tone': tone } as React.CSSProperties}
    >
      <span className="aw-tl-node" aria-hidden="true">
        <Icon name={entry.glyph} size={entry.milestone ? 13 : 12} />
      </span>
      <div className="aw-tl-body">
        {expandable ? (
          <button type="button" data-slot="timeline-entry" className="aw-tl-head" aria-expanded={open} onClick={onToggle}>
            <Head entry={entry} now={now} />
            <Icon name={open ? 'expand_less' : 'expand_more'} size={12} className="aw-tl-chevron" />
          </button>
        ) : (
          <div className="aw-tl-head">
            <Head entry={entry} now={now} />
          </div>
        )}
        {open && entry.detail ? <p className="aw-tl-detail">{entry.detail}</p> : null}
      </div>
    </li>
  )
}

function Head({ entry, now }: { entry: TimelineEntry; now?: Date }) {
  return (
    <>
      <span className="aw-tl-label">{entry.label}</span>
      {entry.actor ? <span className="aw-tl-actor">{entry.actor}</span> : null}
      {entry.at ? (
        <time className="aw-tl-time" title={formatDateTime(entry.at, now)}>
          {formatAgo(entry.at, now)}
        </time>
      ) : null}
    </>
  )
}
