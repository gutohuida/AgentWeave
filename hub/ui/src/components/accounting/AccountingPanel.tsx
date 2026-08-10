import { useEffect, useState } from 'react'
import { useAccounting, useUpdateTokenBudget } from '@/api/accounting'
import { readableApiError } from '@/api/client'
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
  /** Why a submit was refused before it reached the network. A rejected value used to do
   *  nothing at all — the operator pressed Apply and the page did not move, which is
   *  indistinguishable from a save that silently failed. */
  const [inputError, setInputError] = useState<string | null>(null)

  useEffect(() => {
    setBudgetInput(data?.budget.limit_tokens?.toString() ?? '')
  }, [data?.budget.limit_tokens])

  if (isLoading || !data) return null

  const applyBudget = () => {
    const value = Number(budgetInput)
    if (budgetInput.trim() === '') {
      setInputError('Enter a number of tokens, or press Disable to remove the limit.')
      return
    }
    if (!Number.isInteger(value) || value <= 0) {
      setInputError('The budget must be a whole number of tokens greater than zero.')
      return
    }
    setInputError(null)
    updateBudget.mutate(value)
  }

  const disableBudget = () => {
    setInputError(null)
    updateBudget.mutate(null)
  }

  // What the last completed save did, so "saved" and "removed" do not read the same.
  const savedLabel = updateBudget.isSuccess
    ? updateBudget.variables === null
      ? 'Budget removed — autonomous turns are no longer paused by a project limit.'
      : 'Budget saved.'
    : null

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
            onChange={(event) => {
              setBudgetInput(event.target.value)
              // Typing is the operator answering the complaint; keeping it on screen while they
              // fix it would leave them reading a stale objection.
              if (inputError) setInputError(null)
            }}
            aria-invalid={inputError ? true : undefined}
            placeholder="Disabled"
            className="block w-32 rounded px-2 py-1.5 text-xs"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)', color: 'var(--text)' }}
          />
          <Button variant="primary" size="sm" onClick={applyBudget} disabled={updateBudget.isPending}>Apply</Button>
          <Button
            variant="outline"
            size="sm"
            onClick={disableBudget}
            disabled={updateBudget.isPending}
          >
            Disable
          </Button>
        </div>
      </SettingsRow>

      {/* Both outcomes are reported in the section, the way `ProjectSettingsPanel` does it.
          Neither Apply nor Disable used to report anything at all: a save, a rejected value and a
          server failure were three different events that looked identical from the operator's
          chair. */}
      {savedLabel && !inputError && !updateBudget.isError && (
        <div role="status" className="py-3 text-xs" style={{ color: 'var(--green)' }}>
          {savedLabel}
        </div>
      )}
      {inputError && (
        <div role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>
          {inputError}
        </div>
      )}
      {updateBudget.isError && !inputError && (
        <div role="alert" className="py-3 text-xs" style={{ color: 'var(--red)' }}>
          {readableApiError(updateBudget.error, 'The budget could not be saved.')}
        </div>
      )}
    </SettingsSection>
  )
}
