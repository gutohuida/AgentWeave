import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { formatAgo } from '@/lib/format'
import { arrangeList, SHOWN_LABEL, type ListPreferences, type SpecListEntry } from './model'
import { SpecDocList } from './SpecDocList'
import '@/styles/spec-page.css'

export interface SpecOpenPickerProps {
  entries: SpecListEntry[]
  prefs: ListPreferences
  onPrefsChange: (next: ListPreferences) => void
  onOpen: (path: string) => void
  onNew: () => void
  now: Date
  /** The document this conversation is attached to, if any. */
  attachedPath?: string | null
  /** The document open in the panel now, marked in the list. */
  openPath?: string | null
  /** Paths opened recently, most recent first. */
  recent?: string[]
  /** A running build's progress per document path: tasks approved of tasks in the build. */
  progress?: Record<string, { done: number; total: number }>
  /** In the switcher's popover the picker is narrower and does not repeat its title. */
  compact?: boolean
  autoFocus?: boolean
  /** Beside a document in the list (Adopt, on one the Hub keeps no record of). */
  rowAction?: (entry: SpecListEntry) => React.ReactNode
}

/**
 * Choosing a spec to open (the side panel's Specs tab, the Ctrl/Cmd+K picker and the panel's
 * switcher): one search field that Enter opens from, shortcuts back into what matters right now
 * (the conversation's own document, builds running, recently opened), then every document with the
 * Spec tab's filters, order and roadmap grouping.
 */
export function SpecOpenPicker(props: SpecOpenPickerProps) {
  const { entries, prefs, now } = props
  const byPath = new Map(entries.map((e) => [e.path, e]))
  const searching = prefs.query.trim() !== ''
  const attached = props.attachedPath ? byPath.get(props.attachedPath) ?? null : null
  const building = entries.filter((e) => e.building && e.path !== attached?.path)
  const recent = (props.recent ?? [])
    .map((p) => byPath.get(p))
    .filter((e): e is SpecListEntry => Boolean(e) && e!.path !== attached?.path && !e!.building)
    .slice(0, 3)
  const firstMatch = React.useMemo(() => arrangeList(entries, prefs).flatMap((g) => (g.roadmap ? [g.roadmap, ...g.entries] : g.entries))[0] ?? null, [entries, prefs])

  return (
    <div className="aw-sp-open" data-compact={props.compact ? 'true' : 'false'}>
      {props.compact ? null : (
        <div className="aw-sp-open-head">
          <span className="aw-sp-open-title">Open a spec</span>
          <span className="aw-sp-open-count">{entries.length}</span>
          <button data-slot="open-new" type="button" className="aw-sp-open-new" onClick={props.onNew}>
            <Icon name="add" size={13} />
            New change
          </button>
        </div>
      )}
      <label className="aw-sp-open-search">
        <Icon name="search" size={15} />
        <input
          autoFocus={props.autoFocus}
          value={prefs.query}
          onChange={(e) => props.onPrefsChange({ ...prefs, query: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && firstMatch) props.onOpen(firstMatch.path)
            if (e.key === 'Escape') props.onPrefsChange({ ...prefs, query: '' })
          }}
          placeholder="Search by title, path or what it is about"
          aria-label="Search specs"
        />
        {searching ? (
          <span className="aw-sp-open-hint">
            <kbd>Enter</kbd> opens {firstMatch ? <b className="truncate">{firstMatch.title}</b> : 'nothing'}
          </span>
        ) : (
          <kbd className="aw-sp-open-kbd">Ctrl K</kbd>
        )}
      </label>

      {!searching && (attached || building.length || recent.length) ? (
        <div className="aw-sp-open-quick">
          {attached ? (
            <QuickGroup label="This conversation">
              <QuickCard entry={attached} now={now} onOpen={props.onOpen} open={props.openPath === attached.path} icon="link" progress={props.progress?.[attached.path]} />
            </QuickGroup>
          ) : null}
          {building.length ? (
            <QuickGroup label="Building now">
              {building.map((e) => (
                <QuickCard key={e.path} entry={e} now={now} onOpen={props.onOpen} open={props.openPath === e.path} progress={props.progress?.[e.path]} />
              ))}
            </QuickGroup>
          ) : null}
          {recent.length ? (
            <QuickGroup label="Recently opened">
              {recent.map((e) => (
                <QuickCard key={e.path} entry={e} now={now} onOpen={props.onOpen} open={props.openPath === e.path} icon="schedule" />
              ))}
            </QuickGroup>
          ) : null}
        </div>
      ) : null}

      <div className="aw-sp-open-all">
        {!searching ? <div className="aw-sp-open-label">All specs</div> : null}
        <SpecDocList
          entries={entries}
          active={props.openPath ?? null}
          prefs={prefs}
          onPrefsChange={props.onPrefsChange}
          onOpen={props.onOpen}
          onNew={props.onNew}
          now={now}
          variant="popover"
          hideSearch
          hideHead
          rowAction={props.rowAction}
        />
      </div>
    </div>
  )
}

function QuickGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="aw-sp-open-group">
      <div className="aw-sp-open-label">{label}</div>
      <div className="aw-sp-open-cards">{children}</div>
    </div>
  )
}

function QuickCard({
  entry: e,
  now,
  onOpen,
  open,
  icon,
  progress,
}: {
  entry: SpecListEntry
  now: Date
  onOpen: (path: string) => void
  open: boolean
  icon?: string
  progress?: { done: number; total: number }
}) {
  return (
    <button data-slot="open-card" type="button" className="aw-sp-open-card" data-open={open ? 'true' : 'false'} onClick={() => onOpen(e.path)} title={e.path}>
      <span className="aw-sp-open-card-top">
        {icon ? <Icon name={icon} size={12} className="aw-sp-open-card-icon" /> : <span className="aw-sp-live" aria-label="A build is running" />}
        <span className="aw-sp-open-card-title">{e.title}</span>
        {open ? <span className="aw-sp-open-card-here">Open</span> : null}
      </span>
      <span className="aw-sp-open-card-meta">
        <span className="aw-sp-list-dot" data-state={e.shown} aria-hidden="true" />
        {SHOWN_LABEL[e.shown]} · {formatAgo(e.updatedAt, now)}
        {progress ? (
          <span className="aw-sp-open-card-progress">
            {progress.done} of {progress.total}
          </span>
        ) : null}
      </span>
      {progress ? (
        <span className="aw-sp-open-card-bar" aria-hidden="true">
          <span style={{ width: `${Math.round((progress.done / Math.max(1, progress.total)) * 100)}%` }} />
        </span>
      ) : null}
    </button>
  )
}
