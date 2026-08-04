import { tint } from '@/lib/colorTint'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  className?: string
  pill?: boolean
}

// Every status/variant colour is a semantic token (--green/--amber/--red/--blue/--text-2), never a
// raw literal — the badge palette must recolour automatically with the ground plane, not survive it
// unchanged. bg/border are derived from the same token via color-mix rather than authored separately,
// so a status can never drift into a colour its text doesn't share.
function tone(token: string): { bg: string; border: string; color: string } {
  return {
    bg: tint(token, 10),
    border: tint(token, 20),
    color: token,
  }
}

const NEUTRAL = tone('var(--text-2)')
const INFO = tone('var(--blue)')
const WARNING = tone('var(--amber)')
const SUCCESS = tone('var(--green)')
const DANGER = tone('var(--red)')

const STATUS_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  pending:         NEUTRAL,
  assigned:        NEUTRAL,
  in_progress:     INFO,
  under_review:    WARNING,
  completed:       NEUTRAL,
  approved:        SUCCESS,
  rejected:        DANGER,
  revision_needed: DANGER,
}

const VARIANT_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  default:   NEUTRAL,
  success:   SUCCESS,
  warning:   WARNING,
  danger:    DANGER,
  info:      INFO,
  secondary: NEUTRAL,
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
