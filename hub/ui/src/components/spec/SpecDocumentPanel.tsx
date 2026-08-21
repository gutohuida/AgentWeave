import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { SpecPhaseBar } from './SpecPhaseBar'
import { SpecCoverageBar } from './SpecCoverageBar'
import { SpecProposalsPanel } from './SpecProposalsPanel'
import { SpecDocumentTasksLink } from './SpecDocumentTasksLink'
import { Button } from '@/components/ui/button'
import { useSpec, type SpecDiagnostic, type SpecListResponse } from '@/api/spec'
import { useConfigStore } from '@/store/configStore'
import { SpecFrame, type SpecFrameHandle } from './SpecFrame'
import type { SpecInventory } from './specNavigation'
import type { TocAnchor } from './specBridge'

const REJECTION_TEXT: Record<string, string> = {
  external: 'That link points outside the specification and was not opened.',
  unsafe: 'That link is not a valid specification path and was not opened.',
  'not-html': 'That link is not a specification document and was not opened.',
  unknown: 'That document is not in the current specification inventory.',
}

interface SpecDocumentPanelProps {
  /** The document open beside the conversation. The panel does not render without one — being
   *  open *is* having a path, which is why it lives in the destination. */
  path: string
  inventory: SpecInventory
  specList: SpecListResponse | undefined
  listLoading: boolean
  /** Follow a link the document itself resolved to another specification document. */
  onSelectPath: (path: string) => void
  /** Choosing a document is the Ctrl+K picker, which the conversation view owns because it must
   *  also be reachable when no document is open at all. The breadcrumb opens it. */
  onOpenPicker: () => void
  /** Omitted on the Spec screen, where there is nothing behind the panel to reveal. Closing a
   *  document is a conversation-view action, because there the conversation is underneath. */
  onClose?: () => void
  onRefresh: () => void
  /** A fragment carried in from outside the frame — a task's requirement chip, not a link followed
   *  inside the document. Applied once per distinct `(path, initialAnchor)` pair it is given,
   *  the same way an in-frame `pendingFragment` is consumed once per navigation (`design.md` D7). */
  initialAnchor?: string | null
  /** Threaded down to `SpecCoverageBar` — switches to the Tasks tab, filtered. */
  onOpenTasks?: (taskIds: string[]) => void
}

