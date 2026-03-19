import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useCopy } from '@/hooks/useCopy'
import { AgentSummary, useAgentOutput } from '@/api/agents'

interface AgentOutputPanelProps {
  agent: AgentSummary
}

export function AgentOutputPanel({ agent }: AgentOutputPanelProps) {
  const { lines, isLoading } = useAgentOutput(agent.name)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoscroll, setAutoscroll] = useState(true)
  const { copied, copy } = useCopy(2000)

  useEffect(() => {
    if (autoscroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, autoscroll])

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoscroll(atBottom)
  }

  const sessionId = [...lines].reverse().find((l) => l.session_id)?.session_id
  const isRunning = agent.status === 'running'

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--background)' }}>
      {/* Header bar */}
      <div
        className="flex items-center gap-2 px-4 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
      >
        <span className="m3-title-small" style={{ color: 'var(--foreground)' }}>{agent.name}</span>

        {/* Session ID chip */}
        {sessionId && (
          <button
            onClick={() => copy(sessionId)}
            title="Click to copy full session ID"
            className="m3-chip m3-label-small flex items-center gap-1 transition-colors cursor-pointer"
            style={copied
              ? { background: 'var(--p-cont)', color: 'var(--on-p-cont)' }
              : { background: 'var(--s-cont)', color: 'var(--on-s-cont)' }
            }
          >
            <Icon name={copied ? 'check' : 'content_copy'} size={12} />
            {copied ? 'copied' : `session: ${sessionId.slice(0, 12)}…`}
          </button>
        )}

        {/* Status chip */}
        <span
          className="m3-chip m3-label-small flex items-center gap-1.5"
          style={isRunning
            ? { background: 'var(--p-cont)', color: 'var(--on-p-cont)' }
            : { background: 'var(--surface-highest)', color: 'var(--on-sv)' }
          }
        >
          {isRunning && (
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          )}
          {agent.status}
        </span>

        {/* Autoscroll toggle */}
        <button
          onClick={() => {
            setAutoscroll((v) => {
              if (!v && bottomRef.current) {
                bottomRef.current.scrollIntoView({ behavior: 'smooth' })
              }
              return !v
            })
          }}
          className="ml-auto m3-chip m3-label-small transition-colors"
          style={{ background: 'var(--s-cont)', color: 'var(--on-s-cont)', cursor: 'pointer' }}
        >
          {autoscroll ? 'Pause scroll' : 'Resume scroll'}
        </button>
      </div>

      {/* Output body — darkest surface for terminal feel */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-0.5"
        style={{ background: 'var(--surface-lowest)' }}
      >
        {isLoading ? (
          <p className="font-mono m3-body-small italic" style={{ color: 'var(--on-sv)' }}>Loading output…</p>
        ) : lines.length === 0 ? (
          <p className="font-mono m3-body-small italic" style={{ color: 'var(--on-sv)' }}>Waiting for output…</p>
        ) : (
          lines.map((line, i) => (
            <div
              key={line.id ?? i}
              className="font-mono m3-body-small leading-5 whitespace-pre-wrap break-all"
              style={{ color: 'var(--foreground)' }}
            >
              {line.content}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
