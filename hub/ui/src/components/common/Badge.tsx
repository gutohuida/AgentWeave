interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  className?: string
}

/* M3 tonal chip — all colors via CSS variables for theme/mode compatibility */
const variantStyle: Record<string, { background: string; color: string }> = {
  default:   { background: 'var(--surface-highest)', color: 'var(--on-sv)' },
  success:   { background: 'var(--s-cont)',          color: 'var(--on-s-cont)' },
  warning:   { background: 'var(--t-cont)',          color: 'var(--on-t-cont)' },
  danger:    { background: 'var(--error-cont)',      color: 'var(--on-error-cont)' },
  info:      { background: 'var(--p-cont)',          color: 'var(--on-p-cont)' },
  secondary: { background: 'var(--sur-var)',         color: 'var(--on-sv)' },
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  const s = variantStyle[variant]
  return (
    <span
      className={`m3-chip m3-label-small${className ? ' ' + className : ''}`}
      style={{ background: s.background, color: s.color }}
    >
      {children}
    </span>
  )
}

export function statusVariant(status: string): BadgeProps['variant'] {
  const map: Record<string, BadgeProps['variant']> = {
    pending:         'warning',
    assigned:        'info',
    in_progress:     'info',
    completed:       'success',
    under_review:    'secondary',
    approved:        'success',
    rejected:        'danger',
    revision_needed: 'warning',
  }
  return map[status] ?? 'default'
}

export function priorityVariant(priority: string): BadgeProps['variant'] {
  const map: Record<string, BadgeProps['variant']> = {
    low:      'default',
    medium:   'info',
    high:     'warning',
    critical: 'danger',
  }
  return map[priority] ?? 'default'
}
