import { MessageCard } from './MessageCard'

interface ConversationGroupProps {
  pairKey: string
  messages: Array<{
    id: string
    from: string
    to: string
    content: string
    subject?: string
    timestamp: string
    type: string
    read: boolean
    task_id?: string
  }>
}

export function ConversationGroup({ pairKey, messages }: ConversationGroupProps) {
  const [a, b] = pairKey.split(':')
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-3)' }}>
        <span style={{ color: 'var(--text)' }}>{a}</span>
        <span>↔</span>
        <span style={{ color: 'var(--text)' }}>{b}</span>
        <span
          className="ml-1 rounded-full px-2 py-0.5 text-xs font-normal normal-case"
          style={{ background: 'var(--surface-3)', color: 'var(--text-2)' }}
        >
          {messages.length} message{messages.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="space-y-2 pl-2" style={{ borderLeft: '2px solid var(--border)' }}>
        {messages.map((msg) => (
          <MessageCard key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  )
}
