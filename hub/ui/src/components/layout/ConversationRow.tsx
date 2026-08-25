import { useEffect, useRef, useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import {
  conversationErrorMessage,
  conversationLabel,
  useArchiveConversation,
  useRenameConversation,
  useUnarchiveConversation,
  type AgentConversation,
} from '@/api/agentChat'
import { Icon } from '@/components/common/Icon'
import { hubDate } from '@/lib/hubTime'
import { loopTabId, usePanelTabsStore } from '@/store/panelTabsStore'
import { RowMenu, type RowMenuItem } from './RowMenu'

/**
 * A conversation's age, in the width a rail row can spare.
 *
 * `formatDistanceToNow` — what the agent row one level up uses — produces "about 2 hours ago",
 * which is right on a line of its own and impossible beside a title that is already truncating.
 * This is the compact form (`2m`, `1h`, `3d`), floored rather than rounded so a row never claims
 * to be newer than it is.
 *
 * Why it is needed at all: a rail of five threads called "New conversation" has no ordering cue
 * whatsoever, and `RecencyView` — whose entire purpose is recency — was sorting by a fact it
 * never showed. Read from `updated_at`, which the conversation payload already carries and which
 * is what both views sort on, so the number and the order can never disagree.
 *
 * Returns null for a timestamp that will not parse, so a Hub sending something unexpected costs
 * the row its age rather than printing "NaNm".
 *
 * Deliberately not exported: `react-refresh/only-export-components` (lint runs at
 * `--max-warnings 0`) refuses a non-component export from a component module, and `src/lib/` is
 * where this belongs the day a second caller wants it. `railHierarchy.test.tsx` covers the
 * boundaries through rendered rows instead, which is what actually ships anyway.
 */
function relativeShort(iso: string, now: number = Date.now()): string | null {
  const at = hubDate(iso).getTime()
  if (Number.isNaN(at)) return null
  const seconds = Math.max(0, Math.floor((now - at) / 1000))
  if (seconds < 60) return 'now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d`
  const weeks = Math.floor(days / 7)
  if (weeks < 52) return `${weeks}w`
  return `${Math.floor(days / 365)}y`
}

/** What each attention state looks like at rest.
 *
 * `waiting` is the one that matters: a run that stopped for the operator is invisible today
 * unless you open the conversation it stopped in, while the agent's answer timeout counts down.
 * Colour here is information, not decoration — an idle conversation carries none. */
const ATTENTION: Record<AgentConversation['attention'], { color: string; label: string } | null> = {
  running: { color: 'var(--green)', label: 'Running' },
  waiting: { color: 'var(--amber)', label: 'Waiting for you' },
  idle: null,
}

interface ConversationRowProps {
  projectId: string
  conversation: AgentConversation
  active: boolean
  onOpen: () => void
  /** The owning agent's identity colour, drawn as a persistent leading edge. Set in the recency
   *  view, where rows from different agents are interleaved; unset in the tree, where the parent
   *  agent row already carries the colour. Never a hover tint — that defeats scanning, which is
   *  the only reason the recency view exists. */
  agentColor?: string
  /** Shown in the recency view, where the agent is not implied by the row's position. */
  agentName?: string
  /** Set false inside a `LoopFiringGroup`, whose own row already names the loop once for every
   *  firing beneath it. Repeating it per row would spend the width the title needs to say the one
   *  thing that differs between them. */
  showLoopMarker?: boolean
  testId: string
}

export function ConversationRow({
  projectId,
  conversation,
  active,
  onOpen,
  agentColor,
  agentName,
  showLoopMarker = true,
  testId,
}: ConversationRowProps) {
  const attention = ATTENTION[conversation.attention]
  const label = conversationLabel(conversation)
  const archived = conversation.lifecycle === 'archived'
  // Computed at render, not on a timer: every surface that changes `updated_at` also invalidates
  // this list over SSE, so the row re-renders with a fresh reading anyway and a ticking clock per
  // row would be a cost with no reader.
  const age = relativeShort(conversation.updated_at)
  // Held as a const so the null check below narrows inside the click handler too.
  const loop = (showLoopMarker ? conversation.loop : null) ?? null

  const [renaming, setRenaming] = useState(false)
  const [draft, setDraft] = useState(label)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const rename = useRenameConversation()
  const toArchive = useArchiveConversation()
  const toUnarchive = useUnarchiveConversation()
  const openTab = usePanelTabsStore((state) => state.openTab)

  useEffect(() => {
    if (renaming) inputRef.current?.select()
  }, [renaming])

  const target = { projectId, agent: conversation.agent, conversationId: conversation.id }

  const commitRename = () => {
    const title = draft.trim()
    setRenaming(false)
    // An unchanged or emptied title is a cancel, not a request the Hub should refuse.
    if (!title || title === conversation.title) return
    setError(null)
    rename.mutate(
      { ...target, title },
      { onError: (err) => setError(conversationErrorMessage(err, 'Could not rename')) },
    )
  }

  const items: RowMenuItem[] = archived
    ? [
        {
          id: 'unarchive',
          label: 'Unarchive',
          onSelect: () => {
            setError(null)
            toUnarchive.mutate(target, {
              onError: (err) => setError(conversationErrorMessage(err, 'Could not unarchive')),
            })
          },
        },
      ]
    : [
        {
          id: 'rename',
          label: 'Rename',
          onSelect: () => {
            setDraft(conversation.title ?? '')
            setRenaming(true)
          },
        },
        {
          id: 'archive',
          label: 'Archive',
          onSelect: () => {
            setError(null)
            // Refused with a reason when a run is live or a queued entry is undelivered; that
            // reason is why this is not a fire-and-forget.
            toArchive.mutate(target, {
              onError: (err) => setError(conversationErrorMessage(err, 'Could not archive')),
            })
          },
        },
      ]

  return (
    <div className="row-group flex flex-col">
      <div className="flex items-center gap-1">
        {renaming ? (
          <input
            ref={inputRef}
            className="row-item"
            data-testid={`${testId}-rename`}
            aria-label={`Rename ${label}`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commitRename}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                commitRename()
              }
              if (event.key === 'Escape') {
                event.preventDefault()
                setRenaming(false)
              }
            }}
            style={{ color: 'var(--text)', outline: 'none' }}
          />
        ) : (
          <button
            type="button"
            className="row-item min-w-0 flex-1"
            data-testid={testId}
            data-active={active ? 'true' : 'false'}
            /* Level 3 of the rail's selection ladder, and its leaf: the one row in navigation
             * that carries a resting fill, because it is the one the operator is actually
             * reading. See the `.row-item[data-active]` block in index.css for the whole scale
             * and for why the fill is spent here and nowhere else. */
            data-depth="conversation"
            data-attention={conversation.attention}
            data-origin={conversation.origin}
            aria-current={active ? 'page' : undefined}
            onClick={onOpen}
            title={agentName ? `${label} — ${agentName}` : label}
          >
            {agentColor && (
              <span
                data-testid={`${testId}-edge`}
                aria-hidden="true"
                className="h-4 w-[2px] shrink-0 rounded-full"
                style={{ background: agentColor }}
              />
            )}
            <span className="min-w-0 flex-1 truncate">{label}</span>
            {conversation.origin === 'peer' && (
              <span
                data-testid={`${testId}-origin`}
                className="shrink-0 text-[11px]"
                style={{ color: 'var(--text-3)' }}
                title="Started by another agent"
              >
                peer
              </span>
            )}
            {/* Before the attention dot, never after: the dot is the highest-priority signal on
                the row and its position against the row's right edge has to be stable, or a
                waiting run appears to move when a neighbour's age changes width. The `title`
                carries the unabbreviated reading, since "2m" on its own is a guess. */}
            {age && (
              <span
                className="row-meta"
                data-testid={`${testId}-age`}
                title={`Last activity ${formatDistanceToNow(hubDate(conversation.updated_at), { addSuffix: true })}`}
              >
                {age}
              </span>
            )}
            {attention && (
              <span
                data-testid={`${testId}-attention`}
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: attention.color }}
                title={attention.label}
                aria-label={attention.label}
                role="img"
              />
            )}
          </button>
        )}
        {!renaming && loop && (
          /* A sibling of the row button, not a child of it: nesting one button inside another is
           * invalid, and this one has its own destination. It opens the loop's existing drill-down
           * tab rather than introducing a second place loop history lives — the rejected
           * alternative was a whole extra level in this rail (design D2: never give "open on the
           * right" two meanings).
           *
           * Deliberately not `.row-action`: that class hides at rest and reveals on hover, which is
           * right for an action and wrong for this. Which loop a thread came from is the fact that
           * tells it apart from one the operator typed, so it has to be legible while scanning. */
          <button
            type="button"
            /* `min-w-0` and a proportional cap rather than `shrink-0` and a fixed width: the rail
             * is narrow, and a fixed 96px marker truncated real conversation titles to "taste…"
             * — which loses the thing the row is primarily for to the thing that qualifies it.
             * The icon never shrinks, so a firing stays identifiable even when the name is cut;
             * the full name is on the tooltip and the accessible name either way. */
            className="flex min-w-0 items-center gap-0.5 rounded px-1 py-0.5 text-[11px]"
            data-testid={`${testId}-loop`}
            data-loop-id={loop.id}
            style={{ color: 'var(--text-3)', maxWidth: '40%' }}
            title={`Fired by the loop “${loop.label}” — open it`}
            aria-label={`Open loop ${loop.label}`}
            onClick={(event) => {
              event.stopPropagation()
              openTab(projectId, loopTabId(loop.id))
            }}
          >
            <Icon name="sync" size={13} className="shrink-0" aria-hidden="true" />
            <span className="truncate">{loop.label}</span>
          </button>
        )}
        {!renaming && (
          <RowMenu
            label={`Actions for ${label}`}
            testId={`${testId}-menu`}
            persistent={active}
            items={items}
          />
        )}
      </div>
      {error && (
        <span
          className="px-2 pb-1 text-[11px]"
          role="alert"
          data-testid={`${testId}-error`}
          style={{ color: 'var(--red)' }}
        >
          {error}
        </span>
      )}
    </div>
  )
}
