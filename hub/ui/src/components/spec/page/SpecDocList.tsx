import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { formatAgo } from '@/lib/format'
import { arrangeList, SHOWN_LABEL, type ListOrder, type ListPreferences, type SpecListEntry } from './model'
import { NewCapabilityAction } from './NewCapability'
import '@/styles/spec-page.css'

const ORDERS: Array<{ value: ListOrder; label: string; detail: string }> = [
  { value: 'roadmap', label: 'Roadmap order', detail: 'Slices under their roadmap, in build order.' },
  { value: 'changed', label: 'Last change', detail: 'Most recently changed first.' },
  { value: 'phase', label: 'Phase', detail: 'Building, writing, approved, archived.' },
  { value: 'title', label: 'Title', detail: 'A to Z.' },
]

/** The project's specification documents (FR-4): search, filters, an order, roadmaps with their
 *  slices in build order, and a live pulse on any document with a build running. */
export function SpecDocList({
  entries,
  active,
  prefs,
  onPrefsChange,
  onOpen,
  onNew,
  now,
  variant = 'column',
  hideSearch = false,
  hideHead = false,
  footer,
  rowAction,
}: {
  entries: SpecListEntry[]
  active: string | null
  prefs: ListPreferences
  onPrefsChange: (next: ListPreferences) => void
  onOpen: (path: string) => void
  onNew: () => void
  now: Date
  /** A left column, or the body of the top switcher's popover. */
  variant?: 'column' | 'popover'
  /** The picker searches from its own field; the list then leaves its own out. */
  hideSearch?: boolean
  /** The picker titles itself; the list then leaves its heading out and its order menu joins the filters. */
  hideHead?: boolean
  /** Pinned under the list: the evidence view's entry and the defects report. */
  footer?: React.ReactNode
  /** Beside a row (Adopt, on a document the Hub keeps no record of). */
  rowAction?: (entry: SpecListEntry) => React.ReactNode
}) {
  const groups = arrangeList(entries, prefs)
  const shown = groups.reduce((n, g) => n + g.entries.length + (g.roadmap ? 1 : 0), 0)
  const building = entries.filter((e) => e.building).length
  const set = (patch: Partial<ListPreferences>) => onPrefsChange({ ...prefs, ...patch })
  const filtered = prefs.kind !== 'all' || prefs.phase !== 'any' || prefs.buildingOnly || prefs.query.trim() !== ''

  return (
    <aside className="aw-sp-list" data-variant={variant} aria-label="Specification documents">
      {hideHead ? null : (
        <div className="aw-sp-list-head">
        <span className="aw-sp-list-title">Specs</span>
        <span className="aw-sp-list-count">{entries.length}</span>
        <OrderMenu value={prefs.order} onChange={(order) => set({ order })} />
        <button data-slot="icon-button" type="button" className="aw-icon-button" onClick={onNew} aria-label="New change" title="New change">
          <Icon name="add" size={15} />
        </button>
        </div>
      )}
      {hideSearch ? null : (
        <div className="aw-sp-list-search">
        <Icon name="search" size={13} className="aw-sp-list-search-icon" />
        <Input value={prefs.query} onChange={(e) => set({ query: e.target.value })} placeholder="Search specs" aria-label="Search specs" className="aw-sp-list-input" />
        </div>
      )}
      <div className="aw-sp-list-filters" role="group" aria-label="Filter specs">
        {(
          [
            ['all', 'All'],
            ['change-spec', 'Changes'],
            ['roadmap', 'Roadmaps'],
            ['capability', 'Capabilities'],
          ] as const
        ).map(([value, label]) => (
          <button data-slot="filter-chip" type="button" key={value} className="aw-sp-chip" aria-pressed={prefs.kind === value} onClick={() => set({ kind: value })}>
            {label}
          </button>
        ))}
        <button data-slot="filter-chip" type="button" className="aw-sp-chip" aria-pressed={prefs.buildingOnly} onClick={() => set({ buildingOnly: !prefs.buildingOnly })} disabled={!building && !prefs.buildingOnly}>
          <span className="aw-sp-live" data-still={building ? undefined : 'true'} aria-hidden="true" />
          Building now
          {building ? <span className="aw-sp-chip-count">{building}</span> : null}
        </button>
        {hideHead ? <OrderMenu value={prefs.order} onChange={(order) => set({ order })} /> : null}
        <span className="aw-sp-list-phase">
          <MenuSelect
            label="Phase"
            value={prefs.phase}
            onChange={(phase) => set({ phase })}
            maxWidth={150}
            options={[
              { value: 'any', label: 'Any phase' },
              { value: 'writing', label: 'Writing' },
              { value: 'approved', label: 'Approved' },
              { value: 'archived', label: 'Archived' },
            ]}
          />
        </span>
        {prefs.kind === 'capability' ? <NewCapabilityAction onOpen={onOpen} /> : null}
      </div>

      <div className="aw-sp-list-body">
        {groups.map((g, gi) => (
          <div key={g.roadmap?.path ?? g.label ?? `run-${gi}`} className="aw-sp-list-group" data-roadmap={g.roadmap ? 'true' : 'false'}>
            {g.label ? <div className="aw-sp-list-label">{g.label}</div> : null}
            {g.roadmap ? <Row entry={g.roadmap} active={active} onOpen={onOpen} now={now} roadmap slices={g.entries.length} action={rowAction} /> : null}
            {g.entries.length ? (
              <ol className="aw-sp-list-rows" data-slices={g.roadmap ? 'true' : 'false'}>
                {g.entries.map((e, i) => (
                  <li key={e.path}>
                    <Row entry={e} active={active} onOpen={onOpen} now={now} position={g.roadmap ? i + 1 : undefined} action={rowAction} />
                  </li>
                ))}
              </ol>
            ) : null}
          </div>
        ))}
        {!shown ? (
          <div className="aw-sp-list-empty">
            No documents match.
            {filtered ? (
              <Button variant="ghost" size="xs" onClick={() => onPrefsChange({ ...prefs, query: '', kind: 'all', phase: 'any', buildingOnly: false })}>
                Clear filters
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {footer ? <div className="aw-sp-list-footer">{footer}</div> : null}
    </aside>
  )
}

function Row({
  entry: e,
  active,
  onOpen,
  now,
  roadmap,
  slices,
  position,
  action,
}: {
  entry: SpecListEntry
  active: string | null
  onOpen: (path: string) => void
  now: Date
  roadmap?: boolean
  slices?: number
  position?: number
  action?: (entry: SpecListEntry) => React.ReactNode
}) {
  const extra = action?.(e)
  const row = (
    <button
      data-slot="spec-row"
      type="button"
      className="aw-sp-list-row"
      data-active={e.path === active ? 'true' : 'false'}
      data-roadmap={roadmap ? 'true' : undefined}
      aria-current={e.path === active ? 'page' : undefined}
      onClick={() => onOpen(e.path)}
      title={`${e.title} — ${SHOWN_LABEL[e.shown]}, changed ${formatAgo(e.updatedAt, now)}`}
    >
      {roadmap ? (
        <Icon name="list_tree" size={13} className="aw-sp-list-icon" />
      ) : position !== undefined ? (
        <span className="aw-sp-list-pos">{position}</span>
      ) : null}
      <span className="aw-sp-list-dot" data-state={e.shown} aria-hidden="true" />
      <span className="aw-sp-list-name">{e.title}</span>
      {e.building ? <span className="aw-sp-live" title="A build is running" aria-label="A build is running" /> : null}
      {roadmap && slices !== undefined ? <span className="aw-sp-list-meta">{slices}</span> : <span className="aw-sp-list-meta">{formatAgo(e.updatedAt, now)}</span>}
    </button>
  )
  return extra ? (
    <div className="aw-sp-list-rowwrap">
      {row}
      <span className="aw-sp-list-rowaction">{extra}</span>
    </div>
  ) : (
    row
  )
}

function OrderMenu({ value, onChange }: { value: ListOrder; onChange: (value: ListOrder) => void }) {
  const current = ORDERS.find((o) => o.value === value)!
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button data-slot="order-trigger" type="button" className="aw-sp-order" title={`Ordered by ${current.label.toLowerCase()}`}>
          <Icon name="sort" size={13} />
          <span className="aw-sp-order-label">{current.label}</span>
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} collisionPadding={12} className="aw-menu aw-pop">
          <DropdownMenu.Label className="aw-menu-label">Order by</DropdownMenu.Label>
          <DropdownMenu.RadioGroup value={value} onValueChange={(next) => onChange(next as ListOrder)}>
            {ORDERS.map((o) => (
              <DropdownMenu.RadioItem key={o.value} value={o.value} className="aw-menu-item" data-two-line="true">
                <span className="aw-menu-item-icon" />
                <span className="min-w-0 flex-1">
                  <span className="block">{o.label}</span>
                  <span className="aw-menu-item-detail">{o.detail}</span>
                </span>
                <DropdownMenu.ItemIndicator className="aw-menu-check">
                  <Icon name="check" size={14} />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

/** The top switcher: the open document's title as a button that drops the same list down, so the
 *  document gets the full width (the document's open question 2). */
export function SpecDocSwitcher({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false)
  const root = React.useRef<HTMLDivElement>(null)
  // A document opened from inside the popover without a row click: New capability's dialog.
  React.useEffect(() => setOpen(false), [title])
  React.useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node) && !(e.target as HTMLElement).closest?.('.aw-menu, [role="dialog"]')) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div className="aw-sp-switcher" ref={root} onClickCapture={(e) => (e.target as HTMLElement).closest('.aw-sp-list-row') && setOpen(false)}>
      <button data-slot="switcher" type="button" className="aw-sp-switcher-trigger" aria-expanded={open} onClick={() => setOpen((o) => !o)} title="Switch document">
        <Icon name="description" size={13} />
        <span className="truncate">{title}</span>
        <Icon name="unfold_more" size={13} className="aw-sp-switcher-chevron" />
      </button>
      {open ? <div className="aw-sp-switcher-pop aw-pop" data-state="open">{children}</div> : null}
    </div>
  )
}
