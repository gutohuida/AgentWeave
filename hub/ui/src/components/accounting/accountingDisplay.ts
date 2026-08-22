import type { AccountingDisplay } from '@/api/accounting'
import { hubDate } from '@/lib/hubTime'

function allowancePeriod(value: unknown): string {
  if (value === 'seven_day') return 'Weekly'
  if (value === 'daily') return 'Daily'
  return 'Rate-limit'
}

function resetLabel(value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const date = hubDate(value * 1000)
  if (Number.isNaN(date.getTime())) return null
  return `resets ${date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })}`
}

/** Turn runner-specific allowance payloads into operator language. The object is retained in the
 * API for diagnostics, but a settings or overview surface must never print it as raw JSON. */
export function accountingDisplayLabel(display: AccountingDisplay): string {
  if (display.kind === 'allowance') {
    const allowance = display.allowance
    if (!('status' in allowance) && !('overageStatus' in allowance) && !('rateLimitType' in allowance)) {
      return display.label
    }
    const period = allowancePeriod(allowance.rateLimitType)
    const status = String(allowance.status ?? allowance.overageStatus ?? '').toLowerCase()
    const reset = resetLabel(allowance.resetsAt)
    const state = allowance.isUsingOverage === true
      ? 'using paid overage'
      : status === 'rejected'
        ? 'allowance exhausted'
        : status === 'allowed' || status === 'accepted'
          ? 'allowance available'
          : 'allowance reported'
    return `${period} ${state}${reset ? ` · ${reset}` : ''}`
  }
  if (display.kind === 'api_equivalent') {
    return `$${(display.usd_micros / 1_000_000).toFixed(4)} API-equivalent estimate`
  }
  return display.label
}
