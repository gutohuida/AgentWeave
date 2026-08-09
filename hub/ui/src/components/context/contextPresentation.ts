import type {
  ContextUsage,
  ContextUsageBasis,
  ContextUsageStatus,
} from '@/api/agents'

export const CONTEXT_WARNING_PERCENT = 70
export const CONTEXT_CRITICAL_PERCENT = 90

export type ContextSeverity = 'normal' | 'warning' | 'critical' | 'neutral'

export interface ContextPresentation {
  usage: ContextUsage
  label: string
  detail: string
  percent: number | null
  severity: ContextSeverity
  color: string
  showBar: boolean
  isPolicyWarning: boolean
}

type ContextRecord = Record<string, unknown>

const STATUSES = new Set<ContextUsageStatus>([
  'measured',
  'estimated',
  'unsupported',
  'unavailable',
])

const BASES = new Set<ContextUsageBasis>([
  'provider_context',
  'latest_request_input',
  'provider_reported_ratio',
  'cumulative_delta',
])

function isRecord(value: unknown): value is ContextRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function nonNegativeInteger(value: unknown): number | null {
  const number = finiteNumber(value)
  return number !== null && Number.isInteger(number) && number >= 0 ? number : null
}

function positiveInteger(value: unknown): number | null {
  const number = nonNegativeInteger(value)
  return number !== null && number > 0 ? number : null
}

function firstInteger(data: ContextRecord, keys: string[]): number | null {
  for (const key of keys) {
    const value = nonNegativeInteger(data[key])
    if (value !== null) return value
  }
  return null
}

function observedAt(value: unknown): number {
  const numeric = finiteNumber(value)
  if (numeric !== null && numeric >= 0) return numeric
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) return parsed / 1000
  }
  return 0
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function normalizedPercent(value: unknown): number | null {
  const number = finiteNumber(value)
  return number !== null && number >= 0 && number <= 100 ? number : null
}

function normalizeBreakdown(value: unknown): ContextUsage['breakdown'] {
  if (!isRecord(value)) return null
  const allowed = [
    'input_tokens',
    'output_tokens',
    'cache_read_tokens',
    'cache_creation_tokens',
    'reasoning_tokens',
    'cached_input_tokens',
  ] as const
  const normalized: NonNullable<ContextUsage['breakdown']> = {}
  for (const key of allowed) {
    const item = nonNegativeInteger(value[key])
    if (item !== null) normalized[key] = item
  }
  return Object.keys(normalized).length > 0 ? normalized : null
}

function neutralUsage(
  status: 'unavailable' | 'unsupported',
  data: ContextRecord,
): ContextUsage {
  return {
    status,
    source: optionalString(data.source) ?? (status === 'unsupported' ? 'runner' : 'unknown'),
    basis: null,
    context_tokens: null,
    limit_tokens: null,
    percent: null,
    model: optionalString(data.model),
    session_id: optionalString(data.session_id),
    observed_at: observedAt(data.observed_at ?? data.updated_at),
    breakdown: normalizeBreakdown(data.breakdown),
  }
}

/**
 * Normalize canonical Hub data and the aliases emitted by older Hub/CLI
 * versions. Contradictory or unusable dictionaries become unavailable rather
 * than presenting a fabricated zero.
 */
