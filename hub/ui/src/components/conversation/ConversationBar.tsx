import * as React from 'react'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import { Icon } from '@/components/common/Icon'
import { ContextUsageIndicator } from '@/components/context/ContextUsageIndicator'
import { Button } from '@/components/ui/button'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { agentColorVars } from '@/lib/agentColors'
import { formatDuration, formatTokens, formatTokensExact } from '@/lib/format'
import '@/styles/conversation.css'

/** The conversation's one bar, replacing the project header above it plus a header row of three
 *  icon buttons, a status chip, a token count and four text buttons (which wrapped to a second
 *  line at 900px).
 *
 *  Left: who (agent dot and name) and what (the conversation's title, renamed in place), then how
 *  it is going ("working · 2m 14s" with the pulse, or "idle"). Right: the context ring, Checkpoint,
 *  Stop while a turn runs, and one overflow menu for the rest. It never wraps; the title gives way. */
export interface ConversationBarProps {
  agent: AgentSummary
  conversation: AgentConversation | null
  /** The conversation's label, `conversationLabel(conversation)`; "New conversation" for none. */
  title: string
  /** Rejecting puts the old title back; the caller reports why. */
  onRename?: (title: string) => void | Promise<unknown>
  isRunning: boolean
  /** The agent's live turn belongs to another of its conversations (F844). Shown in place of the
   *  working chip, with no Stop: the one that exists would stop that other turn. */
  busyElsewhere?: { title: string; waitingOnYou: boolean; onOpen?: () => void } | null
  /** Seconds the current turn has run; null when idle or unknown. */
  elapsedSeconds: number | null
  isStopping?: boolean
  onStop?: () => void
  /** Checkpoint: label and availability come from the same rules as today's control. */
  checkpointLabel?: string
  checkpointDisabledReason?: string | null
  onCheckpoint?: () => void
  /** This conversation's running total, for the menu's header line. */
  totalTokens?: number | null
  /** The AI credits it cost, already formatted ("0.28 AI credits"); null when none were reported. */
  creditsLabel?: string | null
  /** How many checkpoints this conversation has, for the menu item. */
  checkpointCount?: number
  onBackToProject?: () => void
  /** The bar's root, for callers that measure the panel's room (the interjection tray). */
  barRef?: React.Ref<HTMLDivElement>
  diagnosticsHidden: boolean
  onToggleDiagnostics: () => void
  onFoldAll: () => void
  onOpenCheckpoints?: () => void
  onOpenTrace?: () => void
  onOpenAgentSettings?: () => void
  onTogglePanel?: () => void
  panelOpen?: boolean
  onArchive?: () => void
}

