import * as React from 'react'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { agentColorVars } from '@/lib/agentColors'
import { formatAgo, formatDateTime, formatMoney } from '@/lib/format'
import {
  countLine,
  groupProfiles,
  listOrder,
  modelLine,
  statusWord,
  type ProfileGroups,
  type ProfileListItem,
} from './profilesModel'
import '@/styles/profiles.css'

/** What a profile's spend column says when it has no figure (vault P18: unknown is not zero). */
export const UNPRICED_NOTE = 'Some of its runs finished and the Hub could not measure their cost'

/**
 * The Profiles index: every profile in one dense list, at reading-page width (P1, P2). One row per
 * profile: name, default model, status and what it is on, spend, last active, then "New thread" and
 * an open chevron. Working profiles first, then A to Z (said once, quietly, under the filter);
 * archived profiles sit collapsed at the end in a counted group. Clicking a row opens the
 * profile's own page. Arrow keys move between rows and "/" reaches the filter (P23).
 */
export function ProfilesIndex({
  items,
  query,
  onQueryChange,
  onOpen,
  onNewThread,
  onAdd,
  state = 'ready',
  onRetry,
  now,
  focusProfile,
}: {
  items: readonly ProfileListItem[]
  query: string
  onQueryChange: (query: string) => void
  onOpen: (name: string) => void
  onNewThread: (name: string) => void
  onAdd: () => void
  state?: 'ready' | 'loading' | 'error'
  onRetry?: () => void
  now: Date
  /** The profile whose row takes focus on arrival: the one the operator just came back from (P9). */
  focusProfile?: string | null
}) {
  const [archivedOpen, setArchivedOpen] = React.useState(false)
  const groups = groupProfiles(items, query)
  const filtering = query.trim() !== ''
  // A filter that matches an archived profile shows it; otherwise the group stays as it was left.
  const open = archivedOpen || (filtering && groups.archived.length > 0)
  const rows = listOrder(groups, open)
  const total = items.length
  const matched = groups.active.length + groups.rest.length + groups.archived.length
  const filterRef = React.useRef<HTMLInputElement>(null)
  const bodyRef = React.useRef<HTMLDivElement>(null)
  const tabStop = (focusProfile && rows.find((r) => r.name === focusProfile)?.name) || rows[0]?.name || null

  React.useEffect(() => {
    if (!focusProfile) return
    bodyRef.current?.querySelector<HTMLElement>(`[data-slot="profile-row"][data-profile="${CSS.escape(focusProfile)}"]`)?.focus()
  }, [focusProfile])

  const move = (event: React.KeyboardEvent) => {
    if (event.key === '/' && event.target !== filterRef.current) {
      event.preventDefault()
      filterRef.current?.focus()
      return
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || event.target === filterRef.current) return
    const buttons = Array.from(bodyRef.current?.querySelectorAll<HTMLElement>('[data-slot="profile-row"]') ?? [])
    if (buttons.length === 0) return
    event.preventDefault()
    const at = buttons.indexOf(document.activeElement as HTMLElement)
    const next =
      event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : Math.min(buttons.length - 1, Math.max(0, at + (event.key === 'ArrowDown' ? 1 : -1)))
    buttons[next]?.focus()
  }

  const rowProps = { tabStop, onOpen, onNewThread, now }

  return (
    <section className="aw-pf-index" aria-label="Profiles" onKeyDown={move}>
      <header className="aw-pf-index-head">
        <div className="aw-pf-search">
          <Icon name="search" size={13} className="aw-pf-search-icon" />
          <Input
            ref={filterRef}
            type="search"
            className="aw-pf-search-input"
            placeholder="Filter profiles"
            aria-label="Filter profiles"
            value={query}
            disabled={state !== 'ready' || total === 0}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape' && query) {
                e.stopPropagation()
                onQueryChange('')
              }
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                bodyRef.current?.querySelector<HTMLElement>('[data-slot="profile-row"]')?.focus()
              }
            }}
          />
        </div>
        <Button size="sm" variant="primary" onClick={onAdd}>
          <Icon name="add" size={14} />
          Add profile
        </Button>
      </header>

      {state === 'ready' && total > 0 ? (
        <p className="aw-pf-order" aria-live="polite">
          {countLine(matched, total)} · working first, then A to Z
        </p>
      ) : null}

      <div className="aw-pf-index-body" ref={bodyRef}>
        {state === 'ready' && matched > 0 ? (
          <div className="aw-pf-cols" aria-hidden="true">
            <span>Profile</span>
            <span>Model</span>
            <span>Status</span>
            <span className="aw-pf-num">Spent</span>
            <span className="aw-pf-num">Last active</span>
          </div>
        ) : null}
        {state === 'loading' ? <LoadingThread label="Loading profiles" minHeight={200} /> : null}
        {state === 'error' ? (
          <div className="aw-pf-note" role="alert">
            <Icon name="warning" size={14} className="aw-pf-note-icon" />
            <div>
              <p className="aw-pf-note-title">Profiles could not be loaded</p>
              <p className="aw-pf-note-body">The Hub did not answer, so this list says nothing about whether you have any.</p>
              <Button size="xs" variant="outline" onClick={onRetry}>
                Retry
              </Button>
            </div>
          </div>
        ) : null}
        {state === 'ready' && total > 0 && matched === 0 ? (
          <div className="aw-pf-note">
            <div>
              <p className="aw-pf-note-title">No profile matches “{query.trim()}”</p>
              <p className="aw-pf-note-body">The filter looks at names, charters, models and status words.</p>
              <Button size="xs" variant="outline" onClick={() => onQueryChange('')}>
                Clear filter
              </Button>
            </div>
          </div>
        ) : null}
        {state === 'ready' ? (
          <>
            <Group label="Working now" rows={groups.active} {...rowProps} />
            <Group label={groups.active.length > 0 ? 'Others' : null} rows={groups.rest} {...rowProps} />
            <ArchivedGroup groups={groups} open={open} onToggle={() => setArchivedOpen((v) => !v)} {...rowProps} />
          </>
        ) : null}
      </div>
    </section>
  )
}

