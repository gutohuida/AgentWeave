import { useAccounting } from '@/api/accounting'
import { Icon } from '@/components/common/Icon'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'
import { accountingDisplayLabel, formatAiCredits } from '@/components/accounting/accountingDisplay'

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

  const credits = formatAiCredits(data.project.ai_nano_aiu)
  // F722: the project total includes what the Hub's own workers spent (checkpoints, titles, vault
  // jobs; F240), so without this line the rows below it never summed to it. One line, not one per
  // kind -- Environment -> Budgets breaks it down. Null when every call ran unmeasured; absent when
  // no worker ran at all.
  const workers = (data.workers ?? []).filter(
    (line) => line.measured_calls + (line.credited_calls ?? 0) + line.unmeasured_calls > 0,
  )
  const measuredWorkers = workers.filter((line) => line.total_tokens !== null)
  const workerTokens: number | null | undefined =
    workers.length === 0
      ? undefined
      : measuredWorkers.length === 0
        ? null
        : measuredWorkers.reduce((sum, line) => sum + (line.total_tokens ?? 0), 0)

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
      {credits && (
        <div className="overview-budget-row">
          <span>AI credits</span>
          <strong>{credits}</strong>
        </div>
      )}
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
      {workerTokens !== undefined && (
        <div className="overview-budget-row" data-testid="overview-budget-workers">
          <span className="truncate">Hub workers</span>
          <strong>{formatTokens(workerTokens)}</strong>
        </div>
      )}
      {data.agents.length > 4 && (
        <p className="mt-2 text-[11px]" style={{ color: 'var(--text-3)' }}>
          +{data.agents.length - 4} more agents
        </p>
      )}
      <BudgetExhaustionNotice exhausted={data.budget.exhausted} compact />
    </div>
  )
}
