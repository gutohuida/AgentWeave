import { useEffect, useState } from 'react'
import { AgentSummary, useAgentSessions } from '@/api/agents'
import { useBindAgentCharter, useCharters } from '@/api/charters'
import {
  MAX_WAITING_SECONDS,
  MIN_WAITING_SECONDS,
  useBindAgentRunner,
  useRunners,
  useUpdateAgentWaiting,
} from '@/api/runners'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { useCopy } from '@/hooks/useCopy'
import { Icon } from '@/components/common/Icon'
import { formatDistanceToNow } from 'date-fns'
import { getStatusConfig, StatusDot } from '@/lib/agentStatus'
import { tint } from '@/lib/colorTint'

interface AgentInfoTabProps {
  agent: AgentSummary
}

const ROLE_CONFIG: Record<string, { bg: string; color: string }> = {
  principal: { bg: tint('var(--blue)'), color: 'var(--blue)' },
  delegate: { bg: tint('var(--green)'), color: 'var(--green)' },
  collaborator: { bg: tint('var(--text-3)'), color: 'var(--text-3)' },
}

const RUNNER_CONFIG: Record<string, { bg: string; color: string; label: string }> = {
  claude_proxy: { bg: tint('var(--amber)'), color: 'var(--amber)', label: 'proxy' },
  manual: { bg: tint('var(--text-3)'), color: 'var(--text-3)', label: 'manual' },
  native: { bg: tint('var(--green)'), color: 'var(--green)', label: 'native' },
  copilot: { bg: tint('var(--blue)'), color: 'var(--blue)', label: 'copilot' },
}

