import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { composerControlClassName } from './ComposerModelControls'
import type { ProviderDescriptor } from '@/api/modelCatalog'

const FAVOURITES_STORAGE_KEY = 'aw.composer.favouriteModels'

/**
 * Favourites are the operator's own browsing preference, not project data (task 4b.6) —
 * they live in this browser's localStorage, the same place `configStore.ts` keeps mode
 * and the selected project, not in a Hub-persisted table. A model's own default/resolved
 * value is untouched by this: favouriting only ever reorders the picker's list (task 4b.7).
 */
function readFavourites(): Set<string> {
  if (typeof window === 'undefined') return new Set()
  try {
    const raw = window.localStorage.getItem(FAVOURITES_STORAGE_KEY)
    if (!raw) return new Set()
    const parsed: unknown = JSON.parse(raw)
    return new Set(Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : [])
  } catch {
    return new Set()
  }
}

function writeFavourites(favourites: Set<string>): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(FAVOURITES_STORAGE_KEY, JSON.stringify([...favourites]))
}

function favouriteKey(provider: string, modelId: string): string {
  return `${provider}:${modelId}`
}

interface ModelPickerProps {
  /** Scoped to one already-resolved provider, matching model-catalog's own contract
   * ("the choices are the ones the catalog declares for the relevant provider" — a turn
   * never crosses providers). Grouping is still built generically (a labelled section per
   * provider) so this reads correctly if a future catalog ever offers more than one
   * group here; today there is exactly one. */
  provider: ProviderDescriptor
  effectiveModel: string | null
  onChangeModel: (modelId: string) => void
}

export function ModelPicker({ provider, effectiveModel, onChangeModel }: ModelPickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlighted, setHighlighted] = useState(0)
  const [favourites, setFavourites] = useState<Set<string>>(() => readFavourites())
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const current = provider.models.find((m) => m.id === effectiveModel) ?? provider.models.find((m) => m.default)

  useEffect(() => {
    if (!open) return
    setQuery('')
    setHighlighted(0)
    searchRef.current?.focus()
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
  }, [open])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const models = q
      ? provider.models.filter(
          (m) =>
            m.label.toLowerCase().includes(q) ||
            m.id.toLowerCase().includes(q) ||
            provider.label.toLowerCase().includes(q),
        )
      : provider.models
    // Favourites first; stable within each group otherwise (no reordering beyond that —
    // task 4b.7's "ordering only" guarantee).
    return [...models].sort((a, b) => {
      const aFav = favourites.has(favouriteKey(provider.provider, a.id)) ? 0 : 1
      const bFav = favourites.has(favouriteKey(provider.provider, b.id)) ? 0 : 1
      return aFav - bFav
    })
  }, [provider, query, favourites])

  useEffect(() => {
    setHighlighted((h) => Math.min(h, Math.max(filtered.length - 1, 0)))
  }, [filtered.length])

  function toggleFavourite(modelId: string) {
    const key = favouriteKey(provider.provider, modelId)
    setFavourites((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      writeFavourites(next)
      return next
    })
  }

  function select(modelId: string) {
    onChangeModel(modelId)
    setOpen(false)
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((h) => Math.min(h + 1, filtered.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const target = filtered[highlighted]
      if (target) select(target.id)
    }
  }

  const mark = <ProviderMark provider={provider.provider} label={provider.label} className="mr-1" />

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
        // Same rule as `ControlPill`: the model's name is what truncates, never the word "Model".
        title={`Model: ${current?.label ?? effectiveModel ?? '—'}`}
      >
        <span className="shrink-0" style={{ color: 'var(--text-3)' }}>Model: </span>
        {mark}
        <span className="min-w-0 truncate">{current?.label ?? effectiveModel ?? '—'}</span>
        <span className="shrink-0">▾</span>
      </Button>
      {open && (
        <div
          className="absolute left-0 bottom-full mb-1 max-w-72 rounded border z-50"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
          }}
          onKeyDown={handleKeyDown}
        >
          <div className="p-1.5" style={{ borderBottom: '1px solid var(--border)' }}>
            <input
              ref={searchRef}
              type="search"
              aria-label="Search models"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search models…"
              className="w-full rounded px-2 py-1 text-xs outline-none"
              style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
            />
          </div>
          <div role="listbox" aria-label="Model" className="max-h-56 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-[11px]" style={{ color: 'var(--text-3)' }}>
                No models match &ldquo;{query}&rdquo;.{' '}
                <button
                  type="button"
                  className="underline"
                  onClick={() => setQuery('')}
                  style={{ color: 'var(--text-2)' }}
                >
                  Clear search
                </button>
              </div>
            ) : (
              <>
                <div
                  className="flex items-center gap-1.5 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide"
                  style={{ color: 'var(--text-3)' }}
                >
                  {mark}
                  {provider.label}
                </div>
                {filtered.map((model, index) => {
                  const isFavourite = favourites.has(favouriteKey(provider.provider, model.id))
                  const active = model.id === (effectiveModel ?? current?.id)
                  return (
                    <div
                      key={model.id}
                      role="option"
                      aria-selected={active}
                      aria-label={model.label}
                      data-active={active ? 'true' : 'false'}
                      data-highlighted={index === highlighted ? 'true' : 'false'}
                      onMouseEnter={() => setHighlighted(index)}
                      onClick={() => select(model.id)}
                      className="row-item w-full cursor-pointer items-center justify-between gap-2"
                      style={{
                        color: 'var(--text)',
                        background: index === highlighted ? 'var(--row-hover)' : undefined,
                      }}
                    >
                      <span className="flex min-w-0 items-center gap-1.5">
                        {active && <Icon name="check" size={14} style={{ color: 'var(--blue)' }} />}
                        <span className="min-w-0 flex-1 truncate">{model.label}</span>
                      </span>
                      <button
                        type="button"
                        aria-label={
                          isFavourite
                            ? `Remove ${model.label} from favourites`
                            : `Add ${model.label} to favourites`
                        }
                        aria-pressed={isFavourite}
                        onClick={(event) => {
                          event.stopPropagation()
                          toggleFavourite(model.id)
                        }}
                        className="shrink-0"
                        style={{ color: isFavourite ? 'var(--amber)' : 'var(--text-3)' }}
                      >
                        <Icon name="star" size={13} />
                      </button>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
