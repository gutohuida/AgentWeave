import { formatCount } from '@/lib/format'

interface BudgetExhaustionNoticeProps {
  exhausted: boolean
  compact?: boolean
  /** The limit and the use, so the notice says how far over it is (F953). */
  limitTokens?: number | null
  usedTokens?: number
  /** Turns waiting for the budget; none is not said. */
  heldCount?: number
  /** Where the limit is changed. Without it the notice offers no control. */
  onOpenBudgets?: () => void
  /** Inside a tinted wrapper that already draws the band: no second border. */
  embedded?: boolean
}

export function BudgetExhaustionNotice({
  exhausted,
  compact = false,
  limitTokens,
  usedTokens,
  heldCount = 0,
  onOpenBudgets,
  embedded = false,
}: BudgetExhaustionNoticeProps) {
  if (!exhausted) return null

  const explanation = 'Autonomous turns are paused; operator messages can still run.'
  if (compact) {
    return (
      <span
        role="status"
        title={explanation}
        style={{ color: 'var(--amber)', fontWeight: 500 }}
      >
        budget paused
      </span>
    )
  }
  const figures =
    limitTokens != null && usedTokens != null
      ? `Token limit reached: ${formatCount(usedTokens)} of ${formatCount(limitTokens)} tokens. `
      : ''
  const held = heldCount > 0 ? ` ${heldCount} ${heldCount === 1 ? 'turn' : 'turns'} waiting.` : ''
  return (
    <div
      role="alert"
      style={{
        border: embedded ? undefined : '1px solid color-mix(in srgb, var(--amber) 35%, transparent)',
        background: embedded ? undefined : 'color-mix(in srgb, var(--amber) 8%, transparent)',
        borderRadius: 'var(--radius)',
        color: 'var(--amber)',
        padding: embedded ? 0 : '8px 10px',
        fontSize: 12,
      }}
    >
      {figures}
      {explanation}
      {held}
      {onOpenBudgets ? (
        <>
          {' '}
          <button type="button" className="aw-overview-link" onClick={onOpenBudgets}>
            Change it in Budgets
          </button>
        </>
      ) : null}
    </div>
  )
}
