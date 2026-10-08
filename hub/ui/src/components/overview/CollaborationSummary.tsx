import type { ReactNode } from 'react'
import { readableApiError } from '@/api/client'
import { useAccounting } from '@/api/accounting'
import { useAgents } from '@/api/agents'
import { useProjectSettings, useUpdateProjectSettings } from '@/api/projects'
import { useQueueStatuses } from '@/api/queue'
import { useConfigStore } from '@/store/configStore'

/** The `waiting_reason` the queue route derives when every waiting entry is past the hop budget
 *  (`inbound_queue.py`). Read, never stored, so it names the hold exactly while it stands. */
export const HOP_HELD_REASON = 'hop budget exhausted'

const count = (value: number) => value.toLocaleString('en-US')

/**
 * The settings that decide whether agents can work together, as live values
 * (`the-settings-that-gate-collaboration-are-on-the-project-page`).
 *
 * Each of these, left at its default, has stopped a real run without saying why (F379). They are
 * shown, not edited: numbers are typed in Settings and Budgets, and every row opens its editor. The
 * one exception is the flows switch, a single bit with nothing to type, sent alone because the
 * settings route merges a partial body onto what is stored.
 */
export function CollaborationSummary({ onNavigate }: { onNavigate: (page: string) => void }) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: settings } = useProjectSettings(projectId ?? null)
  const update = useUpdateProjectSettings(projectId ?? '')
  const { data: accounting } = useAccounting()
  const { data: agents = [] } = useAgents()
  const statuses = useQueueStatuses(agents.map((agent) => agent.name))

  if (!settings) return null

  const held = statuses.filter((status) => status.waiting_reason === HOP_HELD_REASON).length
  const budget = accounting?.budget
  const limit = budget ? budget.limit_tokens : settings.token_budget
  const used = budget?.used_tokens ?? null
  const checks = settings.checks?.length ?? 0

  return (
    <section className="lifted-surface px-4 py-3" aria-labelledby="overview-collaboration" data-testid="collab-summary">
      <h2 id="overview-collaboration" className="text-[13px] font-semibold" style={{ color: 'var(--text)' }}>
        Collaboration
      </h2>
      <div className="mt-2 grid gap-x-6 md:grid-cols-2">
        <div className="collab-row" data-testid="collab-row-flows">
          <RowText label="Agents may start flows" hint="Needed for create_flow and create_loop" />
          <button
            type="button"
            role="switch"
            aria-checked={settings.allow_agent_jobs}
            aria-label="Agents may start flows"
            disabled={update.isPending}
            onClick={() => update.mutate({ allow_agent_jobs: !settings.allow_agent_jobs })}
            className="collab-switch"
          >
            <span className="collab-switch-track" aria-hidden="true"><span className="collab-switch-thumb" /></span>
            <span className="text-xs font-medium" style={{ color: settings.allow_agent_jobs ? 'var(--text)' : 'var(--text-2)' }}>
              {settings.allow_agent_jobs ? 'On' : 'Off'}
            </span>
          </button>
        </div>

        <LinkRow id="hop" label="Hop budget" hint="Agent-to-agent hops before a chain pauses for you" onClick={() => onNavigate('settings')}>
          <Value>{settings.hop_budget} hops</Value>
          {held > 0 && <Value flag>{held} agent{held === 1 ? '' : 's'} held</Value>}
        </LinkRow>

        <LinkRow id="token" label="Token budget" hint="Autonomous turns pause once it is spent" onClick={() => onNavigate('budgets')}>
          {limit == null ? (
            <Value flag>No limit{used != null ? ` · ${count(used)} used` : ''}</Value>
          ) : (
            <Value flag={budget?.exhausted ?? false}>
              {used != null ? `${count(used)} of ${count(limit)} used` : `${count(limit)} limit`}
            </Value>
          )}
        </LinkRow>

        <LinkRow id="branch" label="Approval merges into" hint="The branch approving a task lands work in" onClick={() => onNavigate('settings')}>
          {settings.main_branch ? <Value>{settings.main_branch}</Value> : <Value flag>Not set</Value>}
        </LinkRow>

        <LinkRow id="checks" label="Checks on approval" hint="Commands run before a task's work merges" onClick={() => onNavigate('settings')}>
          <Value>{checks === 0 ? 'None' : `${checks} check${checks === 1 ? '' : 's'}`}</Value>
        </LinkRow>

        <LinkRow
          id="limits"
          label="Delivery cap · agent budget"
          hint="Messages one turn drains · agents an agent may staff the project up to"
          onClick={() => onNavigate('settings')}
        >
          <Value>{settings.turn_delivery_cap} per turn · {agents.length} of {settings.agent_budget} agents</Value>
        </LinkRow>
      </div>
      {update.error && (
        <p role="alert" className="mt-2 text-xs" style={{ color: 'var(--red)' }}>
          {readableApiError(update.error, 'The setting could not be saved.')}
        </p>
      )}
    </section>
  )
}

function RowText({ label, hint }: { label: string; hint: string }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block text-xs font-medium" style={{ color: 'var(--text)' }}>{label}</span>
      <span className="block text-[11px]" style={{ color: 'var(--text-3)' }}>{hint}</span>
    </span>
  )
}

function LinkRow({ id, label, hint, onClick, children }: {
  id: string
  label: string
  hint: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button type="button" className="collab-row" data-testid={`collab-row-${id}`} onClick={onClick}>
      <RowText label={label} hint={hint} />
      <span className="flex shrink-0 flex-wrap justify-end gap-1">{children}</span>
    </button>
  )
}

/** A value, or with `flag` a value that is a problem as it stands ("No limit", "Not set"). */
function Value({ flag = false, children }: { flag?: boolean; children: ReactNode }) {
  return (
    <span className="collab-value" data-flag={flag ? 'true' : undefined}>
      {children}
    </span>
  )
}
