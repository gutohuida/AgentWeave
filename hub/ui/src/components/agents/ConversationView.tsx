import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AgentSummary } from '@/api/agents'
import { useSpecEvents, useSpecList } from '@/api/spec'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Drawer } from '@/components/layout/Drawer'
import { PaneResizer } from '@/components/layout/PaneResizer'
import { useWorkspaceWidth } from '@/components/layout/useWorkspaceWidth'
import { SpecDocumentPanel } from '@/components/spec/SpecDocumentPanel'
import { SpecDocumentPicker } from '@/components/spec/SpecDocumentPicker'
import { buildInventory } from '@/components/spec/specNavigation'
import {
  CONVERSATION_DEFAULT_WIDTH,
  CONVERSATION_MAX_WIDTH,
  CONVERSATION_MIN_WIDTH,
  DEFAULT_SPEC_PREFERENCES,
  SPEC_DOC_MIN_WIDTH,
  loadSpecPreferences,
  saveSpecPreferences,
} from '@/components/spec/specPreferences'
import { AgentOutputPanel } from './AgentOutputPanel'

/** What a divider costs the row. `PaneResizer` is an 11px strip with -5px margins either side. */
const DIVIDER_WIDTH = 1

/**
 * Below this the two columns stop fitting and the document becomes an overlay.
 *
 * Derived from what has to fit rather than written down, so changing either minimum cannot leave
 * the breakpoint and the layout disagreeing — the mistake the three-column workspace made once.
 */
export const DOCUMENT_COLUMN_BREAKPOINT =
  CONVERSATION_MIN_WIDTH + SPEC_DOC_MIN_WIDTH + DIVIDER_WIDTH

interface ConversationViewProps {
  agent: AgentSummary
  conversationId: string | null
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
  document,
  onSelectConversation,
  onOpenDocument,
  onBackToProject,
  onOpenAgentSettings,
}: ConversationViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const measuredWidth = useWorkspaceWidth(containerRef)
  const { data: specList, isLoading: listLoading, refetch: refetchList } = useSpecList()
  useSpecEvents()
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

  const documentOpen = document !== null
  const fitsAsColumn = measuredWidth === null || measuredWidth >= DOCUMENT_COLUMN_BREAKPOINT

  /* What the conversation may take without pushing the document below its minimum.
   *
   * `PaneResizer`'s own max is static and cannot know how much room there is, so the ceiling is
   * budgeted against the measurement and floored at the conversation's own minimum — a ceiling
   * that falls below the floor would invert the range. The rendered width is clamped by that
   * budget rather than written back, so narrowing the window does not silently discard the width
   * the operator chose for a wide one. */
  const conversationMax =
    measuredWidth === null
      ? CONVERSATION_MAX_WIDTH
      : Math.max(
          CONVERSATION_MIN_WIDTH,
          Math.min(CONVERSATION_MAX_WIDTH, measuredWidth - SPEC_DOC_MIN_WIDTH - DIVIDER_WIDTH),
        )
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

  const panel = document ? (
    <SpecDocumentPanel
      path={document}
      inventory={inventory}
      specList={specList}
      listLoading={listLoading}
      onSelectPath={(path) => onOpenDocument(path)}
      onOpenPicker={openPicker}
      onClose={() => onOpenDocument(null)}
      onRefresh={handleRefresh}
    />
  ) : null

  const conversation = (
    <AgentOutputPanel
      agent={agent}
      conversationId={conversationId}
      onSelectConversation={onSelectConversation}
      onBackToProject={onBackToProject}
      onOpenAgentSettings={onOpenAgentSettings}
      specDocumentPath={document}
    />
  )

  return (
    <div
      ref={containerRef}
      className="flex h-full min-w-0 flex-row overflow-hidden"
      data-testid="conversation-workspace"
      data-document={documentOpen ? 'open' : 'closed'}
      data-layout={documentOpen ? (fitsAsColumn ? 'column' : 'overlay') : 'full'}
    >
      <div
        className="flex min-h-0 min-w-0 flex-col"
        data-testid="conversation-pane"
        style={
          documentOpen && fitsAsColumn
            ? { width: conversationWidth, flex: '0 0 auto' }
            : { flex: '1 1 0%' }
        }
      >
        {/* Only in overlay mode: the document is open but not on screen, so there has to be a way
            back to it — and a stable element for focus to return to when the overlay closes. */}
        {documentOpen && !fitsAsColumn && (
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
              <Icon name="article" size={14} />
              <span className="truncate">{documentNode?.title ?? document}</span>
            </button>
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
          </div>
        )}
        <div className="min-h-0 flex-1">{conversation}</div>
      </div>

      {documentOpen && fitsAsColumn && (
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
            style={{ minWidth: SPEC_DOC_MIN_WIDTH }}
          >
            {panel}
          </div>
        </>
      )}

      {documentOpen && !fitsAsColumn && (
        <Drawer
          open={overlayOpen}
          onOpenChange={setOverlayOpen}
          title="Document"
          side="right"
          width={SPEC_DOC_MIN_WIDTH}
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
        onSelect={(node) => onOpenDocument(node.path)}
      />
    </div>
  )
}
