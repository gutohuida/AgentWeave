import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { clearComposerDraft, getComposerDraft, setComposerDraft } from '@/lib/composerDrafts'
import {
  acceptTriggerResult,
  detectComposerTrigger,
  formatMention,
  type ComposerTriggerMatch,
} from '@/lib/composerTrigger'
import { resolveTriggerResults } from '@/lib/composerTriggerSources'
import { ComposerTriggerMenu, type ComposerTriggerMenuItem } from './ComposerTriggerMenu'
import { ComposerModelControls } from './ComposerModelControls'
import { ComposerSpecControl } from './ComposerSpecControl'

export const COMPOSER_MIN_ROWS = 3
const COMPOSER_MAX_ROWS = 12
const COMPOSER_ROW_HEIGHT_PX = 20
export const COMPOSER_MAX_HEIGHT_PX = COMPOSER_ROW_HEIGHT_PX * COMPOSER_MAX_ROWS
export const COMPOSER_DRAFT_DEBOUNCE_MS = 300

export interface ComposerProps {
  agent: string
  projectId: string
  /** null identifies the not-yet-created conversation for this agent. */
  conversationId: string | null
  isRunning: boolean
  /** Resolves on a started-or-queued outcome, rejects on failure. */
  onSubmit: (text: string) => Promise<void>
  /** Allow sending with an empty box. Set while a pending question already has options
   *  selected: the send button then confirms that selection, so the panel needs no submit
   *  control of its own and free text and choices go out through one place. */
  canSubmitEmpty?: boolean
  /** Current draft text, for callers that need to react to typing — a pending question clears
   *  its selection once the operator starts writing instead. */
  onTextChange?: (text: string) => void
  /** Overrides the resting placeholder, e.g. while a question is waiting. */
  placeholder?: string
  /** Workspace paths backing the `@path`/`$skill` trigger sources — fetched once by the
   *  caller (design.md's caching mitigation), filtered client-side here per keystroke. */
  workspacePaths?: string[]
  /** The agent's bound runner CLI — resolves which catalog provider's models and
   * controls the composer offers (2026-08-04-hub-model-control-and-provisioning). Omitted
   * (or one the catalog doesn't declare) renders no model/control pills. */
  runner?: string | null
  /** The value each control will use if the operator sends without touching it — the
   * runner's own model / the catalog's declared default, resolved by the caller. */
  effectiveModel?: string | null
  effectiveControls?: Record<string, string>
  /** The overrides the operator has actively chosen this composer session; empty means
   * "no override, inherit the resolved effective values above." Sent with the next
   * message only when non-empty. */
  pendingOverrides?: Record<string, string>
  onPendingOverridesChange?: (overrides: Record<string, string>) => void
  /** Why this composer cannot send yet. Set on the new-conversation surface started from the
   *  recency view, where the message cannot go anywhere until an agent is chosen. Stated rather
   *  than left to a silently dead button. */
  disabledReason?: string
  /** Opens the specification document picker. Omitted on surfaces that have no document panel
   *  to open one into (the new-conversation surface), where the control renders nothing. */
  onOpenSpecPicker?: () => void
  onStartExploration?: () => void
  onStopExploring?: () => void
  /** Reopen a document not currently attached to this conversation. Optional -- omitted on
   *  surfaces with no real picker to open (the new-conversation surface), where the second
   *  control next to Explore does not render. */
  onOpenExistingSpec?: () => void
  specArmed?: boolean
  specBusy?: boolean
  /** The open document's display name, for the Spec pill. `null` means none is open. */
  specDocumentLabel?: string | null
  /** The files tab's "Insert into composer" (task 5.4, `2026-08-18-one-shell-three-panels`): a
   *  `@path` mention to append, keyed by `requestId` so a repeat press of the same file inserts
   *  again rather than being swallowed as an unchanged prop (the same `revealRequestId` shape
   *  `panelTabsStore` already uses for "open this again"). `null` means nothing pending. */
  insertPathRequest?: { path: string; requestId: number } | null
}

/**
 * Render this keyed by `${agent}::${conversationId ?? '__new__'}` from the parent so a
 * conversation switch remounts it — that mount/unmount boundary is what makes the draft
 * load-on-mount and flush-on-unmount below correct without re-deriving identity mid-life.
 */
