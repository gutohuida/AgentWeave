import { isSafeMentionValue } from '@/lib/fileMentions'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { LoadingThread } from '@/components/common/LoadingThread'
import { Button } from '@/components/ui/button'
import { clearComposerDraft, getComposerDraft, setComposerDraft } from '@/lib/composerDrafts'
import {
  deleteSelection,
  editorHtml,
  enclosingSpecBox,
  insertAtSelection,
  readEditor,
  readSelection,
  renderEditor,
  selectOffsets,
  setCaret,
  specBoxHtml,
} from '@/lib/composerEditor'
import { detectComposerTrigger, formatMention, triggerInsertion, type ComposerTriggerMatch } from '@/lib/composerTrigger'
import { MODEL_COMMAND, resolveTriggerResults, type SpecReferenceTarget } from '@/lib/composerTriggerSources'
import { findSpecReferences, formatSpecReference } from '@/lib/specReference'
import { ComposerTriggerMenu, type ComposerTriggerMenuItem } from './ComposerTriggerMenu'
import { ComposerModelControls } from './ComposerModelControls'
import { ComposerSpecControl } from './ComposerSpecControl'

export const COMPOSER_MIN_ROWS = 3
// 10 rows of 20px: the box grows from three lines (70px with its padding) to 200px, then scrolls.
const COMPOSER_MAX_ROWS = 10
const COMPOSER_ROW_HEIGHT_PX = 20
export const COMPOSER_MAX_HEIGHT_PX = COMPOSER_ROW_HEIGHT_PX * COMPOSER_MAX_ROWS
// Three rows plus the field's vertical padding (py-2): the height the old textarea rested at.
export const COMPOSER_MIN_HEIGHT_PX = COMPOSER_ROW_HEIGHT_PX * COMPOSER_MIN_ROWS + 16
export const COMPOSER_DRAFT_DEBOUNCE_MS = 300
const EMPTY_SPECS: SpecReferenceTarget[] = []

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
  /** The runner sends its own model to a model provider: `effectiveModel` is shown, not offered. */
  modelIsRunners?: boolean
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
  /** The terminal tab's "Send to agent": text to append to the draft, unsent. Keyed like `insertPathRequest`. */
  insertTextRequest?: { text: string; requestId: number } | null
  /** The project's specification documents, as its document list reports them: the `@` menu's
   *  Specs group (`reference-a-spec-in-a-sentence-from-the-composer`, FR-1). */
  specDocuments?: SpecReferenceTarget[]
  /** Set while the document list is not known: the `@` menu says the specs are loading or could
   *  not be read, rather than showing no Specs as if the project had none. */
  specDocumentsStatus?: 'loading' | 'error'
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
  modelIsRunners = false,
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
  insertTextRequest = null,
  specDocuments = EMPTY_SPECS,
  specDocumentsStatus,
}: ComposerProps) {
  const [text, setText] = useState(() => getComposerDraft(projectId, agent, conversationId))
  const [submitting, setSubmitting] = useState(false)
  const [trigger, setTrigger] = useState<ComposerTriggerMatch | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [modelPickerRequest, setModelPickerRequest] = useState(0)
  const textRef = useRef(text)
  textRef.current = text
  const editorRef = useRef<HTMLDivElement>(null)
  // The value the field's DOM shows. The field's children are not React's: the operator's edits
  // change the DOM and are read back from it, and a change made to `text` by any other route (a
  // restored draft, a send, an insert request) is drawn into the DOM only when it differs from this.
  const domTextRef = useRef('')
  const pendingCursorRef = useRef<number | null>(null)
  // Where the caret last was in the field, for the reference control when the field is not focused.
  const lastCaretRef = useRef<number | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastInsertedRequestId = useRef<number | null>(null)
  const lastInsertedTextId = useRef<number | null>(null)

  const specsNotice =
    trigger?.kind === 'path' && specDocumentsStatus
      ? specDocumentsStatus === 'error'
        ? 'Specs could not be loaded'
        : 'Loading specs…'
      : undefined
  const menuItems: ComposerTriggerMenuItem[] = trigger
    ? resolveTriggerResults(trigger, workspacePaths, specDocuments).map((item) =>
        // Under a Specs heading saying why it is empty, the files sit under their own heading.
        specsNotice && !item.group ? { ...item, group: 'Files' as const } : item,
      )
    : []

  useEffect(() => {
    setActiveIndex(0)
  }, [trigger])

  const updateTrigger = (next: ComposerTriggerMatch | null) => {
    // An unchanged trigger keeps its object, so re-reading the caret does not reset the menu.
    setTrigger((prev) =>
      prev && next && prev.kind === next.kind && prev.query === next.query && prev.rangeStart === next.rangeStart
        ? prev
        : next,
    )
  }

  /** Read the field back into `text`; with `detect`, open or close the trigger menu at the caret. */
  const syncFromDom = (detect: boolean) => {
    const root = editorRef.current
    if (!root) return
    const value = readEditor(root).text
    domTextRef.current = value
    if (value !== textRef.current) {
      textRef.current = value
      setText(value)
      onTextChange?.(value)
    }
    const selection = readSelection(root)
    if (selection) lastCaretRef.current = selection.end
    if (detect) {
      updateTrigger(
        selection && selection.start === selection.end ? detectComposerTrigger(value, selection.end) : null,
      )
    }
  }

  // Draw `text` into the field whenever it changed by a route other than the field itself.
  useLayoutEffect(() => {
    const root = editorRef.current
    const pending = pendingCursorRef.current
    pendingCursorRef.current = null
    if (!root || text === domTextRef.current) return
    renderEditor(root, text)
    domTextRef.current = text
    if (pending !== null || document.activeElement === root) setCaret(root, pending ?? text.length)
  }, [text])

  // A caret can still land inside a box: cancelling an IME composition next to one leaves it there,
  // and the next key typed is then lost (spike RSSC-1). Move it to just after the box.
  useEffect(() => {
    const onSelectionChange = () => {
      const root = editorRef.current
      const selection = window.getSelection()
      if (!root || !selection || selection.rangeCount === 0 || !root.contains(selection.anchorNode)) return
      if (selection.isCollapsed) {
        const box = enclosingSpecBox(root, selection.anchorNode)
        if (box) {
          const range = document.createRange()
          range.setStartAfter(box)
          range.collapse(true)
          selection.removeAllRanges()
          selection.addRange(range)
          return
        }
      }
      const current = readSelection(root)
      if (current) lastCaretRef.current = current.end
    }
    document.addEventListener('selectionchange', onSelectionChange)
    return () => document.removeEventListener('selectionchange', onSelectionChange)
  }, [])

  const acceptItem = (item: ComposerTriggerMenuItem) => {
    const root = editorRef.current
    if (!root || !trigger) return
    root.focus()
    selectOffsets(root, trigger.rangeStart, trigger.rangeEnd)
    // `/model` is an action, not text: it opens the model picker and leaves nothing in the box.
    if (trigger.kind === 'slash-command' && item.value === MODEL_COMMAND) {
      deleteSelection(root)
      syncFromDom(false)
      setTrigger(null)
      setModelPickerRequest((n) => n + 1)
      return
    }
    if (item.spec) {
      // A spec becomes a box in place of the typed `@query`, then a space, with the caret after (FR-2).
      // One insertion: Chromium refuses `insertText` with the caret straight after a box it has
      // just inserted, and a second command would be a second undo step anyway.
      insertAtSelection(root, { html: specBoxHtml(item.spec) + ' ' })
    } else {
      insertAtSelection(root, { text: triggerInsertion(trigger, item.value) })
    }
    // The caret goes after what was inserted, whatever the browser's command left it.
    const inserted = item.spec ? formatSpecReference(item.spec) + ' ' : triggerInsertion(trigger, item.value)
    setCaret(root, trigger.rangeStart + inserted.length)
    syncFromDom(false)
    setTrigger(null)
  }

  const acceptActiveResult = () => {
    if (!trigger || menuItems.length === 0) return
    acceptItem(menuItems[Math.min(activeIndex, menuItems.length - 1)])
  }

  // The visible reference control (FR-5) types `@` at the caret, so the same menu opens and picking
  // from it inserts exactly what typing `@` and picking would.
  const openReferenceMenu = () => {
    const root = editorRef.current
    if (!root || submitting) return
    if (document.activeElement !== root || !readSelection(root)) {
      root.focus()
      setCaret(root, Math.min(lastCaretRef.current ?? textRef.current.length, textRef.current.length))
    }
    const value = readEditor(root).text
    const before = value.slice(0, readSelection(root)?.start ?? value.length)
    const afterBox = findSpecReferences(before).some((reference) => reference.end === before.length)
    const needsSpace = before.length > 0 && !/\s$/.test(before) && !afterBox
    insertAtSelection(root, { text: needsSpace ? ' @' : '@' })
    syncFromDom(true)
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
    // F409 D10: an unsafe path would type a live second mention.
    if (!isSafeMentionValue(insertPathRequest.path)) return
    const mention = formatMention('path', insertPathRequest.path)
    setText((prev) => {
      const needsLeadingSpace = prev.length > 0 && !/\s$/.test(prev)
      return prev + (needsLeadingSpace ? ' ' : '') + mention + ' '
    })
    editorRef.current?.focus()
  }, [insertPathRequest])

  useEffect(() => {
    if (!insertTextRequest || insertTextRequest.requestId === lastInsertedTextId.current) return
    lastInsertedTextId.current = insertTextRequest.requestId
    const addition = insertTextRequest.text
    setText((prev) => prev + (prev.length > 0 && !prev.endsWith(String.fromCharCode(10)) ? String.fromCharCode(10) : '') + addition)
    editorRef.current?.focus()
  }, [insertTextRequest])

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
    setTrigger(null)
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // Keys that end or steer an IME composition belong to it, not to the menu or to sending.
    if (e.nativeEvent.isComposing) return
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

  // Paste is plain text, except that references (the text a copied box carries) come back as boxes.
  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    const root = editorRef.current
    if (!root) return
    e.preventDefault()
    const pasted = e.clipboardData.getData('text/plain')
    if (!pasted) return
    if (findSpecReferences(pasted).length > 0) insertAtSelection(root, { html: editorHtml(pasted) })
    else insertAtSelection(root, { text: pasted })
    syncFromDom(true)
  }

  // Copying writes the selection's text form, so a copied box reads as plain text anywhere else.
  const handleCopy = (e: React.ClipboardEvent<HTMLDivElement>, cut: boolean) => {
    const root = editorRef.current
    const selection = root ? readSelection(root) : null
    if (!root || !selection || selection.start === selection.end) return
    e.preventDefault()
    e.clipboardData.setData('text/plain', readEditor(root).text.slice(selection.start, selection.end))
    if (cut) {
      deleteSelection(root)
      syncFromDom(true)
    }
  }

  // The resting placeholder teaches the triggers, which were otherwise found by accident.
  const restingPlaceholder =
    placeholder ??
    (isRunning ? `${agent} is responding…` : `Message ${agent} — @ to mention a spec or file, / for commands`)

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
            specsNotice={specsNotice}
            activeIndex={activeIndex}
            onHover={setActiveIndex}
            onSelect={acceptItem}
          />
        )}
        {text === '' && (
          <div
            aria-hidden="true"
            data-slot="composer-placeholder"
            className="pointer-events-none absolute left-0 top-0 px-2 py-2 text-[13.5px] leading-5"
            style={{ color: 'var(--text-3)' }}
          >
            {restingPlaceholder}
          </div>
        )}
        {/* A contenteditable field, not a textarea, so a spec reference can be a box that acts as
            one character (design D5). Its children are never React's: see `domTextRef`. Growth is
            CSS: three rows at rest, up to the maximum, then it scrolls. */}
        <div
          ref={editorRef}
          role="textbox"
          aria-multiline="true"
          aria-label={`Message ${agent}`}
          aria-placeholder={restingPlaceholder}
          aria-disabled={submitting || undefined}
          contentEditable={!submitting}
          suppressContentEditableWarning
          data-testid="composer-input"
          onInput={() => syncFromDom(true)}
          onKeyDown={handleKeyDown}
          onKeyUp={(e) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
            syncFromDom(true)
          }}
          onMouseUp={() => syncFromDom(true)}
          onCompositionEnd={() => syncFromDom(true)}
          onPaste={handlePaste}
          onCopy={(e) => handleCopy(e, false)}
          onCut={(e) => handleCopy(e, true)}
          className="composer-textarea w-full border-0 bg-transparent px-2 py-2 text-[13.5px] leading-5"
          style={{
            background: 'transparent',
            color: 'var(--text)',
            minHeight: `${COMPOSER_MIN_HEIGHT_PX}px`,
            maxHeight: `${COMPOSER_MAX_HEIGHT_PX}px`,
            overflowY: 'auto',
            outline: 'none',
            whiteSpace: 'pre-wrap',
            overflowWrap: 'anywhere',
            opacity: submitting ? 0.5 : undefined,
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
          {/* The reference menu without typing (FR-5): the operator did not know `@` existed.
              `onMouseDown` keeps the field's caret where it was. */}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Insert a reference"
            title="Insert a reference to a spec or file (@)"
            data-testid="composer-reference-control"
            disabled={submitting}
            onMouseDown={(event) => event.preventDefault()}
            onClick={openReferenceMenu}
          >
            <Icon name="mention" size={16} />
          </Button>
          <ComposerModelControls
            runner={runner}
            effectiveModel={modelIsRunners ? effectiveModel : (pendingOverrides.model ?? effectiveModel)}
            runnerModel={effectiveModel}
            modelIsRunners={modelIsRunners}
            modelPickerRequest={modelPickerRequest}
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
            {submitting ? <LoadingThread label="Sending" size="control" /> : <Icon name="send" size={18} />}
          </Button>
        </div>
      </div>
    </div>
  )
}
