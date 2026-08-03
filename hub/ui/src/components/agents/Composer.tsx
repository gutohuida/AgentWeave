import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { clearComposerDraft, getComposerDraft, setComposerDraft } from '@/lib/composerDrafts'
import {
  acceptTriggerResult,
  detectComposerTrigger,
  type ComposerTriggerMatch,
} from '@/lib/composerTrigger'
import { resolveTriggerResults } from '@/lib/composerTriggerSources'
import { ComposerTriggerMenu, type ComposerTriggerMenuItem } from './ComposerTriggerMenu'
import { ComposerAgentSelector } from './ComposerAgentSelector'
import type { AgentLaunchability, AgentSummary } from '@/api/agents'

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
  /** Workspace paths backing the `@path`/`$skill` trigger sources — fetched once by the
   *  caller (design.md's caching mitigation), filtered client-side here per keystroke. */
  workspacePaths?: string[]
  agents?: AgentSummary[]
  launchability?: Record<string, AgentLaunchability>
  targetAgent?: string
  onTargetAgentChange?: (agent: string) => void
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
  workspacePaths = [],
  agents = [],
  launchability = {},
  targetAgent = agent,
  onTargetAgentChange = () => undefined,
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
    refreshTrigger(e.target.value, e.target.selectionStart)
  }

  const handleCursorMove = (e: React.SyntheticEvent<HTMLTextAreaElement>) => {
    const target = e.target as HTMLTextAreaElement
    refreshTrigger(target.value, target.selectionStart)
  }

  return (
    <div className="flex gap-2">
      <ComposerAgentSelector
        agents={agents.length > 0 ? agents : [{
          name: agent,
          status: 'idle',
          message_count: 0,
          active_task_count: 0,
        }]}
        launchability={launchability}
        selectedAgent={targetAgent}
        onSelect={onTargetAgentChange}
      />
      <div className="relative flex-1">
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
          placeholder={isRunning ? `${agent} is responding…` : `Message ${agent}…`}
          rows={COMPOSER_MIN_ROWS}
          disabled={submitting}
          className="w-full px-3 py-2 rounded-lg text-xs resize-none border disabled:opacity-50"
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
      </div>
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
