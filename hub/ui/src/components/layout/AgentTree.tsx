import { useMemo, useState } from 'react'
import { useProjectConversations, type AgentConversation } from '@/api/agentChat'
import type { ProjectAgentSummary } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { agentColorVars } from '@/lib/agentColors'
import { ConversationRow } from './ConversationRow'
import { RowMenu, type RowMenuItem } from './RowMenu'

/** How many of an agent's conversations the tree shows before the rest go behind an expander.
 *
 * Three agents expanded at seven each is 25 rows with their parents — a rail that still fits
 * without scrolling. Operator's call, 2026-08-08; one constant, cheap to revisit against a real
 * project. The remainder is never dropped silently: the expander states how many are hidden. */
export const CONVERSATION_DISPLAY_CAP = 7

interface AgentTreeProps {
  projectId: string
  agents: ProjectAgentSummary[]
  activeProject: boolean
  activeAgent: string | null
  activeConversation: string | null
  expandedAgents: Record<string, boolean>
  onToggleAgent: (agent: string) => void
  onOpenAgent: (projectId: string, agent: string) => void
  onOpenConversation?: (projectId: string, agent: string, conversationId: string) => void
  onNewConversation?: (projectId: string, agent: string) => void
  onOpenAgentSettings?: (projectId: string, agent: string) => void
  onAddAgent?: (projectId: string) => void
}

/** One fetch per project rather than one per agent: expanding an agent shows its conversations
 *  immediately instead of starting a request, and the recency view reads the same cache. */
