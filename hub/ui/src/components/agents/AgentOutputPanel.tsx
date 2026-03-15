import { useEffect, useRef, useState } from 'react'
import { AgentSummary, useAgentOutput } from '@/api/agents'

interface AgentOutputPanelProps {
  agent: AgentSummary
}

export function AgentOutputPanel({ agent }: AgentOutputPanelProps) {
  const { lines } = useAgentOutput(agent.name)
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoscroll, setAutoscroll] = useState(true)

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (autoscroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, autoscroll])

  // Detect manual scroll up to pause autoscroll
  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoscroll(atBottom)
  }

  // Latest session ID from the most recent line that has one
  const sessionId = [...lines].reverse().find((l) => l.session_id)?.session_id

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-green-400 font-mono text-xs rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-900 shrink-0">
        <span className="text-zinc-200 font-semibold">{agent.name}</span>
        {sessionId && (
          <span className="px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 text-[10px]">
            session: {sessionId.slice(0, 12)}…
          </span>
        )}
        <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${
          agent.status === 'running'
            ? 'bg-green-900 text-green-300'
            : 'bg-zinc-700 text-zinc-400'
        }`}>
          {agent.status}
        </span>
        <button
          onClick={() => {
            setAutoscroll((v) => {
              if (!v && bottomRef.current) {
                bottomRef.current.scrollIntoView({ behavior: 'smooth' })
              }
              return !v
            })
          }}
          className="ml-auto text-[10px] px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {autoscroll ? 'Pause scroll' : 'Resume scroll'}
        </button>
      </div>

      {/* Output body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 space-y-0.5"
      >
        {lines.length === 0 ? (
          <p className="text-zinc-600 italic">Waiting for output…</p>
        ) : (
          lines.map((line, i) => (
            <div key={line.id ?? i} className="whitespace-pre-wrap break-all leading-5">
              {line.content}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
