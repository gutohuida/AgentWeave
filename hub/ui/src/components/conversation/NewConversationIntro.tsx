import type { AgentSummary } from '@/api/agents'
import { Icon } from '@/components/common/Icon'
import { agentColorVars } from '@/lib/agentColors'
import '@/styles/conversation.css'

/** What a new conversation shows before the first message: who you are about to talk to, what
 *  it runs on, and a few ways to start. Replaces "No conversation yet / Write below to start this
 *  thread", which told the operator nothing they did not already know. */
export interface ConversationStarter {
  label: string
  /** The message it puts in the composer (not sent: the operator edits and sends). */
  message: string
  icon?: string
}

export function NewConversationIntro({
  agent,
  runnerLabel,
  modelLabel,
  postureLabel,
  starters,
  onPick,
  headlineTestId,
}: {
  agent: AgentSummary
  /** e.g. "Claude Code"; null when no runner is bound (the intro then says it cannot run). */
  runnerLabel: string | null
  modelLabel?: string | null
  /** The permission posture its next run gets, e.g. "Workspace only". */
  postureLabel?: string | null
  starters: ConversationStarter[]
  onPick: (message: string) => void
  headlineTestId?: string
}) {
  const color = agentColorVars(agent.color_index)
  const runsOn = runnerLabel ? [runnerLabel, modelLabel, postureLabel].filter(Boolean).join(' · ') : null
  return (
    <div className="aw-newconv">
      <span className="aw-newconv-avatar" style={{ background: color.tint, color: color.accent, boxShadow: `inset 0 0 0 1px ${color.border}` }} aria-hidden="true">
        {agent.name.slice(0, 2)}
      </span>
      <h2 className="aw-newconv-title" data-testid={headlineTestId}>New conversation with {agent.name}</h2>
      {agent.description ? <p className="aw-newconv-desc">{agent.description}</p> : null}
      <p className="aw-newconv-runs" data-unbound={runsOn ? 'false' : 'true'}>
        {runsOn ?? `${agent.name} has no runner, so a message here will wait until one is bound.`}
      </p>
      {starters.length > 0 ? (
        <div className="aw-newconv-starters" role="list">
          {starters.map((starter) => (
            <button
              key={starter.label}
              type="button"
              role="listitem"
              data-slot="conversation-starter"
              className="aw-newconv-starter"
              onClick={() => onPick(starter.message)}
            >
              <Icon name={starter.icon ?? 'chat'} size={14} className="aw-newconv-starter-icon" />
              <span className="min-w-0">
                <span className="aw-newconv-starter-label">{starter.label}</span>
                <span className="aw-newconv-starter-message">{starter.message}</span>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
