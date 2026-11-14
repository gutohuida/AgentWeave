import type { DashboardSummary } from '@/api/dashboards'

/** The line Ask to change puts in the composer: the dashboard named visibly, nothing hidden. */
export function askToChangeLine(dashboard: Pick<DashboardSummary, 'id' | 'name'>): string {
  return `Change the dashboard "${dashboard.name}" (${dashboard.id}): `
}
