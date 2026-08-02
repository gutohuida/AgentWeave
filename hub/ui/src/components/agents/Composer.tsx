import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { clearComposerDraft, getComposerDraft, setComposerDraft } from '@/lib/composerDrafts'

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
}

/**
 * Render this keyed by `${agent}::${conversationId ?? '__new__'}` from the parent so a
 * conversation switch remounts it — that mount/unmount boundary is what makes the draft
 * load-on-mount and flush-on-unmount below correct without re-deriving identity mid-life.
 */
export function Composer({ agent, projectId, conversationId, isRunning, onSubmit }: ComposerProps) {
  const [text, setText] = useState(() => getComposerDraft(projectId, agent, conversationId))
  const [submitting, setSubmitting] = useState(false)
  const textRef = useRef(text)
  textRef.current = text
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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

  const handleSend = async () => {
    const trimmed = text.trim()
    if (!trimmed || submitting) return
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
      clearComposerDraft(projectId, agent, conversationId)
    } catch {
      setText(typed)
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  return (
    <div className="flex gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isRunning ? `${agent} is responding…` : `Message ${agent}…`}
        rows={COMPOSER_MIN_ROWS}
        disabled={submitting}
        className="flex-1 px-3 py-2 rounded-lg text-xs resize-none border disabled:opacity-50"
        style={{
          background: 'var(--surface)',
          borderColor: 'var(--border)',
          color: 'var(--text-3)',
          maxHeight: `${COMPOSER_MAX_HEIGHT_PX}px`,
          overflowY: 'auto',
          outline: 'none',
          fontFamily: "'JetBrains Mono', monospace",
        }}
        onInput={(e) => {
          const t = e.target as HTMLTextAreaElement
          t.style.height = 'auto'
          t.style.height = `${Math.min(t.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`
        }}
      />
      <button
        onClick={() => void handleSend()}
        aria-label="Send message"
        disabled={!text.trim() || submitting}
        className="px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        style={{
          background: text.trim() && !submitting ? 'var(--blue)' : 'var(--surface)',
          color: text.trim() && !submitting ? '#fff' : 'var(--text-3)',
          border: 'none',
          cursor: 'pointer',
        }}
      >
        <Icon name="send" size={18} />
      </button>
    </div>
  )
}
