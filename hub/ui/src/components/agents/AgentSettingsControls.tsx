import { useEffect, useState } from 'react'
import {
  AgentSummary,
  useUpdateAgentCheckpointMode,
  useUpdateAgentCheckpointOverride,
  useUpdateAgentGithubMcp,
  useUpdateAgentReviewAgents,
} from '@/api/agents'
import { useBindAgentCharter, useCharters } from '@/api/charters'
import {
  MAX_WAITING_SECONDS,
  MIN_WAITING_SECONDS,
  useUpdateAgentWaiting,
} from '@/api/runners'
import { SettingsRow } from '@/components/environment/SettingsSection'
import { runnerCeilingNote } from '@/components/environment/describeThreshold'
import { useProjectSettings } from '@/api/projects'
import { useConfigStore } from '@/store/configStore'
import { Select } from '@/components/ui/input'

/**
 * The editable per-agent controls, shared by the settings page and — until it is retired — the
 * conversation's info tab.
 *
 * They live here rather than inside either surface so that moving a setting between sections is a
 * change of where a control is rendered, not a rewrite of the control. `agent-configuration`
 * requires that no setting be editable from two surfaces; that is a statement about where these
 * are *placed*, which is why the placement is deliberately not baked into the controls.
 */

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

/** Copilot's own built-in review agents, in the order the closed vocabulary
 *  (`COPILOT_REVIEW_AGENTS`, `hub/hub/api/v1/agents.py`) declares them. */
const COPILOT_REVIEW_AGENT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'code-review', label: 'code-review' },
  { value: 'security-review', label: 'security-review' },
  { value: 'rubber-duck', label: 'rubber-duck' },
]

/** Which of Copilot's built-ins this `copilot`-bound agent consults as a subagent before
 *  recording its verdict (design D8). Shown only for a `copilot` agent — *"A setting with no
 *  backing state is not presented"* — because the setting does nothing for any other runner.
 *
 *  Off by default: each consult is at least one extra model call. The note below the checkboxes
 *  states the one caveat the design calls out by name — on a provider runner (the Runners page's
 *  own setting), these built-in subagents may send Copilot's own model id to the provider or
 *  spend the operator's key running them, so they may not run at all; group B deliberately does
 *  not read group C's state to suppress the setting itself (design D10).
 */
export function CopilotReviewAgentsSetting({ agent }: { agent: AgentSummary }) {
  const update = useUpdateAgentReviewAgents()
  const stored = agent.config?.copilot_review_agents ?? []

  const toggle = (value: string, checked: boolean) => {
    const next = checked
      ? [...stored, value]
      : stored.filter((entry) => entry !== value)
    update.mutate({ agent: agent.name, agents: next })
  }

  return (
    <div className="max-w-[320px] space-y-3">
      {COPILOT_REVIEW_AGENT_OPTIONS.map((option) => (
        <label key={option.value} className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={stored.includes(option.value)}
            onChange={(event) => toggle(option.value, event.target.checked)}
            disabled={update.isPending}
            aria-label={`Consult ${option.label} for ${agent.name}`}
            className="control-choice mt-0.5"
          />
          <span className="text-sm font-mono" style={{ color: 'var(--text)' }}>{option.label}</span>
        </label>
      ))}
      <p className="text-[11px]" style={{ color: 'var(--text-3)' }}>
        Consulted as a subagent before this agent records its verdict. It does not see this
        repository's instructions, and its findings are not the verdict — the verdict is still
        recorded only by <code>update_task</code>. On a provider runner, Copilot's review agents
        may not run.
      </p>
      {update.isError && (
        <p className="text-xs" style={{ color: 'var(--red)' }}>Could not save.</p>
      )}
    </div>
  )
}

/** Whether this `copilot`-bound agent's Copilot spawn loads the built-in GitHub MCP server
 *  (design D9). Off by default: `--disable-builtin-mcps` is passed unless this is on. Shown only
 *  for a `copilot` agent, same rule as the review-agents setting above — a setting with no
 *  backing state is not presented.
 *
 *  The help text says what happens (slice 5 D9a, F485, 2026-10-04): Copilot loads only its
 *  read-only GitHub tools and approves them itself (`mcp-read-only`), so no card ever comes from
 *  them, in any posture. The flags that add write tools are removed from any run without Full
 *  access, where every call is allowed. The `gh` command in a shell is the Hub's ordinary command
 *  decision, not this setting's. The earlier text promised a card that could not appear.
 */
export function CopilotGithubMcpSetting({ agent }: { agent: AgentSummary }) {
  const update = useUpdateAgentGithubMcp()
  const checked = agent.config?.copilot_github_mcp === true

  return (
    <div className="max-w-[320px] space-y-3">
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => update.mutate({ agent: agent.name, enabled: event.target.checked })}
          disabled={update.isPending}
          aria-label={`Enable the GitHub MCP server for ${agent.name}`}
          className="control-choice mt-0.5"
        />
        <span className="text-sm" style={{ color: 'var(--text)' }}>
          Enable the built-in GitHub server
        </span>
      </label>
      <p className="text-[11px]" style={{ color: 'var(--text-3)' }}>
        Gives this agent Copilot's built-in GitHub tools, read-only. Copilot runs them without
        asking you, in every posture, Ask me included. Tools that write to GitHub can be added
        only on a runner with Full access, where they run without asking too. This setting does
        not govern the <code>gh</code> command, which a shell call runs and the Hub decides like
        any other command.
      </p>
      {update.isError && (
        <p className="text-xs" style={{ color: 'var(--red)' }}>Could not save.</p>
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
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projectSettings, isError: projectSettingsFailed } = useProjectSettings(
    projectId ?? null,
  )
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

  // Where the checkpoint actually fires (D10): the agent's own override, else the project's.
  const hasOverride = agent.checkpoint_threshold_value != null
  const ceilingNote = runnerCeilingNote(
    agent.checkpoint_compaction_percent,
    hasOverride ? agent.checkpoint_threshold_mode : projectSettings?.checkpoint_threshold_mode,
    hasOverride ? agent.checkpoint_threshold_value : projectSettings?.checkpoint_threshold_value,
    agent.runner,
  )

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
      {ceilingNote && (
        <p className="text-[11px]" style={{ color: 'var(--text-2)' }}>
          {ceilingNote}
        </p>
      )}
      {!hasOverride && projectSettingsFailed && (
        <p className="text-[11px]" style={{ color: 'var(--text-3)' }}>
          The project's threshold could not be read, so where this agent's checkpoint fires is not
          shown.
        </p>
      )}
      {(updateMode.isError || updateThreshold.isError) && (
        <p className="text-xs" style={{ color: 'var(--red)' }}>
          Could not update the checkpoint policy.
        </p>
      )}
    </div>
  )
}
