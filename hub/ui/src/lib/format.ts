/** One place for how numbers, money, dates and schedules read on screen.
 *
 *  The app had three date styles side by side ("Oct 16", "2026-10-14", "10/20/2026, 6:23:45 PM"),
 *  the last from bare `toLocaleString()` calls that follow the OS locale, and token counts printed
 *  in full ("31,843,065 tokens"). Every screen formats through here instead. All functions are
 *  pure and take `now` where the answer depends on it, so tests and the mock are deterministic. */

import { hubDate } from './hubTime'

const COMPACT = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const WHOLE = new Intl.NumberFormat('en-US')

/** 31843065 → "31.8M", 166280 → "166K", 950 → "950". */
export function formatCount(value: number): string {
  return Math.abs(value) < 1000 ? WHOLE.format(value) : COMPACT.format(value)
}

/** 31843065 → "31.8M tokens"; 1 → "1 token". */
export function formatTokens(value: number): string {
  return `${formatCount(value)} ${value === 1 ? 'token' : 'tokens'}`
}

/** The exact figure, for a tooltip behind a compact one: "31,843,065 tokens". */
export function formatTokensExact(value: number): string {
  return `${WHOLE.format(value)} ${value === 1 ? 'token' : 'tokens'}`
}

/** Dollars: two decimals under $100, whole dollars above, never mixed within one figure. */
export function formatMoney(value: number): string {
  if (Math.abs(value) >= 100) return `$${WHOLE.format(Math.round(value))}`
  return `$${value.toFixed(2)}`
}

/** A firing's cost in words: its tokens, then its money when the runner reported it. */
export interface TokenUsage {
  input_tokens?: number
  output_tokens?: number
  cache_read_tokens?: number
  cache_write_tokens?: number
  reasoning_tokens?: number
  cost_usd_micros?: number
}

const TOKEN_DIMENSIONS: Array<[keyof TokenUsage, string]> = [
  ['input_tokens', 'input'],
  ['output_tokens', 'output'],
  ['cache_read_tokens', 'cache read'],
  ['cache_write_tokens', 'cache write'],
  ['reasoning_tokens', 'reasoning'],
]

/** Every token dimension a runner reported, summed — on a claude runner most input is cache. */
function totalTokens(usage: TokenUsage): number | null {
  const reported = TOKEN_DIMENSIONS.filter(([key]) => usage[key] != null)
  return reported.length ? reported.reduce((sum, [key]) => sum + (usage[key] ?? 0), 0) : null
}

/** "10 input · 4,486 output · 7,679 cache write", for a tooltip beside the total. */
export function formatTokenBreakdown(usage: TokenUsage | null | undefined): string | undefined {
  if (!usage) return undefined
  const parts = TOKEN_DIMENSIONS.filter(([key]) => usage[key] != null).map(([key, label]) => `${WHOLE.format(usage[key] ?? 0)} ${label}`)
  return parts.length ? parts.join(' · ') : undefined
}

export function formatUsage(usage: TokenUsage | null | undefined): string {
  if (!usage) return '—'
  const tokens = totalTokens(usage)
  const money = usage.cost_usd_micros
  const parts: string[] = []
  if (tokens != null) parts.push(`${WHOLE.format(tokens)} tokens`)
  if (money != null) parts.push(money < 10_000 ? '<$0.01' : formatMoney(money / 1_000_000))
  return parts.length ? parts.join(' · ') : '—'
}

/** 0.1345 → "13%", 0.0583 → "5.8%". */
export function formatPercent(ratio: number): string {
  const pct = ratio * 100
  return `${pct < 10 ? pct.toFixed(1) : Math.round(pct)}%`
}

/** 239 → "3m 59s", 4 → "4s", 3725 → "1h 2m". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

/** A typed calendar day ("2026-10-14") as local noon on that day, so no time zone moves it to the
 *  day before. Built field by field: it is not a Hub timestamp, so `hubDate` does not apply. */
