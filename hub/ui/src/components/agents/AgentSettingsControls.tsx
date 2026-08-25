import { useEffect, useState } from 'react'
import {
  AgentSummary,
  MAX_AGENT_DESCRIPTION_CHARS,
  useUpdateAgentCheckpointMode,
  useUpdateAgentCheckpointOverride,
  useUpdateAgentDescription,
  useUpdateAgentGrant,
  useUpdateAgentPermissionDefault,
} from '@/api/agents'
import { permissionModeValues, useModelCatalog } from '@/api/modelCatalog'
import { useBindAgentCharter, useCharters } from '@/api/charters'
import {
  MAX_WAITING_SECONDS,
  MIN_WAITING_SECONDS,
  useBindAgentRunner,
  useRunners,
  useUpdateAgentWaiting,
} from '@/api/runners'
import { SettingsRow } from '@/components/environment/SettingsSection'
import { Select, Textarea } from '@/components/ui/input'

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
      <Textarea
        value={draft}
        rows={2}
        maxLength={MAX_AGENT_DESCRIPTION_CHARS}
        placeholder="What this agent is for."
        aria-label={`Description for ${agent.name}`}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        disabled={update.isPending}
        className="control-field w-full px-3 py-2 rounded-md text-sm resize-y"
        style={{
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
            // The invalid state is the recipe's, not an inline red border — `.control-field` styles
            // `aria-invalid`, which also announces the error rather than only colouring it.
            aria-invalid={error ? true : undefined}
            className="control-field w-24 px-3 py-2 rounded-md text-sm"
            style={{
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

/** What this agent may do when the conversation has not said.
 *
 * The same four postures the composer's Permissions pill offers, and deliberately the same
 * labels: this is not a second vocabulary for the same choice, it is that choice applied when no
 * run states one. Blank means the built-in default rather than a stored copy of today's — the
 * same reasoning as `WaitingSetting`.
 *
 * The options come from the catalog's union across providers rather than from the agent's bound
 * runner, because an agent may have none bound and rebinding one must not invalidate a default
 * the operator already chose.
 */
export function PermissionDefaultSetting({ agent }: { agent: AgentSummary }) {
  const { data: catalog, isLoading } = useModelCatalog()
  const update = useUpdateAgentPermissionDefault()
  const options = permissionModeValues(catalog)

  if (isLoading) {
    return <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading postures...</span>
  }

  return (
    <div>
      <Select
        value={agent.default_permission_mode ?? ''}
        onChange={(event) => update.mutate({ agent: agent.name, mode: event.target.value || null })}
        disabled={update.isPending}
        aria-label={`Default permissions for ${agent.name}`}
        className="control-field w-full px-3 py-2 rounded-md text-sm"
        style={{
          opacity: update.isPending ? 0.6 : 1,
        }}
      >
        <option value="">Built-in default (Edit files)</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>{option.label}</option>
        ))}
      </Select>
      <p className="mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
        Used when a conversation has not chosen one — including runs a peer or a schedule starts,
        where there is no composer to choose in.
      </p>
      {update.isError && (
        <p className="text-xs mt-2" style={{ color: 'var(--red)' }}>
          Could not update the default posture.
        </p>
      )}
    </div>
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
      <Select
        value={agent.runner_id ?? ''}
        onChange={(event) => {
          bindRunner.mutate({ agent: agent.name, runnerId: event.target.value || null })
        }}
        disabled={bindRunner.isPending}
        aria-label={`Runner for ${agent.name}`}
        className="control-field w-full px-3 py-2 rounded-md text-sm"
        style={{
          opacity: bindRunner.isPending ? 0.6 : 1,
        }}
      >
        <option value="">No runner</option>
        {runners.map((runner) => (
          <option key={runner.id} value={runner.id}>
            {runner.name} ({runner.cli})
          </option>
        ))}
      </Select>
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
      <Select
        value={agent.charter_id ?? ''}
        onChange={(event) => bindCharter.mutate({
          agent: agent.name,
          charterId: event.target.value || null,
        })}
        disabled={bindCharter.isPending}
        aria-label={`Charter for ${agent.name}`}
        className="control-field w-full px-3 py-2 rounded-md text-sm"
        style={{
          opacity: bindCharter.isPending ? 0.6 : 1,
        }}
      >
        <option value="">No charter</option>
        {charters.map((charter) => (
          <option key={charter.id} value={charter.id}>{charter.name}</option>
        ))}
      </Select>
      {bindCharter.isError && (
        <p className="text-xs mt-2" style={{ color: 'var(--red)' }}>
          Could not update charter binding.
        </p>
      )}
    </div>
  )
}

/** Token thresholds are entered in thousands and stored as a count. Same conversion as the
 *  project panel, at the only other place that collects the number. */
const TOKENS_PER_UNIT = 1000

/**
 * This agent's checkpoint policy, or the project's.
 *
 * The threshold is submitted as a whole — mode and value together — because an override that
 * inherited its mode from the project would read as a number in a unit nobody chose. Clearing the
 * value clears the override entirely and the agent goes back to the project's threshold.
 */
export function CheckpointOverrideSetting({ agent }: { agent: AgentSummary }) {
  const updateMode = useUpdateAgentCheckpointMode()
  const updateThreshold = useUpdateAgentCheckpointOverride()
  const storedMode = agent.checkpoint_threshold_mode ?? 'percent'
  const stored = agent.checkpoint_threshold_value ?? null
  const [unit, setUnit] = useState<'percent' | 'tokens'>(storedMode)
  const [entry, setEntry] = useState(
    stored === null ? '' : String(storedMode === 'tokens' ? Math.round(stored / TOKENS_PER_UNIT) : stored),
  )

  const commit = () => {
    const parsed = Number(entry)
    const value = !entry.trim() || !Number.isFinite(parsed) || parsed <= 0
      ? null
      : unit === 'tokens' ? Math.round(parsed * TOKENS_PER_UNIT) : Math.round(parsed)
    updateThreshold.mutate({ agent: agent.name, mode: unit, value, notes: null })
  }

  const selectStyle = {
  }

  return (
    <div className="space-y-3">
      <div>
        <Select
          value={agent.checkpoint_mode ?? ''}
          onChange={(event) => updateMode.mutate({ agent: agent.name, mode: event.target.value || null })}
          aria-label={`Automatic checkpointing for ${agent.name}`}
          className="control-field w-full px-3 py-2 rounded-md text-sm"
          style={selectStyle}
        >
          <option value="">Inherit the project's setting</option>
          <option value="off">Off for this agent</option>
          <option value="offered">Offer me one</option>
          <option value="automatic">Do it automatically</option>
        </Select>
        <p className="mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
          Whether this agent checkpoints at all. Independent of the threshold below, so an agent can
          opt out while still accepting the project's threshold.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Select
          value={unit}
          onChange={(event) => setUnit(event.target.value as 'percent' | 'tokens')}
          aria-label={`Threshold unit for ${agent.name}`}
          className="control-field px-3 py-2 rounded-md text-sm"
          style={selectStyle}
        >
          <option value="percent">Percent</option>
          <option value="tokens">K tokens</option>
        </Select>
        <input
          type="number"
          min={1}
          placeholder="Inherit"
          value={entry}
          onChange={(event) => setEntry(event.target.value)}
          onBlur={commit}
          aria-label={`Checkpoint threshold for ${agent.name}`}
          className="control-field w-28 px-3 py-2 rounded-md text-sm"
          style={selectStyle}
        />
      </div>
      <p className="text-[11px]" style={{ color: 'var(--text-3)' }}>
        Replaces the project's threshold whole. Leave blank to inherit it.
      </p>
      {(updateMode.isError || updateThreshold.isError) && (
        <p className="text-xs" style={{ color: 'var(--red)' }}>
          Could not update the checkpoint policy.
        </p>
      )}
    </div>
  )
}

/**
 * The two access grants.
 *
 * Separate controls because they are separate permissions: a checkpoint is a bounded summary,
 * while recall returns another agent's recorded output verbatim. Both are closed by default, and
 * neither can be granted from a charter — a charter is text the model reads, so it must not be
 * able to widen what the model may reach.
 */
export function CheckpointGrantsSetting({ agent }: { agent: AgentSummary }) {
  const update = useUpdateAgentGrant()

  const rows: Array<{ grant: 'can_read_checkpoints' | 'can_recall'; label: string; hint: string }> = [
    {
      grant: 'can_read_checkpoints',
      label: 'Read other agents’ checkpoints',
      hint: 'Summaries of where their conversations got to. Still bounded by each checkpoint’s own visibility.',
    },
    {
      grant: 'can_recall',
      label: 'Recall the observations behind them',
      hint: 'The original recorded output a checkpoint cites, verbatim. Requires the grant above.',
    },
  ]

  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <label key={row.grant} className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={Boolean(agent[row.grant])}
            onChange={(event) =>
              update.mutate({ agent: agent.name, grant: row.grant, enabled: event.target.checked })
            }
            aria-label={`${row.label} for ${agent.name}`}
            className="control-choice mt-0.5"
          />
          <span>
            <span className="text-sm" style={{ color: 'var(--text)' }}>{row.label}</span>
            <span className="block text-[11px]" style={{ color: 'var(--text-3)' }}>{row.hint}</span>
          </span>
        </label>
      ))}
      {update.isError && (
        <p className="text-xs" style={{ color: 'var(--red)' }}>Could not update the grant.</p>
      )}
    </div>
  )
}

