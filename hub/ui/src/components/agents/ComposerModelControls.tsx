import { useEffect, useRef, useState } from 'react'
import { Icon, ProviderMark } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useModelCatalog, providerForRunner, type ControlDescriptor, type ProviderDescriptor } from '@/api/modelCatalog'

/** The AgentWeave counterpart of t3code's `composerControlClassName` (design.md Decision
 * 1) — every composer trigger (model, effort, conversation routing, target agent) renders
 * through this, on the `Button` primitive's `ghost`/`pill` combination, so they cannot
 * drift into their own private visual dialect the way `ControlPill` used to. `ghost`
 * supplies "no border or fill at rest, hover brightens fill only"; `pill` supplies content
 * height with no radius of its own, so `rounded-full` here is the only rounding rule in
 * play — never fighting a size variant's own radius class for specificity. */
export const composerControlClassName =
  'rounded-full text-[var(--text-2)] hover:text-[var(--text)]'

interface ComposerModelControlsProps {
  /** The target agent's bound runner CLI (e.g. "claude", "codex") — resolves which
   * catalog provider's models/controls are offered. Re-derives the moment this changes,
   * so switching the composer's target agent switches the offered catalog with it. */
  runner: string | undefined | null
  /** Effective values at rest: an explicit override, or (when absent) the resolved
   * default — the caller is responsible for that resolution so this component only ever
   * renders what it's given, with no catalog knowledge of its own beyond rendering it. */
  effectiveModel: string | null
  effectiveControls: Record<string, string>
  onChangeModel: (modelId: string) => void
  onChangeControl: (controlId: string, value: string) => void
}

/** A compact "Label: Value ▾" trigger + popover listbox — the one interaction shape every
 * catalog-driven control (model, effort, any future one) shares. Exported so
 * ComposerConversationRouting can reuse the same shape for a non-catalog pill
 * (conversation destination isn't a model-catalog control, but the interaction is
 * identical). */
export function ControlPill({
  label,
  valueLabel,
  icon,
  children,
}: {
  label: string
  valueLabel: string
  /** A leading mark (e.g. a provider's brand mark) shown before the value — optional
   * because most pills (Effort, conversation routing) have no icon of their own. */
  icon?: React.ReactNode
  children: (close: () => void) => React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <Button
        type="button"
        variant="ghost"
        size="pill"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={composerControlClassName}
        title={label}
      >
        <span style={{ color: 'var(--text-3)' }}>{label}: </span>
        {icon}
        {valueLabel} ▾
      </Button>
      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute left-0 bottom-full mb-1 max-w-64 max-h-56 overflow-y-auto p-1 rounded border z-50"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
          }}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

export function ControlOption({
  active,
  label,
  icon,
  onSelect,
}: {
  active: boolean
  label: string
  icon?: React.ReactNode
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      data-active={active ? 'true' : 'false'}
      onClick={onSelect}
      className="row-item w-full text-left"
      style={{ color: 'var(--text)' }}
    >
      {active && <Icon name="check" size={12} style={{ color: 'var(--blue)' }} />}
      {icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
    </button>
  )
}

function ModelPill({
  provider,
  effectiveModel,
  onChangeModel,
}: {
  provider: ProviderDescriptor
  effectiveModel: string | null
  onChangeModel: (modelId: string) => void
}) {
  const current = provider.models.find((m) => m.id === effectiveModel) ?? provider.models.find((m) => m.default)
  // One mark for the whole pill: every model offered here belongs to the same provider
  // (the target agent's runner already resolved that), so the mark identifies the group,
  // not which row within it — matching t3code's own per-provider grouping.
  const mark = <ProviderMark provider={provider.provider} label={provider.label} className="mr-1" />
  return (
    <ControlPill label="Model" valueLabel={current?.label ?? effectiveModel ?? '—'} icon={mark}>
      {(close) => (
        <>
          {provider.models.map((model) => (
            <ControlOption
              key={model.id}
              active={model.id === (effectiveModel ?? current?.id)}
              label={model.label}
              icon={mark}
              onSelect={() => {
                onChangeModel(model.id)
                close()
              }}
            />
          ))}
        </>
      )}
    </ControlPill>
  )
}

function EnumControlPill({
  control,
  effectiveValue,
  onChangeControl,
}: {
  control: ControlDescriptor
  effectiveValue: string | undefined
  onChangeControl: (controlId: string, value: string) => void
}) {
  const value = effectiveValue ?? control.default ?? control.values[0]?.id
  const current = control.values.find((v) => v.id === value)
  return (
    <ControlPill label={control.label} valueLabel={current?.label ?? value ?? '—'}>
      {(close) => (
        <>
          {control.values.map((option) => (
            <ControlOption
              key={option.id}
              active={option.id === value}
              label={option.label}
              onSelect={() => {
                onChangeControl(control.id, option.id)
                close()
              }}
            />
          ))}
        </>
      )}
    </ControlPill>
  )
}

/**
 * Renders the target agent's provider's models and controls, entirely from the catalog —
 * no provider name, model id, or control id is hardcoded here
 * (2026-08-04-hub-model-control-and-provisioning). Renders nothing for a provider the
 * catalog doesn't declare (e.g. runner not yet resolved) rather than guessing.
 */
export function ComposerModelControls({
  runner,
  effectiveModel,
  effectiveControls,
  onChangeModel,
  onChangeControl,
}: ComposerModelControlsProps) {
  const { data: catalog } = useModelCatalog()
  const providerId = providerForRunner(runner)
  const provider = catalog?.providers.find((p) => p.provider === providerId)
  if (!provider) return null

  return (
    <>
      <ModelPill provider={provider} effectiveModel={effectiveModel} onChangeModel={onChangeModel} />
      {provider.controls
        .filter((control) => control.kind === 'enum')
        .map((control) => (
          <EnumControlPill
            key={control.id}
            control={control}
            effectiveValue={effectiveControls[control.id]}
            onChangeControl={onChangeControl}
          />
        ))}
    </>
  )
}
