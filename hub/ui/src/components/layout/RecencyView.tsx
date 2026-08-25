import { useState } from 'react'
import { useProjectConversations } from '@/api/agentChat'
import type { ProjectAgentSummary } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { agentColorVars } from '@/lib/agentColors'
import { capRows, groupConsecutiveFirings } from '@/lib/loopGrouping'
import { ConversationRow } from './ConversationRow'
import { LoopFiringGroup } from './LoopFiringGroup'

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
  /** No agent is implied by a row's position here, so the surface has to ask for one. */
  onNewConversation?: (projectId: string, agent: string | null) => void
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
  onNewConversation,
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
  // Grouped before capping, so the cap can never fall inside a run and split it. With no loops in
  // the list this is the identity, and the cap behaves exactly as it did before grouping existed.
  const rows = groupConsecutiveFirings(conversations)
  const { visible, hiddenConversations } = capRows(rows, showAll ? rows.length : RECENCY_DISPLAY_CAP)
  const hidden = hiddenConversations

  return (
    <div className="ml-7 flex flex-col gap-0.5" data-testid={`rail-recency-${projectId}`}>
      {visible.map((row) =>
        row.kind === 'loopGroup' ? (
          <LoopFiringGroup
            key={`group-${row.conversations[0].id}`}
            projectId={projectId}
            loopId={row.loopId}
            label={row.label}
            conversations={row.conversations}
            activeConversation={activeProject ? activeConversation : null}
            onOpen={(conversation) =>
              onOpenConversation?.(projectId, conversation.agent, conversation.id)
            }
            rowTestId={(conversation) => `recency-conversation-${conversation.id}`}
            testId={`recency-loop-group-${row.conversations[0].id}`}
            agentColor={colorFor(row.conversations[0].agent)}
            agentName={row.conversations[0].agent}
          />
        ) : (
          <ConversationRow
            key={row.conversation.id}
            projectId={projectId}
            conversation={row.conversation}
            active={activeProject && activeConversation === row.conversation.id}
            onOpen={() =>
              onOpenConversation?.(projectId, row.conversation.agent, row.conversation.id)
            }
            agentColor={colorFor(row.conversation.agent)}
            agentName={row.conversation.agent}
            testId={`recency-conversation-${row.conversation.id}`}
          />
        ),
      )}

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

      {/* Dressed at rail scale, for the same reason `AgentTree`'s is: a bare grey line was the
          plainest thing in the product, sitting exactly where the operator has nothing to click.
          It absorbs the standalone "New conversation" row below rather than sitting above a
          second copy of it — the one action available from this spot should appear once. */}
      {conversations.length === 0 && (
        <div className="rail-empty" data-testid={`recency-empty-${projectId}`}>
          <div className="rail-empty-head">
            <span className="rail-empty-icon" aria-hidden="true">
              <Icon name="forum" size={14} />
            </span>
            <span className="rail-empty-title">No conversations yet</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start"
            data-testid={`recency-new-conversation-${projectId}`}
            aria-label="Start a conversation"
            onClick={() => onNewConversation?.(projectId, null)}
          >
            <Icon name="add" size={14} />
            New conversation
          </Button>
        </div>
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
            projectId={projectId}
            conversation={conversation}
            active={activeProject && activeConversation === conversation.id}
            onOpen={() => onOpenConversation?.(projectId, conversation.agent, conversation.id)}
            agentColor={colorFor(conversation.agent)}
            agentName={conversation.agent}
            testId={`recency-archived-${conversation.id}`}
          />
        ))}

      {/* The tree starts a conversation from an agent's row menu. This view has no agent rows,
          so it needs its own way in — and the surface it opens has to ask which agent.
          Suppressed while the list is empty: the empty state above carries this same action, under
          the same test id, and two identical entry points stacked on top of each other is the
          "is 2 buttons the right call?" defect the project rail already had once. */}
      {conversations.length > 0 && (
        <button
          type="button"
          className="row-item"
          data-testid={`recency-new-conversation-${projectId}`}
          onClick={() => onNewConversation?.(projectId, null)}
        >
          <Icon name="add" size={14} />
          New conversation
        </button>
      )}
    </div>
  )
}
