import type { ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'

const SECTION_ICONS: Record<string, string> = {
  Quality: 'verified_user',
  Instructions: 'description',
  Runners: 'terminal',
  Charters: 'menu_book',
  Worktrees: 'file_vcs',
  Diagnostics: 'monitoring',
  Budgets: 'bar_chart',
  Settings: 'settings',
}

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
}) {
  const headingId = `settings-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  return (
    <section className="settings-section" aria-labelledby={headingId}>
      <div className="settings-section-heading">
        <div className="flex min-w-0 items-start gap-3">
          <span className="settings-section-icon" aria-hidden="true">
            <Icon name={SECTION_ICONS[title] ?? 'settings'} size={17} />
          </span>
          <div className="min-w-0">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em]" style={{ color: 'var(--text-3)' }}>
              Project configuration
            </div>
            <h2 id={headingId} className="text-base font-semibold" style={{ color: 'var(--text)' }}>{title}</h2>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed" style={{ color: 'var(--text-3)' }}>{description}</p>
          </div>
        </div>
        {actions}
      </div>
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
