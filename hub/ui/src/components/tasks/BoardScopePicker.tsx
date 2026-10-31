import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { BoardScope } from '@/store/boardScopeStore'

/** One spec the picker offers: every spec in the project that holds at least one task. */
export interface ScopeSpec {
  id: string
  title: string
  count: number
}

interface Option {
  key: string
  label: string
  count: number | null
  scope: BoardScope
}

/** The board's scope control: a button naming the scope that opens a list of All, No spec and the
 *  specs that hold tasks, narrowed by what is typed. */
export function BoardScopePicker({
  scope,
  scopeLabel,
  specs,
  noSpecCount,
  onChoose,
}: {
  scope: BoardScope
  scopeLabel: string
  specs: ScopeSpec[]
  noSpecCount: number
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
    { key: 'none', label: 'No spec', count: noSpecCount, scope: { kind: 'none' } },
    ...specs.map((spec) => ({
      key: spec.id,
      label: spec.title,
      count: spec.count,
      scope: { kind: 'spec', id: spec.id } as BoardScope,
    })),
  ]
  const typed = filter.trim().toLowerCase()
  // A typed title looks for a spec: All and No spec are not specs and do not answer to it.
  const offered = typed
    ? options.filter((option) => option.scope.kind === 'spec' && option.label.toLowerCase().includes(typed))
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
              <span className="truncate">{option.label}</span>
              {option.count !== null ? <span className="aw-filter-chip-count">{option.count}</span> : null}
            </button>
          ))}
          {offered.length === 0 ? <p className="aw-board-scope-empty">No spec matches.</p> : null}
        </div>
      ) : null}
    </div>
  )
}
