import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { PaneResizer } from '@/components/layout/PaneResizer'
import {
  DEFAULT_SPEC_PREFERENCES,
  SPEC_CHAT_MAX_WIDTH,
  SPEC_CHAT_MIN_WIDTH,
  SPEC_NAV_MAX_WIDTH,
  SPEC_NAV_MIN_WIDTH,
} from './specPreferences'

// The two side panes are now operator-sized through the shared `PaneResizer`. The comment that
// stood here said "the splitter is an explicit non-goal of this change" — that non-goal belonged
// to the change that wrote it, before `layout/PaneResizer.tsx` existed and became what the rest
// of the app uses. The constants below survive as the defaults and as the wide-mode budget.
export const SPEC_NAV_WIDTH = DEFAULT_SPEC_PREFERENCES.navWidth
export const SPEC_DOC_MIN_WIDTH = 520
export const SPEC_CHAT_WIDTH = DEFAULT_SPEC_PREFERENCES.chatWidth
/** What a divider costs the row. `PaneResizer` is an 11px strip with -5px margins either side. */
const DIVIDER_WIDTH = 1
/** The rail the chat pane leaves behind when collapsed, so the budget stays honest. */
const COLLAPSED_CHAT_WIDTH = 36

/**
 * The width below which the three panes stop fitting, and the drawers take over.
 *
 * Derived rather than written down. It was 1140 — exactly the three defaults — until the panes
 * gained dividers, at which point the same number was two pixels short and navigation silently
 * rendered narrower than its own default. A breakpoint that means "the panes no longer fit"
 * should be computed from what has to fit, so changing a default cannot leave the two disagreeing.
 */
export const SPEC_WIDE_BREAKPOINT =
  SPEC_NAV_WIDTH + SPEC_DOC_MIN_WIDTH + SPEC_CHAT_WIDTH + DIVIDER_WIDTH * 2

export type WorkspaceMode = 'wide' | 'compact'

/**
 * The measured width of the workspace, or `null` before the first real measurement.
 *
 * Measured rather than taken from the viewport: the Hub rail and any other chrome already
 * consume viewport width, so a media query would report "wide" while the document is actually
 * being crushed. The same measurement decides the mode and budgets the pane widths.
 *
 * A zero width means "not laid out yet", not "narrow". Acting on it would flash the compact
 * drawers before anything has been measured, so it is ignored rather than recorded.
 */
export function useWorkspaceWidth(ref: React.RefObject<HTMLElement>): number | null {
  const [width, setWidth] = useState<number | null>(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const apply = (measured: number) => {
      if (measured <= 0) return
      setWidth(measured)
    }

    apply(element.getBoundingClientRect().width)

    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) apply(entry.contentRect.width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  return width
}

export function useWorkspaceMode(ref: React.RefObject<HTMLElement>): WorkspaceMode {
  const width = useWorkspaceWidth(ref)
  return width === null || width >= SPEC_WIDE_BREAKPOINT ? 'wide' : 'compact'
}

/**
 * A compact-mode surface. Radix Dialog gives the focus trap, Escape handling,
 * and focus restoration FR-9 requires without adding a dependency.
 */
function Drawer({
  open,
  onOpenChange,
  title,
  side,
  width,
  triggerRef,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  side: 'left' | 'right'
  width: number
  /** Focus returns here on close, however the drawer was dismissed. */
  triggerRef: React.RefObject<HTMLButtonElement>
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay style={{ position: 'fixed', inset: 0, background: 'var(--scrim)' }} />
        <Dialog.Content
          aria-label={title}
          // Restore focus to the control that opened the drawer rather than
          // relying on which element happened to be focused at mount time.
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            triggerRef.current?.focus()
          }}
          style={{
            position: 'fixed',
            top: 0,
            bottom: 0,
            [side]: 0,
            width: `min(${width}px, 92vw)`,
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--surface)',
            [side === 'left' ? 'borderRight' : 'borderLeft']: '1px solid var(--border)',
          }}
        >
          <div
            className="flex items-center justify-between px-3 py-2 shrink-0"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <Dialog.Title style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>
              {title}
            </Dialog.Title>
            <Dialog.Close
              aria-label={`Close ${title}`}
              style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer' }}
            >
              <Icon name="close" size={16} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            {title} panel for the current specification workspace.
          </Dialog.Description>
          <div className="flex-1 min-h-0 overflow-hidden">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

interface SpecWorkspaceProps {
  navigation: ReactNode
  document: ReactNode
  chat: ReactNode
  chatCollapsed: boolean
  onChatCollapsedChange: (collapsed: boolean) => void
  /** Persisted pane widths. Both are supplied by the page from its stored preferences, so a
   *  width the operator chose survives a reload. */
  navWidth?: number
  chatWidth?: number
  onNavWidthChange?: (width: number) => void
  onChatWidthChange?: (width: number) => void
}

