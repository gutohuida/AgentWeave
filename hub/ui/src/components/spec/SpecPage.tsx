import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchWithAuth } from '@/api/client'
import { useSpec, useSpecEvents, useSpecList, type SpecDiagnostic, type SpecMissingEntry } from '@/api/spec'
import { useQueryClient } from '@tanstack/react-query'
import { useAgentOutput, useAgentSessions, useAgents } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'

// Bounded, deterministic instruction for the spec-repair agent — built from
// the Hub's own computed drift set (never a client-side guess), capped so
// the message stays readable and finite regardless of how much drift exists.
const MAX_REPAIR_ITEMS = 50

function buildRepairMessage(diagnostics: SpecDiagnostic[], missing: SpecMissingEntry[]): string {
  const lines: string[] = ['Run aw-spec-reindex to repair spec/index.json. Detected drift:']
  const capped = diagnostics.slice(0, MAX_REPAIR_ITEMS)
  for (const d of capped) {
    const parts = [d.code]
    if (d.path) parts.push(d.path)
    if (d.field) parts.push(`field=${d.field}`)
    if (d.expected != null) parts.push(`expected=${d.expected}`)
    if (d.actual != null) parts.push(`actual=${d.actual}`)
    lines.push(`- ${parts.join(' ')}`)
  }
  if (diagnostics.length > capped.length) {
    lines.push(`…and ${diagnostics.length - capped.length} more diagnostic(s)`)
  }
  if (missing.length > 0) {
    lines.push('Missing manifest entries (declared in spec/index.json, no file found):')
    for (const m of missing.slice(0, MAX_REPAIR_ITEMS)) {
      lines.push(`- ${m.path}`)
    }
    if (missing.length > MAX_REPAIR_ITEMS) {
      lines.push(`…and ${missing.length - MAX_REPAIR_ITEMS} more missing entr(y/ies)`)
    }
  }
  return lines.join('\n')
}

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
  // The Hub reports each missing document twice by design: structured in
  // `missing` and as a `missing_document` entry in `diagnostics`. Keep only
  // the `missing` representation so the banner count, details list, and
  // repair message never double-count or duplicate them.
  const diagnostics = (specList?.diagnostics ?? []).filter((d) => d.code !== 'missing_document')
  const missing = specList?.missing ?? []
  const hasDrift = diagnostics.length > 0 || missing.length > 0
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Default selection, preserved while still available: the manifest's
  // declared home, else spec/spec.html, else the first entry.
  useEffect(() => {
    if (specs.length === 0) return
    if (selectedPath && specs.some((s) => s.path === selectedPath)) return
    const home = specList?.home
    const preferred =
      (home ? specs.find((s) => s.path === home) : undefined) ??
      specs.find((s) => s.path === 'spec/spec.html') ??
      specs[0]
    setSelectedPath(preferred.path)
  }, [specs, selectedPath, specList?.home])

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

  // Messages resume the agent's last saved session by default. `startNewSession`
  // is a one-shot escape: it applies to the next message only, so the message
  // after it continues the session that was just created.
  const [startNewSession, setStartNewSession] = useState(false)
  useEffect(() => {
    setStartNewSession(false)
  }, [selectedAgent])

  // Only used to tell the user whether the next message continues something.
  // The session id itself is never sent — the watchdog resolves it.
  const { data: sessionData } = useAgentSessions(selectedAgent || null)
  const hasSavedSession = (sessionData?.sessions?.length ?? 0) > 0

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

  // Repair target: an idle spec-role agent first, else the currently
  // selected chat agent (matching the existing session-mode control).
  const idleSpecAgent = agents?.find((a) => a.dev_roles?.includes('spec') && a.status !== 'running')
  const repairTarget = idleSpecAgent ?? agent
  const repairTargetBusy = repairTarget?.status === 'running'
  const [isRepairing, setIsRepairing] = useState(false)
  const [repairError, setRepairError] = useState<string | null>(null)
  const [showDriftDetails, setShowDriftDetails] = useState(false)
  const repairDisabled = !hasDrift || !repairTarget || repairTargetBusy || isRepairing

  const handleRepair = async () => {
    if (repairDisabled || !repairTarget || !apiKey) return
    setIsRepairing(true)
    setRepairError(null)
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 15000)
    try {
      const res = await fetchWithAuth('/api/v1/agent/trigger', {
        method: 'POST',
        body: JSON.stringify({
          agent: repairTarget.name,
          message: buildRepairMessage(diagnostics, missing),
          session_mode: startNewSession ? 'new' : 'resume',
        }),
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setStartNewSession(false)
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
      await queryClient.refetchQueries({ queryKey: ['agents'], type: 'active' })
    } catch (err) {
      console.error('Failed to trigger spec repair:', err)
      setRepairError(
        err instanceof DOMException && err.name === 'AbortError'
          ? 'Request timed out; check the watchdog and try again'
          : 'Failed to send repair request'
      )
    } finally {
      window.clearTimeout(timeoutId)
      setIsRepairing(false)
    }
  }

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
        // `resume` with no session_id makes the trigger endpoint emit no
        // session tag, so the watchdog falls back to the agent's last saved
        // session (or starts a new one if there is none). Resolving the id
        // here would duplicate that rule in a second place.
        body: JSON.stringify({
          agent: selectedAgent,
          message: message.trim(),
          session_mode: startNewSession ? 'new' : 'resume',
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
      // Consumed — the next message resumes the session this one creates.
      setStartNewSession(false)
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

      {/* Drift summary — only rendered when the Hub reports manifest drift */}
      {hasDrift && (
        <div
          className="flex flex-col gap-1.5 px-6 py-2 shrink-0 text-xs"
          style={{
            background: 'rgba(234,179,8,0.08)',
            borderBottom: '1px solid var(--border)',
            color: 'var(--text-2)',
          }}
        >
          <div className="flex items-center justify-between gap-3">
            <button
              onClick={() => setShowDriftDetails((v) => !v)}
              className="flex items-center gap-1.5"
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
            >
              <Icon name="warning" size={14} />
              <span>
                {diagnostics.length + missing.length} spec manifest drift item
                {diagnostics.length + missing.length === 1 ? '' : 's'}
              </span>
              <Icon name={showDriftDetails ? 'expand_less' : 'expand_more'} size={14} />
            </button>
            <div className="flex items-center gap-2">
              {repairError && <span style={{ color: 'var(--red)' }}>{repairError}</span>}
              <span style={{ color: 'var(--text-3)' }}>
                {!repairTarget
                  ? 'No agent available to repair'
                  : repairTargetBusy
                    ? `${repairTarget.name} is busy`
                    : `Target: ${repairTarget.name}`}
              </span>
              <button
                onClick={handleRepair}
                disabled={repairDisabled}
                className="px-2 py-1 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text)',
                  cursor: repairDisabled ? 'not-allowed' : 'pointer',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {isRepairing ? 'Sending…' : 'Repair manifest'}
              </button>
            </div>
          </div>
          {showDriftDetails && (
            <ul className="flex flex-col gap-0.5 pl-5" style={{ color: 'var(--text-3)' }}>
              {diagnostics.map((d, i) => (
                <li key={`d-${i}`}>
                  {d.code}
                  {d.path ? ` — ${d.path}` : ''}
                  {d.field ? ` (${d.field}: ${d.expected} → ${d.actual})` : ''}
                </li>
              ))}
              {missing.map((m) => (
                <li key={`m-${m.path}`}>missing_document — {m.path}</li>
              ))}
            </ul>
          )}
        </div>
      )}

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
            <button
              onClick={() => setStartNewSession((v) => !v)}
              disabled={!selectedAgent}
              title={
                startNewSession
                  ? 'Next message starts a new session — click to keep the current one'
                  : 'Start a new session with the next message'
              }
              aria-pressed={startNewSession}
              aria-label="Start a new session"
              className="px-1.5 py-1 rounded-md transition-colors disabled:opacity-50"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: startNewSession ? 'var(--blue)' : 'var(--surface)',
                border: '1px solid var(--border)',
                color: startNewSession ? '#fff' : 'var(--text-3)',
                cursor: selectedAgent ? 'pointer' : 'not-allowed',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <Icon name="restart_alt" size={14} />
            </button>
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
            {selectedAgent && (
              <span
                data-testid="session-continuity"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 11,
                  color: startNewSession ? 'var(--blue)' : 'var(--text-3)',
                }}
              >
                <Icon
                  name={startNewSession ? 'restart_alt' : hasSavedSession ? 'link' : 'add'}
                  size={12}
                />
                {startNewSession
                  ? 'Next message starts a new session'
                  : hasSavedSession
                    ? `Continuing ${selectedAgent}'s most recent session`
                    : 'No session yet — the next message starts one'}
              </span>
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
