import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { useMessages } from '@/api/messages'
import { MessageCard } from './MessageCard'
import { EmptyState } from '@/components/common/EmptyState'

export function MessagesFeed() {
  const [agentFilter, setAgentFilter] = useState<string | undefined>(undefined)
  const { data: messages, isLoading } = useMessages(agentFilter)

  // Collect unique agents
  const { data: allMessages } = useMessages()
  const agents = [...new Set(allMessages?.flatMap((m) => [m.from, m.to]) ?? [])]

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading messages…</div>
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setAgentFilter(undefined)}
          className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
            agentFilter === undefined ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-accent'
          }`}
        >
          All
        </button>
        {agents.map((agent) => (
          <button
            key={agent}
            onClick={() => setAgentFilter(agent)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              agentFilter === agent ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-accent'
            }`}
          >
            {agent}
          </button>
        ))}
      </div>

      {messages?.length === 0 ? (
        <EmptyState icon={MessageSquare} title="No messages" description="Messages between agents will appear here." />
      ) : (
        <div className="space-y-3">
          {messages?.map((msg) => (
            <MessageCard key={msg.id} message={msg} />
          ))}
        </div>
      )}
    </div>
  )
}
