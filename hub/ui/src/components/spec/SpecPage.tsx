import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchWithAuth } from '@/api/client'
import { useSpec, useSpecEvents, useSpecList } from '@/api/spec'
import { useQueryClient } from '@tanstack/react-query'
import { useAgentOutput, useAgents } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'

// Stamps the Hub's active light/dark mode onto the spec document's <html> tag so
// spec.html's `:root[data-theme="..."]` CSS layer (see html-spec-conventions.md)
// matches the dashboard instead of only following the OS preference.
function withHubTheme(html: string, mode: 'light' | 'dark'): string {
  return /<html[^>]*\sdata-theme=/i.test(html)
    ? html.replace(/data-theme="[^"]*"/i, `data-theme="${mode}"`)
    : html.replace(/<html([^>]*)>/i, `<html$1 data-theme="${mode}">`)
}

// The Hub renders spec.html in a sandboxed iframe (sandbox="allow-scripts", no
// allow-same-origin -> opaque origin). Native `#hash` navigation from an in-page
// anchor click can blank that frame out until the user manually reloads it.
// Inject a click interceptor that scrolls manually instead, so this works even
// for specs generated before this fix landed (see html-spec-conventions.md).
const ANCHOR_SCROLL_FIX_MARKER = 'data-aw-anchor-scroll-fix'
const ANCHOR_SCROLL_FIX_SCRIPT = `<script ${ANCHOR_SCROLL_FIX_MARKER}>
document.addEventListener('click', function (e) {
  var a = e.target.closest && e.target.closest('a[href^="#"]');
  if (!a) return;
  var id = a.getAttribute('href').slice(1);
  var target = id ? document.getElementById(id) : null;
  e.preventDefault();
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
</script>`

function withAnchorScrollFix(html: string): string {
  if (html.includes(ANCHOR_SCROLL_FIX_MARKER)) return html
  return /<\/body>/i.test(html)
    ? html.replace(/<\/body>/i, `${ANCHOR_SCROLL_FIX_SCRIPT}</body>`)
    : html + ANCHOR_SCROLL_FIX_SCRIPT
}

