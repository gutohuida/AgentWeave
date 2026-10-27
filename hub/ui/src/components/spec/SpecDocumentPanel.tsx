import { SpecDeletedNote } from './SpecDeletedNote'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import { SpecApprovalReport } from './SpecApprovalReport'
import { SpecAmendmentsPanel } from './SpecAmendmentsPanel'
import { SpecCoverageBar } from './SpecCoverageBar'
import { SpecDriftPanel } from './SpecDriftPanel'
import { SpecVaultWarnings } from './SpecVaultWarnings'
import { SpecRetiredRequirements } from './SpecRetiredRequirements'
import { SpecPlaceUnder } from './SpecPlaceUnder'
import { SpecDocumentHeader } from './SpecDocumentHeader'
import { SpecHealthLine, type HealthFactKey } from './SpecHealthLine'
import { SpecPhaseHeader } from './SpecPhaseBar'
import { useSpecPhaseControls } from './useSpecPhaseControls'
import { Button } from '@/components/ui/button'
import {
  useDetectDrift,
  useSpec,
  useSpecCoverage,
  useSpecDocuments,
  useSpecDrift,
  type SpecApprovalOutcome,
  type SpecDiagnostic,
  type SpecListResponse,
} from '@/api/spec'
import { useCheckVaultWarnings, useVaultChecked, useVaultWarnings } from '@/api/vault'
import { useDocumentTasks } from '@/api/tasks'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { SpecFrame, type SpecFrameHandle } from './SpecFrame'
import type { SpecInventory } from './specNavigation'
import type { TocAnchor } from './specBridge'
import type { LoopSummary } from '@/api/loops'
import '@/styles/spec-header.css'
import { LoadingThread } from '@/components/common/LoadingThread'

const REJECTION_TEXT: Record<string, string> = {
  external: 'That link points outside the specification and was not opened.',
  unsafe: 'That link is not a valid specification path and was not opened.',
  'not-document': 'That link is not a specification document and was not opened.',
  unknown: 'That document is not in the current specification inventory.',
}

const DETAIL_TITLE: Record<HealthFactKey, string> = {
  requirements: 'Requirements',
  drift: 'Drift',
  vault: 'Vault',
  tasks: 'Tasks',
  index: 'Spec index',
  approval: 'What approval did',
}

interface SpecDocumentPanelProps {
  /** Where to go once this document has been deleted (F829). Falls back to `onClose`; the Spec
   *  screen has no close control, so it names its own way out. */
  onDeleted?: () => void
  /** The document open beside the conversation. The panel does not render without one — being
   *  open *is* having a path, which is why it lives in the destination. */
  path: string
  inventory: SpecInventory
  specList: SpecListResponse | undefined
  listLoading: boolean
  /** Follow a link the document itself resolved to another specification document. */
  onSelectPath: (path: string) => void
  /** Choosing a document is the Ctrl+Shift+K picker. The breadcrumb opens it. */
  onOpenPicker: () => void
  /** Omitted on the Spec screen, where there is nothing behind the panel to reveal. Closing a
   *  document is a conversation-view action, because there the conversation is underneath. */
  onClose?: () => void
  onRefresh: () => void
  /** A fragment carried in from outside the frame — a task's requirement chip, not a link followed
   *  inside the document. Applied once per distinct `(path, initialAnchor)` pair it is given,
   *  the same way an in-frame `pendingFragment` is consumed once per navigation (`design.md` D7). */
  initialAnchor?: string | null
  /** Switches to the Tasks tab, filtered. */
  onOpenTasks?: (taskIds: string[]) => void
  /** Opens the loop tab of the document's flow. */
  onOpenLoop?: (loop: LoopSummary) => void
  /** A narrow host (the conversation's side panel): the header tightens. */
  compact?: boolean
}

/** Approval's report, as the history fact's sentences (`SpecApprovalReport` has the full form). */
function approvalHistory(outcome: SpecApprovalOutcome | undefined): string[] {
  if (!outcome) return []
  const lines: string[] = []
  if (outcome.created.length) {
    lines.push(
      `Created ${outcome.created.length} ${outcome.created.length === 1 ? 'task' : 'tasks'}: ${outcome.created.map((c) => c.title).join(', ')}.`,
    )
  }
  if (outcome.already_served.length) {
    lines.push(`${outcome.already_served.length} already served by existing work.`)
  }
  if (outcome.failed) lines.push(`Creating its tasks failed: ${outcome.failed}`)
  if (outcome.dependencies_not_honoured.length) {
    lines.push(`${outcome.dependencies_not_honoured.length} declared dependencies could not be honoured.`)
  }
  lines.push(...(outcome.flow?.messages ?? []))
  return lines
}