function calendarDay(value: string): Date {
  const [y, m, d] = value.split('-').map(Number)
  const day = new Date()
  day.setFullYear(y!, m! - 1, d!)
  day.setHours(12, 0, 0, 0)
  return day
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function toDate(value: string | number | Date): Date {
  return value instanceof Date ? value : hubDate(value)
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** The one absolute style: "Oct 16, 20:04", with the year only when it is not `now`'s. */
export function formatDateTime(value: string | number | Date, now: Date = new Date()): string {
  const d = toDate(value)
  const year = d.getFullYear() === now.getFullYear() ? '' : ` ${d.getFullYear()}`
  return `${MONTHS[d.getMonth()]} ${d.getDate()}${year}, ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** A day with no time: "Oct 16" (or "Oct 16 2025"). For calendar dates the operator typed. */
export function formatDay(value: string | number | Date, now: Date = new Date()): string {
  const d = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? calendarDay(value) : toDate(value)
  const year = d.getFullYear() === now.getFullYear() ? '' : ` ${d.getFullYear()}`
  return `${MONTHS[d.getMonth()]} ${d.getDate()}${year}`
}

/** "now", "4m", "3h", "4d", "3w", then the day. Pair with `formatDateTime` in a title attribute. */
export function formatAgo(value: string | number | Date, now: Date = new Date()): string {
  const seconds = (now.getTime() - toDate(value).getTime()) / 1000
  if (seconds < 45) return 'now'
  const minutes = seconds / 60
  if (minutes < 60) return `${Math.round(minutes)}m`
  const hours = minutes / 60
  if (hours < 24) return `${Math.round(hours)}h`
  const days = hours / 24
  if (days < 14) return `${Math.round(days)}d`
  if (days < 60) return `${Math.round(days / 7)}w`
  return formatDay(value, now)
}

/** "4 days ago" style for prose; `formatAgo` is the compact one for rows. */
export function formatAgoLong(value: string | number | Date, now: Date = new Date()): string {
  const short = formatAgo(value, now)
  if (short === 'now') return 'just now'
  const match = /^(\d+)([mhdw])$/.exec(short)
  if (!match) return short
  const n = Number(match[1])
  const unit = { m: 'minute', h: 'hour', d: 'day', w: 'week' }[match[2] as 'm' | 'h' | 'd' | 'w']
  return `${n} ${unit}${n === 1 ? '' : 's'} ago`
}

/** A cron expression as a sentence, for the five shapes the Hub's job editor produces; anything
 *  else is returned as-is (the raw expression still sits in the tooltip). UTC, as the Hub fires. */
export function describeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return expr
  const [min, hour, dom, mon, dow] = parts
  const every = /^\*\/(\d+)$/
  if (every.test(min) && hour === '*' && dom === '*' && mon === '*' && dow === '*') {
    const n = Number(every.exec(min)![1])
    return n === 1 ? 'Every minute' : `Every ${n} minutes`
  }
  if (/^\d+$/.test(min) && every.test(hour) && dom === '*' && mon === '*' && dow === '*') {
    const n = Number(every.exec(hour)![1])
    return n === 1 ? 'Every hour' : `Every ${n} hours`
  }
  if (/^\d+$/.test(min) && hour === '*' && dom === '*' && mon === '*' && dow === '*') return `Hourly at :${pad(Number(min))}`
  if (/^\d+$/.test(min) && /^\d+$/.test(hour) && dom === '*' && mon === '*') {
    const at = `${pad(Number(hour))}:${pad(Number(min))} UTC`
    if (dow === '*') return `Daily at ${at}`
    if (dow === '1-5') return `Weekdays at ${at}`
  }
  return expr
}

/** The future counterpart of `formatAgo`: "in 4m", "in 3h", "in 2d", then the day. A time already
 *  past reads "now" (a schedule about to fire). Pair with `formatDateTime` in a title attribute. */
export function formatIn(value: string | number | Date, now: Date = new Date()): string {
  const seconds = (toDate(value).getTime() - now.getTime()) / 1000
  if (seconds < 45) return 'now'
  const minutes = seconds / 60
  if (minutes < 60) return `in ${Math.round(minutes)}m`
  const hours = minutes / 60
  if (hours < 24) return `in ${Math.round(hours)}h`
  const days = hours / 24
  if (days < 14) return `in ${Math.round(days)}d`
  return formatDay(value, now)
}
