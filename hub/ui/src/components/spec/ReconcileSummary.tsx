import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { hubDate } from '@/lib/hubTime'
import {
  useAskReconcile,
  type SpecReconcileClass,
  type SpecReconcileResult,
} from '@/api/spec'

const CLASS_ORDER: SpecReconcileClass[] = ['missing', 'partial', 'contradicts', 'unrequested']

function counts(result: Extract<SpecReconcileResult, { state: 'recorded' }>): string {
  const parts = CLASS_ORDER.filter((kind) => result.counts[kind] > 0).map(
    (kind) => `${result.counts[kind]} ${kind}`,
  )
  return parts.length ? parts.join(' · ') : 'no gaps found'
}

/**
 * A change's latest reconcile result (`a-change-is-reconciled-with-its-code-before-it-is-folded`):
 * the gaps an agent found between the change and its code, each classed. `compact` is the phase
 * bar's one line; the full form is the fold dialog's, with every gap and, when the change was never
 * reconciled, a way to ask an agent to do it. Nothing here gates the fold (design D5).
 */
export function ReconcileSummary({
  path,
  result,
  compact = false,
}: {
  path: string
  result: SpecReconcileResult | undefined
  compact?: boolean
}) {
  if (!result) return null
  if (result.state === 'none') {
    return compact ? null : <AskToReconcile path={path} />
  }
  const at = result.at ? hubDate(result.at) : null
  return (
    <div
      data-testid="reconcile-result"
      className="flex flex-col gap-1 rounded-[var(--radius-sm)] px-2 py-1.5"
      style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
    >
      <span className="flex flex-wrap items-center gap-1.5">
        <Icon name="fact_check" size={13} />
        <span>
          Reconciled with the code by @{result.author}
          {at ? ` ${formatDistanceToNow(at, { addSuffix: true })}` : ''}: {counts(result)}
        </span>
      </span>
      {!compact && (
        <>
          {result.summary && <span style={{ color: 'var(--text-3)' }}>{result.summary}</span>}
          {result.gaps.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {result.gaps.map((gap, index) => (
                <li key={`${gap.class}:${gap.where}:${index}`} className="flex flex-wrap gap-x-1.5">
                  <span
                    style={{
                      color: gap.class === 'unrequested' ? 'var(--text-3)' : 'var(--amber)',
                      fontWeight: 600,
                    }}
                  >
                    {gap.class}
                  </span>
                  {gap.requirement && <code>{gap.requirement}</code>}
                  <code>{gap.where}</code>
                  <span>{gap.summary}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function AskToReconcile({ path }: { path: string }) {
  const { data: agentsData, isError: agentsError } = useAgents()
  const ask = useAskReconcile()
  const [agent, setAgent] = useState('')
  const [asked, setAsked] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const agents = agentsError ? [] : (agentsData ?? []).filter((row) => row.lifecycle !== 'archived')

  function onAsk() {
    if (!agent) return
    setRefusal(null)
    ask.mutate(
      { path, agent },
      {
        onSuccess: () => setAsked(agent),
        onError: (error: unknown) =>
          setRefusal(readableApiError(error, 'The Hub refused to start the reconcile.')),
      },
    )
  }

  return (
    <div
      data-testid="reconcile-none"
      className="flex flex-col gap-1 rounded-[var(--radius-sm)] px-2 py-1.5"
      style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
    >
      <span>
        Not reconciled with the code. An agent can read the change and the code and class each gap
        as missing, partial, contradicts or unrequested.
      </span>
      {asked ? (
        <span style={{ color: 'var(--text-3)' }}>Asked @{asked} to reconcile it.</span>
      ) : (
        <div className="flex items-center gap-1.5">
          <select
            aria-label="Agent to reconcile"
            value={agent}
            onChange={(event) => setAgent(event.target.value)}
            className="rounded-[var(--radius-sm)] px-1.5 py-0.5"
            style={{
              background: 'var(--surface)',
              color: 'var(--text-2)',
              border: '1px solid var(--border)',
              fontSize: 11,
            }}
          >
            <option value="" disabled>
              {agentsError ? 'Could not load the agents' : 'Choose an agent…'}
            </option>
            {agents.map((row) => (
              <option key={row.name} value={row.name}>
                @{row.name}
              </option>
            ))}
          </select>
          <Button
            variant="primary"
            size="xs"
            data-testid="reconcile-ask"
            disabled={!agent || ask.isPending}
            onClick={onAsk}
          >
            Ask to reconcile
          </Button>
        </div>
      )}
      {refusal && (
        <span role="alert" style={{ color: 'var(--red)' }}>
          {refusal}
        </span>
      )}
    </div>
  )
}
