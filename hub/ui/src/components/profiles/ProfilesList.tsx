import * as React from 'react'
import { Icon, ProviderMark } from '@/components/common/Icon'
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
 * The Profiles page's list (master). One dense two-line row per profile: name and default model,
 * its status in a word, what it spent and when it last worked. Working profiles first, then A to Z
 * (said once, quietly, under the filter); archived profiles sit collapsed at the end in a counted
 * group. The selected row stays put while the detail beside it changes (P9); arrow keys move
 * between rows and "/" reaches the filter (P23).
 */
export function ProfilesList({
  items,
  selected,
  query,
  onQueryChange,
  onSelect,
  onAdd,
  state = 'ready',
  onRetry,
  now,
}: {
  items: readonly ProfileListItem[]
  selected: string | null
  query: string
  onQueryChange: (query: string) => void
  onSelect: (name: string) => void
  onAdd: () => void
  state?: 'ready' | 'loading' | 'error'
  onRetry?: () => void
  now: Date
}) {
  const [archivedOpen, setArchivedOpen] = React.useState(false)
  const groups = groupProfiles(items, query)
  const filtering = query.trim() !== ''
  // A filter that matches an archived profile shows it; otherwise the group stays as it was left.
  const open = archivedOpen || (filtering && groups.archived.length > 0)
  const rows = listOrder(groups, open)
  const total = items.length
  const matched = groups.active.length + groups.rest.length + groups.archived.length
  const tabStop = rows.find((r) => r.name === selected)?.name ?? rows[0]?.name ?? null
  const filterRef = React.useRef<HTMLInputElement>(null)
  const listRef = React.useRef<HTMLDivElement>(null)

  const move = (event: React.KeyboardEvent) => {
    if (event.key === '/' && event.target !== filterRef.current) {
      event.preventDefault()
      filterRef.current?.focus()
      return
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || event.target === filterRef.current) return
    const buttons = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[data-slot="profile-row"]') ?? [])
    if (buttons.length === 0) return
    event.preventDefault()
    const at = buttons.indexOf(document.activeElement as HTMLElement)
    const next =
      event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : Math.min(buttons.length - 1, Math.max(0, at + (event.key === 'ArrowDown' ? 1 : -1)))
    buttons[next]?.focus()
  }

  const rowProps = { selected, tabStop, onSelect, now }

  return (
    <section className="aw-pf-list" aria-label="Profiles" onKeyDown={move}>
      <header className="aw-pf-list-head">
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
                listRef.current?.querySelector<HTMLElement>('[data-slot="profile-row"]')?.focus()
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

      <div className="aw-pf-list-body" ref={listRef}>
        {state === 'loading' ? <Skeleton /> : null}
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
  selected: string | null
  tabStop: string | null
  onSelect: (name: string) => void
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
          <li key={item.name}>
            <Row item={item} {...rest} />
          </li>
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
            <li key={item.name}>
              <Row item={item} {...rest} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function Row({ item, selected, tabStop, onSelect, now }: { item: ProfileListItem } & RowsProps) {
  const color = agentColorVars(item.colorIndex)
  const detail = item.status.detail
  const unpriced = item.spendUsd === null
  return (
    <button
      type="button"
      data-slot="profile-row"
      data-profile={item.name}
      className="aw-pf-row"
      data-kind={item.status.kind}
      aria-current={item.name === selected ? 'true' : undefined}
      tabIndex={item.name === tabStop ? 0 : -1}
      style={{ '--agent-accent': color.accent } as React.CSSProperties}
      onClick={() => onSelect(item.name)}
    >
      <span className="aw-pf-cell aw-pf-id">
        <span className="aw-agent-dot" aria-hidden="true" />
        <span className="aw-pf-name" title={item.name}>
          {item.name}
        </span>
        {/* A profile with no model says so once, in its status. */}
        {item.model ? (
          <span className="aw-pf-model" title={item.providerLabel ?? undefined}>
            {item.provider ? <ProviderMark provider={item.provider} label={item.providerLabel ?? item.provider} size={12} /> : null}
            <span className="truncate">{modelLine(item)}</span>
          </span>
        ) : null}
      </span>
      <span
        className="aw-pf-cell aw-pf-num tabular"
        title={item.spendUsd === undefined ? 'Nothing spent yet' : unpriced ? UNPRICED_NOTE : 'Spent so far'}
        data-unknown={unpriced ? 'true' : undefined}
      >
        {item.spendUsd === undefined ? '—' : item.spendUsd === null ? 'unpriced' : formatMoney(item.spendUsd)}
      </span>
      <span className="aw-pf-cell aw-pf-state">
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
      <span className="aw-pf-cell aw-pf-num aw-pf-ago tabular">
        {item.lastActiveAt ? (
          <time dateTime={item.lastActiveAt} title={`Last active ${formatDateTime(item.lastActiveAt, now)}`}>
            {formatAgo(item.lastActiveAt, now)}
          </time>
        ) : (
          <span title="Has not run">—</span>
        )}
      </span>
    </button>
  )
}

function Skeleton() {
  return (
    <div className="aw-pf-skeleton aw-delayed" role="status" aria-label="Loading profiles">
      {[0, 1, 2, 3, 4].map((i) => (
        <span key={i} className="aw-pf-skeleton-row" />
      ))}
    </div>
  )
}
