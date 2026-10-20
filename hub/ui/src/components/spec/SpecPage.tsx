import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import {
  useProjectEvidence,
  useSpecDocumentRename,
  useSpecDocuments,
  useSpecEvents,
  useSpecList,
  type SpecDocumentRecord,
} from '@/api/spec'
import { SpecDocumentPanel } from './SpecDocumentPanel'
import { SpecDocumentPicker } from './SpecDocumentPicker'
import { SpecDocumentList, type SpecListDocument } from './SpecDocumentList'
import { SpecDefectsReport } from './SpecDefectsReport'
import { buildInventory, resolveSelection, type SpecInventory } from './specNavigation'
import type { LoopSummary } from '@/api/loops'
import '@/styles/spec-header.css'

interface SpecPageProps {
  /** The document open, from the destination — so this screen is linkable and survives a reload
   *  exactly as the conversation's document panel does. */
  document: string | null
  /** The requirement fragment a cross-tab click (a task's requirement chip) arrived with, from the
   *  destination. Read once by `SpecDocumentPanel`, the same as an in-frame `pendingFragment`. */
  anchor?: string | null
  onOpenDocument: (path: string | null) => void
  /** Switches to the Tasks tab, filtered to a coverage row's linked tasks. */
  onOpenTasks?: (taskIds: string[]) => void
  /** Opens a flow's loop tab; the Spec screen has no panel shell, so the host navigates too. */
  onOpenLoop?: (loop: LoopSummary) => void
  /** Opens the Spec tab's evidence view (slice evidence-browser), from the document list. */
  onOpenEvidence?: () => void
  /** Which entry of the list is current when `children` replace the document (evidence). */
  evidenceOpen?: boolean
  /** Shown in place of the document beside the list: the evidence view, or one requirement's story. */
  children?: ReactNode
}

/** The document list's rows: every document the inventory holds, with the kind and phase the
 *  Hub's records give (a capability is told by its record, or by living under spec/capabilities/). */
function listDocuments(inventory: SpecInventory, records: SpecDocumentRecord[] | undefined): SpecListDocument[] {
  const byPath = new Map((records ?? []).map((record) => [record.path, record]))
  return inventory.nodes.map((node) => {
    const record = byPath.get(node.path)
    const kind = record?.kind ?? node.kind ?? (node.path.startsWith('spec/capabilities/') ? 'capability' : 'other')
    return {
      path: node.path,
      title: record?.title ?? node.title,
      kind,
      phase: record?.phase ?? node.status ?? (kind === 'capability' ? 'current' : ''),
      archived: node.archived || record?.phase === 'archived',
      missing: node.missing,
    }
  })
}

/**
 * The specification, on its own.
 *
 * This is not the page that was deleted. That one put a navigator, a document and a chat in three
 * columns, collapsed the Hub rail to make room, and crushed the conversation into 360px. The
 * conversation is not here at all: working on a specification *with an agent* is the conversation
 * view's job, reached from the composer's Spec pill. This is the other half — the specification as
 * the thing you are working on rather than the thing you are working beside.
 *
 * Documents are chosen from the list beside the document (`SpecDocumentList`, ui-finesse). The
 * rail used to stand in for it (`SpecRailNav`), which made the agents disappear whenever a
 * document was open; now the rail stays and the list, with Evidence and the defects report the
 * rail carried, lives in the tab. The evidence view and one requirement's story render beside the
 * same list (`children`), so moving between them never loses it.
 */
