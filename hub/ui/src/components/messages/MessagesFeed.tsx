import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useMessages, useMessageHistory, Message } from '@/api/messages'
import { MessageCard } from './MessageCard'
import { ConversationGroup } from './ConversationGroup'
import { EmptyState } from '@/components/common/EmptyState'

type Mode = 'inbox' | 'history'

function convKey(msg: Message): string {
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

  const groupedMessages: Record<string, Message[]> = {}
  if (grouped && messages) {
    for (const msg of messages) {
      const key = convKey(msg)
      ;(groupedMessages[key] ??= []).push(msg)
    }
  }

  if (isLoading) {
    return <div className="p-6 m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading messages…</div>
  }

  return (
    <div className="flex flex-col gap-4 p-5">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Mode toggle — M3 segmented-style */}
        <div
          className="flex rounded-full overflow-hidden border"
          style={{ borderColor: 'var(--outline-variant)' }}
        >
          {(['inbox', 'history'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className="px-4 h-8 capitalize m3-label-medium transition-colors"
              style={{
                background: mode === m ? 'var(--p-cont)' : 'transparent',
                color:      mode === m ? 'var(--on-p-cont)' : 'var(--on-sv)',
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
              className={`m3-chip-filter${agentFilter === undefined ? ' active' : ''}`}
            >
              {agentFilter === undefined && <Icon name="check" size={14} />}
              All
            </button>
            {agents.map((agent) => (
              <button
                key={agent}
                onClick={() => setAgentFilter(agent)}
                className={`m3-chip-filter${agentFilter === agent ? ' active' : ''}`}
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
              className="m3-chip-filter flex items-center gap-1.5"
            >
              <Icon name={sort === 'asc' ? 'arrow_upward' : 'arrow_downward'} size={14} />
              {sort === 'asc' ? 'Oldest first' : 'Newest first'}
            </button>
            <button
              onClick={() => setGrouped(!grouped)}
              className={`m3-chip-filter${grouped ? ' active' : ''}`}
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