interface RowsProps {
  tabStop: string | null
  onOpen: (name: string) => void
  onNewThread: (name: string) => void
  now: Date
}

function Group({ label, rows, ...rest }: { label: string | null; rows: ProfileListItem[] } & RowsProps) {
  if (rows.length === 0) return null
  return (
    <div className="aw-pf-group" role="group" aria-label={label ?? 'Profiles'}>
      {label ? (
        <h3 className="aw-pf-group-label">
          {label}
          <span className="aw-pf-group-count tabular">{rows.length}</span>
        </h3>
      ) : null}
      <ul className="aw-pf-rows">
        {rows.map((item) => (
          <Row key={item.name} item={item} {...rest} />
        ))}
      </ul>
    </div>
  )
}

function ArchivedGroup({ groups, open, onToggle, ...rest }: { groups: ProfileGroups; open: boolean; onToggle: () => void } & RowsProps) {
  if (groups.archived.length === 0) return null
  return (
    <div className="aw-pf-group" data-archived="true">
      <h3 className="aw-pf-group-label">
        <button type="button" data-slot="archived-toggle" className="aw-pf-disclosure" aria-expanded={open} aria-controls="aw-pf-archived" onClick={onToggle}>
          <Icon name={open ? 'expand_more' : 'chevron_right'} size={13} />
          Archived
          <span className="aw-pf-group-count tabular">{groups.archived.length}</span>
        </button>
      </h3>
      {open ? (
        <ul className="aw-pf-rows" id="aw-pf-archived">
          {groups.archived.map((item) => (
            <Row key={item.name} item={item} {...rest} />
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/** One profile. The row is a button that opens the page; "New thread" sits beside it (a button
 *  cannot hold a button), laid over the row's reserved end. */
function Row({ item, tabStop, onOpen, onNewThread, now }: { item: ProfileListItem } & RowsProps) {
  const color = agentColorVars(item.colorIndex)
  const detail = item.status.detail
  const canStart = !item.archived && item.status.kind !== 'no-model'
  return (
    <li className="aw-pf-item" style={{ '--agent-accent': color.accent } as React.CSSProperties}>
      <button
        type="button"
        data-slot="profile-row"
        data-profile={item.name}
        className="aw-pf-row"
        data-kind={item.status.kind}
        tabIndex={item.name === tabStop ? 0 : -1}
        onClick={() => onOpen(item.name)}
      >
        <span className="aw-pf-cell aw-pf-c-name">
          <span className="aw-agent-dot" aria-hidden="true" />
          <span className="aw-pf-name" title={item.charterName ? `${item.name} · ${item.charterName}` : item.name}>
            {item.name}
          </span>
        </span>
        <span className="aw-pf-cell aw-pf-c-model">
          {item.model ? (
            <span className="aw-pf-model" title={item.providerLabel ?? undefined}>
              {item.provider ? <ProviderMark provider={item.provider} label={item.providerLabel ?? item.provider} size={12} /> : null}
              <span className="truncate">{modelLine(item)}</span>
            </span>
          ) : (
            <span className="aw-pf-detail">—</span>
          )}
        </span>
        <span className="aw-pf-cell aw-pf-c-state">
          <span className="aw-pf-status" data-kind={item.archived ? 'archived' : item.status.kind}>
            <span className="aw-pf-status-mark" aria-hidden="true" />
            {item.archived ? 'Archived' : statusWord(item.status)}
          </span>
          {detail && !item.archived ? (
            <span className="aw-pf-detail" title={detail}>
              {item.status.kind === 'held' ? detail : `on ${detail}`}
            </span>
          ) : null}
        </span>
        <span
          className="aw-pf-cell aw-pf-num aw-pf-c-spend tabular"
          title={item.spendUsd === undefined ? 'Nothing spent yet' : item.spendUsd === null ? UNPRICED_NOTE : 'Spent so far'}
          data-unknown={item.spendUsd === null ? 'true' : undefined}
        >
          {item.spendUsd === undefined ? '—' : item.spendUsd === null ? 'unpriced' : formatMoney(item.spendUsd)}
        </span>
        <span className="aw-pf-cell aw-pf-num aw-pf-c-ago tabular">
          {item.lastActiveAt ? (
            <time dateTime={item.lastActiveAt} title={`Last active ${formatDateTime(item.lastActiveAt, now)}`}>
              {formatAgo(item.lastActiveAt, now)}
            </time>
          ) : (
            <span title="Has not run">—</span>
          )}
        </span>
        <span className="aw-pf-c-end" aria-hidden="true">
          <Icon name="chevron_right" size={14} />
        </span>
      </button>
      {canStart ? (
        <Button
          size="xs"
          variant="ghost"
          className="aw-pf-new"
          aria-label={`New thread with ${item.name}`}
          onClick={() => onNewThread(item.name)}
        >
          New thread
        </Button>
      ) : null}
    </li>
  )
}