export function SpecWorkspace({
  navigation,
  document: documentPane,
  chat,
  chatCollapsed,
  onChatCollapsedChange,
  navWidth = SPEC_NAV_WIDTH,
  chatWidth = SPEC_CHAT_WIDTH,
  onNavWidthChange,
  onChatWidthChange,
}: SpecWorkspaceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const measuredWidth = useWorkspaceWidth(containerRef)
  const mode =
    measuredWidth === null || measuredWidth >= SPEC_WIDE_BREAKPOINT ? 'wide' : 'compact'
  const [navDrawerOpen, setNavDrawerOpen] = useState(false)
  const [chatDrawerOpen, setChatDrawerOpen] = useState(false)
  const navTriggerRef = useRef<HTMLButtonElement>(null)
  const chatTriggerRef = useRef<HTMLButtonElement>(null)

  // Leaving compact mode must not strand an open drawer over the wide layout.
  useEffect(() => {
    if (mode === 'wide') {
      setNavDrawerOpen(false)
      setChatDrawerOpen(false)
    }
  }, [mode])

  const isWide = mode === 'wide'

  /* What each side pane may take without pushing the document below its minimum.
   *
   * `PaneResizer`'s own min/max are static, so they cannot know how much room there is: at the
   * breakpoint the three panes exactly fill the workspace, and dragging navigation to its 420
   * ceiling there would leave the document 100px short of `SPEC_DOC_MIN_WIDTH` and overflow.
   * Each side is budgeted against the *stored* width of the other, so the two do not chase each
   * other, and floored at its own minimum so the ceiling can never fall below the floor.
   *
   * The rendered width is clamped by the same budget rather than written back to preferences —
   * narrowing the window must not silently discard the width the operator chose for a wide one.
   */
  const budget = (otherWidth: number, min: number, max: number) => {
    if (measuredWidth === null) return max
    const available = measuredWidth - SPEC_DOC_MIN_WIDTH - otherWidth - DIVIDER_WIDTH * 2
    return Math.max(min, Math.min(max, available))
  }
  const navMax = budget(chatCollapsed ? COLLAPSED_CHAT_WIDTH : chatWidth, SPEC_NAV_MIN_WIDTH, SPEC_NAV_MAX_WIDTH)
  const chatMax = budget(navWidth, SPEC_CHAT_MIN_WIDTH, SPEC_CHAT_MAX_WIDTH)
  const effectiveNavWidth = Math.min(navWidth, navMax)
  const effectiveChatWidth = Math.min(chatWidth, chatMax)

  return (
    <div
      ref={containerRef}
      className="flex flex-row flex-1 min-w-0 w-full max-w-full min-h-0 overflow-hidden"
      data-testid="spec-workspace"
      data-mode={mode}
    >
      {isWide ? (
        <>
          <div
            className="shrink-0 min-h-0"
            data-testid="spec-nav-pane"
            style={{ width: effectiveNavWidth }}
          >
            {navigation}
          </div>
          {/* The divider owns the dividing line, so the pane above carries no border of its
              own — two separation signals on one boundary read as a seam. */}
          <PaneResizer
            width={effectiveNavWidth}
            onChange={(width) => onNavWidthChange?.(width)}
            defaultWidth={SPEC_NAV_WIDTH}
            min={SPEC_NAV_MIN_WIDTH}
            max={navMax}
            label="Resize document navigation"
            containerRef={containerRef}
          />
        </>
      ) : (
        <Drawer
          open={navDrawerOpen}
          onOpenChange={setNavDrawerOpen}
          title="Documents"
          side="left"
          width={SPEC_NAV_WIDTH + 40}
          triggerRef={navTriggerRef}
        >
          {navigation}
        </Drawer>
      )}

      <div
        className="flex flex-col flex-1 min-w-0 min-h-0"
        data-testid="spec-document-pane"
        style={{ minWidth: isWide ? SPEC_DOC_MIN_WIDTH : undefined }}
      >
        {!isWide && (
          <div
            className="flex items-center gap-2 px-3 py-1.5 shrink-0"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <button
              type="button"
              ref={navTriggerRef}
              onClick={() => setNavDrawerOpen(true)}
              aria-label="Open documents"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 8px',
                fontSize: 11,
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-2)',
                cursor: 'pointer',
              }}
            >
              <Icon name="menu_book" size={14} />
              Documents
            </button>
            <button
              type="button"
              ref={chatTriggerRef}
              onClick={() => setChatDrawerOpen(true)}
              aria-label="Open chat"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                marginLeft: 'auto',
                padding: '4px 8px',
                fontSize: 11,
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-2)',
                cursor: 'pointer',
              }}
            >
              <Icon name="chat" size={14} />
              Chat
            </button>
          </div>
        )}
        <div className="flex-1 min-h-0 overflow-hidden">{documentPane}</div>
      </div>

      {isWide ? (
        chatCollapsed ? (
          <div
            className="shrink-0 flex flex-col items-center pt-2"
            style={{ width: 36, borderLeft: '1px solid var(--border)' }}
          >
            <Button variant="ghost" size="icon-xs" onClick={() => onChatCollapsedChange(false)} aria-label="Expand chat">
              <Icon name="chat" size={16} />
            </Button>
          </div>
        ) : (
          <>
            {/* Measured from the container's right edge, so this reports the chat pane's own
                width rather than everything to its left. */}
            <PaneResizer
              width={effectiveChatWidth}
              onChange={(width) => onChatWidthChange?.(width)}
              defaultWidth={SPEC_CHAT_WIDTH}
              min={SPEC_CHAT_MIN_WIDTH}
              max={chatMax}
              label="Resize chat"
              containerRef={containerRef}
              side="right"
            />
            <div
              className="flex flex-col shrink-0 min-h-0"
              data-testid="spec-chat-pane"
              style={{ width: effectiveChatWidth }}
            >
              <div className="flex justify-end px-1 pt-1 shrink-0">
                <Button variant="ghost" size="icon-xs" onClick={() => onChatCollapsedChange(true)} aria-label="Collapse chat">
                  <Icon name="right_panel_close" size={16} />
                </Button>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden">{chat}</div>
            </div>
          </>
        )
      ) : (
        <Drawer
          open={chatDrawerOpen}
          onOpenChange={setChatDrawerOpen}
          title="Chat"
          side="right"
          width={SPEC_CHAT_WIDTH}
          triggerRef={chatTriggerRef}
        >
          {chat}
        </Drawer>
      )}
    </div>
  )
}