/**
 * A specification document: its header (where it sits, its phase, the one action it waits for,
 * and one line of facts), then the document itself with its outline.
 *
 * The header replaces eight stacked strips — the phase bar, approval report, vault warnings,
 * coverage, drift, the tasks link and the manifest-drift row — that pushed the document 380px
 * down. Every one of them is still a click away: each fact on the health line opens its detail,
 * and "Show details" opens the old panel, with all its actions, under the header. Amendments,
 * proposed ones included, waiting on the operator are panels of their own under the header, because they are
 * decisions rather than facts, and appear only when there is one.
 *
 * `SpecFrame`'s contract is carried across untouched — `sandbox="allow-scripts"` without
 * `allow-same-origin`, message identity in place of origin checking, path-allowlisted link
 * resolution.
 */
export function SpecDocumentPanel({
  path,
  inventory,
  specList,
  listLoading,
  onSelectPath,
  onOpenPicker,
  onClose,
  onRefresh,
  initialAnchor,
  onOpenTasks,
  onOpenLoop,
  onDeleted,
  compact = false,
}: SpecDocumentPanelProps) {
  const { mode } = useConfigStore()
  const { data: specDoc } = useSpec(path)
  const frameRef = useRef<SpecFrameHandle>(null)
  const controls = useSpecPhaseControls(path, onOpenLoop, onDeleted ?? onClose)

  const readablePaths = useMemo(
    () => new Set(inventory.nodes.filter((node) => !node.missing).map((node) => node.path)),
    [inventory],
  )

  const [outline, setOutline] = useState<TocAnchor[]>([])
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [pendingFragment, setPendingFragment] = useState<string | null>(initialAnchor ?? null)
  const [navStatus, setNavStatus] = useState<string | null>(null)
  const [detail, setDetail] = useState<HealthFactKey | null>(null)
  // The last `(path, anchor)` pair already applied, so a repeat render with the same
  // `initialAnchor` (the prop does not clear itself) does not re-fire the scroll, while a fresh
  // chip click — a new anchor, possibly on the document already open — does.
  const appliedAnchorRef = useRef<{ path: string; anchor: string } | null>(
    initialAnchor ? { path, anchor: initialAnchor } : null,
  )
  /* Open by default, because the bridge does not ask before removing the alternative: `specBridge`
   * hides the document's own `nav.toc` as soon as it has collected the anchors. */
  const [outlineOpen, setOutlineOpen] = useState(true)

  // A new document has its own outline, its own active section and its own details.
  useEffect(() => {
    setOutline([])
    setActiveSection(null)
    setNavStatus(null)
    setDetail(null)
  }, [path])

  // A cross-tab anchor for the document already open never triggers a fresh `toc-ready` message
  // (nothing about the document changed), so `pendingFragment` alone would never be consumed —
  // scroll directly in that case. A cross-tab anchor for a *different* document is handled the
  // same way `pendingFragment` already is for in-frame navigation.
  useEffect(() => {
    if (!initialAnchor) return
    const already =
      appliedAnchorRef.current?.path === path && appliedAnchorRef.current?.anchor === initialAnchor
    if (already) return
    appliedAnchorRef.current = { path, anchor: initialAnchor }
    setPendingFragment(initialAnchor)
    frameRef.current?.scrollToSection(initialAnchor)
  }, [path, initialAnchor])

  const handleNavigate = useCallback(
    (nextPath: string, fragment: string | null) => {
      setNavStatus(null)
      if (nextPath === path) {
        if (fragment) frameRef.current?.scrollToSection(fragment)
        return
      }
      // Consumed by SpecFrame once the new document reports its outline.
      setPendingFragment(fragment)
      onSelectPath(nextPath)
    },
    [path, onSelectPath],
  )

  const handleRejected = useCallback((reason: string) => {
    setNavStatus(REJECTION_TEXT[reason] ?? REJECTION_TEXT.unknown)
  }, [])

  const handleOutline = useCallback((anchors: TocAnchor[]) => {
    setOutline(anchors)
    setPendingFragment(null)
  }, [])

  // The Hub reports each missing document twice by design: structured in `missing` and as a
  // `missing_document` entry in `diagnostics`. Keep only the `missing` representation so the
  // count and the details list never double-count them.
  const diagnostics: SpecDiagnostic[] = (specList?.diagnostics ?? []).filter(
    (d) => d.code !== 'missing_document',
  )
  const missing = specList?.missing ?? []
  const indexIssues = diagnostics.length + missing.length

  const node = inventory.byPath.get(path)

  // ── The health line's facts ──────────────────────────────────────────────────────────────
  const { data: coverage } = useSpecCoverage(path)
  const { data: drift, isError: driftError } = useSpecDrift(path)
  const { data: vault } = useVaultWarnings(path)
  const { data: vaultChecked } = useVaultChecked(path)
  const { data: documents } = useSpecDocuments()
  const record = documents?.documents.find((entry) => entry.path === path)
  const { data: documentTasks } = useDocumentTasks(record?.id ?? null)
  const detect = useDetectDrift()
  const checkVault = useCheckVaultWarnings()

  const toggleDetail = (fact: HealthFactKey) => setDetail((current) => (current === fact ? null : fact))

  const health = (
    <SpecHealthLine
      coverage={coverage?.requirements ?? []}
      coverageDiagnostics={coverage?.diagnostics.length ?? 0}
      driftCount={driftError || !drift ? null : drift.drift.length}
      vaultWarnings={vault === undefined ? null : vault.length}
      vaultChecked={vaultChecked}
      indexIssues={indexIssues}
      tasks={(documentTasks ?? []).map((task) => ({ id: task.id, title: task.title, status: task.status }))}
      history={approvalHistory(specDoc?.approval_outcome)}
      approvedAt={record?.phase === 'approved' && specDoc?.approval_outcome ? record.updated_at : null}
      onScanDrift={() =>
        detect.mutate(undefined, {
          onSuccess: (result) =>
            toast({
              title: result.raised.length ? `${result.raised.length} drifted` : 'No drift found',
              description: result.raised.length ? 'Answer each under Drift.' : undefined,
              tone: result.raised.length ? 'neutral' : 'success',
            }),
          onError: (error: unknown) =>
            toast({ title: 'Could not scan for drift', description: readableApiError(error, 'The Hub did not answer.'), tone: 'error' }),
        })
      }
      onCheckVault={() =>
        checkVault.mutate(path, {
          onSuccess: () => toast({ title: 'Checking against the vault', description: 'The result arrives here when the check finishes.' }),
          onError: (error: unknown) =>
            toast({ title: 'Could not start the check', description: readableApiError(error, 'The Hub did not answer.'), tone: 'error' }),
        })
      }
      onOpenTasks={() => onOpenTasks?.((documentTasks ?? []).map((task) => task.id))}
      onOpenRequirement={(identifier) => frameRef.current?.scrollToSection(identifier)}
      activeDetail={detail}
      onShowDetail={toggleDetail}
    />
  )

  const tools = (
    <>
      {outline.length > 0 && (
        <Button
          variant="ghost"
          size="icon-sm"
          data-testid="spec-outline-toggle"
          aria-pressed={outlineOpen}
          onClick={() => setOutlineOpen((open) => !open)}
          aria-label={outlineOpen ? 'Hide page outline' : 'Show page outline'}
          title={outlineOpen ? 'Hide page outline' : 'Show page outline'}
        >
          <Icon name="list_alt" size={15} />
        </Button>
      )}
      <Button variant="ghost" size="icon-sm" onClick={onRefresh} aria-label="Refresh spec" title="Refresh spec">
        <Icon name="refresh" size={15} />
      </Button>
      {onClose && (
        <Button
          variant="ghost"
          size="icon-sm"
          data-testid="spec-document-close"
          onClick={onClose}
          aria-label="Close document"
          title="Close document"
        >
          <Icon name="close" size={15} />
        </Button>
      )}
    </>
  )

  const extraBadges = (
    <>
      {node?.archived && (
        <span className="aw-spec-kind" data-testid="spec-archived-marker">
          Archived{node.archiveDate ? ` · ${node.archiveDate}` : ''}
        </span>
      )}
      {/* D4 (F206): a filed document, under a valid index, can be placed in the hierarchy. */}
      {node?.state === 'filed' && specList?.manifest?.state === 'valid' && (
        <SpecPlaceUnder path={path} parent={node.parent} specList={specList} />
      )}
    </>
  )

  return (
    <div className="aw-spec-main" data-testid="spec-document-panel" data-compact={compact ? 'true' : 'false'}>
      <SpecDeletedNote />
      {controls ? (
        <SpecPhaseHeader
          path={path}
          controls={controls}
          health={health}
          tools={tools}
          badges={extraBadges}
          onOpenLocation={onOpenPicker}
        />
      ) : (
        // A document the Hub keeps no record of (the overview, a file found on disk): no phase,
        // no decisions, the same header and facts.
        <SpecDocumentHeader
          path={path}
          title={node?.title ?? path}
          kind={node?.kind ?? ''}
          phase={null}
          health={health}
          tools={tools}
          badges={extraBadges}
          onCopyPath={() => {
            void navigator.clipboard?.writeText(path)
            toast({ title: 'Path copied', tone: 'success' })
          }}
          onOpenLocation={onOpenPicker}
        />
      )}

      {detail && (
        <section className="aw-spec-detail aw-pop" aria-label={DETAIL_TITLE[detail]} data-testid={`spec-detail-${detail}`}>
          <div className="aw-spec-detail-head">
            {DETAIL_TITLE[detail]}
            <Button variant="ghost" size="icon-xs" aria-label="Hide details" title="Hide details" onClick={() => setDetail(null)}>
              <Icon name="close" size={13} />
            </Button>
          </div>
          <div className="aw-spec-detail-body">
            {detail === 'requirements' && <SpecCoverageBar path={path} onOpenTasks={onOpenTasks} defaultOpen />}
            {detail === 'drift' && <SpecDriftPanel path={path} />}
            {detail === 'vault' && <SpecVaultWarnings path={path} />}
            {detail === 'approval' && <SpecApprovalReport path={path} />}
            {detail === 'index' && (
              <ul className="flex flex-col gap-0.5 px-3 py-1 text-xs" data-testid="spec-index-issues" style={{ color: 'var(--text-3)' }}>
                {diagnostics.map((d, i) => (
                  <li key={`d-${i}`}>
                    {/* The Hub's sentence when it sends one (F643); the code is for an older Hub. */}
                    {d.message ?? (
                      <>
                        {d.code}
                        {d.path ? ` — ${d.path}` : ''}
                        {d.field ? ` (${d.field}: ${d.expected} → ${d.actual})` : ''}
                      </>
                    )}
                  </li>
                ))}
                {missing.map((m) => (
                  <li key={`m-${m.path}`}>Named by the index, not on disk: {m.path}</li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      {/* Decisions waiting on the operator, each only when there is one: a tester's amendments,
          proposed edits (design F1-F3) and what was resolved, and retired requirements with work
          still pointing at them (F211). */}
      <SpecAmendmentsPanel path={path} />
      <SpecRetiredRequirements path={path} onOpenTasks={onOpenTasks} />

      {/* An unresolved link must never block reading the current document. */}
      {navStatus && (
        <div role="status" aria-live="polite" data-testid="spec-nav-status" className="aw-spec-message mx-6 mt-2">
          <Icon name="info" size={14} />
          <span className="aw-spec-message-text">{navStatus}</span>
          <Button variant="ghost" size="icon-xs" onClick={() => setNavStatus(null)} aria-label="Dismiss navigation message">
            <Icon name="close" size={14} />
          </Button>
        </div>
      )}

      <div className="aw-spec-reading">
        <div className="aw-spec-body">
          {listLoading ? (
            <LoadingThread label="Loading specification" minHeight={240} />
          ) : specDoc ? (
            <SpecFrame
              ref={frameRef}
              path={path}
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
            <LoadingThread label="Loading specification document" minHeight={240} />
          )}
        </div>

        {/* The outline sits on the document's far side, next to the page it indexes. */}
        {outlineOpen && outline.length > 0 && (
          <nav aria-label="Page outline" data-testid="spec-outline" className="aw-spec-outline">
            <div className="aw-spec-outline-label">On this page</div>
            {outline.map((anchor) => (
              <button
                key={anchor.id}
                type="button"
                data-slot="outline-row"
                className="aw-spec-outline-row"
                onClick={() => frameRef.current?.scrollToSection(anchor.id)}
                aria-current={activeSection === anchor.id ? 'true' : undefined}
                data-active={activeSection === anchor.id ? 'true' : 'false'}
                title={anchor.label}
              >
                {anchor.label}
              </button>
            ))}
          </nav>
        )}
      </div>
    </div>
  )
}