export function normalizeContextUsage(value: unknown): ContextUsage | null {
  if (value == null) return null
  if (!isRecord(value)) return neutralUsage('unavailable', {})

  const rawStatus = optionalString(value.status)
  if (rawStatus && !STATUSES.has(rawStatus as ContextUsageStatus)) {
    return neutralUsage('unavailable', value)
  }
  if (rawStatus === 'unavailable' || rawStatus === 'unsupported') {
    return neutralUsage(rawStatus, value)
  }

  const isLegacy = rawStatus === null
  const status = (rawStatus ?? 'measured') as 'measured' | 'estimated'
  const source = optionalString(value.source) ?? 'legacy'
  const contextTokens = firstInteger(value, [
    'context_tokens',
    'tokens_used',
    'input_tokens',
  ])
  let limitTokens = positiveInteger(
    value.limit_tokens
      ?? value.tokens_limit
      ?? value.context_limit
      ?? value.max_context_tokens,
  )
  const rawRatio = finiteNumber(value.context_usage ?? value.context_usage_ratio)
  const suppliedPercent = normalizedPercent(
    rawRatio !== null ? rawRatio * 100 : value.percent,
  )
  const rawBasis = optionalString(value.basis)
  let basis = rawBasis && BASES.has(rawBasis as ContextUsageBasis)
    ? rawBasis as ContextUsageBasis
    : null

  if (isLegacy && contextTokens === 0 && limitTokens === null && suppliedPercent === null) {
    return neutralUsage('unavailable', value)
  }

  let percent: number | null = null
  if (contextTokens !== null && limitTokens !== null) {
    const derived = Math.min(100, Math.round((contextTokens / limitTokens) * 10000) / 100)
    if (isLegacy && suppliedPercent !== null && Math.abs(suppliedPercent - derived) > 1) {
      // Mirror Hub ingress: a contradictory legacy percentage makes the
      // denominator untrustworthy, but the token count remains useful.
      limitTokens = null
    } else {
      percent = derived
    }
    basis ??= 'provider_context'
  } else if (contextTokens !== null) {
    basis ??= 'provider_context'
  } else if (suppliedPercent !== null && (!isLegacy || suppliedPercent > 0)) {
    // A legacy zero percentage is not a measurement: older CLIs wrote
    // `{"percent": 0}` on every session reset, so it must degrade to
    // unavailable rather than paint a 0% bar. A canonical sample that
    // explicitly declares provider_reported_ratio may still report 0.
    percent = suppliedPercent
    basis ??= 'provider_reported_ratio'
  } else {
    return neutralUsage('unavailable', value)
  }

  return {
    status,
    source,
    basis,
    context_tokens: contextTokens,
    limit_tokens: limitTokens,
    percent,
    model: optionalString(value.model),
    session_id: optionalString(value.session_id),
    observed_at: observedAt(value.observed_at ?? value.updated_at),
    breakdown: normalizeBreakdown(value.breakdown),
  }
}

function formatTokens(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

export function presentContextUsage(value: unknown): ContextPresentation | null {
  const usage = normalizeContextUsage(value)
  if (!usage) return null

  if (usage.status === 'unsupported') {
    return {
      usage,
      label: 'Context unsupported',
      detail: 'This runner does not report context usage',
      percent: null,
      severity: 'neutral',
      color: 'var(--text-3)',
      showBar: false,
      isPolicyWarning: false,
    }
  }
  if (usage.status === 'unavailable') {
    return {
      usage,
      label: 'Context unavailable',
      detail: 'Waiting for a context sample',
      percent: null,
      severity: 'neutral',
      color: 'var(--text-3)',
      showBar: false,
      isPolicyWarning: false,
    }
  }

  const estimated = usage.status === 'estimated'
  const percent = usage.percent ?? null
  const severity: ContextSeverity = estimated || percent === null
    ? 'neutral'
    : percent >= CONTEXT_CRITICAL_PERCENT
      ? 'critical'
      : percent >= CONTEXT_WARNING_PERCENT
        ? 'warning'
        : 'normal'
  const color = severity === 'critical'
    ? 'var(--red)'
    : severity === 'warning'
      ? 'var(--amber)'
      : severity === 'normal'
        ? 'var(--green)'
        : 'var(--text-2)'

  let label: string
  let detail: string
  if (percent !== null) {
    // Both readings, on screen rather than in a tooltip. The percentage alone answers "how full"
    // but not "of what" — and the window differs by an order of magnitude between models, which
    // is the same reason a threshold can be set in either unit.
    const counted = usage.context_tokens !== null && usage.context_tokens !== undefined
    label = counted && usage.limit_tokens
      ? `${formatTokens(usage.context_tokens as number)} / ${formatTokens(usage.limit_tokens)} · ${percent}%${estimated ? ' est.' : ''}`
      : `${percent}%${estimated ? ' estimated' : ''}`
    detail = counted
      ? `${formatTokens(usage.context_tokens as number)} / ${
        usage.limit_tokens ? formatTokens(usage.limit_tokens) : 'unknown'
      } tokens${usage.model ? ` — ${usage.model}` : ''}`
      : `${percent}% of context`
  } else {
    label = `${formatTokens(usage.context_tokens ?? 0)} tokens${estimated ? ' estimated' : ''}`
    detail = 'Unknown context limit'
  }

  return {
    usage,
    label,
    detail,
    percent,
    severity,
    color,
    showBar: percent !== null,
    isPolicyWarning: severity === 'warning' || severity === 'critical',
  }
}
