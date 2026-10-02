import type { AccountingDisplay } from '@/api/accounting'
import { hubDate } from '@/lib/hubTime'

/** Copilot reports charges in nano-AIU; one AI credit is 10^9 of them. The SDK documents the
 * figure as the session's own accounting, not a bill, so it is shown as credits and never as a
 * currency amount. */
export const NANO_AIU_PER_AI_CREDIT = 1_000_000_000

/** `0.28 AI credits`, `<0.01 AI credits` below the display floor, null when nothing was reported. */
export function formatAiCredits(nano: number | null | undefined): string | null {
  if (typeof nano !== 'number' || !Number.isFinite(nano) || nano <= 0) return null
  const credits = nano / NANO_AIU_PER_AI_CREDIT
  if (credits < 0.01) return '<0.01 AI credits'
  return `${credits.toFixed(2)} AI credits`
}

const RUNNER_NAMES: Record<string, string> = { copilot: 'Copilot', codex: 'Codex' }

function allowancePeriod(value: unknown): string {
  if (value === 'seven_day') return 'Weekly'
  if (value === 'daily') return 'Daily'
  if (value === 'monthly') return 'Monthly'
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
    // A non-Claude reading names its provider: Copilot writes one on every run, so a mixed
    // project's headline would otherwise switch providers silently (design D6).
    const provider = display.runner ? RUNNER_NAMES[display.runner] : undefined
    if (provider) {
      const remaining = allowance.remainingPercentage
      const left = typeof remaining === 'number' && Number.isFinite(remaining)
        ? ` · ${Math.floor(remaining)}% left`
        : ''
      return `${provider} ${period.toLowerCase()} ${state}${left}${reset ? ` · ${reset}` : ''}`
    }
    return `${period} ${state}${reset ? ` · ${reset}` : ''}`
  }
  if (display.kind === 'api_equivalent') {
    const base = `$${(display.usd_micros / 1_000_000).toFixed(4)} API-equivalent estimate`
    if (display.unpriced_turns > 0) {
      const noun = display.unpriced_turns === 1 ? 'turn' : 'turns'
      return `${base} — excludes ${display.unpriced_turns} ${noun} with no reported cost`
    }
    return base
  }
  return display.label
}
