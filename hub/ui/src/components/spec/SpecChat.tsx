import { useEffect, useMemo, useState } from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { useAgentConversations } from '@/api/agentChat'
import type { AgentSummary } from '@/api/agents'

interface SpecChatProps {
  agents: AgentSummary[] | undefined
  selectedAgent: string
  onSelectedAgentChange: (name: string) => void
  /** The document the operator has open. Carried to the trigger so the Hub can name it in the
   *  turn context — see `agent_trigger.py`'s `spec_document`. */
  documentPath: string | null
}

/**
 * The specification workspace's chat.
 *
 * It implements no message input, no run trigger, and no output rendering: it picks which agent
 * the operator is talking to, resolves which of that agent's conversations is on screen, and
 * mounts the one conversation surface the rest of the app uses. Everything that made the old
 * `SpecChatPane` a second application — its own `fetch` to `/agent/trigger`, its own 15-second
 * timeout, its own error vocabulary, and its inability to draw a permission card, a question
 * card, or a checkpoint banner — is gone by not being written twice.
 *
 * The conversation is the agent's own (design.md Decision 1). There is no specification-scoped
 * thread, and nothing here produces `origin="spec"`: what a specification thread would be scoped
 * to is not defined yet, and the direction taken is that a thread's phase derives from the
 * document open in it, which makes the durable relationship a link rather than an origin value.
 */
export function SpecChat({
  agents,
  selectedAgent,
  onSelectedAgentChange,
  documentPath,
}: SpecChatProps) {
  const agent = agents?.find((a) => a.name === selectedAgent)
  const { data: conversations = [] } = useAgentConversations(selectedAgent || null)

  /** `undefined` means "nothing chosen here yet — show the agent's most recent". A real id or
   *  `null` is a choice this pane has made: `null` after the panel hands back a fresh start, an
   *  id after the first message creates one. Kept distinct from `null` so the arrival of the
   *  conversation list cannot silently reopen a thread the operator just left. */
  const [chosen, setChosen] = useState<string | null | undefined>(undefined)

  // Another agent's conversations are not this one's.
  useEffect(() => {
    setChosen(undefined)
  }, [selectedAgent])

  const mostRecent = useMemo(() => {
    const open = conversations.filter((c) => c.lifecycle === 'open')
    if (open.length === 0) return null
    return open.reduce((newest, candidate) =>
      candidate.updated_at > newest.updated_at ? candidate : newest,
    )
  }, [conversations])

  const conversationId = chosen !== undefined ? chosen : (mostRecent?.id ?? null)

  if (!agent) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon="chat"
          title="No agent"
          description="Add an agent to this project to work on the specification with it."
        />
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col" style={{ background: 'var(--bg)' }}>
      {(agents?.length ?? 0) > 1 && (
        <div
          className="flex shrink-0 items-center gap-2 px-3 py-2"
          style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}
        >
          <label
            htmlFor="spec-chat-agent"
            className="text-[11px]"
            style={{ color: 'var(--text-3)' }}
          >
            Agent
          </label>
          <select
            id="spec-chat-agent"
            value={selectedAgent}
            onChange={(e) => onSelectedAgentChange(e.target.value)}
            className="flex-1 rounded-lg border px-2 py-1 text-xs"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              color: 'var(--text-2)',
              outline: 'none',
            }}
          >
            {agents?.map((a) => (
              <option key={a.name} value={a.name}>
                {a.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <AgentOutputPanel
          // A different agent is a different conversation surface, not the same one re-pointed:
          // remounting drops the previous agent's drafts, notices and pending overrides rather
          // than carrying them across.
          key={selectedAgent}
          agent={agent}
          conversationId={conversationId}
          onSelectConversation={setChosen}
          specDocumentPath={documentPath}
        />
      </div>
    </div>
  )
}
