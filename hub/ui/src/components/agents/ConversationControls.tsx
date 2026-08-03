import { useRef, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Icon } from '@/components/common/Icon'
import { AgentSummary } from '@/api/agents'
import { AgentConversation } from '@/api/agentChat'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'
import { StatusDot, getStatusConfig } from '@/lib/agentStatus'
import { AgentInfoTab } from './AgentInfoTab'

export type HandoffState = 'idle' | 'preparing' | 'ready'

interface ConversationControlsProps {
  agent: AgentSummary
  isRunning: boolean
  isStopping: boolean
  onStop: () => void
  conversations: AgentConversation[]
  currentConversationId?: string
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  handoffState: HandoffState
  handoffUnavailable: boolean
  interactionLocked: boolean
  onHandoff: () => void
  onFoldAll: () => void
}

const itemStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: 2,
  width: '100%',
  padding: '6px 10px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 12,
  color: 'var(--text-2)',
  cursor: 'pointer',
  outline: 'none',
}

function handoffReason(
  handoffUnavailable: boolean,
  currentConversationId: string | undefined,
  interactionLocked: boolean,
  handoffState: HandoffState,
): string | null {
  if (handoffUnavailable) return 'Requires an automatically managed runner'
  if (!currentConversationId) return 'Start a conversation first'
  if (handoffState === 'preparing') return 'Already preparing'
  if (handoffState === 'ready') return 'Already ready — send a message to resume it'
  if (interactionLocked) return 'Unavailable while the agent is busy'
  return null
}

export function ConversationControls({
  agent,
  isRunning,
  isStopping,
  onStop,
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  handoffState,
  handoffUnavailable,
  interactionLocked,
  onHandoff,
  onFoldAll,
}: ConversationControlsProps) {
  const [detailsOpen, setDetailsOpen] = useState(false)
  const menuTriggerRef = useRef<HTMLButtonElement>(null)
  const statusCfg = getStatusConfig(agent.status)

  const reason = handoffReason(handoffUnavailable, currentConversationId, interactionLocked, handoffState)
  const handoffDisabled = reason !== null

  const handoffLabel =
    handoffState === 'preparing' ? 'Preparing…' : handoffState === 'ready' ? 'Handoff ready' : 'Handoff'

  return (
    <div className="flex items-center gap-3">
      {/* Active-agent indicator */}
      <span className="flex items-center gap-1.5 min-w-0">
        <StatusDot status={agent.status} size="sm" />
        <span className="text-xs font-medium truncate" style={{ color: 'var(--text)' }}>
          {agent.name}
        </span>
        <span className="text-[11px]" style={{ color: statusCfg.labelColor }}>
          {statusCfg.label}
        </span>
      </span>

      <ContextUsageIndicator value={agent.context_usage} compact />

      <div className="flex-1" />

      {isRunning && (
        <button
          type="button"
          onClick={onStop}
          disabled={isStopping}
          title="Terminate the in-progress run"
          className="transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 500,
            background: 'rgba(239,68,68,0.1)',
            color: 'var(--red)',
            cursor: isStopping ? 'default' : 'pointer',
          }}
        >
          <Icon name="stop" size={12} />
          {isStopping ? 'Stopping…' : 'Stop'}
        </button>
      )}

      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            ref={menuTriggerRef}
            type="button"
            aria-label="Conversation actions"
            className="transition-colors"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 'var(--radius-sm)',
              width: 24,
              height: 24,
              background: 'var(--surface-3)',
              color: 'var(--text-2)',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <Icon name="more_vert" size={16} />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            style={{
              minWidth: 220,
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              padding: 4,
              boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
              zIndex: 50,
            }}
          >
            <DropdownMenu.Item style={itemStyle} onSelect={() => onNewConversation()}>
              New conversation
            </DropdownMenu.Item>

            {conversations.length === 0 ? (
              <DropdownMenu.Item style={{ ...itemStyle, opacity: 0.5, cursor: 'not-allowed' }} disabled aria-disabled="true">
                No conversations yet
              </DropdownMenu.Item>
            ) : (
              conversations.map((conversation) => (
                <DropdownMenu.Item
                  key={conversation.id}
                  style={itemStyle}
                  onSelect={() => onSelectConversation(conversation.id)}
                >
                  <span className="flex items-center gap-1.5">
                    {conversation.id === currentConversationId && (
                      <Icon name="check" size={12} style={{ color: 'var(--blue)' }} />
                    )}
                    {conversation.id.slice(0, 20)}
                    {conversation.id.length > 20 ? '…' : ''}
                  </span>
                </DropdownMenu.Item>
              ))
            )}

            <DropdownMenu.Item
              style={{ ...itemStyle, ...(handoffDisabled ? { opacity: 0.5, cursor: 'not-allowed' } : {}) }}
              disabled={handoffDisabled}
              aria-disabled={handoffDisabled ? 'true' : undefined}
              onSelect={(event) => {
                if (handoffDisabled) {
                  event.preventDefault()
                  return
                }
                onHandoff()
              }}
            >
              <span>{handoffLabel}</span>
              {reason && (
                <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{reason}</span>
              )}
            </DropdownMenu.Item>

            <DropdownMenu.Item style={itemStyle} onSelect={() => onFoldAll()}>
              Fold all turns
            </DropdownMenu.Item>

            <DropdownMenu.Item style={itemStyle} onSelect={() => setDetailsOpen(true)}>
              Agent details
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog.Root open={detailsOpen} onOpenChange={setDetailsOpen}>
        <Dialog.Portal>
          <Dialog.Overlay style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 60 }} />
          <Dialog.Content
            aria-label={`${agent.name} details`}
            onCloseAutoFocus={(event) => {
              event.preventDefault()
              menuTriggerRef.current?.focus()
            }}
            style={{
              position: 'fixed',
              top: '10vh',
              left: '50%',
              transform: 'translateX(-50%)',
              width: 'min(520px, 92vw)',
              maxHeight: '78vh',
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              overflow: 'hidden',
              zIndex: 61,
            }}
          >
            <Dialog.Title style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
              {agent.name} details
            </Dialog.Title>
            <Dialog.Description className="sr-only">
              Status, sessions, configuration, and statistics for {agent.name}.
            </Dialog.Description>
            <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
              <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{agent.name}</span>
              <Dialog.Close asChild>
                <button
                  type="button"
                  aria-label="Close details"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}
                >
                  <Icon name="close" size={16} />
                </button>
              </Dialog.Close>
            </div>
            <AgentInfoTab agent={agent} />
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
