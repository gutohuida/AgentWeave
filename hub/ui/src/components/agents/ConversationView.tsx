import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AgentSummary } from '@/api/agents'
import { useAgentConversations } from '@/api/agentChat'
import {
  useCreateSpecDocument,
  useSpecDocumentRename,
  useSpecEvents,
  useSpecList,
} from '@/api/spec'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Drawer } from '@/components/layout/Drawer'
import { PaneResizer } from '@/components/layout/PaneResizer'
import { useWorkspaceWidth } from '@/components/layout/useWorkspaceWidth'
import { FileTab } from '@/components/spec/FileTab'
import { FilesIndexTab } from '@/components/spec/FilesIndexTab'
import { LoopTab } from '@/components/spec/LoopTab'
import { LoopsIndexTab } from '@/components/spec/LoopsIndexTab'
import { PanelShell, type PanelTabDescriptor } from '@/components/spec/PanelShell'
import { SpecDocumentPanel } from '@/components/spec/SpecDocumentPanel'
import { SpecDocumentPicker } from '@/components/spec/SpecDocumentPicker'
import { SpecIndexTab } from '@/components/spec/SpecIndexTab'
import { buildInventory, resolveTabPath, tabKeyForNode } from '@/components/spec/specNavigation'
import { useWorkspacePaths } from '@/api/workspace'
import { useLoops } from '@/api/loops'
import {
  CONVERSATION_DEFAULT_WIDTH,
  CONVERSATION_MIN_WIDTH,
  DEFAULT_SPEC_PREFERENCES,
  loadSpecPreferences,
  minWidthForTabKind,
  saveSpecPreferences,
} from '@/components/spec/specPreferences'
import {
  fileTabId,
  filePath,
  isFileTabId,
  isLoopTabId,
  isSpecTabId,
  loopId as loopIdFromTab,
  loopTabId,
  selectProjectPanel,
  specDocumentId,
  specTabId,
  tabKind,
  usePanelTabsStore,
  type PanelTab,
  type TabId,
} from '@/store/panelTabsStore'
import { AgentOutputPanel } from './AgentOutputPanel'

/** What a divider costs the row. `PaneResizer` is an 11px strip with -5px margins either side. */
const DIVIDER_WIDTH = 1

/**
 * Below this the two columns stop fitting and the document becomes an overlay, when a specification
 * document is the tab on screen — the only kind the shell can host until the files tab (section 5
 * of `2026-08-18-one-shell-three-panels`) exists. `ConversationView` itself computes the *real*
 * threshold from whichever tab is actually visible (`minWidthForTabKind`, same source as the pane's
 * own `minWidth`); this export is the spec-tab case of that, kept as a constant because every test
 * and caller that reads it today only ever has a spec tab open.
 */
export const DOCUMENT_COLUMN_BREAKPOINT =
  CONVERSATION_MIN_WIDTH + minWidthForTabKind('spec') + DIVIDER_WIDTH

interface ConversationViewProps {
  agent: AgentSummary
  conversationId: string | null
  /** The project this conversation belongs to — the panel shell's tab configuration is
   *  per-project (`panelTabsStore`), keyed by this id. */
  projectId: string
  /** The specification document open beside this conversation, from the destination. */
  document: string | null
  onSelectConversation: (conversationId: string | null) => void
  /** Open, change, or close (with `null`) the document. Moves the destination, so the pair
   *  survives a reload and can be linked to. */
  onOpenDocument: (path: string | null) => void
  onBackToProject: () => void
  onOpenAgentSettings: () => void
}

/**
 * A conversation, with a specification document optionally open beside it.
 *
 * This is the shape that replaced the Spec page. A specification is not a place you go — it is a
 * thing you work on with an agent — so the conversation is the frame and the document is a panel
 * within it. Every conversation gets the panel, which is what makes the relationship between a
 * thread and a document a link the operator makes rather than a category the thread was born into.
 *
 * There is no agent selector here. The agent is whichever conversation the operator is in; the
 * rail is the one place that changes it.
 */
