import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useMessages, useMessageHistory } from '@/api/messages'
import { MessageCard } from './MessageCard'
import { ConversationGroup } from './ConversationGroup'
import { EmptyState } from '@/components/common/EmptyState'

type Mode = 'inbox' | 'history'

function convKey(msg: { from: string; to: string }): string {
  return [msg.from, msg.to].sort().join(':')
}

export function MessagesFeed() {
  const [mode,        setMode]        = useState<Mode>('inbox')
  const [agentFilter, setAgentFilter] = useState<string | undefined>(undefined)
  const [sort,        setSort]        = useState<'asc' | 'desc'>('asc')
  const [grouped,     setGrouped]     = useState(false)

  const { data: inboxMessages,   isLoading: inboxLoading }   = useMessages(agentFilter)
  const { data: historyMessages, isLoading: historyLoading } = useMessageHistory({ sort })

  const isLoading = mode === 'inbox' ? inboxLoading : historyLoading
  const messages  = mode === 'inbox' ? inboxMessages : historyMessages

  const { data: allMessages } = useMessageHistory({})
  const agents = [...new Set(allMessages?.flatMap((m) => [m.from, m.to]) ?? [])]

  const groupedMessages: Record<string, Array<{ id: string; from: string; to: string; content: string; subject?: string; timestamp: string; type: string; read: boolean; task_id?: string }>> = {}
  if (grouped && messages) {
    for (const msg of messages) {
      const key = convKey(msg)
      ;(groupedMessages[key] ??= []).push(msg)
    }
  }

  if (isLoading) {
    return <div className="p-6 text-sm" style={{ color: 'var(--text-3)' }}>Loading messages…</div>
  }

  const chipBase = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    height: '32px',
    borderRadius: '8px',
    padding: '0 12px',
    fontSize: '12px',
    fontWeight: 500,
    letterSpacing: '0.5px',
    border: '1px solid var(--border)',
    background: 'transparent',
    color: 'var(--text-3)',
    transition: 'background-color 0.15s, border-color 0.15s, color 0.15s',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  } as React.CSSProperties

  return (
    <div className="flex flex-col gap-4 p-5">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Mode toggle */}
        <div
          className="flex rounded-full overflow-hidden border"
          style={{ borderColor: 'var(--border)' }}
        >
          {(['inbox', 'history'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className="px-4 h-8 capitalize text-xs font-medium transition-colors"
              style={{
                background: mode === m ? 'var(--surface-3)' : 'transparent',
                color:      mode === m ? 'var(--text)' : 'var(--text-3)',
              }}
            >
              {m}
            </button>
          ))}
        </div>

        {/* Agent filter chips */}
        {mode === 'inbox' && (
          <>
            <button
              onClick={() => setAgentFilter(undefined)}
              style={{
                ...chipBase,
                background: agentFilter === undefined ? 'var(--surface-3)' : 'transparent',
                color: agentFilter === undefined ? 'var(--text)' : 'var(--text-3)',
                borderColor: agentFilter === undefined ? 'var(--border-hi)' : 'var(--border)',
              }}
            >
              {agentFilter === undefined && <Icon name="check" size={14} />}
              All
            </button>
            {agents.map((agent) => (
              <button
                key={agent}
                onClick={() => setAgentFilter(agent)}
                style={{
                  ...chipBase,
                  background: agentFilter === agent ? 'var(--surface-3)' : 'transparent',
                  color: agentFilter === agent ? 'var(--text)' : 'var(--text-3)',
                  borderColor: agentFilter === agent ? 'var(--border-hi)' : 'var(--border)',
                }}
              >
                {agentFilter === agent && <Icon name="check" size={14} />}
                {agent}
              </button>
            ))}
          </>
        )}

        {mode === 'history' && (
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => setSort(sort === 'asc' ? 'desc' : 'asc')}
              style={{ ...chipBase }}
            >
              <Icon name={sort === 'asc' ? 'arrow_upward' : 'arrow_downward'} size={14} />
              {sort === 'asc' ? 'Oldest first' : 'Newest first'}
            </button>
            <button
              onClick={() => setGrouped(!grouped)}
              style={{
                ...chipBase,
                background: grouped ? 'var(--surface-3)' : 'transparent',
                color: grouped ? 'var(--text)' : 'var(--text-3)',
                borderColor: grouped ? 'var(--border-hi)' : 'var(--border)',
              }}
            >
              {grouped && <Icon name="check" size={14} />}
              Group by conversation
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      {!messages || messages.length === 0 ? (
        <EmptyState
          icon="chat"
          title={mode === 'inbox' ? 'No messages' : 'No message history'}
          description="Messages between agents will appear here."
        />
      ) : mode === 'history' && grouped ? (
        <div className="space-y-6">
          {Object.entries(groupedMessages).map(([key, msgs]) => (
            <ConversationGroup key={key} pairKey={key} messages={msgs} />
          ))}
        </div>
      ) : (
        <div className="space-y-2.5">
          {messages.map((msg) => (
            <MessageCard key={msg.id} message={msg} />
          ))}
        </div>
      )}
    </div>
  )
}