export function AgentTree({
  projectId,
  agents,
  activeProject,
  activeAgent,
  activeConversation,
  expandedAgents,
  onToggleAgent,
  onOpenAgent,
  onOpenConversation,
  onNewConversation,
  onOpenAgentSettings,
  onAddAgent,
}: AgentTreeProps) {
  const { data } = useProjectConversations(projectId)
  const [showAll, setShowAll] = useState<Record<string, boolean>>({})
  const [showArchived, setShowArchived] = useState<Record<string, boolean>>({})
  // The archived rows are only fetched once an agent's menu asks for them — the tree is for
  // what is open.
  const anyArchivedShown = Object.values(showArchived).some(Boolean)
  const archived = useProjectConversations(anyArchivedShown ? projectId : null, 'archived')

  const byAgent = useMemo(() => {
    const grouped = new Map<string, AgentConversation[]>()
    for (const conversation of data?.conversations ?? []) {
      const bucket = grouped.get(conversation.agent)
      if (bucket) bucket.push(conversation)
      else grouped.set(conversation.agent, [conversation])
    }
    return grouped
  }, [data])

  const archivedByAgent = useMemo(() => {
    const grouped = new Map<string, AgentConversation[]>()
    for (const conversation of archived.data?.conversations ?? []) {
      const bucket = grouped.get(conversation.agent)
      if (bucket) bucket.push(conversation)
      else grouped.set(conversation.agent, [conversation])
    }
    return grouped
  }, [archived.data])

  return (
    <div className="ml-7 flex flex-col gap-0.5">
      {agents.map((agent) => {
        const colors = agentColorVars(agent.color_index)
        const active = activeProject && activeAgent === agent.name
        const expanded = expandedAgents[agent.name] ?? false
        const conversations = byAgent.get(agent.name) ?? []
        const expandedAll = showAll[agent.name] ?? false
        const visible = expandedAll ? conversations : conversations.slice(0, CONVERSATION_DISPLAY_CAP)
        const hidden = conversations.length - visible.length
        // Waiting anywhere beneath a collapsed agent still has to be visible, or collapsing the
        // agent hides the thing the attention state exists to surface.
        const needsAttention = conversations.some((c) => c.attention === 'waiting')
        const archivedCount = data?.archived_by_agent?.[agent.name] ?? 0
        const archivedShown = showArchived[agent.name] ?? false

        const menuItems: RowMenuItem[] = [
          {
            id: 'new-conversation',
            label: 'New conversation',
            onSelect: () => onNewConversation?.(projectId, agent.name),
          },
          {
            id: 'settings',
            label: 'Agent settings',
            onSelect: () => onOpenAgentSettings?.(projectId, agent.name),
          },
          {
            id: 'archived',
            label: archivedShown ? 'Hide archived' : `Show archived (${archivedCount})`,
            disabled: archivedCount === 0,
            reason: 'Nothing archived yet',
            onSelect: () => {
              // Showing them is only useful under an expanded agent.
              if (!expanded) onToggleAgent(agent.name)
              setShowArchived((state) => ({ ...state, [agent.name]: !archivedShown }))
            },
          },
        ]

        return (
          <div key={agent.id}>
            <div className="row-group flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`${expanded ? 'Collapse' : 'Expand'} ${agent.name}`}
                aria-expanded={expanded}
                data-testid={`agent-expander-${projectId}-${agent.name}`}
                onClick={() => onToggleAgent(agent.name)}
              >
                <span
                  style={{
                    transform: expanded ? 'rotate(90deg)' : undefined,
                    transition: 'transform var(--dur-fast) var(--ease)',
                  }}
                >
                  <Icon name="chevron_right" size={14} />
                </span>
              </Button>
              <button
                type="button"
                data-testid={`rail-agent-${projectId}-${agent.name}`}
                data-active={active ? 'true' : 'false'}
                onClick={() => onOpenAgent(projectId, agent.name)}
                className="row-item min-w-0 flex-1"
              >
                <span
                  data-testid={`rail-agent-color-${projectId}-${agent.name}`}
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ background: colors.accent }}
                />
                <span className="min-w-0 flex-1 truncate">{agent.name}</span>
                {!expanded && needsAttention && (
                  <span
                    data-testid={`rail-agent-attention-${projectId}-${agent.name}`}
                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: 'var(--amber)' }}
                    title="A conversation is waiting for you"
                    aria-label="A conversation is waiting for you"
                    role="img"
                  />
                )}
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  title={agent.status}
                  style={{ background: agent.status === 'running' ? 'var(--green)' : 'var(--text-3)' }}
                />
              </button>
              <RowMenu
                label={`Actions for ${agent.name}`}
                testId={`agent-menu-${projectId}-${agent.name}`}
                persistent={active}
                items={menuItems}
              />
            </div>

            {expanded && (
              <div className="ml-7 flex flex-col gap-0.5" data-testid={`agent-conversations-${projectId}-${agent.name}`}>
                {visible.map((conversation) => (
                  <ConversationRow
                    key={conversation.id}
                    projectId={projectId}
                    conversation={conversation}
                    active={activeProject && activeConversation === conversation.id}
                    onOpen={() => onOpenConversation?.(projectId, agent.name, conversation.id)}
                    testId={`rail-conversation-${conversation.id}`}
                  />
                ))}
                {(hidden > 0 || expandedAll) && (
                  <button
                    type="button"
                    className="row-item"
                    data-testid={`conversation-expander-${projectId}-${agent.name}`}
                    aria-expanded={expandedAll}
                    onClick={() =>
                      setShowAll((state) => ({ ...state, [agent.name]: !expandedAll }))
                    }
                    style={{ color: 'var(--text-3)' }}
                  >
                    {expandedAll
                      ? `Show fewer`
                      : `Show ${hidden} more`}
                  </button>
                )}
                {archivedShown &&
                  (archivedByAgent.get(agent.name) ?? []).map((conversation) => (
                    <ConversationRow
                      key={conversation.id}
                      projectId={projectId}
                      conversation={conversation}
                      active={activeProject && activeConversation === conversation.id}
                      onOpen={() => onOpenConversation?.(projectId, agent.name, conversation.id)}
                      testId={`rail-archived-${conversation.id}`}
                    />
                  ))}
                {conversations.length === 0 && (
                  <span
                    className="px-2 py-1 text-[11px]"
                    data-testid={`no-conversations-${projectId}-${agent.name}`}
                    style={{ color: 'var(--text-3)' }}
                  >
                    No conversations yet
                  </span>
                )}
              </div>
            )}
          </div>
        )
      })}
      <button
        type="button"
        className="row-item"
        data-testid={`rail-add-agent-${projectId}`}
        aria-label={`Add agent to this project`}
        onClick={() => onAddAgent?.(projectId)}
      >
        <Icon name="person_add" size={14} />
        Add agent
      </button>
    </div>
  )
}
