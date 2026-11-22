import { useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { ControlOption, ControlPill, composerControlClassName } from '../ComposerModelControls'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { ControlDescriptor, ModelCatalogResponse, ProviderDescriptor } from '@/api/modelCatalog'
import {
  chatEffortOverrides,
  chatPickOverrides,
  cliLabel,
  entryKey,
  entryLabel,
  isEntryControl,
  modelLabel,
  sameModel,
  type ChatChoice,
  type ChatPick,
} from './poolModel'

interface Option {
  key: string
  pick: ChatPick
  cli: string
  label: string
  /** The accessible name: the label, and "the default" for the pool's default entry. */
  name: string
  active: boolean
  allowed: boolean
  isDefault: boolean
}

interface Group {
  key: string
  heading: string
  /** The CLI whose mark the heading carries; none for the profile's own group. */
  cli?: string
  options: Option[]
}

/**
 * The composer's model choice (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-provider`,
 * FR-3, FR-11): the profile's pool first, under the profile's name, then every catalog model the
 * pool does not hold, grouped by provider. Always a picker, also for a pool of one entry. Once the
 * chat has had a turn its CLI is fixed: models of another CLI are listed but not choosable, saying
 * a new chat is needed. Any model of the chat's own CLI stays choosable. The effort is its own
 * control beside it (FR-6).
 */
export function ChatModelPicker({
  agentName,
  pool,
  catalog,
  current,
  startedOn,
  onPick,
  openRequest = 0,
}: {
  agentName: string
  pool: AgentPoolEntry[]
  catalog: ModelCatalogResponse | undefined
  /** What the next turn runs on (`chatChoice`). */
  current: ChatChoice | undefined
  /** The CLI the conversation started on; null before its first turn. */
  startedOn: string | null
  onPick: (pick: ChatPick) => void
  /** Bumped when the operator accepts `/model`. */
  openRequest?: number
}) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [highlighted, setHighlighted] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const label = current ? modelLabel(catalog, current.cli, current.model) : 'No model'

  const groups = useMemo<Group[]>(() => {
    const allowed = (cli: string) => !startedOn || cli === startedOn
    const own: Option[] = pool.map((entry) => {
      const name = entryLabel(catalog, entry)
      return {
        key: `entry:${entryKey(entry)}`,
        pick: { kind: 'entry', entry },
        cli: entry.cli,
        label: name,
        name: entry.default ? `${name}, the default` : name,
        active: Boolean(current?.entry && entryKey(current.entry) === entryKey(entry)),
        allowed: allowed(entry.cli),
        isDefault: entry.default,
      }
    })
    const providers: Group[] = (catalog?.providers ?? []).map((provider) => ({
      key: `provider:${provider.provider}`,
      heading: provider.label,
      cli: provider.provider,
      options: provider.models
        .filter((model) => !pool.some((e) => e.cli === provider.provider && sameModel(catalog, provider.provider, e.model, model.id)))
        .map((model) => ({
          key: `model:${provider.provider}:${model.id}`,
          pick: { kind: 'model', provider: provider.provider, model: model.id },
          cli: provider.provider,
          label: model.label,
          name: model.label,
          active: Boolean(current && !current.entry && current.cli === provider.provider && sameModel(catalog, provider.provider, current.model, model.id)),
          allowed: allowed(provider.provider),
          isDefault: false,
        })),
    }))
    const needle = filter.trim().toLowerCase()
    return [{ key: 'pool', heading: agentName, options: own }, ...providers]
      .map((group) => ({
        ...group,
        options: needle
          ? group.options.filter((o) => o.label.toLowerCase().includes(needle) || cliLabel(o.cli).toLowerCase().includes(needle))
          : group.options,
      }))
      .filter((group) => group.options.length > 0)
  }, [agentName, catalog, current, filter, pool, startedOn])
  const ordered = groups.flatMap((group) => group.options)

  useEffect(() => {
    if (openRequest > 0) setOpen(true)
  }, [openRequest])

  useEffect(() => {
    if (!open) return
    setFilter('')
    inputRef.current?.focus()
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
  }, [open])

  useEffect(() => {
    if (!open) return
    setHighlighted(Math.max(0, ordered.findIndex((o) => o.active)))
    // Re-highlighted when the list opens or the filter changes it, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, filter])

  useEffect(() => {
    if (!open) return
    document.getElementById(optionId(ordered[highlighted]))?.scrollIntoView?.({ block: 'nearest' })
  }, [open, highlighted, ordered])

  function choose(option: Option | undefined) {
    if (!option || !option.allowed) return
    onPick(option.pick)
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
      choose(ordered[highlighted])
    }
  }

  const mark = current ? <ProviderMark provider={current.cli} label={cliLabel(current.cli)} className="mr-1" /> : null

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
        aria-label={`Model: ${label}`}
      >
        <span className="aw-composer-prefix shrink-0" style={{ color: 'var(--text-3)' }}>Model: </span>
        {mark}
        <span className="min-w-0 truncate">{label}</span>
        <span className="shrink-0">▾</span>
      </Button>
      {open ? (
        <div className="aw-pool-popover" onKeyDown={onKeyDown}>
          <div className="aw-pool-filter">
            <Icon name="search" size={14} />
            <input
              ref={inputRef}
              type="text"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Find a model"
              aria-label="Find a model"
              role="combobox"
              aria-expanded="true"
              aria-controls="aw-chat-model-options"
              aria-activedescendant={ordered[highlighted] ? optionId(ordered[highlighted]) : undefined}
            />
          </div>
          <div id="aw-chat-model-options" role="listbox" aria-label={`Models for this chat with ${agentName}`} className="aw-pool-options">
            {groups.map((group) => (
              <div key={group.key} role="group" aria-label={group.heading}>
                <div className="aw-pool-group-head" aria-hidden="true">
                  {group.cli ? <ProviderMark provider={group.cli} label={group.heading} /> : null}
                  {group.heading}
                </div>
                {group.options.map((option) => {
                  const index = ordered.indexOf(option)
                  return (
                    <div
                      key={option.key}
                      id={optionId(option)}
                      role="option"
                      aria-selected={option.active}
                      aria-disabled={option.allowed ? undefined : 'true'}
                      aria-label={option.name}
                      data-highlighted={index === highlighted ? 'true' : 'false'}
                      className="aw-pool-option"
                      onMouseEnter={() => setHighlighted(index)}
                      onClick={() => choose(option)}
                    >
                      <span className="aw-pool-option-check">{option.active ? <Icon name="check" size={14} /> : null}</span>
                      <span className="aw-pool-option-text">
                        <span className="aw-pool-option-label">
                          {group.cli ? null : <ProviderMark provider={option.cli} label={cliLabel(option.cli)} className="mr-1" />}
                          {option.label}
                        </span>
                        {!option.allowed ? (
                          <span className="aw-pool-option-detail">
                            This chat runs on {cliLabel(startedOn!)}; start a new chat for {cliLabel(option.cli)}
                          </span>
                        ) : null}
                      </span>
                      {option.isDefault ? <span className="aw-pool-option-tag">Default</span> : null}
                    </div>
                  )
                })}
              </div>
            ))}
            {ordered.length === 0 ? <p className="aw-pool-option-detail aw-pool-none">No model matches “{filter}”.</p> : null}
          </div>
          <p className="aw-pool-popover-foot">
            This choice is for this chat only. Tasks and reviews run on {agentName}’s own models and do not follow it.
          </p>
        </div>
      ) : null}
    </div>
  )
}