export function SpecPage({
  document: openDocument,
  anchor,
  onOpenDocument,
  onOpenTasks,
  onOpenLoop,
  onOpenEvidence,
  evidenceOpen = false,
  children,
}: SpecPageProps) {
  const { data: specList, isLoading, refetch } = useSpecList()
  const { data: records } = useSpecDocuments()
  const { data: evidence, isError: evidenceError } = useProjectEvidence(!!onOpenEvidence)
  useSpecEvents()
  /* The agent renames the document it is exploring, so the open path can move under this screen. */
  useSpecDocumentRename(openDocument, onOpenDocument)
  const inventory = useMemo(() => buildInventory(specList), [specList])

  /* Arriving with no document named opens the manifest home, then `spec/spec.json`, then the first
   * readable current document — `resolveSelection`'s existing order. Written back to the
   * destination with `replace`, because resolving "the specification" to a document is not a
   * navigation the operator performed. */
  useEffect(() => {
    if (openDocument || children) return
    if (inventory.nodes.length === 0) return
    const resolved = resolveSelection(inventory, null, specList?.home)
    if (resolved) onOpenDocument(resolved)
  }, [openDocument, children, inventory, specList?.home, onOpenDocument])

  const [pickerOpen, setPickerOpen] = useState(false)
  const searchOriginRef = useRef<HTMLElement | null>(null)
  const openPicker = useCallback(() => {
    searchOriginRef.current = window.document.activeElement as HTMLElement | null
    setPickerOpen(true)
  }, [])

  /* Document search is Ctrl/Cmd+Shift+K. Ctrl/Cmd+K is the command palette's.
   *
   * `2026-08-10-conversation-first-spec-workspace` gave the plain chord to document search;
   * `2026-08-18-2026-08-16-conversation-formatting-and-quick-nav` then specified a global command
   * palette on that same chord, naming "no global command palette for cross-cutting navigation"
   * as the problem it solved. The palette shipped and these listeners did not go — and being
   * mounted, they won, so Ctrl+K opened the spec from anywhere and the palette was unreachable
   * (operator, 2026-08-21: "ctrl + k is always opening the spec directly").
   *
   * Moved rather than deleted. The picker does have buttons, but not in every state — a
   * conversation that does not exist yet omits the reopen control entirely — so deleting the
   * keyboard route would strand document search exactly where there is nothing else to click. */
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        openPicker()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [openPicker])

  const list = (
    <SpecDocumentList
      documents={listDocuments(inventory, records?.documents)}
      active={children ? null : openDocument}
      evidenceCount={evidenceError ? 'error' : (evidence?.evidence?.length ?? null)}
      evidenceActive={evidenceOpen}
      onOpen={(path) => onOpenDocument(path)}
      onOpenEvidence={onOpenEvidence}
      footer={<SpecDefectsReport currentPath={openDocument} onSelect={(path) => onOpenDocument(path)} />}
    />
  )

  let main: ReactNode
  if (children) {
    main = <div className="aw-spec-main min-h-0 overflow-auto">{children}</div>
  } else if (!isLoading && inventory.nodes.length === 0) {
    main = (
      <div className="aw-spec-main items-center justify-center">
        <EmptyState
          icon="article"
          title="No specification yet"
          description="Open a conversation and ask an agent to write one — the composer's Spec pill opens it beside the chat."
        />
      </div>
    )
  } else if (!isLoading && !openDocument && resolveSelection(inventory, null, specList?.home) === null) {
    // Every document present is archived (or missing) — resolveSelection above has nothing to hand
    // to onOpenDocument and the effect never fires, so without this branch the screen sits on
    // "Loading…" forever with no visible way out.
    main = (
      <div className="aw-spec-main items-center justify-center">
        <EmptyState
          icon="archive"
          title="Everything here is archived"
          description="Open one from Archived in the list, or press Ctrl/Cmd+Shift+K to search."
        />
      </div>
    )
  } else if (openDocument) {
    main = (
      <SpecDocumentPanel
        path={openDocument}
        inventory={inventory}
        specList={specList}
        listLoading={isLoading}
        onSelectPath={onOpenDocument}
        onOpenPicker={openPicker}
        onRefresh={() => void refetch()}
        // No close control: there is nothing behind this panel to reveal. Closing a document is
        // what the conversation view offers, because there the conversation is underneath.
        initialAnchor={anchor}
        onOpenTasks={onOpenTasks}
        onOpenLoop={onOpenLoop}
      />
    )
  } else {
    main = (
      <div className="aw-spec-main">
        <div className="spec-loading-card flex flex-col gap-3 aw-delayed" aria-label="Loading specification">
          <div className="skeleton h-6 w-2/3" />
          <div className="skeleton h-3 w-full" />
          <div className="skeleton h-3 w-5/6" />
        </div>
      </div>
    )
  }

  return (
    <div className="aw-spec" data-testid="spec-page">
      {inventory.nodes.length > 0 || children ? list : null}
      {main}

      <SpecDocumentPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        inventory={inventory}
        restoreFocusTo={() => searchOriginRef.current}
        currentPath={openDocument}
        specList={specList}
        onSelect={(node) => onOpenDocument(node.path)}
      />
    </div>
  )
}
