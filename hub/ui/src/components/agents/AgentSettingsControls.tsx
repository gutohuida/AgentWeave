import { useEffect, useState } from 'react'
import {
  AgentSummary,
  MAX_AGENT_DESCRIPTION_CHARS,
  useUpdateAgentDescription,
} from '@/api/agents'
import { useBindAgentCharter, useCharters } from '@/api/charters'
import {
  MAX_WAITING_SECONDS,
  MIN_WAITING_SECONDS,
  useBindAgentRunner,
  useRunners,
  useUpdateAgentWaiting,
} from '@/api/runners'
import { SettingsRow } from '@/components/environment/SettingsSection'

/**
 * The editable per-agent controls, shared by the settings page and — until it is retired — the
 * conversation's info tab.
 *
 * They live here rather than inside either surface so that moving a setting between sections is a
 * change of where a control is rendered, not a rewrite of the control. `agent-configuration`
 * requires that no setting be editable from two surfaces; that is a statement about where these
 * are *placed*, which is why the placement is deliberately not baked into the controls.
 */

/** What this agent is for, in the operator's own words.
 *
 * Committed on blur, like `WaitingSetting` and for the same reason: a mutation per keystroke would
 * write a sentence a character at a time. Blank clears it — the API stores no description rather
 * than an empty one, so clearing and never having written are the same state.
 *
 * It is a note to the human reading a roster, not an instruction to the agent: nothing injects it
 * into a turn. The charter is where behaviour is stated, and a second field that also shaped it
 * would leave two places to look when an agent acts wrongly.
 */
export function DescriptionSetting({ agent }: { agent: AgentSummary }) {
  const update = useUpdateAgentDescription()
  const stored = agent.description ?? ''
  const [draft, setDraft] = useState(stored)

  useEffect(() => {
    setDraft(stored)
  }, [stored])

  const commit = () => {
    const trimmed = draft.trim()
    if (trimmed === stored) return
    update.mutate({ agent: agent.name, description: trimmed === '' ? null : trimmed })
  }

  return (
    <div>
      <textarea
        value={draft}
        rows={2}
        maxLength={MAX_AGENT_DESCRIPTION_CHARS}
        placeholder="What this agent is for."
        aria-label={`Description for ${agent.name}`}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        disabled={update.isPending}
        className="w-full px-3 py-2 rounded-md text-sm resize-y"
        style={{
          background: 'var(--surface-3)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          opacity: update.isPending ? 0.6 : 1,
        }}
      />
      {update.isError && (
        <p className="mt-1 text-[11px]" style={{ color: 'var(--red)' }}>Could not save.</p>
      )}
    </div>
  )
}

/** One wait, in seconds, or blank for the built-in default.
 *
 * Committed on blur rather than on every keystroke: typing "45" over "240" passes through "4",
 * and saving that would set a wait shorter than the card takes to render. Blank clears the
 * setting back to the default rather than sending 0, which the API would refuse anyway.
 */
