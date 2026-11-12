import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { ChangedOnlyContext } from './settingsView'

/** Settings layout. The old `.settings-row` was a flex row with `space-between`, so each label
 *  column took whatever width its own text and control left over: no two rows lined up, and a
 *  wide control squeezed "Granted reach" to one word per line. These rows share one grid, so
 *  labels and controls align down the page at every width.
 *
 *  Save model: rows apply on change. A row whose value differs from its default shows a reset
 *  button in a reserved slot (so nothing shifts when it appears); the page confirms with a toast. */

/** Where a row's value comes from, when it is not the default: `changed` (an app or project value;
 *  `other` is the default), `own` (an agent's own; `other` is the project's value) or `project`
 *  (an agent following the project; `other` is that value). */
export interface SettingOrigin {
  kind: 'changed' | 'own' | 'project'
  other: string
}

const ORIGIN_WORDS: Record<SettingOrigin['kind'], [string, string]> = {
  changed: ['Changed', 'default'],
  own: ["Agent's own", 'project'],
  project: ['From project', ''],
}

export function SettingsPage({
  icon,
  title,
  description,
  actions,
  children,
}: {
  icon: string
  title: string
  description?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="aw-settings-page">
      <header className="aw-settings-page-head">
        <span className="settings-section-icon" aria-hidden="true">
          <Icon name={icon} size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="aw-settings-page-title">{title}</h1>
          {description ? <p className="aw-settings-page-desc">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </div>
  )
}

export function SettingsGroup({
  title,
  description,
  aside,
  children,
}: {
  title: string
  description?: React.ReactNode
  /** Right side of the group heading (a group switch, a count). */
  aside?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="aw-settings-group" aria-label={title}>
      <div className="aw-settings-group-head">
        <div className="min-w-0">
          <h2 className="aw-settings-group-title">{title}</h2>
          {description ? <p className="aw-settings-group-desc">{description}</p> : null}
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </div>
      <div className="aw-settings-rows">{children}</div>
    </section>
  )
}

export function SettingsRow({
  label,
  description,
  htmlFor,
  control,
  changed,
  onReset,
  stacked,
  inactive,
  listItem,
  origin,
  overrides,
  children,
}: {
  label: React.ReactNode
  description?: React.ReactNode
  htmlFor?: string
  /** The control, right column. */
  control?: React.ReactNode
  /** True when the value differs from its default: shows the reset button. */
  changed?: boolean
  onReset?: () => void
  /** Control goes under the label at full width (lists, multi-field editors). */
  stacked?: boolean
  /** Greyed while the setting it depends on is off (still focusable, still readable). */
  inactive?: boolean
  /** One entry of a list (a step, a checkpoint, a session), not a setting: search does not look for it. */
  listItem?: boolean
  /** Where the value comes from, and what it would otherwise be: shown under the label, and the
   *  reset says what it returns to. */
  origin?: SettingOrigin
  /** Under a project setting: the agents holding their own value (`AgentOverrides`). */
  overrides?: React.ReactNode
  /** Anything that belongs to the row below the label/control line (nested rows, a list). */
  children?: React.ReactNode
}) {
  const Label = htmlFor ? 'label' : 'div'
  const changedOnly = React.useContext(ChangedOnlyContext)
  if (changedOnly && !listItem && !changed) return null
  const resetWord = origin && origin.kind !== 'project' ? `Reset to ${origin.other}` : 'Reset to default'
  return (
    <div className="aw-settings-row" data-stacked={stacked ? 'true' : 'false'} data-inactive={inactive ? 'true' : 'false'} {...(listItem ? { 'data-list-item': 'true' } : {})}>
      <div className="aw-settings-row-text">
        <Label className="aw-settings-row-label" {...(htmlFor ? { htmlFor } : {})}>
          {label}
        </Label>
        {description ? <p className="aw-settings-row-desc">{description}</p> : null}
        {origin && (origin.kind !== 'changed' || changed) ? (
          <p className="aw-settings-row-source" data-testid="setting-source" data-source={origin.kind}>
            <span className="aw-settings-row-source-mark">{ORIGIN_WORDS[origin.kind][0]}</span>
            {ORIGIN_WORDS[origin.kind][1] ? ` · ${ORIGIN_WORDS[origin.kind][1]}: ` : ' · '}
            {origin.other}
          </p>
        ) : null}
        {overrides}
      </div>
      {control !== undefined ? (
        <div className="aw-settings-row-control">
          <span className="aw-settings-reset-slot">
            {changed && onReset ? (
              <button data-slot="icon-button" type="button" className="aw-icon-button" aria-label={resetWord} title={resetWord} onClick={onReset}>
                <Icon name="restart_alt" size={13} />
              </button>
            ) : null}
          </span>
          {control}
        </div>
      ) : null}
      {children ? <div className="aw-settings-row-children">{children}</div> : null}
    </div>
  )
}

/** One field with its hint or error on a single reserved line below it, so validation never
 *  moves the layout. */
export function Field({
  label,
  hint,
  error,
  warning,
  htmlFor,
  children,
}: {
  label?: React.ReactNode
  hint?: React.ReactNode
  error?: React.ReactNode
  /** Not wrong, but worth knowing (e.g. "This agent cannot run until a runner is bound"). */
  warning?: React.ReactNode
  htmlFor?: string
  children: React.ReactNode
}) {
  return (
    <div className="aw-field">
      {label ? (
        <label className="aw-field-label" htmlFor={htmlFor}>
          {label}
        </label>
      ) : null}
      {children}
      <p className="aw-field-note" data-tone={error ? 'error' : warning ? 'warning' : 'hint'} role={error ? 'alert' : undefined}>
        {error || warning || hint || ' '}
      </p>
    </div>
  )
}

/** A sentence about the page's state, in the page: a failed read (with Retry), a refused save, a
 *  warning the Hub answered with. `error` is announced (`role="alert"`), the rest are `status`. */
export function SettingsNotice({
  tone = 'info',
  title,
  children,
  action,
  testId,
}: {
  tone?: 'error' | 'warning' | 'info' | 'success'
  title?: React.ReactNode
  children?: React.ReactNode
  action?: { label: string; onClick: () => void }
  testId?: string
}) {
  const icon = tone === 'error' ? 'alert_triangle' : tone === 'warning' ? 'warning' : tone === 'success' ? 'check' : 'info'
  return (
    <div className="aw-notice" data-tone={tone} role={tone === 'error' || tone === 'warning' ? 'alert' : 'status'} data-testid={testId}>
      <Icon name={icon} size={14} className="aw-notice-icon" />
      <div className="min-w-0 flex-1">
        {title ? <p className="aw-notice-title">{title}</p> : null}
        {children ? <div className="aw-notice-body">{children}</div> : null}
        {action ? (
          <button type="button" data-slot="notice-action" className="aw-notice-action" onClick={action.onClick}>
            {action.label}
          </button>
        ) : null}
      </div>
    </div>
  )
}

/** The loading thread while a section's data is on its way, holding roughly the height of `rows`
 *  setting rows (behind `.aw-delayed`, so a fast answer shows no flash). */
export function SettingsLoading({ label, rows = 4 }: { label: string; rows?: number }) {
  return <LoadingThread label={label} minHeight={rows * 62} />
}
