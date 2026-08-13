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
  onOpenDocument: (path: string | null) => void
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
export function SpecPage({ document: openDocument, onOpenDocument }: SpecPageProps) {
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
          />
        ) : (
          <div className="p-6" style={{ color: 'var(--text-3)', fontSize: 14 }}>Loading…</div>
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
