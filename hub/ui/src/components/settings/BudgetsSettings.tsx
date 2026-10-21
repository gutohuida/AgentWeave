import type * as React from 'react'
import { agentColorVars } from '@/lib/agentColors'
import { SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import type { AccountingSnapshot, WorkerUsageLine } from '@/api/accounting'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'
import { accountingDisplayLabel, formatAiCredits } from '@/components/accounting/accountingDisplay'
import { formatCount, formatMoney, formatPercent, formatTokens, formatTokensExact } from '@/lib/format'
import { CommittedInput } from './CommittedInput'

/** Project settings → Budgets: what the project has used, and the one limit on it.
 *
 *  The old page showed the total as "31,843,065 tokens" with each agent as a grey chip, and the
 *  limit as a field reading "Disabled" beside both "Apply" and "Disable". Now: one summary in the
 *  Ledger's style (amounts, per-agent bars), and the limit as a switch that reveals its amount.
 *  Every figure the old page reported is still here: unavailable turns, Copilot's credits (never
 *  counted against the limit), a stopped turn's estimate, and what the Hub's own jobs spent. */

/** A worker kind as the operator knows it; an unknown kind (a future job) shows as recorded. */
const WORKER_LABELS: Record<string, string> = {
  checkpoint: 'Checkpoints',
  checkpoint_probe: 'Checkpoint probes',
  conversation_title: 'Conversation titles',
  'vault-distillation': 'Vault distillation',
  'vault-reports': 'Vault reports',
  'spec-vault-check': 'Spec checks',
}

function premium(n: number | null | undefined): string | null {
  return typeof n === 'number' && Number.isFinite(n) ? `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })} premium request${n === 1 ? '' : 's'}` : null
}

/** A stopped turn's interrupted call, estimated from its last context reading (F697). */
function estimate(tokens: number | null | undefined): string | null {
  return typeof tokens === 'number' && tokens > 0 ? `≈${tokens.toLocaleString()} input tokens, not measured` : null
}

/** What a line spent beyond its tokens, and what it could not measure, as one muted sentence. */
function extras(line: { ai_nano_aiu?: number | null; premium_requests?: number | null; unavailable_turns?: number; unmeasured_calls?: number; estimated_input_tokens?: number | null }): string {
  const unmeasured = line.unavailable_turns ?? line.unmeasured_calls ?? 0
  return [
    formatAiCredits(line.ai_nano_aiu ?? null),
    premium(line.premium_requests),
    unmeasured > 0 ? `${formatCount(unmeasured)} unavailable` : null,
    estimate(line.estimated_input_tokens),
  ]
    .filter(Boolean)
    .join(' · ')
}

function workerTokens(line: WorkerUsageLine): number {
  return line.total_tokens ?? 0
}

export function BudgetsSettings({
  accounting,
  agentColor,
  onSetLimit,
  saving,
  notices,
}: {
  accounting: AccountingSnapshot
  agentColor: (agent: string) => number | null | undefined
  /** Null turns the limit off. Amount in tokens. */
  onSetLimit: (tokens: number | null, said: string) => void
  saving?: boolean
  /** A refused save, under the page heading. */
  notices?: React.ReactNode
}) {
  const project = accounting.project
  const total = project.total_tokens
  const spent = project.api_equivalent_usd_micros
  const agents = [...accounting.agents].sort((a, b) => (b.total_tokens ?? 0) - (a.total_tokens ?? 0))
  const workers = accounting.workers ?? []
  const max = Math.max(1, ...agents.map((a) => a.total_tokens ?? 0), ...workers.map(workerTokens))
  const limit = accounting.budget.limit_tokens
  const limited = limit != null
  // The headline includes the worker calls (F240), so the caption says so.
  const workerCalls = workers.reduce((sum, w) => sum + w.measured_calls + (w.credited_calls ?? 0) + w.unmeasured_calls, 0)
  const credits = [formatAiCredits(project.ai_nano_aiu), premium(project.premium_requests)].filter(Boolean).join(' · ')
  const projectEstimate = estimate(project.estimated_input_tokens)

  return (
    <SettingsPage icon="bar_chart" title="Budgets" description="What this project has used, and the limit that pauses agents working on their own.">
      {notices}
      <div className="aw-usage">
        <div className="aw-usage-tiles">
          <div className="aw-usage-tile">
            <span className="aw-usage-label">Spent</span>
            <span className="aw-usage-value tabular">{spent != null ? formatMoney(spent / 1_000_000) : 'Unavailable'}</span>
            <span className="aw-usage-sub">{project.unpriced_turns > 0 ? `API-equivalent; ${formatCount(project.unpriced_turns)} turns could not be priced` : 'API-equivalent, all turns'}</span>
          </div>
          <div className="aw-usage-tile">
            <span className="aw-usage-label">Tokens</span>
            <span className="aw-usage-value tabular" title={total != null ? formatTokensExact(total) : undefined}>
              {total != null ? formatCount(total) : 'Unavailable'}
            </span>
            <span className="aw-usage-sub" data-testid="budgets-caption">
              {formatCount(project.measured_turns)} measured turns
              {workerCalls > 0 ? ` · ${formatCount(workerCalls)} Hub job call${workerCalls === 1 ? '' : 's'}` : ''}
              {project.unavailable_turns > 0 ? ` · ${formatCount(project.unavailable_turns)} unavailable` : ''}
            </span>
          </div>
          <div className="aw-usage-tile">
            <span className="aw-usage-label">Limit</span>
            <span className="aw-usage-value tabular">{limited ? formatCount(limit) : 'None'}</span>
            <span className="aw-usage-sub">{limited ? `${formatPercent(Math.min(1, (total ?? accounting.budget.used_tokens) / limit))} used` : 'Agents are never paused'}</span>
          </div>
        </div>
        <div className="aw-usage-notes">
          <p className="aw-row-note" data-testid="budgets-display">{accountingDisplayLabel(accounting.preferred_display)}</p>
          {credits ? <p className="aw-row-note" data-testid="budgets-credits">{credits} (Copilot), not counted against the limit</p> : null}
          {projectEstimate ? <p className="aw-row-note" data-testid="budgets-estimate">{projectEstimate}, not counted against the limit</p> : null}
        </div>
        <BudgetExhaustionNotice exhausted={accounting.budget.exhausted} />
        <ul className="aw-usage-bars" aria-label="Usage by agent">
          {agents.map((a) => {
            const tokens = a.total_tokens ?? 0
            const color = agentColorVars(agentColor(a.agent))
            const more = extras(a)
            return (
              <li key={a.agent} className="aw-usage-bar-row" title={a.total_tokens != null ? formatTokensExact(tokens) : 'Usage unavailable'} data-testid={`budget-agent-${a.agent}`}>
                <span className="aw-usage-bar-name">
                  <span className="aw-usage-dot" style={{ background: color.accent }} />
                  <span className="min-w-0">
                    <span className="block truncate">{a.agent}</span>
                    {more ? <span className="aw-usage-extra">{more}</span> : null}
                  </span>
                </span>
                <span className="aw-usage-track">
                  <span className="aw-usage-fill" style={{ width: `${(tokens / max) * 100}%`, background: color.accent }} />
                </span>
                <span className="aw-usage-num tabular">{a.total_tokens != null ? formatTokens(tokens) : 'Unavailable'}</span>
                <span className="aw-usage-num aw-usage-money tabular">{a.api_equivalent_usd_micros != null ? formatMoney(a.api_equivalent_usd_micros / 1_000_000) : '—'}</span>
              </li>
            )
          })}
        </ul>
        {workers.length ? (
          <ul className="aw-usage-bars" aria-label="Usage by worker">
            {workers.map((w) => {
              const tokens = workerTokens(w)
              const more = extras(w)
              return (
                <li key={w.kind} className="aw-usage-bar-row" title={w.total_tokens != null ? formatTokensExact(tokens) : undefined} data-testid={`budget-worker-${w.kind}`}>
                  <span className="aw-usage-bar-name">
                    <span className="aw-usage-dot" style={{ background: 'var(--text-3)' }} />
                    <span className="min-w-0">
                      <span className="block truncate">{WORKER_LABELS[w.kind] ?? w.kind}</span>
                      {more ? <span className="aw-usage-extra">{more}</span> : null}
                    </span>
                  </span>
                  <span className="aw-usage-track">
                    <span className="aw-usage-fill" style={{ width: `${(tokens / max) * 100}%`, background: 'var(--text-3)' }} />
                  </span>
                  <span className="aw-usage-num tabular">{w.total_tokens != null ? formatTokens(tokens) : formatAiCredits(w.ai_nano_aiu ?? null) ?? 'Unavailable'}</span>
                  <span className="aw-usage-num aw-usage-money tabular">{w.api_equivalent_usd_micros != null ? formatMoney(w.api_equivalent_usd_micros / 1_000_000) : '—'}</span>
                </li>
              )
            })}
          </ul>
        ) : null}
      </div>

      <SettingsGroup title="Limit">
        <SettingsRow
          label="Pause agents working on their own"
          description="Once the project has used this many tokens, turns you did not ask for wait. Your own messages still run."
          control={
            <Switch
              aria-label="Pause agents working on their own"
              checked={limited}
              disabled={saving}
              onCheckedChange={(v) =>
                onSetLimit(v ? Math.max(1_000_000, Math.ceil(((total ?? 0) * 1.25) / 1_000_000) * 1_000_000) : null, v ? 'Token limit on' : 'Token limit off: agents are no longer paused')
              }
            />
          }
        />
        {limited ? (
          <SettingsRow
            label="After"
            htmlFor="b-limit"
            description={`Used so far: ${total != null ? formatTokens(total) : 'unavailable'}.`}
            control={
              <CommittedInput
                id="b-limit"
                numeric
                width={96}
                suffix="M tokens"
                disabled={saving}
                value={String(Math.round((limit / 1_000_000) * 10) / 10)}
                validate={(d) => (/^\d+(\.\d)?$/.test(d) && Number(d) > 0 ? null : 'Millions of tokens, like 40 or 12.5.')}
                onCommit={(v) => onSetLimit(Math.round(Number(v) * 1_000_000), `Agents pause after ${v}M tokens`)}
              />
            }
          />
        ) : null}
      </SettingsGroup>
    </SettingsPage>
  )
}
