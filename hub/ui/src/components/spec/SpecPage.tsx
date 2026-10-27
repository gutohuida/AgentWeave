import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { toast } from '@/lib/toast'
import { useProjectEvidence, useSpecDocumentRename, useSpecEvents } from '@/api/spec'
import type { LoopSummary } from '@/api/loops'
import { SpecDocList } from './page/SpecDocList'
import { SpecPlainDocument } from './page/SpecPlainDocument'
import { SpecWorkspace } from './page/SpecWorkspace'
import { useSpecListData, useSpecSurface } from './page/useSpecSurface'
import { SpecDocumentPicker } from './SpecDocumentPicker'
import { SpecDefectsReport } from './SpecDefectsReport'
import { buildInventory, resolveSelection } from './specNavigation'
import '@/styles/spec-header.css'

interface SpecPageProps {
  /** The document open, from the destination, so this screen is linkable and survives a reload. */
  document: string | null
  /** The position a link named (a requirement, a task, a section, a build). */
  anchor?: string | null
  onOpenDocument: (path: string | null) => void
  /** Switches to the Tasks tab, filtered to a coverage row's linked tasks. */
  onOpenTasks?: (taskIds: string[]) => void
  /** Opens a flow's loop tab; the Spec screen has no panel shell, so the host navigates too. */
  onOpenLoop?: (loop: LoopSummary) => void
  /** Opens the Spec tab's evidence view. */
  onOpenEvidence?: () => void
  /** Which entry of the list is current when `children` replace the document (evidence). */
  evidenceOpen?: boolean
  /** Shown in place of the document beside the list: the evidence view, or one requirement's story. */
  children?: ReactNode
}

const NEW_CHANGE_HINT = { title: 'Start a change from a conversation', description: "Open one and press the composer's Spec pill." }

/**
 * The specification, on its own (spec `the-spec-page-redesigned`): the document list as a left
 * column, and the open document drawn natively with its header, outline, filters and builds. The
 * conversation is not here; working on a specification with an agent is the conversation view's job.
 */
export function SpecPage({ document: openDocument, anchor, onOpenDocument, onOpenTasks, onOpenLoop, onOpenEvidence, evidenceOpen = false, children }: SpecPageProps) {
  const list = useSpecListData()
  const { data: evidence, isError: evidenceError } = useProjectEvidence(!!onOpenEvidence)
  useSpecEvents()
  /* The agent renames the document it is exploring, so the open path can move under this screen. */
  useSpecDocumentRename(openDocument, onOpenDocument)
  const inventory = useMemo(() => buildInventory(list.specList), [list.specList])

  /* Arriving with no document named opens the manifest home, then the first readable current one.
   * Written back with `replace`: resolving "the specification" to a document is not a navigation. */
  useEffect(() => {
    if (openDocument || children) return
    if (inventory.nodes.length === 0) return
    const resolved = resolveSelection(inventory, null, list.specList?.home)
    if (resolved) onOpenDocument(resolved)
  }, [openDocument, children, inventory, list.specList?.home, onOpenDocument])

  const [pickerOpen, setPickerOpen] = useState(false)
  const searchOriginRef = useRef<HTMLElement | null>(null)
  const openPicker = useCallback(() => {
    searchOriginRef.current = window.document.activeElement as HTMLElement | null
    setPickerOpen(true)
  }, [])
  /* Document search is Ctrl/Cmd+Shift+K; Ctrl/Cmd+K is the command palette's. */
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

  const footer = (
    <>
      {onOpenEvidence ? (
        <button
          type="button"
          data-slot="spec-row"
          className="aw-sp-list-row"
          data-testid="spec-list-evidence"
          data-active={evidenceOpen ? 'true' : 'false'}
          aria-current={evidenceOpen ? 'page' : undefined}
          onClick={onOpenEvidence}
        >
          <Icon name="fact_check" size={13} className="aw-sp-list-icon" />
          <span className="aw-sp-list-name">Evidence</span>
          <span className="aw-sp-list-meta" title={evidenceError ? 'The evidence count could not be read' : undefined}>
            {evidenceError ? '—' : (evidence?.evidence?.length ?? '')}
          </span>
        </button>
      ) : null}
      <SpecDefectsReport currentPath={openDocument} onSelect={(path) => onOpenDocument(path)} />
    </>
  )

  const now = useMemo(() => new Date(), [])
  const column = (active: string | null) => (
    <SpecDocList
      entries={list.entries}
      active={active}
      prefs={list.prefs}
      onPrefsChange={list.setPrefs}
      onOpen={(path) => onOpenDocument(path)}
      onNew={() => toast(NEW_CHANGE_HINT)}
      now={now}
      footer={footer}
    />
  )

  let main: ReactNode
  if (children) {
    main = (
      <div className="aw-sp" data-layout="column">
        {column(null)}
        <div className="aw-sp-main aw-sp-override">{children}</div>
      </div>
    )
  } else if (!list.loading && inventory.nodes.length === 0) {
    main = (
      <div className="aw-sp-empty-page">
        <EmptyState icon="article" title="No specification yet" description="Open a conversation and ask an agent to write one; the composer's Spec pill opens it beside the chat." />
      </div>
    )
  } else if (!list.loading && !openDocument && resolveSelection(inventory, null, list.specList?.home) === null) {
    main = (
      <div className="aw-sp-empty-page">
        <EmptyState icon="archive" title="Everything here is archived" description="Open one from the list, or press Ctrl/Cmd+Shift+K to search." />
      </div>
    )
  } else if (openDocument) {
    main = <OpenDocument key={`${openDocument}:${anchor ?? ''}`} path={openDocument} anchor={anchor ?? null} column={column(openDocument)} footer={footer} onOpenDocument={onOpenDocument} onOpenTasks={onOpenTasks} onOpenLoop={onOpenLoop} />
  } else {
    main = <LoadingThread label="Loading specification" minHeight={240} />
  }

  return (
    <div className="aw-sp-page" data-testid="spec-page">
      {main}
      <SpecDocumentPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        restoreFocusTo={() => searchOriginRef.current}
        currentPath={openDocument}
        onSelect={(path) => onOpenDocument(path)}
        onNew={() => toast(NEW_CHANGE_HINT)}
      />
    </div>
  )
}

function OpenDocument({
  path,
  anchor,
  column,
  footer,
  onOpenDocument,
  onOpenTasks,
  onOpenLoop,
}: {
  path: string
  anchor: string | null
  column: ReactNode
  footer: ReactNode
  onOpenDocument: (path: string | null) => void
  onOpenTasks?: (taskIds: string[]) => void
  onOpenLoop?: (loop: LoopSummary) => void
}) {
  const list = useSpecListData()
  const result = useSpecSurface(path, {
    onOpenDocument: (next) => onOpenDocument(next),
    onOpenTasks,
    onOpenLoop,
    onDeleted: () => onOpenDocument(null),
    initialAnchor: anchor,
  })
  if (result.status === 'ready') {
    return <SpecWorkspace {...result.surface} entries={list.entries} listPrefs={list.prefs} onListPrefsChange={list.setPrefs} onNew={() => toast(NEW_CHANGE_HINT)} layout="column" listFooter={footer} />
  }
  return (
    <div className="aw-sp" data-layout="column">
      {column}
      <div className="aw-sp-main">
        {result.status === 'loading' ? (
          <LoadingThread label="Loading specification document" minHeight={240} />
        ) : (
          <SpecPlainDocument plain={result.plain} message={result.message} />
        )}
      </div>
    </div>
  )
}
