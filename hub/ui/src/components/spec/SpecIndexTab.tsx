import { SpecPickerContainer } from './page/SpecPanelContainer'
import { specTabId, usePanelTabsStore } from '@/store/panelTabsStore'

interface SpecIndexTabProps {
  projectId: string
  /** The document attached to this conversation, if any: the first shortcut. */
  attachedPath: string | null
  /** Documents opened lately (the open tabs), most recent first. */
  recent?: string[]
  /** The tab key a path opens under (its document id where the Hub has one, else the path). */
  keyFor: (path: string) => string
  /** Start a new change from the conversation. */
  onNew?: () => void
}

/**
 * The panel shell's `specs` index tab: the redesigned picker (search, shortcuts, filters, order).
 * Choosing a document only opens it for **reading**, a `spec:<key>` tab; it never touches the
 * conversation's attached document. Attaching is the composer's control alone (design D9).
 */
export function SpecIndexTab({ projectId, attachedPath, recent, keyFor, onNew }: SpecIndexTabProps) {
  const openTab = usePanelTabsStore((state) => state.openTab)
  return (
    <SpecPickerContainer
      attachedPath={attachedPath}
      recent={recent}
      onNew={onNew ?? (() => undefined)}
      onOpen={(path) => openTab(projectId, specTabId(keyFor(path)))}
    />
  )
}
