/**
 * The status/priority → badge variant maps, kept out of `Badge.tsx` so that file
 * exports components only and stays eligible for fast refresh.
 */

export type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary'

export function statusVariant(status: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
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

export function priorityVariant(priority: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    low:      'default',
    normal:   'default',
    medium:   'warning',
    high:     'danger',
    critical: 'danger',
  }
  return map[priority] ?? 'default'
}