/**
 * A specification document, open beside a conversation.
 *
 * It replaces `SpecPage` + `SpecWorkspace` + `SpecNavigator`: the library column is gone (the
 * picker already searched the full inventory, archives included), and the outline moved in here,
 * next to the page it indexes.
 *
 * `SpecFrame`'s contract is carried across untouched — `sandbox="allow-scripts"` without
 * `allow-same-origin`, message identity in place of origin checking, path-allowlisted link
 * resolution. This changed the frame's container and nothing else about it.
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
}: SpecDocumentPanelProps) {
  const { mode } = useConfigStore()
  const { data: specDoc } = useSpec(path)
  const frameRef = useRef<SpecFrameHandle>(null)

  const readablePaths = useMemo(
    () => new Set(inventory.nodes.filter((node) => !node.missing).map((node) => node.path)),
    [inventory],
  )

  const [outline, setOutline] = useState<TocAnchor[]>([])
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [pendingFragment, setPendingFragment] = useState<string | null>(initialAnchor ?? null)
  const [navStatus, setNavStatus] = useState<string | null>(null)
  // The last `(path, anchor)` pair already applied, so a repeat render with the same
  // `initialAnchor` (the prop does not clear itself) does not re-fire the scroll, while a fresh
  // chip click — a new anchor, possibly on the document already open — does.
  const appliedAnchorRef = useRef<{ path: string; anchor: string } | null>(
    initialAnchor ? { path, anchor: initialAnchor } : null,
  )
  /* Open by default, because the bridge does not ask before removing the alternative.
   *
   * `specBridge` hides the document's own `nav.toc` as soon as it has collected the anchors —
   * "safe only now that the shell has a working replacement for it". That replacement is this
   * strip, and it defaulted to closed: the removal was unconditional while the replacement was
   * opt-in, so a document opened at rest had no table of contents anywhere. */
  const [outlineOpen, setOutlineOpen] = useState(true)
  const [showDriftDetails, setShowDriftDetails] = useState(false)

  // A new document has its own outline and its own active section.
  useEffect(() => {
    setOutline([])
    setActiveSection(null)
    setNavStatus(null)
  }, [path])

  // A cross-tab anchor for the document already open never triggers a fresh `toc-ready` message
  // (nothing about the document changed), so `pendingFragment` alone would never be consumed —
  // scroll directly in that case. A cross-tab anchor for a *different* document is handled the
  // same way `pendingFragment` already is for in-frame navigation: set, and consumed once the new
  // document's outline arrives.
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
  // banner count and the details list never double-count them.
  const diagnostics: SpecDiagnostic[] = (specList?.diagnostics ?? []).filter(
    (d) => d.code !== 'missing_document',
  )
  const missing = specList?.missing ?? []
  const driftCount = diagnostics.length + missing.length

  const node = inventory.byPath.get(path)

  return (
    <div
      className="flex h-full min-w-0 flex-col overflow-hidden"
      data-testid="spec-document-panel"
      style={{ background: 'var(--bg)' }}
    >
      {/* No rule under the header. The panel already has a boundary — the divider on its left —
          and a second horizontal line across the top read as a seam cutting the document off from
          the control that names it (operator, 2026-08-10). The header's own background is what
          separates it from the document. */}
      <div className="flex shrink-0 items-center gap-2 px-3 py-2">
        {/* The breadcrumb is the way to another document: it opens the same Ctrl/Cmd+Shift+K
            search that already covers the whole inventory, rather than a second, worse copy. */}
        <button
          type="button"
          data-testid="spec-document-breadcrumb"
          onClick={onOpenPicker}
          className="flex min-w-0 items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
          style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer' }}
          title={`${node?.path ?? path} — choose another document`}
        >
          <Icon name="article" size={14} />
          <span className="truncate" style={{ fontSize: 12 }}>{node?.title ?? path}</span>
          <Icon name="expand_more" size={13} />
        </button>

        {node?.archived && (
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
            Archived{node.archiveDate ? ` · ${node.archiveDate}` : ''}
          </span>
        )}

        <div className="flex-1" />

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
            <Icon name="list_alt" size={16} />
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onRefresh}
          aria-label="Refresh spec"
          title="Refresh spec"
        >
          <Icon name="refresh" size={16} />
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
            <Icon name="close" size={16} />
          </Button>
        )}
      </div>

      {/* Phase and the operator's decisions. Above the document, because what an operator may
          do next is part of reading it — and because none of these controls exists on the
          agent's side, which is what makes the approval gate real. */}
      <SpecPhaseBar path={path} />

      {/* Which requirements this document has work for, and which of that work is actually in the
          product. Under the phase bar because it is about what the document *says*, not about
          reading it. */}
      <SpecCoverageBar path={path} onOpenTasks={onOpenTasks} />

      {/* Pending proposals (design F1-F3) — a `contract`/`gate` submission lands here instead of
          on the document itself. Directly beneath coverage, on the same document view, so a
          pending change stays discoverable without a separate screen. */}
      <SpecProposalsPanel path={path} />
      <SpecDocumentTasksLink path={path} onOpenTasks={onOpenTasks} />

      {/* Drift summary — only rendered when the Hub reports manifest drift. */}
      {driftCount > 0 && (
        <div
          className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
          style={{
            background: 'color-mix(in srgb, var(--amber) 8%, transparent)',
            color: 'var(--text-2)',
          }}
        >
          <button
            onClick={() => setShowDriftDetails((v) => !v)}
            className="flex items-center gap-1.5"
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
          >
            <Icon name="warning" size={14} />
            <span>
              {driftCount} spec manifest drift item{driftCount === 1 ? '' : 's'}
            </span>
            <Icon name={showDriftDetails ? 'expand_less' : 'expand_more'} size={14} />
          </button>
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
          className="flex shrink-0 items-center gap-2 px-3 py-1.5 text-xs"
          style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
        >
          <Icon name="info" size={14} />
          <span className="flex-1">{navStatus}</span>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setNavStatus(null)}
            aria-label="Dismiss navigation message"
          >
            <Icon name="close" size={14} />
          </Button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-hidden">
          {listLoading ? (
            <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
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
            <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading spec…</div>
          )}
        </div>

        {/* The outline sits on the document's far side, next to the page it indexes rather than
            in a navigation column two panes away from it. */}
        {outlineOpen && outline.length > 0 && (
          <nav
            aria-label="Page outline"
            data-testid="spec-outline"
            className="w-[200px] shrink-0 overflow-y-auto px-2 py-2"
            style={{ borderLeft: '1px solid var(--border)' }}
          >
            <div
              style={{
                padding: '0 8px 4px',
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '.06em',
                textTransform: 'uppercase',
                color: 'var(--text-3)',
              }}
            >
              On this page
            </div>
            {outline.map((anchor) => (
              <button
                key={anchor.id}
                type="button"
                onClick={() => frameRef.current?.scrollToSection(anchor.id)}
                aria-current={activeSection === anchor.id ? 'true' : undefined}
                data-active={activeSection === anchor.id ? 'true' : 'false'}
                className="row-item"
                style={{ fontSize: 11 }}
              >
                <span className="truncate">{anchor.label}</span>
              </button>
            ))}
          </nav>
        )}
      </div>
    </div>
  )
}
