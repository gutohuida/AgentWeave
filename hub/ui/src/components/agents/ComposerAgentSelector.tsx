import { useEffect, useRef, useState } from 'react'
import type { AgentLaunchability, AgentSummary } from '@/api/agents'

interface ComposerAgentSelectorProps {
  agents: AgentSummary[]
  launchability: Record<string, AgentLaunchability>
  selectedAgent: string
  onSelect: (agent: string) => void
}

function statusLabel(state: AgentLaunchability | undefined): string {
  if (state?.runnable) return 'Runnable'
  if (state && !state.present) return 'Not present'
  if (state && !state.authorized) return 'Not authorized'
  return 'Unavailable'
}

export function ComposerAgentSelector({
  agents,
  launchability,
  selectedAgent,
  onSelect,
}: ComposerAgentSelectorProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const filtered = agents.filter((agent) =>
    agent.name.toLowerCase().includes(query.trim().toLowerCase()),
  )

  useEffect(() => {
    if (!open) return
    searchRef.current?.focus()
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label={`Target agent: ${selectedAgent}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => {
          setQuery('')
          setOpen((value) => !value)
        }}
        className="h-8 rounded border bg-[var(--surface)] px-2 text-xs hover:bg-[var(--accent)]"
        style={{
          borderColor: 'var(--border)',
          color: 'var(--text-2)',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {selectedAgent} ▾
      </button>

      {open && (
        <div
          className="absolute left-0 bottom-full mb-1 w-72 p-2 rounded border z-50"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              setOpen(false)
            }
          }}
        >
          <input
            ref={searchRef}
            type="search"
            aria-label="Search agents"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="w-full px-2 py-1.5 mb-2 rounded border text-xs"
            style={{
              background: 'var(--surface-2)',
              borderColor: 'var(--border)',
              color: 'var(--text)',
            }}
          />
          <div role="listbox" aria-label="Configured agents" className="max-h-56 overflow-y-auto">
            {filtered.map((agent) => {
              const state = launchability[agent.name]
              const label = statusLabel(state)
              return (
                <button
                  key={agent.name}
                  type="button"
                  role="option"
                  aria-selected={agent.name === selectedAgent}
                  aria-label={`${agent.name} — ${label}`}
                  onClick={() => {
                    onSelect(agent.name)
                    setOpen(false)
                  }}
                  data-active={agent.name === selectedAgent ? 'true' : 'false'}
                  className="row-item w-full items-start justify-between gap-3 text-left"
                  style={{ color: 'var(--text)' }}
                >
                  <span className="text-xs font-medium">{agent.name}</span>
                  <span className="text-[10px] text-right" style={{ color: state?.runnable ? 'var(--green)' : 'var(--text-3)' }}>
                    <span>{label}</span>
                    {state?.reason && <span className="block">{state.reason}</span>}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
