import type { ReactNode } from 'react'

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
        <div>
          <h2 id={headingId} className="text-base font-semibold" style={{ color: 'var(--text)' }}>{title}</h2>
          <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>{description}</p>
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
