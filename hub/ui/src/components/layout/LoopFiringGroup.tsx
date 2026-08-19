import { useEffect, useState } from 'react'
import type { AgentConversation } from '@/api/agentChat'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { loopTabId, usePanelTabsStore } from '@/store/panelTabsStore'
import { ConversationRow } from './ConversationRow'

interface LoopFiringGroupProps {
  projectId: string
  loopId: string
  label: string
  /** The consecutive run this row stands for, in the order it appeared. */
  conversations: AgentConversation[]
  activeConversation: string | null
  onOpen: (conversation: AgentConversation) => void
  /** Prefix for the child rows' test ids, so the tree and the recency view keep their own. */
  rowTestId: (conversation: AgentConversation) => string
  testId: string
  agentColor?: string
  agentName?: string
}

/**
 * A run of consecutive firings of one loop, collapsed to a single row.
 *
 * Shaped after the agent row directly above it in this rail, deliberately: a chevron that expands,
 * a name that opens the thing itself, and the state that must survive collapsing shown on the row.
 * A third idiom for "expandable row in the sidebar" would be one more thing to learn for no gain.
 *
 * Two things collapsing must not hide, both already established rules here:
 *
 * - **Attention.** A firing that stopped for the operator is the entire reason the attention state
 *   exists; hiding it behind a collapsed row would defeat it exactly as collapsing an agent would
 *   (`AgentTree` makes the same argument for `needsAttention`).
 * - **The conversation being read.** A group holding the active conversation opens itself, so
 *   opening a firing never makes it vanish from the rail.
 */
export function LoopFiringGroup({
  projectId,
  loopId,
  label,
  conversations,
  activeConversation,
  onOpen,
  rowTestId,
  testId,
  agentColor,
  agentName,
}: LoopFiringGroupProps) {
  const holdsActive = conversations.some((c) => c.id === activeConversation)
  const [expanded, setExpanded] = useState(holdsActive)
  const openTab = usePanelTabsStore((state) => state.openTab)

  // Opening a firing from anywhere else — the recency view, a URL, a notification — must reveal it
  // here too, not leave the rail pointing at a collapsed row.
  useEffect(() => {
    if (holdsActive) setExpanded(true)
  }, [holdsActive])

  const waiting = conversations.some((c) => c.attention === 'waiting')
  const running = !waiting && conversations.some((c) => c.attention === 'running')
  const attention = waiting
    ? { color: 'var(--amber)', label: 'A firing is waiting for you' }
    : running
      ? { color: 'var(--green)', label: 'A firing is running' }
      : null

  return (
    <div className="flex flex-col gap-0.5" data-testid={testId}>
      <div className="row-group flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon-xs"
          data-testid={`${testId}-expander`}
          aria-expanded={expanded}
          aria-label={expanded ? `Collapse ${label} firings` : `Expand ${label} firings`}
          onClick={() => setExpanded((value) => !value)}
        >
          <span
            className="flex"
            style={{
              transform: expanded ? 'rotate(90deg)' : 'none',
              transition: 'transform var(--dur-fast) var(--ease)',
            }}
          >
            <Icon name="chevron_right" size={14} />
          </span>
        </Button>
        <button
          type="button"
          className="row-item min-w-0 flex-1"
          data-testid={`${testId}-open`}
          data-loop-id={loopId}
          onClick={() => openTab(projectId, loopTabId(loopId))}
          title={`${conversations.length} firings of “${label}” — open the loop`}
        >
          {agentColor && (
            <span
              aria-hidden="true"
              className="h-4 w-[2px] shrink-0 rounded-full"
              style={{ background: agentColor }}
            />
          )}
          <Icon name="sync" size={11} className="shrink-0" style={{ color: 'var(--text-3)' }} />
          <span className="min-w-0 flex-1 truncate">{label}</span>
          <span
            data-testid={`${testId}-count`}
            className="shrink-0 text-[10px]"
            style={{ color: 'var(--text-3)' }}
          >
            {conversations.length}
          </span>
          {attention && (
            <span
              data-testid={`${testId}-attention`}
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: attention.color }}
              title={attention.label}
              aria-label={attention.label}
              role="img"
            />
          )}
        </button>
      </div>

      {expanded && (
        <div className="ml-5 flex flex-col gap-0.5" data-testid={`${testId}-firings`}>
          {conversations.map((conversation) => (
            <ConversationRow
              key={conversation.id}
              projectId={projectId}
              conversation={conversation}
              active={activeConversation === conversation.id}
              onOpen={() => onOpen(conversation)}
              agentColor={agentColor}
              agentName={agentName}
              testId={rowTestId(conversation)}
              /* The group row already names the loop, once, for every firing under it. */
              showLoopMarker={false}
            />
          ))}
        </div>
      )}
    </div>
  )
}