export function SpecPage() {
  const { data: specList, isLoading: listLoading, refetch: refetchList } = useSpecList()
  const specs = specList?.specs ?? []
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Default selection: spec/spec.html if present, else the first entry
  useEffect(() => {
    if (specs.length === 0) return
    if (!selectedPath || !specs.some((s) => s.path === selectedPath)) {
      const preferred = specs.find((s) => s.path === 'spec/spec.html') ?? specs[0]
      setSelectedPath(preferred.path)
    }
  }, [specs, selectedPath])

  const { data: specDoc, refetch: refetchSpec } = useSpec(selectedPath)

  // Auto-refresh list + open spec when a spec_updated SSE event arrives
  useSpecEvents()

  const { mode, apiKey } = useConfigStore()
  const { data: agents } = useAgents()
  const queryClient = useQueryClient()
  const [selectedAgent, setSelectedAgent] = useState<string>('')

  // Default agent: first with a 'spec' dev role, else one named 'spec', else first
  useEffect(() => {
    if (!agents || agents.length === 0) return
    if (selectedAgent && agents.some((a) => a.name === selectedAgent)) return
    const preferred =
      agents.find((a) => a.dev_roles?.includes('spec')) ??
      agents.find((a) => a.name === 'spec') ??
      agents[0]
    setSelectedAgent(preferred.name)
  }, [agents, selectedAgent])

  const agent = agents?.find((a) => a.name === selectedAgent)
  const isRunning = agent?.status === 'running'

  const { lines } = useAgentOutput(selectedAgent || null)
  const filteredLines = lines.filter(
    (line) =>
      !line.content.startsWith('[watchdog]') &&
      !line.content.startsWith('[stderr]') &&
      !line.content.startsWith('[session:') &&
      !line.content.startsWith('[done] cost:')
  )

  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [filteredLines.length])

  const [message, setMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [triggerState, setTriggerState] = useState<'idle' | 'queued' | 'running'>('idle')
  const [sendError, setSendError] = useState<string | null>(null)

  const handleRefresh = () => {
    refetchList()
    refetchSpec()
  }

  const handleSend = async () => {
    if (!message.trim() || !apiKey || !selectedAgent) return
    setIsSending(true)
    setSendError(null)
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 15000)
    try {
      // Use the configured Hub URL. A relative URL targets the Vite dev
      // server when the UI runs on port 5173, causing the request to hang.
      const res = await fetchWithAuth('/api/v1/agent/trigger', {
        method: 'POST',
        body: JSON.stringify({
          agent: selectedAgent,
          message: message.trim(),
          session_mode: 'new',
        }),
        signal: controller.signal,
      })
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }
      // The trigger response confirms queueing, but the status/output stream
      // may arrive later. Refresh immediately so the running state is not
      // dependent on an agent_heartbeat SSE event.
      setTriggerState('queued')
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
      await queryClient.refetchQueries({ queryKey: ['agents'], type: 'active' })
      setMessage('')
    } catch (err) {
      console.error('Failed to send message:', err)
      setSendError(err instanceof DOMException && err.name === 'AbortError'
        ? 'Request timed out; check the watchdog and try again'
        : 'Failed to send message')
    } finally {
      window.clearTimeout(timeoutId)
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  useEffect(() => {
    if (triggerState === 'queued' && isRunning) setTriggerState('running')
    if (triggerState === 'running' && !isRunning) setTriggerState('idle')
  }, [triggerState, isRunning])

  const inputDisabled = !selectedAgent || isRunning || isSending || triggerState !== 'idle'

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg)' }}>
      {/* Header row */}
      <div
        className="flex items-center justify-between px-6 py-4 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>Spec</h1>
          <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
            Live view of the project specification.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={selectedPath ?? ''}
            onChange={(e) => setSelectedPath(e.target.value || null)}
            disabled={specs.length === 0}
            className="px-2 py-1.5 rounded-md text-xs border"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              color: 'var(--text-2)',
              outline: 'none',
              borderRadius: 'var(--radius)',
            }}
          >
            {specs.length === 0 && <option value="">No specs</option>}
            {specs.map((s) => (
              <option key={s.path} value={s.path}>
                {s.path}
              </option>
            ))}
          </select>
          <button
            onClick={handleRefresh}
            title="Refresh spec"
            className="px-2 py-1.5 rounded-md transition-colors"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              color: 'var(--text-2)',
              cursor: 'pointer',
              borderRadius: 'var(--radius)',
            }}
          >
            <Icon name="refresh" size={16} />
          </button>
        </div>
      </div>

      {/* Body: spec viewer + agent chat */}
      <div className="flex flex-row flex-1 min-h-0">
        {/* Main pane: rendered spec HTML */}
        <div className="flex-1 min-w-0 overflow-hidden" style={{ background: 'var(--bg)' }}>
          {listLoading ? (
            <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>
              Loading...
            </div>
          ) : specs.length === 0 ? (
            <EmptyState
              icon="article"
              title="No spec yet"
              description="Ask the spec agent below to create one."
            />
          ) : specDoc ? (
            <iframe
              title={specDoc.path}
              sandbox="allow-scripts"
              srcDoc={withAnchorScrollFix(withHubTheme(specDoc.content, mode))}
              className="w-full h-full border-0"
              style={{ background: 'var(--bg)' }}
            />
          ) : (
            <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>
              Loading spec...
            </div>
          )}
        </div>

        {/* Right pane: embedded agent chat */}
        <div
          className="flex flex-col shrink-0 min-h-0"
          style={{ width: 380, borderLeft: '1px solid var(--border)', background: 'var(--bg)' }}
        >
          {/* Agent selector header */}
          <div
            className="flex items-center gap-2 px-3 py-2.5 shrink-0 border-b"
            style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
          >
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              disabled={!agents || agents.length === 0}
              className="flex-1 px-2 py-1 rounded-lg text-xs border"
              style={{
                background: 'var(--surface)',
                borderColor: 'var(--border)',
                color: 'var(--text-3)',
                outline: 'none',
              }}
            >
              {(!agents || agents.length === 0) && <option value="">No agents</option>}
              {agents?.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
            {agent && (
              <span
                className="flex items-center gap-1.5"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  borderRadius: 'var(--radius-sm)',
                  padding: '2px 8px',
                  fontSize: 11,
                  fontWeight: 500,
                  background: isRunning ? 'rgba(34,197,94,0.1)' : 'var(--surface-3)',
                  color: isRunning ? 'var(--green)' : 'var(--text-3)',
                }}
              >
                {isRunning && (
                  <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                )}
                {agent.status}
              </span>
            )}
          </div>

          {/* Messages area */}
          <div
            className="flex-1 overflow-y-auto p-3 space-y-0.5"
            style={{ background: 'var(--bg)' }}
          >
            {filteredLines.length === 0 ? (
              <p
                className="font-mono text-xs italic"
                style={{ color: 'var(--text-3)', fontFamily: "'JetBrains Mono', monospace" }}
              >
                Waiting for output…
              </p>
            ) : (
              filteredLines.map((line, i) => (
                <div
                  key={line.id ?? i}
                  className="font-mono text-xs leading-5 whitespace-pre-wrap break-all"
                  style={{ color: 'var(--text)', fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {line.content}
                </div>
              ))
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input footer */}
          <div
            className="shrink-0 border-t px-3 py-2 flex flex-col gap-2"
            style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
          >
            {sendError && (
              <span style={{ fontSize: 11, color: 'var(--red)' }}>{sendError}</span>
            )}
            <div className="flex gap-2">
              {triggerState !== 'idle' && (
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
                  {triggerState === 'queued' ? 'Message queued…' : `${selectedAgent} is responding…`}
                </span>
              )}
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  !selectedAgent
                    ? 'Select an agent…'
                    : isRunning
                      ? `${selectedAgent} is responding…`
                      : `Message ${selectedAgent}…`
                }
                rows={1}
                disabled={inputDisabled}
                className="flex-1 px-3 py-2 rounded-lg text-xs resize-none border disabled:opacity-50"
                style={{
                  background: 'var(--surface)',
                  borderColor: 'var(--border)',
                  color: 'var(--text-3)',
                  minHeight: '36px',
                  maxHeight: '96px',
                  outline: 'none',
                  fontFamily: "'JetBrains Mono', monospace",
                }}
                onInput={(e) => {
                  const t = e.target as HTMLTextAreaElement
                  t.style.height = 'auto'
                  t.style.height = `${Math.min(t.scrollHeight, 96)}px`
                }}
              />
              <button
                onClick={handleSend}
                disabled={!message.trim() || inputDisabled}
                className="px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  background: message.trim() && !inputDisabled ? 'var(--blue)' : 'var(--surface)',
                  color: message.trim() && !inputDisabled ? '#fff' : 'var(--text-3)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <Icon name="send" size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
