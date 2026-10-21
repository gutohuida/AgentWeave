import { useMemo, useState } from 'react'
import { useProjectConversations, type AgentConversation } from '@/api/agentChat'
import type { ProjectAgentSummary } from '@/api/projects'
import { Icon } from '@/components/common/Icon'
import { agentColorVars } from '@/lib/agentColors'
import { capRows, groupConsecutiveFirings } from '@/lib/loopGrouping'
import { ConversationRow } from './ConversationRow'
import { LoopFiringGroup } from './LoopFiringGroup'
import { RowMenu, type RowMenuItem } from './RowMenu'
import { formatAgo, formatDateTime } from '@/lib/format'

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

  // F193: an archived agent's open conversations. The tree iterates the open roster, so their
  // bucket was never read and they silently vanished here while the recency view still listed
  // them. They get a group of their own, marked; opening one offers to unarchive the agent.
  const orphans = useMemo(
    () =>
      [...byAgent.entries()]
        .filter(([name]) => !agents.some((agent) => agent.name === name))
        .sort(([a], [b]) => a.localeCompare(b)),
    [byAgent, agents],
  )

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
    <div className="aw-rail-children">
      {agents.map((agent) => {
        const colors = agentColorVars(agent.color_index)
        const active = activeProject && activeAgent === agent.name
        const expanded = expandedAgents[agent.name] ?? false
        const conversations = byAgent.get(agent.name) ?? []
        const expandedAll = showAll[agent.name] ?? false
        // Grouped before capping, so the cap can never fall inside a run of firings and split it.
        // With no loops among an agent's conversations this is the identity, and the cap behaves
        // exactly as it did before grouping existed.
        const rows = groupConsecutiveFirings(conversations)
        const capped = capRows(rows, expandedAll ? rows.length : CONVERSATION_DISPLAY_CAP)
        const visible = capped.visible
        const hidden = capped.hiddenConversations
        // Waiting anywhere beneath the agent has to be visible on its row, or collapsing the agent
        // hides the thing the attention state exists to surface.
        const waiting = conversations.some((c) => c.attention === 'waiting')
        const running =
          agent.status === 'running' ||
          agent.status === 'working' ||
          conversations.some((c) => c.attention === 'running')
        const attention: 'running' | 'waiting' | 'idle' = waiting ? 'waiting' : running ? 'running' : 'idle'
        const containsActive = activeProject && conversations.some((c) => c.id === activeConversation)
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
            <div
              className="aw-rail-row aw-rail-agent-row aw-reveal-host row-group"
              data-attention={attention}
              data-active={active && !containsActive ? 'true' : 'false'}
              style={{ '--agent-accent': colors.accent } as React.CSSProperties}
            >
              <button
                data-slot="rail-chevron"
                type="button"
                className="aw-rail-chevron-button"
                aria-label={`${expanded ? 'Collapse' : 'Expand'} ${agent.name}`}
                aria-expanded={expanded}
                data-testid={`agent-expander-${projectId}-${agent.name}`}
                onClick={() => onToggleAgent(agent.name)}
              >
                <span className="aw-rail-chevron" data-open={expanded ? 'true' : 'false'}>
                  <Icon name="chevron_right" size={12} />
                </span>
              </button>
              <button
                data-slot="rail-row-main"
                type="button"
                className="aw-rail-row-main"
                data-testid={`rail-agent-${projectId}-${agent.name}`}
                data-active={active ? 'true' : 'false'}
                /* Level 2 of the rail's selection ladder. */
                data-depth="agent"
                onClick={() => onOpenAgent(projectId, agent.name)}
              >
                <span
                  data-testid={`rail-agent-color-${projectId}-${agent.name}`}
                  className={['aw-agent-dot', attention === 'running' ? 'aw-pulse' : ''].join(' ')}
                  aria-hidden="true"
                />
                <span className="aw-rail-agent-name min-w-0 flex-1 truncate">{agent.name}</span>
              </button>
              <span className="aw-rail-row-end">
                {/* One status signal, in words: working, waiting, or how long ago it was active —
                    with the exact time in its title. It gives way to the row's actions on hover. */}
                {attention === 'waiting' ? (
                  <span
                    data-testid={`rail-agent-attention-${projectId}-${agent.name}`}
                    className="aw-reveal-rest aw-rail-meta"
                    title="A conversation is waiting for you"
                    aria-label="A conversation is waiting for you"
                    role="img"
                  >
                    waiting
                  </span>
                ) : (
                  <span
                    className="aw-reveal-rest aw-rail-meta"
                    data-testid={`rail-agent-meta-${projectId}-${agent.name}`}
                    title={agent.last_seen ? `Last active ${formatDateTime(agent.last_seen)}` : 'No activity yet'}
                  >
                    {attention === 'running' ? 'working' : agent.last_seen ? formatAgo(agent.last_seen) : ''}
                  </span>
                )}
                <span className="aw-reveal aw-rail-actions">
                  <button
                    data-slot="icon-button"
                    type="button"
                    className="aw-icon-button"
                    aria-label={`New conversation with ${agent.name}`}
                    title="New conversation"
                    onClick={() => onNewConversation?.(projectId, agent.name)}
                  >
                    <Icon name="add" size={13} />
                  </button>
                  <RowMenu
                    label={`Actions for ${agent.name}`}
                    testId={`agent-menu-${projectId}-${agent.name}`}
                    items={menuItems}
                  />
                </span>
              </span>
            </div>

            {expanded && (
              <div
                className="aw-rail-conversations rail-conversation-group"
                data-testid={`agent-conversations-${projectId}-${agent.name}`}
              >
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
                        onOpenConversation?.(projectId, agent.name, conversation.id)
                      }
                      rowTestId={(conversation) => `rail-conversation-${conversation.id}`}
                      testId={`rail-loop-group-${row.conversations[0].id}`}
                    />
                  ) : (
                    <ConversationRow
                      key={row.conversation.id}
                      projectId={projectId}
                      conversation={row.conversation}
                      active={activeProject && activeConversation === row.conversation.id}
                      onOpen={() =>
                        onOpenConversation?.(projectId, agent.name, row.conversation.id)
                      }
                      testId={`rail-conversation-${row.conversation.id}`}
                    />
                  ),
                )}
                {(hidden > 0 || expandedAll) && (
                  <button
                    data-slot="rail-more"
                    type="button"
                    className="aw-rail-more"
                    data-testid={`conversation-expander-${projectId}-${agent.name}`}
                    aria-expanded={expandedAll}
                    onClick={() =>
                      setShowAll((state) => ({ ...state, [agent.name]: !expandedAll }))
                    }
                  >
                    {expandedAll ? `Show fewer` : `Show ${hidden} more`}
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
                {/* An expanded agent with nothing under it carries the single action reachable
                    from this spot: a new conversation with *this* agent. */}
                {conversations.length === 0 && (
                  <div className="rail-empty" data-testid={`no-conversations-${projectId}-${agent.name}`}>
                    <span className="sr-only">No conversations yet</span>
                    <button
                      data-slot="rail-empty"
                      type="button"
                      className="aw-rail-empty"
                      data-testid={`agent-new-conversation-${projectId}-${agent.name}`}
                      aria-label={`Start a conversation with ${agent.name}`}
                      onClick={() => onNewConversation?.(projectId, agent.name)}
                    >
                      <Icon name="add" size={13} />
                      Start a conversation
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
      {orphans.length > 0 && (
        <div data-testid={`rail-archived-agents-${projectId}`} className="aw-rail-orphans">
          <span className="aw-rail-section-label">Archived agents</span>
          {orphans.map(([name, conversations]) =>
            conversations.map((conversation) => (
              <ConversationRow
                key={conversation.id}
                projectId={projectId}
                conversation={conversation}
                active={activeProject && activeConversation === conversation.id}
                onOpen={() => onOpenConversation?.(projectId, name, conversation.id)}
                agentName={name}
                agentArchived
                testId={`agent-conversation-${conversation.id}`}
              />
            )),
          )}
        </div>
      )}
      {agents.length === 0 && (
        <button
          data-slot="rail-empty"
          type="button"
          className="aw-rail-empty"
          data-testid={`rail-first-agent-${projectId}`}
          aria-label="Add agent to this project"
          onClick={() => onAddAgent?.(projectId)}
        >
          <Icon name="person_add" size={13} />
          Add the first agent
        </button>
      )}
    </div>
  )
}
