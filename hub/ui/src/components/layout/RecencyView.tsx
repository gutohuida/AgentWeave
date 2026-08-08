import { useState } from 'react'
import { useProjectConversations } from '@/api/agentChat'
import type { ProjectAgentSummary } from '@/api/projects'
import { agentColorVars } from '@/lib/agentColors'
import { ConversationRow } from './ConversationRow'

/** How many of a project's conversations the recency view shows before the rest go behind an
 *  expander.
 *
 *  The tree caps per *agent*; this view has no agents to cap by, so an unbounded flat list of one
 *  project's whole history is exactly what the cap exists to prevent — six agents at seven each
 *  would be forty-two rows here. Larger than the tree's seven because this is the scanning view
 *  and a cap of seven would hide the second half of a normal working day. Operator's requirement,
 *  2026-08-08: the recency view needs a conversation limit per project too. */
export const RECENCY_DISPLAY_CAP = 15

interface RecencyViewProps {
  projectId: string
  agents: ProjectAgentSummary[]
  activeProject: boolean
  activeConversation: string | null
  onOpenConversation?: (projectId: string, agent: string, conversationId: string) => void
}

/** Every conversation in the project, newest activity first, regardless of which agent owns it.
 *
 * The tree's third level costs the flat scan a two-level sidebar gets for free — this recovers
 * it. Agent identity survives the flattening as a persistent leading edge in the agent's colour,
 * never a hover tint: decoding one row at a time is exactly what a scanning view cannot afford. */
export function RecencyView({
  projectId,
  agents,
  activeProject,
  activeConversation,
  onOpenConversation,
}: RecencyViewProps) {
  const [showArchived, setShowArchived] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const open = useProjectConversations(projectId)
  // Only fetched once asked for — the archived list is not what this view is for.
  const archived = useProjectConversations(showArchived ? projectId : null, 'archived')

  const colorFor = (agentName: string): string => {
    const agent = agents.find((candidate) => candidate.name === agentName)
    return agentColorVars(agent?.color_index ?? null).accent
  }

  const conversations = open.data?.conversations ?? []
  const archivedCount = open.data?.archived_count ?? 0
  const archivedRows = archived.data?.conversations ?? []
  const visible = showAll ? conversations : conversations.slice(0, RECENCY_DISPLAY_CAP)
  const hidden = conversations.length - visible.length

  return (
    <div className="ml-7 flex flex-col gap-0.5" data-testid={`rail-recency-${projectId}`}>
      {visible.map((conversation) => (
        <ConversationRow
          key={conversation.id}
          conversation={conversation}
          active={activeProject && activeConversation === conversation.id}
          onOpen={() => onOpenConversation?.(projectId, conversation.agent, conversation.id)}
          agentColor={colorFor(conversation.agent)}
          agentName={conversation.agent}
          testId={`recency-conversation-${conversation.id}`}
        />
      ))}

      {/* Rendered whenever anything is hidden *or* the list is already expanded — without the
          second half there is no way back, which is the defect the operator found in the tree's
          version of this control on 2026-08-08. */}
      {(hidden > 0 || showAll) && (
        <button
          type="button"
          className="row-item"
          data-testid={`recency-expander-${projectId}`}
          aria-expanded={showAll}
          onClick={() => setShowAll((value) => !value)}
          style={{ color: 'var(--text-3)' }}
        >
          {showAll ? 'Show fewer' : `Show ${hidden} more`}
        </button>
      )}

      {conversations.length === 0 && (
        <span
          className="px-2 py-1 text-[11px]"
          data-testid={`recency-empty-${projectId}`}
          style={{ color: 'var(--text-3)' }}
        >
          No conversations yet
        </span>
      )}

      {archivedCount > 0 && (
        <button
          type="button"
          className="row-item"
          data-testid={`recency-show-archived-${projectId}`}
          aria-expanded={showArchived}
          onClick={() => setShowArchived((value) => !value)}
          style={{ color: 'var(--text-3)' }}
        >
          {showArchived ? 'Hide archived' : `Show archived (${archivedCount})`}
        </button>
      )}

      {showArchived &&
        archivedRows.map((conversation) => (
          <ConversationRow
            key={conversation.id}
            conversation={conversation}
            active={activeProject && activeConversation === conversation.id}
            onOpen={() => onOpenConversation?.(projectId, conversation.agent, conversation.id)}
            agentColor={colorFor(conversation.agent)}
            agentName={conversation.agent}
            testId={`recency-archived-${conversation.id}`}
          />
        ))}
    </div>
  )
}
