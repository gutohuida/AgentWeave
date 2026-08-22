import { tint } from '@/lib/colorTint'
import type { BadgeVariant } from './badgeVariants'
import { Icon } from './Icon'

interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
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
// In-progress/info needs attention but is not terminal. Amber carries that
// meaning; blue remains reserved for focus and selection.
const INFO = tone('var(--amber)')
const PROGRESS = tone('var(--blue)')
const WARNING = tone('var(--amber)')
const SUCCESS = tone('var(--green)')
const DANGER = tone('var(--red)')

const STATUS_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  pending:         NEUTRAL,
  assigned:        NEUTRAL,
  in_progress:     PROGRESS,
  under_review:    WARNING,
  completed:       NEUTRAL,
  approved:        SUCCESS,
  rejected:        DANGER,
  revision_needed: DANGER,
}

const PRIORITY_STYLES: Record<string, { bg: string; border: string; color: string }> = {
  low: NEUTRAL,
  medium: NEUTRAL,
  high: WARNING,
  critical: DANGER,
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
      className={['aw-chip', className].filter(Boolean).join(' ')}
      data-pill={pill || undefined}
      style={{
        background: s.bg,
        border: `1px solid ${s.border}`,
        color: s.color,
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
      className="aw-chip"
      data-pill={pill || undefined}
      style={{
        background: s.bg,
        border: `1px solid ${s.border}`,
        color: s.color,
        textTransform: 'capitalize',
      }}
    >
      {status.replace(/_/g, ' ')}
    </span>
  )
}

/** Priority is a different vocabulary from lifecycle status. Keeping its own map prevents every
 * priority from falling through StatusBadge's neutral pending fallback. The flag makes high-impact
 * priority scannable by shape as well as colour. */
export function PriorityBadge({ priority }: { priority: string }) {
  const s = PRIORITY_STYLES[priority] ?? NEUTRAL
  const flagged = priority === 'high' || priority === 'critical'
  return (
    <span
      className="aw-chip"
      data-testid={`priority-badge-${priority}`}
      style={{
        background: s.bg,
        border: `1px solid ${s.border}`,
        color: s.color,
        textTransform: 'capitalize',
      }}
    >
      {flagged && <Icon name="flag" size={11} />}
      {priority.replace(/_/g, ' ')}
    </span>
  )
}
