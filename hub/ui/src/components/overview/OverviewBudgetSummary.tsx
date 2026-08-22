import { useAccounting } from '@/api/accounting'
import { Icon } from '@/components/common/Icon'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'
import { accountingDisplayLabel } from '@/components/accounting/accountingDisplay'

function formatTokens(value: number | null): string {
  return value === null ? 'Usage unavailable' : `${value.toLocaleString()} tokens`
}

export function OverviewBudgetSummary() {
  const { data, isLoading } = useAccounting()

  if (isLoading || !data) {
    return (
      <div className="overview-budget-summary" aria-label="Loading budget summary">
        <div className="skeleton h-4 w-20" />
        <div className="skeleton mt-3 h-7 w-44" />
        <div className="skeleton mt-3 h-4 w-2/3" />
      </div>
    )
  }

  return (
    <div className="overview-budget-summary" aria-label="Budget summary">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[13px] font-semibold" style={{ color: 'var(--text)' }}>Budgets</h2>
        <span className="inline-flex items-center gap-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
          <Icon name="bar_chart" size={13} />
          {data.project.measured_turns} measured
        </span>
      </div>
      <div className="overview-budget-row">
        <span>Project total</span>
        <strong>{formatTokens(data.project.total_tokens)}</strong>
      </div>
      <div className="overview-budget-row">
        <span>Allowance</span>
        <strong>{accountingDisplayLabel(data.preferred_display)}</strong>
      </div>
      {data.agents.slice(0, 4).map((agent) => (
        <div className="overview-budget-row" key={agent.agent}>
          <span className="truncate">{agent.agent}</span>
          <strong>{formatTokens(agent.total_tokens)}</strong>
        </div>
      ))}
      {data.agents.length > 4 && (
        <p className="mt-2 text-[11px]" style={{ color: 'var(--text-3)' }}>
          +{data.agents.length - 4} more agents
        </p>
      )}
      <BudgetExhaustionNotice exhausted={data.budget.exhausted} compact />
    </div>
  )
}