export function WaitingSetting({
  agent,
  field,
  label,
  description,
  fallback,
}: {
  agent: AgentSummary
  field: 'permission_timeout_seconds' | 'question_timeout_seconds'
  label: string
  description: string
  fallback: number
}) {
  const update = useUpdateAgentWaiting()
  const stored = agent[field] ?? null
  const [draft, setDraft] = useState(stored === null ? '' : String(stored))
  const [error, setError] = useState<string | null>(null)

  // The roster is the source of truth; a value changed elsewhere (or rejected here) has to win
  // over whatever is sitting in the box.
  useEffect(() => {
    setDraft(stored === null ? '' : String(stored))
  }, [stored])

  const commit = () => {
    const trimmed = draft.trim()
    if (trimmed === '') {
      setError(null)
      if (stored !== null) update.mutate({ agent: agent.name, field, seconds: null })
      return
    }
    const seconds = Number(trimmed)
    if (!Number.isInteger(seconds) || seconds < MIN_WAITING_SECONDS || seconds > MAX_WAITING_SECONDS) {
      setError(`Between ${MIN_WAITING_SECONDS} and ${MAX_WAITING_SECONDS} seconds.`)
      return
    }
    setError(null)
    if (seconds !== stored) update.mutate({ agent: agent.name, field, seconds })
  }

  return (
    <SettingsRow label={label} description={description}>
      <div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            inputMode="numeric"
            min={MIN_WAITING_SECONDS}
            max={MAX_WAITING_SECONDS}
            value={draft}
            placeholder={String(fallback)}
            aria-label={`${label} wait for ${agent.name}, in seconds`}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === 'Enter') event.currentTarget.blur()
            }}
            disabled={update.isPending}
            className="w-24 px-3 py-2 rounded-md text-sm"
            style={{
              background: 'var(--surface-3)',
              color: 'var(--text)',
              border: `1px solid ${error ? 'var(--red)' : 'var(--border)'}`,
              opacity: update.isPending ? 0.6 : 1,
            }}
          />
          <span className="text-xs" style={{ color: 'var(--text-3)' }}>seconds</span>
        </div>
        <p className="mt-1 text-[11px]" style={{ color: error ? 'var(--red)' : 'var(--text-3)' }}>
          {error ?? (stored === null ? `Default (${fallback}s). Clear to keep it.` : 'Blank for the default.')}
        </p>
        {update.isError && !error && (
          <p className="mt-1 text-[11px]" style={{ color: 'var(--red)' }}>Could not save.</p>
        )}
      </div>
    </SettingsRow>
  )
}

/** Rebinds this one agent. Deliberately not a link through to the Runner record: rebinding one
 *  agent and editing a record bound by many are different acts, and offering them from the same
 *  control invites the second when the operator meant the first. */
export function RunnerPicker({ agent }: { agent: AgentSummary }) {
  const { data: runners = [], isLoading } = useRunners()
  const bindRunner = useBindAgentRunner()

  if (isLoading) {
    return <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading runners...</span>
  }

  return (
    <div>
      <select
        value={agent.runner_id ?? ''}
        onChange={(event) => {
          bindRunner.mutate({ agent: agent.name, runnerId: event.target.value || null })
        }}
        disabled={bindRunner.isPending}
        aria-label={`Runner for ${agent.name}`}
        className="w-full px-3 py-2 rounded-md text-sm"
        style={{
          background: 'var(--surface-3)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          opacity: bindRunner.isPending ? 0.6 : 1,
        }}
      >
        <option value="">No runner</option>
        {runners.map((runner) => (
          <option key={runner.id} value={runner.id}>
            {runner.name} ({runner.cli})
          </option>
        ))}
      </select>
      {bindRunner.isError && (
        <p className="text-xs mt-2" style={{ color: 'var(--red)' }}>
          Could not update runner binding.
        </p>
      )}
    </div>
  )
}

/** Same rule as `RunnerPicker`: rebinds, does not link through to the charter record. */
export function CharterPicker({ agent }: { agent: AgentSummary }) {
  const { data: charters = [], isLoading } = useCharters()
  const bindCharter = useBindAgentCharter()

  if (isLoading) {
    return <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading charters...</span>
  }

  return (
    <div>
      <select
        value={agent.charter_id ?? ''}
        onChange={(event) => bindCharter.mutate({
          agent: agent.name,
          charterId: event.target.value || null,
        })}
        disabled={bindCharter.isPending}
        aria-label={`Charter for ${agent.name}`}
        className="w-full px-3 py-2 rounded-md text-sm"
        style={{
          background: 'var(--surface-3)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          opacity: bindCharter.isPending ? 0.6 : 1,
        }}
      >
        <option value="">No charter</option>
        {charters.map((charter) => (
          <option key={charter.id} value={charter.id}>{charter.name}</option>
        ))}
      </select>
      {bindCharter.isError && (
        <p className="text-xs mt-2" style={{ color: 'var(--red)' }}>
          Could not update charter binding.
        </p>
      )}
    </div>
  )
}
