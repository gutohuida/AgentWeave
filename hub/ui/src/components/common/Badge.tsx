interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  className?: string
  pill?: boolean
}

const STATUS_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  pending:         { bg: 'rgba(161,161,170,0.1)',  border: 'rgba(161,161,170,0.2)',  color: '#a1a1aa' },
  assigned:        { bg: 'rgba(161,161,170,0.1)',  border: 'rgba(161,161,170,0.2)',  color: '#a1a1aa' },
  in_progress:     { bg: 'rgba(59,130,246,0.1)',  border: 'rgba(59,130,246,0.2)',  color: '#3b82f6' },
  under_review:    { bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.2)',  color: '#f59e0b' },
  completed:       { bg: 'rgba(161,161,170,0.1)',  border: 'rgba(161,161,170,0.2)',  color: '#a1a1aa' },
  approved:        { bg: 'rgba(34,197,94,0.1)',   border: 'rgba(34,197,94,0.2)',   color: '#22c55e' },
  rejected:        { bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.2)',   color: '#ef4444' },
  revision_needed: { bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.2)',   color: '#ef4444' },
}

const VARIANT_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  default:   { bg: 'rgba(161,161,170,0.1)',  border: 'rgba(161,161,170,0.2)',  color: '#a1a1aa' },
  success:   { bg: 'rgba(34,197,94,0.1)',   border: 'rgba(34,197,94,0.2)',   color: '#22c55e' },
  warning:   { bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.2)',  color: '#f59e0b' },
  danger:    { bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.2)',   color: '#ef4444' },
  info:      { bg: 'rgba(59,130,246,0.1)',  border: 'rgba(59,130,246,0.2)',  color: '#3b82f6' },
  secondary: { bg: 'rgba(161,161,170,0.1)',  border: 'rgba(161,161,170,0.2)',  color: '#a1a1aa' },
}

export function Badge({ children, variant = 'default', className, pill = false }: BadgeProps) {
  const s = VARIANT_STYLES[variant]
  return (
    <span
      className={className}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: s.bg,
        border: `1px solid ${s.border}`,
        color: s.color,
        borderRadius: pill ? 9999 : 'var(--radius-sm)',
        padding: pill ? '1px 6px' : '2px 8px',
        fontSize: 11,
        fontWeight: 500,
        lineHeight: 1.4,
      }}
    >
      {children}
    </span>
  )
}

export function StatusBadge({ status, pill }: { status: string; pill?: boolean }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.pending
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        background: s.bg,
        border: `1px solid ${s.border}`,
        color: s.color,
        borderRadius: pill ? 9999 : 'var(--radius-sm)',
        padding: pill ? '1px 6px' : '2px 8px',
        fontSize: 11,
        fontWeight: 500,
        lineHeight: 1.4,
        textTransform: 'capitalize',
      }}
    >
      {status.replace(/_/g, ' ')}
    </span>
  )
}

export function statusVariant(status: string): BadgeProps['variant'] {
  const map: Record<string, BadgeProps['variant']> = {
    pending:         'default',
    assigned:        'default',
    in_progress:     'info',
    completed:       'default',
    under_review:    'warning',
    approved:        'success',
    rejected:        'danger',
    revision_needed: 'danger',
  }
  return map[status] ?? 'default'
}

export function priorityVariant(priority: string): BadgeProps['variant'] {
  const map: Record<string, BadgeProps['variant']> = {
    low:      'default',
    normal:   'default',
    medium:   'warning',
    high:     'danger',
    critical: 'danger',
  }
  return map[priority] ?? 'default'
}