/**
 * Separate from the checkpoint grants, deliberately.
 *
 * Those two widen what an agent may read. This one decides whether work is allowed to merge:
 * approval integrates nothing until some evidence for the requirement has been accepted. Grouping
 * them under one heading would tell the operator that authority over what ships is a kind of
 * reading.
 */
export function EvidenceGrantSetting({ agent }: { agent: AgentSummary }) {
  const update = useUpdateAgentGrant()

  return (
    <div className="space-y-3">
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={Boolean(agent.can_accept_evidence)}
          onChange={(event) =>
            update.mutate({
              agent: agent.name,
              grant: 'can_accept_evidence',
              enabled: event.target.checked,
            })
          }
          aria-label={`Accept evidence for ${agent.name}`}
          className="control-choice mt-0.5"
        />
        <span>
          <span className="text-sm" style={{ color: 'var(--text)' }}>Accept or reject evidence</span>
          <span className="block text-[11px]" style={{ color: 'var(--text-3)' }}>
            Accepted evidence is what lets approving a task merge the work. This agent still cannot
            accept its own — another agent, or you, decides that.
          </span>
        </span>
      </label>
      {update.isError && (
        <p className="text-xs" style={{ color: 'var(--red)' }}>Could not update the grant.</p>
      )}
    </div>
  )
}
