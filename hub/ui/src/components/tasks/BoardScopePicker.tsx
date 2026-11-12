import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { BoardScope } from '@/store/boardScopeStore'

/** One spec the picker offers: every spec in the project that holds at least one task. */
export interface ScopeSpec {
  id: string
  title: string
  /** The short tag cards and the list name the spec by. */
  tag: string
  /** Tasks of the spec that are not finished. */
  unfinished: number
  /** When one of its tasks was last created or moved. */
  lastActivity: string | null
}

/** How long ago, in the picker's words: '5 min', '2 h', '3 days'. */
function sinceLabel(value: string, now: Date = new Date()): string {
  const minutes = Math.max(0, (now.getTime() - new Date(value).getTime()) / 60_000)
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${Math.round(minutes)} min`
  const hours = minutes / 60
  if (hours < 24) return `${Math.round(hours)} h`
  const days = Math.round(hours / 24)
  return `${days} ${days === 1 ? 'day' : 'days'}`
}

interface Option {
  key: string
  label: string
  count: number | null
  scope: BoardScope
  /** What a typed search also looks at, besides the label. */
  title?: string
  since?: string | null
}

/** The board's scope control: a button naming the scope that opens a list of All, Building, No spec and the
 *  specs that hold tasks, narrowed by what is typed. */
export function BoardScopePicker({
  scope,
  scopeLabel,
  specs,
  noSpecCount,
  buildingCount,
  onChoose,
}: {
  scope: BoardScope
  scopeLabel: string
  specs: ScopeSpec[]
  noSpecCount: number
  /** How many specs have a build running now. */
  buildingCount: number
  onChoose: (scope: BoardScope) => void
}) {
  const [open, setOpen] = React.useState(false)
  const [filter, setFilter] = React.useState('')
  const root = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!open) return
    const outside = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', outside)
    return () => document.removeEventListener('mousedown', outside)
  }, [open])

  const toggle = () => {
    setFilter('')
    setOpen((current) => !current)
  }
  const options: Option[] = [
    { key: 'all', label: 'All', count: null, scope: { kind: 'all' } },
    { key: 'building', label: 'Building', count: buildingCount, scope: { kind: 'building' } },
    { key: 'none', label: 'No spec', count: noSpecCount, scope: { kind: 'none' } },
    ...specs.map((spec) => ({
      key: spec.id,
      label: spec.tag,
      title: spec.title,
      since: spec.lastActivity ? sinceLabel(spec.lastActivity) : null,
      count: spec.unfinished,
      scope: { kind: 'spec', id: spec.id } as BoardScope,
    })),
  ]
  const typed = filter.trim().toLowerCase()
  // Typed text looks for a spec by its tag or its title: All and No spec are not specs and do not
  // answer to it. The order is the one given, most recently active first.
  const offered = typed
    ? options.filter(
        (option) =>
          option.scope.kind === 'spec' &&
          (option.label.toLowerCase().includes(typed) || (option.title ?? '').toLowerCase().includes(typed)),
      )
    : options

  return (
    <div
      ref={root}
      className="aw-board-scope"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.stopPropagation()
          setOpen(false)
        }
      }}
    >
      <Button
        variant="outline"
        size="sm"
        data-testid="board-scope"
        aria-haspopup="listbox"
        aria-expanded={open}
        title={scopeLabel}
        className="aw-board-scope-button"
        onClick={toggle}
      >
        <Icon name="filter_alt" size={13} />
        <span className="aw-board-scope-label">{scopeLabel}</span>
        <Icon name="expand_more" size={13} />
      </Button>
      {open ? (
        <div className="aw-board-scope-list" role="listbox" aria-label="Board scope">
          <Input
            autoFocus
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Find a spec"
            aria-label="Find a spec"
            data-testid="board-scope-filter"
          />
          {offered.map((option) => (
            <button
              key={option.key}
              type="button"
              role="option"
              aria-selected={option.scope.kind === scope.kind && (option.scope.kind !== 'spec' || option.scope.id === (scope as { id?: string }).id)}
              className="aw-board-scope-option"
              data-testid={`board-scope-option-${option.key}`}
              onClick={() => {
                setOpen(false)
                onChoose(option.scope)
              }}
            >
              <span className="truncate" title={option.title}>{option.label}</span>
              {option.since ? <span className="aw-board-scope-since" data-testid={`board-scope-since-${option.key}`}>{option.since}</span> : null}
              {option.count !== null ? <span className="aw-filter-chip-count">{option.count}</span> : null}
            </button>
          ))}
          {offered.length === 0 ? <p className="aw-board-scope-empty">No spec matches.</p> : null}
        </div>
      ) : null}
    </div>
  )
}