function optionId(option: Option | undefined): string {
  return option ? `aw-chat-model-${option.key.replace(/[^a-zA-Z0-9_-]/g, '-')}` : ''
}

/** The chat's model picker and its effort pill (FR-3, FR-6), changing the overrides the composer
 *  sends. */
export function ChatChoiceControls({
  agentName,
  pool,
  catalog,
  provider,
  current,
  chatOverrides,
  startedOn,
  onChange,
  openRequest,
}: {
  agentName: string
  pool: AgentPoolEntry[]
  catalog: ModelCatalogResponse | undefined
  /** The chosen model's provider, whose efforts are offered. */
  provider: ProviderDescriptor
  current: ChatChoice | undefined
  chatOverrides: Record<string, string>
  startedOn: string | null
  onChange: (overrides: Record<string, string>) => void
  openRequest?: number
}) {
  const effort = provider.controls.find((control) => control.kind === 'enum' && isEntryControl(control.id))
  return (
    <>
      <ChatModelPicker
        agentName={agentName}
        pool={pool}
        catalog={catalog}
        current={current}
        startedOn={startedOn}
        onPick={(pick) => onChange(chatPickOverrides(catalog, chatOverrides, pick))}
        openRequest={openRequest}
      />
      {effort ? (
        <ChatEffortPill
          control={effort}
          value={current?.effort ?? null}
          onChange={(value) => onChange(chatEffortOverrides(chatOverrides, value))}
        />
      ) : null}
    </>
  )
}

/** The chat's effort (FR-6): the chosen model's provider's efforts, and the usual effort, which
 *  sends none and lets the CLI decide. Changeable on every turn, the first and every later one. */
function ChatEffortPill({
  control,
  value,
  onChange,
}: {
  control: ControlDescriptor
  value: string | null
  onChange: (value: string | null) => void
}) {
  const current = value ? control.values.find((v) => v.id === value) : undefined
  return (
    <ControlPill label={control.label} valueLabel={current?.label ?? value ?? 'Usual'}>
      {(close) => (
        <>
          <ControlOption
            active={!value}
            label="Usual"
            onSelect={() => {
              onChange(null)
              close()
            }}
          />
          {control.values.map((option) => (
            <ControlOption
              key={option.id}
              active={option.id === value}
              label={option.label}
              onSelect={() => {
                onChange(option.id)
                close()
              }}
            />
          ))}
        </>
      )}
    </ControlPill>
  )
}
