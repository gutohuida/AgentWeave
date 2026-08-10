import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { useSpec, useSpecEvents, useSpecList } from '@/api/spec'
import { useAgents } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'
import { SpecChat } from './SpecChat'
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

/* The "Repair manifest" button that used to live here is gone, and nothing replaces it yet.
 *
 * It composed `"Run aw-spec-reindex to repair spec/index.json"` and sent it to "an idle agent
 * named `spec` first, else the selected chat agent" — instructing a skill nothing installs, at
 * an agent identified by a hardcoded name convention, through a second bespoke trigger path.
 *
 * Reimplementing it deterministically here would mean writing a manifest repairer before the
 * manifest format and parser it repairs against are defined, so it goes to B2 as code. The
 * drift it responded to cannot occur meanwhile: nothing produces specification documents today.
 * The drift *report* below stays — a condition worth showing is not the same as a button.
 */

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

  const { mode } = useConfigStore()
  const { data: agents } = useAgents()
  const [selectedAgent, setSelectedAgent] = useState<string>('')

  // Default agent: one named 'spec', else the first available agent.
  useEffect(() => {
    if (!agents || agents.length === 0) return
    if (selectedAgent && agents.some((a) => a.name === selectedAgent)) return
    const preferred = agents.find((a) => a.name === 'spec') ?? agents[0]
    setSelectedAgent(preferred.name)
  }, [agents, selectedAgent])

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

  const [showDriftDetails, setShowDriftDetails] = useState(false)

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
          <Button variant="outline" size="icon-sm" onClick={handleRefresh} title="Refresh spec" aria-label="Refresh spec">
            <Icon name="refresh" size={16} />
          </Button>
        </div>
      </div>

      {/* Drift summary — only rendered when the Hub reports manifest drift */}
      {hasDrift && (
        <div
          className="flex flex-col gap-1.5 px-6 py-2 shrink-0 text-xs"
          style={{
            background: 'color-mix(in srgb, var(--amber) 8%, transparent)',
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
          <Button variant="ghost" size="icon-xs" onClick={() => setNavStatus(null)} aria-label="Dismiss navigation message">
            <Icon name="close" size={14} />
          </Button>
        </div>
      )}

      <SpecWorkspace
        chatCollapsed={preferences.chatCollapsed}
        onChatCollapsedChange={(collapsed) => updatePreferences({ chatCollapsed: collapsed })}
        navWidth={preferences.navWidth}
        chatWidth={preferences.chatWidth}
        onNavWidthChange={(navWidth) => updatePreferences({ navWidth })}
        onChatWidthChange={(chatWidth) => updatePreferences({ chatWidth })}
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
          <SpecChat
            agents={agents}
            selectedAgent={selectedAgent}
            onSelectedAgentChange={setSelectedAgent}
            documentPath={selectedPath}
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