export function AgentInfoTab({ agent }: AgentInfoTabProps) {
  const { data: sessionsData, isLoading: isLoadingSessions } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

  const statusCfg = getStatusConfig(agent.status)
  const roleCfg = agent.role ? (ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.collaborator) : null

  const cardStyle: React.CSSProperties = {
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: 16,
  }

  return (
    <div
      className="flex-1 overflow-y-auto p-6 space-y-6"
      style={{ background: 'var(--surface)' }}
    >
      {/* Status Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="info" size={18} style={{ color: 'var(--blue)' }} />
          Status
        </h3>
        <div className="flex items-center gap-3 mb-3">
          <StatusDot status={agent.status} size="lg" />
          <span
            className="text-sm capitalize"
            style={{ color: statusCfg.labelColor, fontWeight: statusCfg.pulse ? 600 : 500 }}
          >
            {statusCfg.label}
          </span>
        </div>
        {agent.latest_status_msg && (
          <p className="text-sm mb-3" style={{ color: 'var(--text-3)' }}>
            {agent.latest_status_msg}
          </p>
        )}
        {agent.last_seen && (
          <p className="text-xs" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            Last seen {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </p>
        )}
      </section>

      {/* Sessions Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="folder_open" size={18} style={{ color: 'var(--blue)' }} />
          Sessions
        </h3>
        {isLoadingSessions ? (
          <p className="text-sm" style={{ color: 'var(--text-3)' }}>Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            No sessions yet
          </p>
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => (
              <SessionRow key={session.id} session={session} />
            ))}
          </div>
        )}
      </section>

      {/* Roles & Configuration Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="badge" size={18} style={{ color: 'var(--blue)' }} />
          Roles & Configuration
        </h3>

        {/* Collaboration Role */}
        {roleCfg && (
          <div className="mb-4">
            <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              Collaboration Role
            </p>
            <span
              className="text-[11px] font-medium capitalize px-2 py-1 rounded-full inline-block"
              style={{ background: roleCfg.bg, color: roleCfg.color }}
            >
              {agent.role}
            </span>
          </div>
        )}

        {/* YOLO & Runner */}
        <div className="flex flex-wrap gap-3">
          {/* YOLO Badge */}
          <div>
            <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              YOLO Mode
            </p>
            {agent.yolo ? (
              <span
                className="text-[11px] font-medium px-2 py-1 rounded-full flex items-center gap-1"
                style={{
                  background: tint('var(--amber)'),
                  color: 'var(--amber)',
                }}
              >
                <Icon name="bolt" size={14} />
                Enabled
              </span>
            ) : (
              <span
                className="text-[11px] font-medium px-2 py-1 rounded-full"
                style={{
                  background: 'var(--surface-3)',
                  color: 'var(--text-3)',
                }}
              >
                Disabled
              </span>
            )}
          </div>

          {/* Runner Type */}
          {agent.runner && (
            <div>
              <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                Runner
              </p>
              <span
                className="text-[11px] font-medium capitalize px-2 py-1 rounded-full"
                style={{
                  background: RUNNER_CONFIG[agent.runner]?.bg || RUNNER_CONFIG.manual.bg,
                  color: RUNNER_CONFIG[agent.runner]?.color || RUNNER_CONFIG.manual.color,
                }}
              >
                {RUNNER_CONFIG[agent.runner]?.label || agent.runner}
              </span>
            </div>
          )}
        </div>

      </section>

      {/* The editable settings, on the same components the project settings panel uses, so the
          two read as one system rather than two panels that happen to both have controls. */}
      <SettingsSection
        title="Bindings"
        description="What this agent runs as, and the behaviour contract it works under."
      >
        <SettingsRow
          label="Runner"
          description="The execution capability this agent is bound to — its CLI, model and flags."
        >
          <RunnerPicker agent={agent} />
        </SettingsRow>
        <SettingsRow
          label="Charter"
          description="The markdown behaviour contract injected into this agent's turn context."
        >
          <CharterPicker agent={agent} />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Waiting for you"
        description="How long this agent holds its turn open for you before giving up and carrying on."
      >
        <WaitingSetting
          agent={agent}
          field="permission_timeout_seconds"
          label="Permission decision"
          fallback={120}
          description="How long a run waits for you to allow or refuse an action under “Ask me”. Running out refuses it. Measured: the provider held a permission prompt open for at least 150s."
        />
        <WaitingSetting
          agent={agent}
          field="question_timeout_seconds"
          label="Answer to a question"
          fallback={240}
          description="How long a run waits for you to answer a question it asked. Longer than a permission decision, because you have to read it and choose. Measured: an ordinary tool call was held open for at least 240s."
        />
      </SettingsSection>

      {/* Stats Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="bar_chart" size={18} style={{ color: 'var(--blue)' }} />
          Statistics
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--surface-3)' }}
          >
            <p className="text-4xl font-normal" style={{ color: 'var(--blue)' }}>
              {agent.active_task_count}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-3)' }}>
              Active Tasks
            </p>
          </div>
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--surface-3)' }}
          >
            <p className="text-4xl font-normal" style={{ color: 'var(--blue)' }}>
              {agent.message_count}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-3)' }}>
              Messages
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

/** One wait, in seconds, or blank for the built-in default.
 *
 * Committed on blur rather than on every keystroke: typing "45" over "240" passes through "4",
 * and saving that would set a wait shorter than the card takes to render. Blank clears the
 * setting back to the default rather than sending 0, which the API would refuse anyway.
 */
function WaitingSetting({
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

function RunnerPicker({ agent }: { agent: AgentSummary }) {
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

function CharterPicker({ agent }: { agent: AgentSummary }) {
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

function SessionRow({ session }: { session: { id: string; type: string; path: string; last_active?: string } }) {
  const { copied, copy } = useCopy()

  return (
    <div
      className="flex items-center gap-3 p-3 rounded-lg"
      style={{ background: 'var(--surface-3)' }}
    >
      <button
        onClick={() => copy(session.id)}
        className="flex-1 min-w-0 text-left group"
        title="Click to copy session ID"
      >
        <code
          className="block truncate text-xs"
          style={{
            background: copied ? tint('var(--green)') : 'var(--surface-2)',
            color: copied ? 'var(--green)' : 'var(--text-3)',
            padding: '4px 8px',
            borderRadius: '4px',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {copied ? 'Copied!' : session.id}
        </code>
      </button>
      <span
        className="text-[11px] px-2 py-1 rounded-full shrink-0"
        style={{
          background: 'var(--surface-2)',
          color: 'var(--text-3)',
          textTransform: 'capitalize',
        }}
      >
        {session.type}
      </span>
      {session.last_active && (
        <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
          {formatDistanceToNow(new Date(session.last_active), { addSuffix: true })}
        </span>
      )}
    </div>
  )
}
