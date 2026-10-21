import type { ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'

const SECTION_ICONS: Record<string, string> = {
  // Project-scoped sections
  Quality: 'verified_user',
  Instructions: 'description',
  Runners: 'terminal',
  Charters: 'menu_book',
  Manager: 'schedule',
  Worktrees: 'file_vcs',
  Diagnostics: 'monitoring',
  Budgets: 'bar_chart',
  Settings: 'settings',
  Traces: 'monitoring',
  // Agent-scoped sections. Without these all seven fell through to the generic gear, in the same
  // pass that gave the rail nav seven distinct glyphs for the very same sections.
  Identity: 'badge',
  Execution: 'terminal',
  Charter: 'menu_book',
  Interaction: 'forum',
  Context: 'data_usage',
  Access: 'lock',
  Workspace: 'folder',
}

/** One settings page in the old row vocabulary, framed like `SettingsPage` (ui/settings.tsx) so
 *  a section not yet rebuilt on the new rows sits in Project settings and agent settings without a
 *  second heading style. The "Project configuration" / "Agent configuration" eyebrow is gone: the
 *  section list beside it already says whose settings these are; `scope` is accepted and unused. */
export function SettingsSection({
  title,
  description,
  children,
  actions,
}: {
  title: string
  description: string
  children: ReactNode
  actions?: ReactNode
  /** Retired: the eyebrow it named is gone. */
  scope?: string
}) {
  const headingId = `settings-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  return (
    <section className="aw-settings-page settings-section-framed" aria-labelledby={headingId}>
      <header className="aw-settings-page-head">
        <span className="settings-section-icon" aria-hidden="true">
          <Icon name={SECTION_ICONS[title] ?? 'settings'} size={16} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id={headingId} className="aw-settings-page-title">{title}</h2>
          <p className="aw-settings-page-desc">{description}</p>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className="settings-section-rows">{children}</div>
    </section>
  )
}

export function SettingsRow({
  label,
  description,
  children,
}: {
  label: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="settings-row">
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{label}</div>
        <p className="mt-1 max-w-[560px] text-xs leading-relaxed" style={{ color: 'var(--text-3)' }}>{description}</p>
      </div>
      <div className="settings-row-control">{children}</div>
    </div>
  )
}
