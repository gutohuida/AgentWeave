interface BudgetExhaustionNoticeProps {
  exhausted: boolean
  compact?: boolean
}

export function BudgetExhaustionNotice({
  exhausted,
  compact = false,
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
  return (
    <div
      role="alert"
      style={{
        border: '1px solid rgba(245,158,11,0.35)',
        background: 'rgba(245,158,11,0.08)',
        borderRadius: 'var(--radius)',
        color: 'var(--amber)',
        padding: '8px 10px',
        fontSize: 12,
      }}
    >
      {explanation}
    </div>
  )
}
