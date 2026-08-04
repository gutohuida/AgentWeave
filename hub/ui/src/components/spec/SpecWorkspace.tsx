import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'

// Fixed dimensions rather than a splitter: deterministic minimums solve the
// document squeeze with far less interaction and persistence surface, and the
// splitter is an explicit non-goal of this change.
export const SPEC_WIDE_BREAKPOINT = 1140
export const SPEC_NAV_WIDTH = 260
export const SPEC_DOC_MIN_WIDTH = 520
export const SPEC_CHAT_WIDTH = 360

export type WorkspaceMode = 'wide' | 'compact'

/**
 * Mode follows the measured Spec workspace, not the viewport: the Hub rail and
 * any future chrome already consume viewport width, so a media query would
 * report "wide" while the document is actually being crushed.
 */
export function useWorkspaceMode(ref: React.RefObject<HTMLElement>): WorkspaceMode {
  const [mode, setMode] = useState<WorkspaceMode>('wide')

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const apply = (width: number) => {
      // A zero width means "not laid out yet", not "narrow". Acting on it
      // would flash the compact drawers before the first real measurement.
      if (width <= 0) return
      setMode(width >= SPEC_WIDE_BREAKPOINT ? 'wide' : 'compact')
    }

    apply(element.getBoundingClientRect().width)

    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) apply(entry.contentRect.width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  return mode
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
}

export function SpecWorkspace({
  navigation,
  document: documentPane,
  chat,
  chatCollapsed,
  onChatCollapsedChange,
}: SpecWorkspaceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mode = useWorkspaceMode(containerRef)
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

  return (
    <div
      ref={containerRef}
      className="flex flex-row flex-1 min-w-0 w-full max-w-full min-h-0 overflow-hidden"
      data-testid="spec-workspace"
      data-mode={mode}
    >
      {isWide ? (
        <div
          className="shrink-0 min-h-0"
          data-testid="spec-nav-pane"
          style={{ width: SPEC_NAV_WIDTH, borderRight: '1px solid var(--border)' }}
        >
          {navigation}
        </div>
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
          <div
            className="flex flex-col shrink-0 min-h-0"
            data-testid="spec-chat-pane"
            style={{ width: SPEC_CHAT_WIDTH, borderLeft: '1px solid var(--border)' }}
          >
            <div className="flex justify-end px-1 pt-1 shrink-0">
              <Button variant="ghost" size="icon-xs" onClick={() => onChatCollapsedChange(true)} aria-label="Collapse chat">
                <Icon name="right_panel_close" size={16} />
              </Button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">{chat}</div>
          </div>
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
