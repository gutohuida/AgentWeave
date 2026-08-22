import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { useSpecDocumentRename, useSpecEvents, useSpecList } from '@/api/spec'
import { SpecDocumentPanel } from './SpecDocumentPanel'
import { SpecDocumentPicker } from './SpecDocumentPicker'
import { buildInventory, resolveSelection } from './specNavigation'

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
 * And there is no navigation column either. Choosing a document is the rail's job while this
 * screen is open (`SpecRailNav`), the way it is Environment's job while that is open — a screen
 * that needs navigation uses the rail rather than growing a second one beside it. So what is left
 * here is the document, which is the whole point of the screen.
 */
export function SpecPage({ document: openDocument, anchor, onOpenDocument, onOpenTasks }: SpecPageProps) {
  const { data: specList, isLoading, refetch } = useSpecList()
  useSpecEvents()
  /* The agent renames the document it is exploring, so the open path can move under this screen. */
  useSpecDocumentRename(openDocument, onOpenDocument)
  const inventory = useMemo(() => buildInventory(specList), [specList])

  /* Arriving with no document named opens the manifest home, then `spec/spec.html`, then the first
   * readable current document — `resolveSelection`'s existing order. Written back to the
   * destination with `replace`, because resolving "the specification" to a document is not a
   * navigation the operator performed. */
  useEffect(() => {
    if (openDocument) return
    if (inventory.nodes.length === 0) return
    const resolved = resolveSelection(inventory, null, specList?.home)
    if (resolved) onOpenDocument(resolved)
  }, [openDocument, inventory, specList?.home, onOpenDocument])

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

  if (!isLoading && inventory.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon="article"
          title="No specification yet"
          description="Open a conversation and ask an agent to write one — the composer's Spec pill opens it beside the chat."
        />
      </div>
    )
  }

  // Every document present is archived (or missing) — resolveSelection above has nothing to hand
  // to onOpenDocument and the effect never fires, so without this branch the screen sits on
  // "Loading…" forever with no visible way out. Ctrl/Cmd+Shift+K still works — its listener is
  // registered unconditionally above — but nothing on screen says so.
  if (!isLoading && !openDocument && resolveSelection(inventory, null, specList?.home) === null) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon="archive"
          title="Everything here is archived"
          description="Open a document from history — press Ctrl/Cmd+Shift+K, or choose one from the rail."
        />
      </div>
    )
  }

  return (
    <div className="flex h-full min-w-0 overflow-hidden" data-testid="spec-page">
      <div className="min-h-0 min-w-0 flex-1">
        {openDocument ? (
          <SpecDocumentPanel
            path={openDocument}
            inventory={inventory}
            specList={specList}
            listLoading={isLoading}
            onSelectPath={onOpenDocument}
            onOpenPicker={openPicker}
            onRefresh={() => void refetch()}
            // No close control: there is nothing behind this panel to reveal. Closing a document
            // is what the conversation view offers, because there the conversation is underneath.
            initialAnchor={anchor}
            onOpenTasks={onOpenTasks}
          />
        ) : (
          <div className="spec-loading-card flex flex-col gap-3" aria-label="Loading specification">
            <div className="skeleton h-6 w-2/3" />
            <div className="skeleton h-3 w-full" />
            <div className="skeleton h-3 w-5/6" />
          </div>
        )}
      </div>

      <SpecDocumentPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        inventory={inventory}
        restoreFocusTo={() => searchOriginRef.current}
        currentPath={openDocument}
        onSelect={(node) => onOpenDocument(node.path)}
      />
    </div>
  )
}