export function Composer({
  agent,
  projectId,
  conversationId,
  isRunning,
  onSubmit,
  canSubmitEmpty = false,
  onTextChange,
  placeholder,
  workspacePaths = [],
  runner = null,
  effectiveModel = null,
  effectiveControls = {},
  pendingOverrides = {},
  onPendingOverridesChange = () => undefined,
  disabledReason,
  onOpenSpecPicker,
  onStartExploration,
  onStopExploring,
  onOpenExistingSpec,
  specArmed = false,
  specBusy = false,
  specDocumentLabel = null,
  insertPathRequest = null,
}: ComposerProps) {
  const [text, setText] = useState(() => getComposerDraft(projectId, agent, conversationId))
  const [submitting, setSubmitting] = useState(false)
  const [trigger, setTrigger] = useState<ComposerTriggerMatch | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const textRef = useRef(text)
  textRef.current = text
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const pendingCursorRef = useRef<number | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastInsertedRequestId = useRef<number | null>(null)

  const menuItems: ComposerTriggerMenuItem[] = trigger ? resolveTriggerResults(trigger, workspacePaths) : []

  useEffect(() => {
    setActiveIndex(0)
  }, [trigger])

  useEffect(() => {
    if (pendingCursorRef.current === null) return
    const position = pendingCursorRef.current
    pendingCursorRef.current = null
    textareaRef.current?.setSelectionRange(position, position)
  }, [text])

  const refreshTrigger = (value: string, cursor: number) => {
    setTrigger(detectComposerTrigger(value, cursor))
  }

  const acceptActiveResult = () => {
    if (!trigger || menuItems.length === 0) return
    const item = menuItems[Math.min(activeIndex, menuItems.length - 1)]
    const result = acceptTriggerResult(text, trigger, item.value)
    pendingCursorRef.current = result.cursor
    setText(result.text)
    setTrigger(null)
  }

  useEffect(() => {
    debounceRef.current = setTimeout(() => {
      setComposerDraft(projectId, agent, conversationId, text)
      debounceRef.current = null
    }, COMPOSER_DRAFT_DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
    }
  }, [text, projectId, agent, conversationId])

  useEffect(() => {
    // Flush-on-unmount, so navigating away before the debounce fires still persists the
    // draft. Deps are intentionally the mount identity only — this instance is remounted
    // (see the key contract above) whenever project/agent/conversation actually changes.
    return () => {
      setComposerDraft(projectId, agent, conversationId, textRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The files tab's "Insert into composer" (task 5.4) — a new `requestId` appends the mention to
  // whatever is already typed rather than replacing it, since unlike the `@`/`$` trigger there is
  // no open range to replace. A trailing space so a second insertion, or continued typing, never
  // runs straight into the mention it follows.
  useEffect(() => {
    if (!insertPathRequest || insertPathRequest.requestId === lastInsertedRequestId.current) return
    lastInsertedRequestId.current = insertPathRequest.requestId
    const mention = formatMention('path', insertPathRequest.path)
    setText((prev) => {
      const needsLeadingSpace = prev.length > 0 && !/\s$/.test(prev)
      return prev + (needsLeadingSpace ? ' ' : '') + mention + ' '
    })
    textareaRef.current?.focus()
  }, [insertPathRequest])

  // The composer's height follows its text, and it has to be an effect rather than an
  // `onInput` handler. `onInput` fires only for input the operator types, so every
  // programmatic change to `text` left the inline height at whatever the last keystroke
  // produced: sending a long message cleared the box but kept it tall until the operator
  // switched conversation and React remounted the element. Inserting a mention and
  // restoring a saved draft had the same gap, in the other direction — text arrived and
  // the box stayed short. Keying off `text` covers all four.
  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    // 'auto' first so the measurement shrinks as well as grows: scrollHeight never reports
    // less than the height already set, so without the reset the box could only get taller.
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`
  }, [text])

  const handleSend = async () => {
    const trimmed = text.trim()
    if ((!trimmed && !canSubmitEmpty) || submitting || disabledReason) return
    const typed = text
    // Cancel the pending debounced write before submitting: otherwise it can fire after
    // a successful clearComposerDraft below and resurrect the just-submitted text.
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    setSubmitting(true)
    setText('')
    try {
      await onSubmit(trimmed)
      onTextChange?.('')
      clearComposerDraft(projectId, agent, conversationId)
    } catch {
      setText(typed)
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (trigger) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        if (menuItems.length > 0) setActiveIndex((i) => (i + 1) % menuItems.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        if (menuItems.length > 0) setActiveIndex((i) => (i - 1 + menuItems.length) % menuItems.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        if (menuItems.length > 0) {
          e.preventDefault()
          acceptActiveResult()
          return
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setTrigger(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    onTextChange?.(e.target.value)
    refreshTrigger(e.target.value, e.target.selectionStart)
  }

  const handleCursorMove = (e: React.SyntheticEvent<HTMLTextAreaElement>) => {
    const target = e.target as HTMLTextAreaElement
    refreshTrigger(target.value, target.selectionStart)
  }

  return (
    <div
      className="composer-form flex flex-col gap-2"
      data-slot="composer"
      data-submitting={submitting ? 'true' : 'false'}
      aria-busy={submitting}
    >
      {/* Row one: the text area, full width, on its own row — text begins at the
          composer's leading edge (2026-08-04-hub-charcoal-visual-refresh). */}
      <div className="relative">
        {trigger && (
          <ComposerTriggerMenu
            items={menuItems}
            activeIndex={activeIndex}
            onHover={setActiveIndex}
            onSelect={(item) => {
              const result = acceptTriggerResult(text, trigger, item.value)
              pendingCursorRef.current = result.cursor
              setText(result.text)
              setTrigger(null)
              textareaRef.current?.focus()
            }}
          />
        )}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onKeyUp={(e) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
            handleCursorMove(e)
          }}
          onClick={handleCursorMove}
          placeholder={placeholder ?? (isRunning ? `${agent} is responding…` : `Message ${agent}…`)}
          rows={COMPOSER_MIN_ROWS}
          disabled={submitting}
          className="composer-textarea w-full resize-none border-0 bg-transparent px-2 py-2 text-xs disabled:opacity-50"
          style={{
            background: 'transparent',
            color: 'var(--text)',
            maxHeight: `${COMPOSER_MAX_HEIGHT_PX}px`,
            overflowY: 'auto',
            outline: 'none',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        />
      </div>

      {/* Row two: the control row — a leading slot and a trailing slot, not a fixed
          arrangement, so 2026-08-04-hub-model-control-and-provisioning's model/effort
          controls can join the leading slot without re-laying-out the composer.

          No recipient selector: a message goes to the agent whose conversation this is.
          The selector that used to sit here could redirect a submission to a different
          agent with no trace in the visible timeline. */}
      {/* `flex-wrap`, and every child free to shrink: the row is now shown between 420 and 560px
          and inside an overlay, where it used to assume it would never be narrow and overflowed
          its container instead — clipping the permission posture mid-word. Nothing leaves the row
          at any width; a control that disappears when the pane narrows is one the operator cannot
          find (design.md Decision 5). */}
      <div className="flex flex-wrap items-center justify-between gap-2" data-slot="composer-control-row">
        <div className="flex min-w-0 flex-wrap items-center gap-2" data-slot="composer-control-row-leading">
          <ComposerModelControls
            runner={runner}
            effectiveModel={pendingOverrides.model ?? effectiveModel}
            effectiveControls={{ ...effectiveControls, ...pendingOverrides }}
            onChangeModel={(modelId) =>
              onPendingOverridesChange({ ...pendingOverrides, model: modelId })
            }
            onChangeControl={(controlId, value) =>
              onPendingOverridesChange({ ...pendingOverrides, [controlId]: value })
            }
          />
          {onOpenSpecPicker && onStartExploration && onStopExploring && (
            <ComposerSpecControl
              documentLabel={specDocumentLabel}
              onOpenPicker={onOpenSpecPicker}
              onStartExploration={onStartExploration}
              onStopExploring={onStopExploring}
              onOpenExisting={onOpenExistingSpec}
              armed={specArmed}
              busy={specBusy}
            />
          )}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2" data-slot="composer-control-row-trailing">
          {disabledReason && (
            <span
              className="text-[11px]"
              data-testid="composer-disabled-reason"
              style={{ color: 'var(--text-3)' }}
            >
              {disabledReason}
            </span>
          )}
          <Button
            variant="primary"
            size="icon-sm"
            onClick={() => void handleSend()}
            aria-label="Send message"
            title={disabledReason}
            disabled={(!text.trim() && !canSubmitEmpty) || submitting || !!disabledReason}
            data-state={submitting ? 'busy' : text.trim() || canSubmitEmpty ? 'ready' : 'idle'}
          >
            <Icon name={submitting ? 'refresh' : 'send'} size={18} className={submitting ? 'composer-send-spinner' : undefined} />
          </Button>
        </div>
      </div>
    </div>
  )
}
