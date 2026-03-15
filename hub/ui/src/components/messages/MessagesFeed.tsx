import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { useMessages, useMessageHistory, Message } from '@/api/messages'
import { MessageCard } from './MessageCard'
import { ConversationGroup } from './ConversationGroup'
import { EmptyState } from '@/components/common/EmptyState'

type Mode = 'inbox' | 'history'

function convKey(msg: Message): string {
  return [msg.from, msg.to].sort().join(':')
}

export function MessagesFeed() {
  const [mode, setMode] = useState<Mode>('inbox')
  const [agentFilter, setAgentFilter] = useState<string | undefined>(undefined)
  const [sort, setSort] = useState<'asc' | 'desc'>('asc')
  const [grouped, setGrouped] = useState(false)

  const { data: inboxMessages, isLoading: inboxLoading } = useMessages(agentFilter)
  const { data: historyMessages, isLoading: historyLoading } = useMessageHistory({ sort })

  const isLoading = mode === 'inbox' ? inboxLoading : historyLoading
  const messages = mode === 'inbox' ? inboxMessages : historyMessages

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
    return <div className="p-6 text-sm text-white/40">Loading messages…</div>
  }

  return (
    <div className="flex flex-col gap-4 p-5">
      {/* Mode toggle + filters */}
      <div className="flex items-center gap-2.5 flex-wrap">
        <div className="flex rounded-xl overflow-hidden text-sm" style={{ border: '1px solid rgba(255,255,255,0.10)' }}>
          {(['inbox', 'history'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 capitalize transition-colors text-xs font-medium ${
                mode === m
                  ? 'bg-primary/20 text-primary'
                  : 'text-white/40 hover:text-white/70 hover:bg-white/[0.05]'
              }`}
            >
              {m}
            </button>
          ))}
        </div>

        {mode === 'inbox' && (
          <>
            <button
              onClick={() => setAgentFilter(undefined)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                agentFilter === undefined
                  ? 'bg-primary/20 text-primary ring-1 ring-primary/30'
                  : 'bg-white/[0.05] text-white/40 hover:text-white/70'
              }`}
            >
              All
            </button>
            {agents.map((agent) => (
              <button
                key={agent}
                onClick={() => setAgentFilter(agent)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  agentFilter === agent
                    ? 'bg-primary/20 text-primary ring-1 ring-primary/30'
                    : 'bg-white/[0.05] text-white/40 hover:text-white/70'
                }`}
              >
                {agent}
              </button>
            ))}
          </>
        )}

        {mode === 'history' && (
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => setSort(sort === 'asc' ? 'desc' : 'asc')}
              className="rounded-full px-3 py-1 text-xs font-medium bg-white/[0.05] text-white/40 hover:text-white/70 transition-colors"
            >
              {sort === 'asc' ? 'Oldest first' : 'Newest first'}
            </button>
            <button
              onClick={() => setGrouped(!grouped)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                grouped
                  ? 'bg-primary/20 text-primary ring-1 ring-primary/30'
                  : 'bg-white/[0.05] text-white/40 hover:text-white/70'
              }`}
            >
              Group by conversation
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      {!messages || messages.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
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
