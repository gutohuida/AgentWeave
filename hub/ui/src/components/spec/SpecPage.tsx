import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { fetchWithAuth } from '@/api/client'
import { useSpec, useSpecEvents, useSpecList, type SpecDiagnostic, type SpecMissingEntry } from '@/api/spec'
import { useQueryClient } from '@tanstack/react-query'
import { useAgents } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'
import { SpecChatPane } from './SpecChatPane'
import { SpecDocumentPicker } from './SpecDocumentPicker'
import { SpecFrame, type SpecFrameHandle } from './SpecFrame'
import { SpecNavigator } from './SpecNavigator'
import { SpecWorkspace } from './SpecWorkspace'
import { buildInventory, resolveSelection } from './specNavigation'
import {
  DEFAULT_SPEC_PREFERENCES,
  loadSpecPreferences,
  saveSpecPreferences,
  type LibraryMode,
} from './specPreferences'
import type { TocAnchor } from './specBridge'

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

const REJECTION_TEXT: Record<string, string> = {
  external: 'That link points outside the specification and was not opened.',
  unsafe: 'That link is not a valid specification path and was not opened.',
  'not-html': 'That link is not a specification document and was not opened.',
  unknown: 'That document is not in the current specification inventory.',
}

export function SpecPage() {
  const { data: specList, isLoading: listLoading, refetch: refetchList } = useSpecList()
  // The Hub reports each missing document twice by design: structured in
  // `missing` and as a `missing_document` entry in `diagnostics`. Keep only
  // the `missing` representation so the banner count, details list, and
  // repair message never double-count or duplicate them.
  const diagnostics = (specList?.diagnostics ?? []).filter((d) => d.code !== 'missing_document')
  const missing = specList?.missing ?? []
  const hasDrift = diagnostics.length > 0 || missing.length > 0

  const inventory = useMemo(() => buildInventory(specList), [specList])
  const readablePaths = useMemo(
    () => new Set(inventory.nodes.filter((n) => !n.missing).map((n) => n.path)),
    [inventory]
  )

  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Selection survives refresh while its path stays readable; otherwise it
  // falls back through manifest home, spec/spec.html, then the first readable
  // current document (never an archive).
  useEffect(() => {
    if (inventory.nodes.length === 0) return
    const next = resolveSelection(inventory, selectedPath, specList?.home)
    if (next !== selectedPath) setSelectedPath(next)
  }, [inventory, selectedPath, specList?.home])

  const { data: specDoc, refetch: refetchSpec } = useSpec(selectedPath)

  // Auto-refresh list + open spec when a spec_updated SSE event arrives
  useSpecEvents()

  const { mode, apiKey } = useConfigStore()
  const { data: agents } = useAgents()
  const queryClient = useQueryClient()
  const [selectedAgent, setSelectedAgent] = useState<string>('')

  // Default agent: one named 'spec', else the first available agent.
  useEffect(() => {
    if (!agents || agents.length === 0) return
    if (selectedAgent && agents.some((a) => a.name === selectedAgent)) return
    const preferred = agents.find((a) => a.name === 'spec') ?? agents[0]
    setSelectedAgent(preferred.name)
  }, [agents, selectedAgent])

  const agent = agents?.find((a) => a.name === selectedAgent)

  // Messages resume the agent's last saved session by default. `startNewSession`
  // is a one-shot escape: it applies to the next message only, so the message
  // after it continues the session that was just created.
  const [startNewSession, setStartNewSession] = useState(false)
  useEffect(() => {
    setStartNewSession(false)
  }, [selectedAgent])

  // Presentation preferences only — never content, payloads, or credentials.
  const [preferences, setPreferences] = useState(DEFAULT_SPEC_PREFERENCES)
  useEffect(() => {
    setPreferences(loadSpecPreferences())
  }, [])
  const updatePreferences = useCallback((patch: Partial<typeof DEFAULT_SPEC_PREFERENCES>) => {
    setPreferences((prev) => {
      const next = { ...prev, ...patch }
      saveSpecPreferences(next)
      return next
    })
  }, [])

  const [outline, setOutline] = useState<TocAnchor[]>([])
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [pendingFragment, setPendingFragment] = useState<string | null>(null)
  const [navStatus, setNavStatus] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const frameRef = useRef<SpecFrameHandle>(null)
  // Captured before the dialog mounts, so focus can return to whatever the
  // user was on — the search button or wherever Ctrl+K was pressed.
  const searchOriginRef = useRef<HTMLElement | null>(null)
  const openPicker = useCallback(() => {
    searchOriginRef.current = document.activeElement as HTMLElement | null
    setPickerOpen(true)
  }, [])

  // A new document has its own outline and its own active section.
  useEffect(() => {
    setOutline([])
    setActiveSection(null)
  }, [selectedPath])

  const selectDocument = useCallback(
    (path: string) => {
      setSelectedPath(path)
      setPendingFragment(null)
      setNavStatus(null)
    },
    []
  )

  const handleNavigate = useCallback(
    (path: string, fragment: string | null) => {
      setNavStatus(null)
      if (path === selectedPath) {
        if (fragment) frameRef.current?.scrollToSection(fragment)
        return
      }
      setSelectedPath(path)
      // Consumed by SpecFrame once the new document reports its outline.
      setPendingFragment(fragment)
    },
    [selectedPath]
  )

  const handleRejected = useCallback((reason: string) => {
    setNavStatus(REJECTION_TEXT[reason] ?? REJECTION_TEXT.unknown)
  }, [])

  const handleOutline = useCallback((anchors: TocAnchor[]) => {
    setOutline(anchors)
    setPendingFragment(null)
  }, [])

  // Ctrl/Cmd+K opens document search from anywhere on the page.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        openPicker()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [openPicker])

  // Repair target: an idle agent named `spec` first, else the selected chat agent.
  const idleSpecAgent = agents?.find((a) => a.name === 'spec' && a.status !== 'running')
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

  const selectedNode = selectedPath ? inventory.byPath.get(selectedPath) : undefined

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg)' }}>
      {/* Header row */}
      <div
        className="flex items-center justify-between px-6 py-4 shrink-0"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="min-w-0">
          <h1 style={{ fontSize: 18, fontWeight: 600, color: 'var(--text)' }}>Spec</h1>
          <p
            className="truncate"
            style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}
          >
            {selectedNode ? selectedNode.path : 'Live view of the project specification.'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {selectedNode?.archived && (
            <span
              data-testid="spec-archived-marker"
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface-3)',
                color: 'var(--text-2)',
              }}
            >
              Archived{selectedNode.archiveDate ? ` · ${selectedNode.archiveDate}` : ''}
            </span>
          )}
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

      {/* An unresolved link must never block reading the current document. */}
      {navStatus && (
        <div
          role="status"
          aria-live="polite"
          data-testid="spec-nav-status"
          className="flex items-center gap-2 px-6 py-1.5 shrink-0 text-xs"
          style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--border)', color: 'var(--text-2)' }}
        >
          <Icon name="info" size={14} />
          <span className="flex-1">{navStatus}</span>
          <button
            type="button"
            onClick={() => setNavStatus(null)}
            aria-label="Dismiss navigation message"
            style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer' }}
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      )}

      <SpecWorkspace
        chatCollapsed={preferences.chatCollapsed}
        onChatCollapsedChange={(collapsed) => updatePreferences({ chatCollapsed: collapsed })}
        navigation={
          <SpecNavigator
            inventory={inventory}
            selectedPath={selectedPath}
            mode={preferences.libraryMode}
            onModeChange={(libraryMode: LibraryMode) => updatePreferences({ libraryMode })}
            onSelect={selectDocument}
            onOpenSearch={openPicker}
            outline={outline}
            activeSection={activeSection}
            onOutlineSelect={(id) => frameRef.current?.scrollToSection(id)}
          />
        }
        document={
          listLoading ? (
            <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>
              Loading...
            </div>
          ) : inventory.nodes.length === 0 ? (
            <EmptyState
              icon="article"
              title="No spec yet"
              description="Ask the spec agent below to create one."
            />
          ) : specDoc && selectedPath ? (
            <SpecFrame
              ref={frameRef}
              path={selectedPath}
              content={specDoc.content}
              mode={mode}
              readablePaths={readablePaths}
              pendingFragment={pendingFragment}
              onOutline={handleOutline}
              onActiveSection={setActiveSection}
              onNavigate={handleNavigate}
              onRejected={handleRejected}
            />
          ) : (
            <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>
              Loading spec...
            </div>
          )
        }
        chat={
          <SpecChatPane
            agents={agents}
            selectedAgent={selectedAgent}
            onSelectedAgentChange={setSelectedAgent}
            startNewSession={startNewSession}
            onStartNewSessionChange={setStartNewSession}
            apiKey={apiKey}
          />
        }
      />

      <SpecDocumentPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        inventory={inventory}
        restoreFocusTo={() => searchOriginRef.current}
        onSelect={(node) => {
          selectDocument(node.path)
          // Selecting an archived result switches the browser to History so
          // the surrounding context matches what was opened.
          if (node.archived) updatePreferences({ libraryMode: 'history' })
        }}
      />
    </div>
  )
}
