import { cn } from '@/lib/utils'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary'
  className?: string
}

const variantClasses: Record<string, string> = {
  default: 'bg-zinc-700/50 text-zinc-300 ring-1 ring-zinc-600/30',
  success: 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20',
  warning: 'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
  danger: 'bg-red-500/15 text-red-400 ring-1 ring-red-500/20',
  info: 'bg-primary/15 text-primary ring-1 ring-primary/20',
  secondary: 'bg-zinc-800/60 text-zinc-400 ring-1 ring-zinc-700/30',
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  )
}

export function statusVariant(status: string): BadgeProps['variant'] {
  const map: Record<string, BadgeProps['variant']> = {
    pending: 'warning',
    assigned: 'info',
    in_progress: 'info',
    completed: 'success',
    under_review: 'secondary',
    approved: 'success',
    rejected: 'danger',
    revision_needed: 'warning',
  }
  return map[status] ?? 'default'
}

export function priorityVariant(priority: string): BadgeProps['variant'] {
  const map: Record<string, BadgeProps['variant']> = {
    low: 'default',
    medium: 'info',
    high: 'warning',
    critical: 'danger',
  }
  return map[priority] ?? 'default'
}
