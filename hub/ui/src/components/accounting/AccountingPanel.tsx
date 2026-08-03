import { useEffect, useState } from 'react'
import { useAccounting, useUpdateTokenBudget } from '@/api/accounting'
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
    <section
      aria-labelledby="accounting-heading"
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: 12,
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="accounting-heading" style={{ fontSize: 13, fontWeight: 600 }}>
            Token accounting
          </h2>
          <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4 }}>
            {formatTokens(data.project.total_tokens)}
          </div>
          <div style={{ color: 'var(--text-3)', fontSize: 11, marginTop: 2 }}>
            {data.project.measured_turns} measured · {data.project.unavailable_turns} usage unavailable
          </div>
          <div style={{ color: 'var(--text-2)', fontSize: 12, marginTop: 6 }}>
            <PreferredDisplay />
          </div>
        </div>
        <div className="flex items-end gap-2">
          <label style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Project token budget
            <input
              aria-label="Project token budget"
              inputMode="numeric"
              value={budgetInput}
              onChange={(event) => setBudgetInput(event.target.value)}
              placeholder="Disabled"
              style={{
                display: 'block',
                width: 130,
                marginTop: 4,
                padding: '5px 7px',
                background: 'var(--surface-1)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text)',
              }}
            />
          </label>
          <button type="button" onClick={applyBudget} disabled={updateBudget.isPending}>
            Apply
          </button>
          <button type="button" onClick={() => updateBudget.mutate(null)}>
            Disable
          </button>
        </div>
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
    </section>
  )
}
