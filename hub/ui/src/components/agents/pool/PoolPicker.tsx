import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { composerControlClassName } from '../ComposerModelControls'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import { cliLabel, entryKey, entryLabel } from './poolModel'

/**
 * The composer's model choice under a pool (FR-9): only the profile's entries, grouped by coding
 * agent, the default marked. It replaces the model picker and the separate Effort pill, because an
 * entry carries its effort. A conversation keeps the coding agent it started on (a non-goal of the
 * slice to change), so once it has a turn, entries on another one are listed but not choosable,
 * saying why. With one entry there is nothing to choose: the pill only shows it.
 */
export function PoolPicker({
  agentName,
  pool,
  catalog,
  current,
  startedOn,
  onChoose,
  openRequest = 0,
}: {
  agentName: string
  pool: AgentPoolEntry[]
  catalog: ModelCatalogResponse | undefined
  /** The entry the next turn runs on. */
  current: AgentPoolEntry | undefined
  /** The coding agent the conversation started on; null before its first turn. */
  startedOn: string | null
  onChoose: (entry: AgentPoolEntry) => void
  /** Bumped when the operator accepts `/model`. */
  openRequest?: number
}) {
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const label = current ? entryLabel(catalog, current) : 'No model'
  const single = pool.length <= 1
  const clis = Array.from(new Set(pool.map((e) => e.cli)))
  const ordered = clis.flatMap((cli) => pool.filter((e) => e.cli === cli))
  const choosable = (e: AgentPoolEntry) => !startedOn || e.cli === startedOn

  useEffect(() => {
    if (openRequest > 0 && !single) setOpen(true)
  }, [openRequest, single])

  useEffect(() => {
    if (!open) return
    setHighlighted(Math.max(0, ordered.findIndex((e) => current && entryKey(e) === entryKey(current))))
    listRef.current?.focus()
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function choose(entry: AgentPoolEntry) {
    if (!choosable(entry)) return
    onChoose(entry)
    setOpen(false)
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setHighlighted((h) => Math.min(Math.max(h + step, 0), ordered.length - 1))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const target = ordered[highlighted]
      if (target) choose(target)
    }
  }

  const mark = current ? <ProviderMark provider={current.cli} label={cliLabel(current.cli)} className="mr-1" /> : null

  if (single) {
    return (
      <span
        data-slot="composer-pool-single"
        className={`${composerControlClassName} inline-flex h-8 min-w-0 max-w-full items-center gap-1 px-2.5 text-xs`}
        title={`Model: ${label}. ${agentName} may run on this model only; add others in its settings.`}
      >
        <span className="shrink-0" style={{ color: 'var(--text-3)' }}>Model: </span>
        {mark}
        <span className="min-w-0 truncate">{label}</span>
      </span>
    )
  }

  return (
    <div ref={rootRef} className="relative">
      <Button
        type="button"
        variant="ghost"
        size="pill"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`${composerControlClassName} min-w-0 max-w-full`}
        title={`Model: ${label}`}
      >
        <span className="shrink-0" style={{ color: 'var(--text-3)' }}>Model: </span>
        {mark}
        <span className="min-w-0 truncate">{label}</span>
        <span className="shrink-0">▾</span>
      </Button>
      {open ? (
        <div className="aw-pool-popover" onKeyDown={onKeyDown}>
          <div
            ref={listRef}
            role="listbox"
            tabIndex={-1}
            aria-label={`Models ${agentName} may run on`}
            aria-activedescendant={ordered[highlighted] ? `aw-pool-opt-${ordered[highlighted]!.id}` : undefined}
            className="aw-pool-options"
          >
            {clis.map((cli) => (
              <div key={cli} role="group" aria-label={cliLabel(cli)}>
                <div className="aw-pool-group-head" aria-hidden="true">
                  <ProviderMark provider={cli} label={cliLabel(cli)} />
                  {cliLabel(cli)}
                </div>
                {pool
                  .filter((e) => e.cli === cli)
                  .map((entry) => {
                    const index = ordered.indexOf(entry)
                    const active = Boolean(current && entryKey(entry) === entryKey(current))
                    const allowed = choosable(entry)
                    const entryName = entryLabel(catalog, entry)
                    return (
                      <div
                        key={entry.id}
                        id={`aw-pool-opt-${entry.id}`}
                        role="option"
                        aria-selected={active}
                        aria-disabled={allowed ? undefined : 'true'}
                        aria-label={entry.default ? `${entryName}, the default` : entryName}
                        data-highlighted={index === highlighted ? 'true' : 'false'}
                        className="aw-pool-option"
                        onMouseEnter={() => setHighlighted(index)}
                        onClick={() => choose(entry)}
                      >
                        <span className="aw-pool-option-check">{active ? <Icon name="check" size={14} /> : null}</span>
                        <span className="aw-pool-option-text">
                          <span className="aw-pool-option-label">{entryName}</span>
                          {!allowed ? (
                            <span className="aw-pool-option-detail">This chat runs on {cliLabel(startedOn!)}; start a new chat for {cliLabel(cli)}</span>
                          ) : null}
                        </span>
                        {entry.default ? <span className="aw-pool-option-tag">Default</span> : null}
                      </div>
                    )
                  })}
              </div>
            ))}
          </div>
          <p className="aw-pool-popover-foot">Only the models {agentName} may run on. Tasks and reviews do not follow this chat’s choice.</p>
        </div>
      ) : null}
    </div>
  )
}
