import { useState } from 'react'
import { useAgentLaunchability, useUpdateAgentGrant, type AgentSummary } from '@/api/agents'
import { permissionModeValues, useModelCatalog } from '@/api/modelCatalog'
import { useQueueStatus } from '@/api/queue'
import { useRunners } from '@/api/runners'
import { PERMISSION_WAIT_FALLBACK_SECONDS, QUESTION_WAIT_FALLBACK_SECONDS } from '@/lib/agentWaits'
import { HOP_HELD_REASON } from './CollaborationSummary'

type Grant = 'can_accept_evidence' | 'can_read_checkpoints' | 'can_recall'

/** Chip colours inline, as the other chips on this page set theirs: the global button treatment
 *  (`index.css`, `button:not([data-slot])`) outranks any one class, and would erase a class's border
 *  and fill on the chips that are buttons. */
const CHIP_STYLE = {
  off: { border: '1px solid var(--border)', color: 'var(--text-3)', background: 'transparent' },
  on: {
    border: '1px solid color-mix(in srgb, var(--green) 45%, transparent)',
    color: 'var(--green)',
    background: 'color-mix(in srgb, var(--green) 10%, transparent)',
  },
  flag: {
    border: '1px solid transparent',
    color: 'var(--amber)',
    background: 'color-mix(in srgb, var(--amber) 14%, transparent)',
  },
} as const

const GRANTS: { grant: Grant; label: string; title: string }[] = [
  { grant: 'can_accept_evidence', label: 'evidence', title: 'May accept or reject evidence; approval merges nothing until evidence is accepted' },
  { grant: 'can_read_checkpoints', label: 'checkpoints', title: "May read other agents' checkpoints" },
  { grant: 'can_recall', label: 'recall', title: 'May read the recorded output behind those checkpoints' },
]

/**
 * One agent's posture on its Overview card (`the-settings-that-gate-collaboration-are-on-the-project-page`).
 *
 * The three grants vary silently between agents, which is the harm (F379: only one of four could
 * accept evidence, so every decision cost two hops through it); side by side on the cards, a
 * difference is visible. They are plain switches, so they are clicked here. What is missing (a
 * charter, a runner that can launch) is flagged and links to its fix. The rest of the posture sits
 * behind a per-agent disclosure, collapsed by default (operator, 2026-10-08).
 */
export function AgentPostureChips({ agent, onNavigate }: { agent: AgentSummary; onNavigate: (page: string) => void }) {
  const [open, setOpen] = useState(false)
  const grant = useUpdateAgentGrant()
  const { data: launchability } = useAgentLaunchability()
  const { data: queue } = useQueueStatus(agent.name)
  const launch = launchability?.agents[agent.name]
  const cannotRun = !!agent.runner_id && launch?.runnable === false

  return (
    <div className="mt-2 flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-1">
        {GRANTS.map(({ grant: key, label, title }) => {
          const on = !!agent[key]
          return (
            <button
              key={key}
              type="button"
              className="aw-chip"
              data-pill="true"
              style={on ? CHIP_STYLE.on : CHIP_STYLE.off}
              aria-pressed={on}
              title={title}
              data-testid={`agent-grant-${agent.name}-${key}`}
              disabled={grant.isPending}
              onClick={() => grant.mutate({ agent: agent.name, grant: key, enabled: !on })}
            >
              {label}
            </button>
          )
        })}
        {!agent.charter_id && (
          <button type="button" className="aw-chip" data-pill="true" data-flag="true" style={CHIP_STYLE.flag} onClick={() => onNavigate(`agent-settings:${agent.name}:charter`)}>
            no charter
          </button>
        )}
        {!agent.runner_id && (
          <button type="button" className="aw-chip" data-pill="true" data-flag="true" style={CHIP_STYLE.flag} onClick={() => onNavigate(`agent-settings:${agent.name}:execution`)}>
            no runner
          </button>
        )}
        {cannotRun && (
          <button type="button" className="aw-chip" data-pill="true" data-flag="true" style={CHIP_STYLE.flag} title={launch?.reason ?? undefined} onClick={() => onNavigate(`agent-settings:${agent.name}:execution`)}>
            can't run
          </button>
        )}
        {queue?.waiting_reason === HOP_HELD_REASON && (
          <span className="aw-chip" data-pill="true" data-flag="true" style={CHIP_STYLE.flag}>held by hop budget</span>
        )}
      </div>
      {cannotRun && launch?.reason && (
        <p className="text-[11px]" style={{ color: 'var(--amber)' }}>{launch.reason}</p>
      )}
      {grant.error && (
        <p role="alert" className="text-[11px]" style={{ color: 'var(--red)' }}>Could not change the grant.</p>
      )}
      <button
        type="button"
        className="self-start text-[11px] hover:underline"
        style={{ color: 'var(--text-3)' }}
        aria-expanded={open}
        data-testid={`agent-details-toggle-${agent.name}`}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? 'Hide details' : 'Details'}
      </button>
      {open && <AgentDetails agent={agent} onNavigate={onNavigate} />}
    </div>
  )
}

function AgentDetails({ agent, onNavigate }: { agent: AgentSummary; onNavigate: (page: string) => void }) {
  const { data: catalog } = useModelCatalog()
  const { data: runners, isLoading: runnersLoading } = useRunners()
  const labelFor = (mode: string) => permissionModeValues(catalog).find((option) => option.id === mode)?.label ?? mode
  const builtIn = agent.permission_mode_built_in ? ` (${labelFor(agent.permission_mode_built_in)})` : ''
  const posture = agent.default_permission_mode ? labelFor(agent.default_permission_mode) : `Built-in default${builtIn}`
  // "None bound" is said from the agent's own record, never from a runner list that has not arrived:
  // these details are the first thing on the Overview to read runners, so the list is often in flight.
  const runner = runners?.find((item) => item.id === agent.runner_id)
  const runnerText = !agent.runner_id
    ? 'None bound'
    : runner
      ? `${runner.name}${runner.model ? ` · ${runner.model}` : ''}`
      : runnersLoading ? 'Loading…' : agent.runner_id
  const wait = (value: number | null | undefined, fallback: number) =>
    value == null ? `${fallback}s (default)` : `${value}s`

  return (
    <dl className="posture-details" data-testid={`agent-details-${agent.name}`}>
      <dt>Default permissions</dt><dd>{posture}</dd>
      <dt>Runner</dt><dd>{runnerText}</dd>
      <dt>Waits for a permission</dt><dd>{wait(agent.permission_timeout_seconds, PERMISSION_WAIT_FALLBACK_SECONDS)}</dd>
      <dt>Waits for an answer</dt><dd>{wait(agent.question_timeout_seconds, QUESTION_WAIT_FALLBACK_SECONDS)}</dd>
      <dd className="col-span-2">
        <button type="button" className="text-[11px] underline-offset-2 hover:underline" style={{ color: 'var(--text-2)' }} onClick={() => onNavigate(`agent-settings:${agent.name}:execution`)}>
          Agent settings
        </button>
      </dd>
    </dl>
  )
}