export function ConversationBar({
  agent,
  conversation,
  title,
  onRename,
  isRunning,
  busyElsewhere = null,
  elapsedSeconds,
  isStopping = false,
  onStop,
  checkpointLabel = 'Checkpoint',
  checkpointDisabledReason = null,
  onCheckpoint,
  totalTokens,
  creditsLabel = null,
  checkpointCount = 0,
  onBackToProject,
  barRef,
  diagnosticsHidden,
  onToggleDiagnostics,
  onFoldAll,
  onOpenCheckpoints,
  onOpenTrace,
  onOpenAgentSettings,
  onTogglePanel,
  panelOpen = false,
  onArchive,
}: ConversationBarProps) {
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(title)
  /** The title just committed, shown until the conversation's own record catches up (or the
   *  rename is refused), so a rename reads as done the moment Enter is pressed. */
  const [renamedTo, setRenamedTo] = React.useState<string | null>(null)
  React.useEffect(() => setRenamedTo(null), [title])
  const shownTitle = renamedTo ?? title
  const color = agentColorVars(agent.color_index)

  const commit = () => {
    const next = draft.trim()
    setEditing(false)
    if (next && next !== shownTitle && onRename) {
      setRenamedTo(next)
      Promise.resolve(onRename(next)).catch(() => setRenamedTo(null))
    } else setDraft(shownTitle)
  }

  return (
    <div ref={barRef} className="conversation-header-surface aw-convbar" data-testid="conversation-header" style={{ '--agent-accent': color.accent } as React.CSSProperties}>
      <span className="aw-convbar-agent">
        <span data-testid={`conversation-agent-color-${agent.name}`} className={['aw-convbar-dot', isRunning ? 'aw-pulse' : ''].join(' ')} aria-hidden="true" />
        {agent.name}
      </span>
      <span className="aw-convbar-sep" aria-hidden="true">/</span>

      {editing ? (
        <input
          className="control-field aw-convbar-title-input"
          aria-label="Conversation title"
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit()
            if (e.key === 'Escape') {
              setDraft(shownTitle)
              setEditing(false)
            }
          }}
        />
      ) : (
        <button
          type="button"
          data-slot="convbar-title"
          className="aw-convbar-title"
          title={onRename && conversation ? `${shownTitle} — click to rename` : shownTitle}
          disabled={!onRename || !conversation}
          onClick={() => {
            setDraft(shownTitle)
            setEditing(true)
          }}
        >
          <span className="truncate">{shownTitle}</span>
          {onRename && conversation ? <Icon name="edit" size={12} className="aw-convbar-title-pencil" /> : null}
        </button>
      )}

      {busyElsewhere ? (
        <span className="aw-convbar-status" data-running="false" data-testid="conversation-busy-elsewhere" role="status" aria-live="polite">
          {busyElsewhere.waitingOnYou ? 'waiting on your answer in ' : 'busy in '}
          {busyElsewhere.onOpen ? (
            <button type="button" className="underline" onClick={busyElsewhere.onOpen}>{busyElsewhere.title}</button>
          ) : busyElsewhere.title}
        </span>
      ) : (
        <span className="aw-convbar-status" data-running={isRunning ? 'true' : 'false'} role="status" aria-live="polite">
          {isRunning ? `working${elapsedSeconds !== null ? ` · ${formatDuration(elapsedSeconds)}` : ''}` : agent.status === 'idle' ? 'idle' : agent.status}
        </span>
      )}

      <div className="aw-convbar-end">
        <ContextUsageIndicator value={conversation?.context_usage ?? null} />
        {isRunning && onStop ? (
          <Button variant="destructive" size="xs" onClick={onStop} disabled={isStopping} title="Stop the turn that is running">
            <Icon name="stop" size={12} />
            {isStopping ? 'Stopping…' : 'Stop'}
          </Button>
        ) : null}
        {onCheckpoint ? (
          // Present and labelled whether or not it can be used: an unavailable checkpoint states its
          // reason rather than being omitted, so the bar does not shift between agents.
          <Button
            variant="outline"
            size="xs"
            data-testid="conversation-handoff"
            onClick={onCheckpoint}
            disabled={checkpointDisabledReason !== null}
            aria-label={checkpointDisabledReason ? `${checkpointLabel} — ${checkpointDisabledReason}` : checkpointLabel}
            title={checkpointDisabledReason ?? 'Write a checkpoint and hand this conversation to a fresh one'}
          >
            <Icon name="move_up" size={13} />
            {checkpointLabel}
          </Button>
        ) : null}
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="icon-xs" data-testid="conversation-more" aria-label="More conversation actions" title="More">
              <Icon name="more_horiz" size={15} />
            </Button>
          </MenuTrigger>
          <MenuContent style={{ minWidth: 236 }}>
            {totalTokens ? (
              <MenuLabel>
                <span data-testid="conversation-token-total" title={`${formatTokensExact(totalTokens)} used across this conversation`}>
                  {`This conversation · ${formatTokens(totalTokens)}${creditsLabel ? ` · ${creditsLabel}` : ''}`}
                </span>
              </MenuLabel>
            ) : null}
            {onOpenCheckpoints ? (
              <MenuItem icon="event_note" data-testid="conversation-checkpoints-toggle" onSelect={onOpenCheckpoints}>
                {checkpointCount > 0 ? `Checkpoints (${checkpointCount})` : 'Checkpoints'}
              </MenuItem>
            ) : null}
            {onOpenTrace ? <MenuItem icon="monitoring" onSelect={onOpenTrace}>Trace of the last turn</MenuItem> : null}
            <MenuItem icon={diagnosticsHidden ? 'visibility' : 'visibility_off'} onSelect={onToggleDiagnostics}>
              {diagnosticsHidden ? 'Show diagnostics' : 'Hide diagnostics'}
            </MenuItem>
            <MenuItem icon="unfold_less" onSelect={onFoldAll}>Fold all turns</MenuItem>
            {onTogglePanel ? (
              <MenuItem icon="right_panel_close" data-testid="conversation-toggle-panel" onSelect={onTogglePanel}>
                {panelOpen ? 'Hide side panel' : 'Show side panel'}
              </MenuItem>
            ) : null}
            {onOpenAgentSettings ? (
              <>
                <MenuSeparator />
                <MenuItem icon="settings" data-testid="conversation-agent-settings" onSelect={onOpenAgentSettings}>{`${agent.name} settings`}</MenuItem>
              </>
            ) : null}
            {onBackToProject ? (
              <>
                <MenuSeparator />
                <MenuItem icon="arrow_left" onSelect={onBackToProject}>Back to project</MenuItem>
              </>
            ) : null}
            {onArchive && conversation ? (
              <>
                <MenuSeparator />
                <MenuItem icon="archive" destructive onSelect={onArchive}>Archive conversation</MenuItem>
              </>
            ) : null}
          </MenuContent>
        </Menu>
      </div>
    </div>
  )
}
