import { useEffect, useState } from 'react'
import { useAccounting, useUpdateTokenBudget } from '@/api/accounting'
import { Button } from '@/components/ui/button'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { BudgetExhaustionNotice } from './BudgetExhaustionNotice'

function formatTokens(value: number | null): string {
  return value === null ? 'Unavailable' : `${value.toLocaleString()} tokens`
}

function PreferredDisplay() {
  const { data } = useAccounting()
  if (!data) return null
  const display = data.preferred_display
  if (display.kind === 'allowance') {
    return (
      <div>
        <span>Rate-limit allowance</span>
        <code className="ml-2" style={{ color: 'var(--text-3)', fontSize: 11 }}>
          {JSON.stringify(display.allowance)}
        </code>
      </div>
    )
  }
  if (display.kind === 'api_equivalent') {
    return (
      <span>
        ${(display.usd_micros / 1_000_000).toFixed(4)} API-equivalent estimate
      </span>
    )
  }
  return <span>{display.label}</span>
}

export function AccountingPanel() {
  const { data, isLoading } = useAccounting()
  const updateBudget = useUpdateTokenBudget()
  const [budgetInput, setBudgetInput] = useState('')

  useEffect(() => {
    setBudgetInput(data?.budget.limit_tokens?.toString() ?? '')
  }, [data?.budget.limit_tokens])

  if (isLoading || !data) return null

  const applyBudget = () => {
    const value = Number(budgetInput)
    if (Number.isInteger(value) && value > 0) updateBudget.mutate(value)
  }

  return (
    <SettingsSection title="Budgets" description="Token usage for this project and its agents, and the limit that pauses autonomous turns.">
      <div className="py-4">
        <div style={{ fontSize: 20, fontWeight: 600 }}>{formatTokens(data.project.total_tokens)}</div>
        <div style={{ color: 'var(--text-3)', fontSize: 11, marginTop: 2 }}>
          {data.project.measured_turns} measured · {data.project.unavailable_turns} usage unavailable
        </div>
        <div style={{ color: 'var(--text-2)', fontSize: 12, marginTop: 6 }}>
          <PreferredDisplay />
        </div>

        <div className="mt-3">
          <BudgetExhaustionNotice exhausted={data.budget.exhausted} />
        </div>

        {data.agents.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2" aria-label="Usage by agent">
            {data.agents.map((agent) => (
              <span
                key={agent.agent}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 9999,
                  padding: '3px 8px',
                  fontSize: 11,
                  color: 'var(--text-2)',
                }}
              >
                {agent.agent}: {formatTokens(agent.total_tokens)}
                {agent.unavailable_turns > 0 ? ` · ${agent.unavailable_turns} unavailable` : ''}
              </span>
            ))}
          </div>
        )}
      </div>

      <SettingsRow label="Project token budget" description="An optional project-wide token allowance that pauses autonomous turns once exhausted; leave blank for no limit.">
        <div className="flex items-center gap-2">
          <input
            aria-label="Project token budget"
            inputMode="numeric"
            value={budgetInput}
            onChange={(event) => setBudgetInput(event.target.value)}
            placeholder="Disabled"
            className="block w-32 rounded px-2 py-1.5 text-xs"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)', color: 'var(--text)' }}
          />
          <Button variant="primary" size="sm" onClick={applyBudget} disabled={updateBudget.isPending}>Apply</Button>
          <Button variant="outline" size="sm" onClick={() => updateBudget.mutate(null)}>Disable</Button>
        </div>
      </SettingsRow>
    </SettingsSection>
  )
}