export function ConversationView({
  agent,
  conversationId,
  projectId,
  document,
  onSelectConversation,
  onOpenDocument,
  onBackToProject,
  onOpenAgentSettings,
}: ConversationViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const measuredWidth = useWorkspaceWidth(containerRef)
  const { data: specList, isLoading: listLoading, refetch: refetchList } = useSpecList()
  const createDocument = useCreateSpecDocument()
  /* What to call the document. The Hub titles a conversation from its first message, so by the
   * time an operator wants to explore there is already a name that means something to them —
   * which is why starting one asks for nothing (task 13.2). */
  const { data: conversations } = useAgentConversations(agent.name)
  const conversationTitle =
    conversations?.find((entry) => entry.id === conversationId)?.title ?? null
  useSpecEvents()
  /* The agent renames the document it is exploring, usually in the turn the operator is watching,
   * so the path in the destination can move out from under this panel. */
  useSpecDocumentRename(document, onOpenDocument)
  const inventory = useMemo(() => buildInventory(specList), [specList])

  const [pickerOpen, setPickerOpen] = useState(false)
  // Captured before the dialog mounts, so focus returns to whatever the operator was on —
  // the breadcrumb, or wherever Ctrl+K was pressed.
  const searchOriginRef = useRef<HTMLElement | null>(null)
  const openPicker = useCallback(() => {
    searchOriginRef.current = window.document.activeElement as HTMLElement | null
    setPickerOpen(true)
  }, [])

  // Ctrl/Cmd+K opens document search from anywhere in a conversation — which is what makes a
  // document reachable without a separate screen to go to first.
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

  // Presentation preferences only — never content, payloads, or credentials.
  const [preferences, setPreferences] = useState(DEFAULT_SPEC_PREFERENCES)
  useEffect(() => {
    setPreferences(loadSpecPreferences())
  }, [])
  const setConversationWidth = useCallback((conversationWidth: number) => {
    setPreferences((prev) => {
      const next = { ...prev, conversationWidth }
      saveSpecPreferences(next)
      return next
    })
  }, [])

  const openTab = usePanelTabsStore((state) => state.openTab)
  const closeTab = usePanelTabsStore((state) => state.closeTab)
  const replaceTabId = usePanelTabsStore((state) => state.replaceTabId)
  const setShellOpen = usePanelTabsStore((state) => state.setShellOpen)
  const panelActiveTabId = usePanelTabsStore(
    (state) => selectProjectPanel(state, projectId).activeTabId,
  )
  // The store's own "should the shell be visible" bit — set by `openTab` whenever any tab opens,
  // cleared by `closeTab` once the last one closes, and settable directly via `setShellOpen`.
  // Read here (not just by `PanelShell` once mounted) because whether to *mount* the shell at all
  // used to be answered by `document !== null` alone (`documentOpen` below), which is the gap
  // flagged in this run's own `decisions_for_user` (iteration 16): a shell tenant that needs no
  // attached document — the `loops` index tab this run adds is exactly that — was unreachable,
  // because nothing rendered `PanelShell` for it to be reachable *from*.
  const shellIsOpen = usePanelTabsStore((state) => selectProjectPanel(state, projectId).isOpen)

  /* Section 3's tenant, id-keyed (design D4): the attached document's reading tab is keyed by its
   * Hub document id where one exists, else its path — `tabKeyForNode` and `resolveTabPath` are the
   * one pair of functions that make that key and undo it, so the open side and the render side can
   * never derive it differently. Falls back to the raw `document` path before the inventory has
   * loaded; the effect below re-keys once it has (see its own note). */
  const attachedNode = document ? (inventory.byPath.get(document) ?? null) : null
  const attachedTabKey = document ? (attachedNode ? tabKeyForNode(attachedNode) : document) : null

  /* Destination -> store, one direction only (design D9's unfuse): attaching a document opens (or
   * refocuses) its reading tab, so the thing the composer just attached is on screen. It does
   * *not* close whatever tab the previously-attached document had — that tab is now an ordinary
   * reading tab like any other the operator opened, and D9 is explicit that closing (or, by the
   * same reasoning, merely no-longer-being-attached) is not an edit an attach action gets to make
   * to what is on screen. There is no reverse effect any more: closing a tab from the strip used to
   * call `onOpenDocument(null)` (task 2.2's fused sync) — that effect is deleted, not merely
   * unused, because D9 says a closed reader must never detach the agent's document.
   *
   * Keyed off the previous *computed key*, not the previous `document` path, so a rename (which
   * keeps the id, so `attachedTabKey` does not change) never re-opens the tab.
   *
   * One case does still re-key the previous tab rather than opening a new one: the one-time
   * upgrade from a path-keyed fallback to the real id once the inventory loads. That is not a
   * change of *document* — the key changed under the same attachment, because `attachedNode` above
   * went from "not found yet" to "found" — and leaving the stale, path-keyed tab open would
   * silently duplicate the id-keyed one this same effect would otherwise open (caught live:
   * `hub/tests/browser/test_panel_shell.py`, against a fixture document that already carries a Hub
   * id on load, where the duplicate was two tabs for the same document, one of them a dangling
   * fallback identity nothing ever closed). Told apart from a genuine attach change — where the
   * previous tab must survive — by resolving both keys back to a path: the same path means the
   * same document, only re-keyed.
   *
   * A re-key uses `replaceTabId`, not `closeTab` + `openTab`: that pair forces activation via
   * `openTab`, which steals the active tab back from whatever the operator has since selected —
   * reproduced live via `testbed/scratch/diag_panel_shell.py` (open the shell with a document
   * attached, click plus -> Specs, and the late inventory resolve flips focus straight back to the
   * document). `replaceTabId` preserves both strip position and `activeTabId`, unless the tab being
   * re-keyed was itself the active one, in which case it stays active under its new key. */
  const previousAttachedTabKeyRef = useRef<string | null>(null)
  useEffect(() => {
    const previous = previousAttachedTabKeyRef.current
    previousAttachedTabKeyRef.current = attachedTabKey
    if (previous === attachedTabKey) return
    if (
      previous &&
      attachedTabKey &&
      resolveTabPath(inventory, previous) === resolveTabPath(inventory, attachedTabKey)
    ) {
      replaceTabId(projectId, specTabId(previous), specTabId(attachedTabKey))
      return
    }
    if (attachedTabKey) openTab(projectId, specTabId(attachedTabKey))
  }, [projectId, attachedTabKey, inventory, openTab, replaceTabId])

  const documentOpen = document !== null
  // What actually governs whether the shell mounts: either a document is attached (the only case
  // that existed before this run) or the operator opened the shell directly — the toggle wired
  // below, and the same bit an index tab like `loops` sets via `openTab`. `documentOpen` alone is
  // kept for document-specific UI (the attached title, the overlay's reopen pill) below; layout
  // decisions read this instead so a document-free shell lays out identically to one with a
  // document in it.
  const shellVisible = documentOpen || shellIsOpen
  // Derived from whichever tab kind is actually visible — today that can only be a `spec` tab
  // (files are section 5), but computing it this way means the breakpoint below never has to be
  // touched again once a second kind exists; it already reads the same source the pane's own
  // `minWidth` reads.
  const visibleTabMinWidth = minWidthForTabKind(panelActiveTabId ? tabKind(panelActiveTabId) : null)
  const documentColumnBreakpoint = CONVERSATION_MIN_WIDTH + visibleTabMinWidth + DIVIDER_WIDTH
  const fitsAsColumn = measuredWidth === null || measuredWidth >= documentColumnBreakpoint

  /* What the conversation may take without pushing the document below its minimum.
   *
   * The ceiling is *only* the measurement: whatever is left once the document has its minimum.
   * There is no design cap on top of it — a cap is what made the document panel impossible to
   * shrink. Floored at the conversation's own minimum, because a ceiling below the floor would
   * invert the range. The rendered width is clamped by this budget rather than written back, so
   * narrowing the window does not silently discard the width the operator chose for a wide one. */
  const conversationMax =
    measuredWidth === null
      ? CONVERSATION_DEFAULT_WIDTH
      : Math.max(CONVERSATION_MIN_WIDTH, measuredWidth - visibleTabMinWidth - DIVIDER_WIDTH)
  const conversationWidth = Math.min(preferences.conversationWidth, conversationMax)

  // The overlay is opened by opening a document and closed by the operator; the document stays in
  // the destination either way, so a dismissed overlay can be reopened from the bar below without
  // losing where they were.
  const [overlayOpen, setOverlayOpen] = useState(false)
  useEffect(() => {
    if (document) setOverlayOpen(true)
  }, [document])
  const overlayTriggerRef = useRef<HTMLButtonElement>(null)

  const documentNode = document ? inventory.byPath.get(document) : undefined
  const handleRefresh = useCallback(() => {
    void refetchList()
  }, [refetchList])

  // Section 3's first index tenant: the plus affordance can always offer the specs browser,
  // whether or not anything is attached yet. Section 5 adds the files tab beside it.
  const { data: workspacePaths = [], isLoading: workspacePathsLoading } = useWorkspacePaths()
  // B5's `loops` index tenant (`2026-08-18-a-loop-writes-its-own-queue`). Fetched with
  // `includeArchived=true` unconditionally — a superset — so `describePanelTab` can resolve a
  // label for a `loop:` tab that is already open even while the index's own filter (task B5.4,
  // state lives in `LoopsIndexTab`... no: kept here, see `includeArchivedLoops` below) is hiding
  // it from the list view. One fetch, not two racing queries with different `include_archived`
  // values for the same data.
  const { data: allLoops = [], isLoading: loopsLoading } = useLoops(true)
  const [includeArchivedLoops, setIncludeArchivedLoops] = useState(false)
  const visibleLoops = useMemo(
    () => (includeArchivedLoops ? allLoops : allLoops.filter((loop) => !loop.archived_at)),
    [allLoops, includeArchivedLoops],
  )
  const availablePanelTabs: PanelTabDescriptor[] = useMemo(
    () => [
      { id: 'specs', label: 'Specs', icon: 'folder_open' },
      { id: 'files', label: 'Files', icon: 'folder_open' },
      { id: 'loops', label: 'Loops', icon: 'sync' },
    ],
    [],
  )
  const describePanelTab = useCallback(
    (id: TabId): PanelTabDescriptor => {
      if (id === 'specs') return { id, label: 'Specs', icon: 'folder_open' }
      if (id === 'files') return { id, label: 'Files', icon: 'folder_open' }
      if (id === 'loops') return { id, label: 'Loops', icon: 'sync' }
      if (isFileTabId(id)) {
        const path = filePath(id)
        return { id, label: path.slice(path.lastIndexOf('/') + 1), icon: 'description' }
      }
      if (isLoopTabId(id)) {
        const loop = allLoops.find((entry) => entry.id === loopIdFromTab(id))
        return { id, label: loop?.label ?? loopIdFromTab(id), icon: 'sync' }
      }
      const path = isSpecTabId(id) ? resolveTabPath(inventory, specDocumentId(id)) : id
      const node = inventory.byPath.get(path)
      return { id, label: node?.title ?? path, icon: 'article' }
    },
    [inventory, allLoops],
  )

  // The files tab's "Insert into composer" (task 5.4): a counter-keyed request the mounted
  // Composer consumes once, the same shape `panelTabsStore` already uses for "reveal this tab
  // again" — a plain boolean or the raw path could not tell a second insert of the same file
  // apart from the first.
  const insertRequestCounter = useRef(0)
  const [insertPathRequest, setInsertPathRequest] = useState<{ path: string; requestId: number } | null>(
    null,
  )
  const insertIntoComposer = useCallback((path: string) => {
    insertRequestCounter.current += 1
    setInsertPathRequest({ path, requestId: insertRequestCounter.current })
  }, [])

  const renderPanelTabContent = useCallback(
    (tab: PanelTab) => {
      if (tab.id === 'specs') {
        return <SpecIndexTab projectId={projectId} inventory={inventory} attachedPath={document} />
      }
      if (tab.id === 'files') {
        return (
          <FilesIndexTab
            paths={workspacePaths}
            isLoading={workspacePathsLoading}
            currentPath={panelActiveTabId && isFileTabId(panelActiveTabId) ? filePath(panelActiveTabId) : null}
            onSelect={(path) => openTab(projectId, fileTabId(path))}
          />
        )
      }
      if (isFileTabId(tab.id)) {
        return (
          <FileTab
            path={filePath(tab.id)}
            onInsertIntoComposer={insertIntoComposer}
            onClose={() => closeTab(projectId, tab.id)}
          />
        )
      }
      if (tab.id === 'loops') {
        return (
          <LoopsIndexTab
            loops={visibleLoops}
            isLoading={loopsLoading}
            includeArchived={includeArchivedLoops}
            onToggleIncludeArchived={setIncludeArchivedLoops}
            currentLoopId={panelActiveTabId && isLoopTabId(panelActiveTabId) ? loopIdFromTab(panelActiveTabId) : null}
            // B5.2: opening a drill-down does not close the index — no `filter` here the way
            // `openTab`'s own `file:` rule closes `files` (design D8's one asymmetry). The index
            // is a governance glance, not a launcher.
            onSelect={(id) => openTab(projectId, loopTabId(id))}
          />
        )
      }
      if (isLoopTabId(tab.id)) {
        return <LoopTab loopId={loopIdFromTab(tab.id)} onClose={() => closeTab(projectId, tab.id)} />
      }
      if (!isSpecTabId(tab.id)) return null
      // `tab.id`'s key is a document id where the node has one, else the path itself
      // (`tabKeyForNode`/`resolveTabPath`, design D4) — resolved back to a path here because
      // `SpecDocumentPanel` only ever knew a path.
      const path = resolveTabPath(inventory, specDocumentId(tab.id))
      return (
        <SpecDocumentPanel
          path={path}
          inventory={inventory}
          specList={specList}
          listLoading={listLoading}
          onSelectPath={(nextPath) => onOpenDocument(nextPath)}
          onOpenPicker={openPicker}
          /* Closing this tab is reading-pane tidying, not an edit to what the agent is attached
           * to (design D9) — it closes *this* tab, and only this tab, the same as the tab strip's
           * own close button (`PanelShell`'s `panel-tab-close-*`) a few pixels to its left. Only
           * `ComposerSpecControl`'s `onStopExploring`, wired below, still calls `onOpenDocument(null)`. */
          onClose={() => closeTab(projectId, tab.id)}
          onRefresh={handleRefresh}
        />
      )
    },
    [
      projectId,
      inventory,
      specList,
      listLoading,
      onOpenDocument,
      openPicker,
      closeTab,
      handleRefresh,
      document,
      workspacePaths,
      workspacePathsLoading,
      openTab,
      insertIntoComposer,
      panelActiveTabId,
      visibleLoops,
      loopsLoading,
      includeArchivedLoops,
    ],
  )
  const panel = shellVisible ? (
    <PanelShell
      projectId={projectId}
      availableTabs={availablePanelTabs}
      describeTab={describePanelTab}
      renderTabContent={renderPanelTabContent}
    />
  ) : null

  /* One press starts an exploration. The conversation already carries a title — the Hub sets it
   * from the first message — so there is nothing to ask for, which is what makes this a toggle
   * rather than a form. §2.7 allows the entry point to look like a pill provided pressing it
   * *creates the document*; a pill holding a mode with no document behind it would leave
   * "propose" and "approve" with no subject. */
  const startExploration = useCallback(
    (title?: string) => {
      /* The path is the Hub's to mint, not this component's to derive. The conversation title is
       * still worth sending — it is the best interim description available — but it is a title,
       * and the two used to be the same string. The agent renames the document once it knows. */
      const chosen = (title ?? conversationTitle ?? '').trim()
      createDocument.mutate(
        { title: chosen || undefined },
        { onSuccess: (created) => onOpenDocument(created.path) },
      )
    },
    [conversationTitle, createDocument, onOpenDocument],
  )

  const conversation = (
    <AgentOutputPanel
      agent={agent}
      conversationId={conversationId}
      onSelectConversation={onSelectConversation}
      onBackToProject={onBackToProject}
      onOpenAgentSettings={onOpenAgentSettings}
      specDocumentPath={document}
      specDocumentLabel={document ? documentNode?.title ?? document : null}
      onOpenSpecPicker={openPicker}
      onOpenExistingSpec={openPicker}
      onStartExploration={() => startExploration()}
      /* Detach, never delete. An exploration leaves an artifact; a toggle that discarded it on
       * the way back would be a trap dressed as a switch.
       *
       * Also closes the shell explicitly (`setShellOpen(false)`) rather than leaving it to go
       * stale: `shellVisible` above is `documentOpen || shellIsOpen`, so without this the store's
       * `isOpen` bit — still `true` from whatever tab was open a moment ago — would keep the
       * shell mounted even after the document it was showing is gone (existing behavior, and
       * `hub/tests/browser/test_panel_shell.py::test_the_composers_own_close_control_also_closes_
       * the_shell` asserts it). */
      onStopExploring={() => {
        onOpenDocument(null)
        setShellOpen(projectId, false)
      }}
      specBusy={createDocument.isPending}
      insertPathRequest={insertPathRequest}
      onTogglePanel={() => setShellOpen(projectId, !shellIsOpen)}
      panelOpen={shellIsOpen}
    />
  )

  return (
    <div
      ref={containerRef}
      className="flex h-full min-w-0 flex-row overflow-hidden"
      data-testid="conversation-workspace"
      data-document={documentOpen ? 'open' : 'closed'}
      data-panel={shellVisible ? 'open' : 'closed'}
      data-layout={shellVisible ? (fitsAsColumn ? 'column' : 'overlay') : 'full'}
    >
      <div
        className="flex min-h-0 min-w-0 flex-col"
        data-testid="conversation-pane"
        style={
          shellVisible && fitsAsColumn
            ? { width: conversationWidth, flex: '0 0 auto' }
            : { flex: '1 1 0%' }
        }
      >
        {/* Only in overlay mode: the panel is open but not on screen, so there has to be a way
            back to it — and a stable element for focus to return to when the overlay closes. A
            document names itself; a document-free shell (the `loops` index, opened via the
            toggle below) gets a generic label — there is no single item to name. */}
        {shellVisible && !fitsAsColumn && (
          <div
            className="flex shrink-0 items-center gap-2 px-3 py-1.5"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <button
              type="button"
              ref={overlayTriggerRef}
              data-testid="conversation-open-document"
              onClick={() => setOverlayOpen(true)}
              className="flex min-w-0 items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1"
              style={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                color: 'var(--text-2)',
                fontSize: 11,
                cursor: 'pointer',
              }}
            >
              <Icon name={document ? 'article' : 'folder_open'} size={14} />
              <span className="truncate">{document ? documentNode?.title ?? document : 'Panel'}</span>
            </button>
            {document && (
              <Button
                variant="ghost"
                size="icon-xs"
                data-testid="conversation-close-document"
                onClick={() => onOpenDocument(null)}
                aria-label="Close document"
                title="Close document"
              >
                <Icon name="close" size={14} />
              </Button>
            )}
          </div>
        )}
        <div className="min-h-0 flex-1">{conversation}</div>
      </div>

      {shellVisible && fitsAsColumn && (
        <>
          <PaneResizer
            width={conversationWidth}
            onChange={setConversationWidth}
            defaultWidth={CONVERSATION_DEFAULT_WIDTH}
            min={CONVERSATION_MIN_WIDTH}
            max={conversationMax}
            label="Resize conversation"
            containerRef={containerRef}
          />
          <div
            className="flex min-h-0 min-w-0 flex-1 flex-col"
            data-testid="document-pane"
            style={{ minWidth: visibleTabMinWidth }}
          >
            {panel}
          </div>
        </>
      )}

      {shellVisible && !fitsAsColumn && (
        <Drawer
          open={overlayOpen}
          onOpenChange={setOverlayOpen}
          title="Panel"
          side="right"
          width={visibleTabMinWidth}
          triggerRef={overlayTriggerRef}
        >
          {panel}
        </Drawer>
      )}

      <SpecDocumentPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        inventory={inventory}
        restoreFocusTo={() => searchOriginRef.current}
        currentPath={document}
        onSelect={(node) => onOpenDocument(node.path)}
        /* Starting an exploration opens the document it just created: the point of creating
         * it here is that the conversation now has a subject, and leaving the operator to go
         * find it would put the step back that this removes. */
        onCreate={(title) => startExploration(title)}
      />
    </div>
  )
}
