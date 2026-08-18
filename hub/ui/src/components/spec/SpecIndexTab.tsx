import { SpecDocumentBrowser } from './SpecDocumentBrowser'
import { tabKeyForNode, type SpecInventory, type SpecNode } from './specNavigation'
import { specTabId, usePanelTabsStore } from '@/store/panelTabsStore'

interface SpecIndexTabProps {
  projectId: string
  inventory: SpecInventory
  /** The document attached to this conversation, if any — marked in the tree the same way the
   *  Ctrl/Cmd+K picker marks it, so the index tab and the picker never disagree about "where the
   *  operator is". */
  attachedPath: string | null
}

/**
 * The panel shell's `specs` index tab (task 3.1, `2026-08-18-one-shell-three-panels`): the same
 * content `SpecDocumentPicker`'s Ctrl/Cmd+K dialog shows, re-hosted as a tab rather than a modal.
 *
 * Selecting a document here only opens it for **reading** — a `spec:<key>` tab — and never touches
 * the conversation's attached document. Attaching is the composer's control alone (design D9); an
 * index tab that also attached would be a second way to change what an agent writes into, which is
 * the fusion D9 exists to end.
 */
export function SpecIndexTab({ projectId, inventory, attachedPath }: SpecIndexTabProps) {
  const openTab = usePanelTabsStore((state) => state.openTab)

  const openForReading = (node: SpecNode) => {
    openTab(projectId, specTabId(tabKeyForNode(node)))
  }

  return (
    <SpecDocumentBrowser
      inventory={inventory}
      currentPath={attachedPath}
      onSelect={openForReading}
    />
  )
}
