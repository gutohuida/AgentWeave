import { useEffect, useRef, useState } from 'react'
import {
  conversationErrorMessage,
  conversationLabel,
  useArchiveConversation,
  useRenameConversation,
  useUnarchiveConversation,
  type AgentConversation,
} from '@/api/agentChat'
import { Icon } from '@/components/common/Icon'
import { loopTabId, usePanelTabsStore } from '@/store/panelTabsStore'
import { RowMenu, type RowMenuItem } from './RowMenu'

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
                className="shrink-0 text-[10px]"
                style={{ color: 'var(--text-3)' }}
                title="Started by another agent"
              >
                peer
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
            className="flex min-w-0 items-center gap-0.5 rounded px-1 py-0.5 text-[10px]"
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
            <Icon name="sync" size={11} className="shrink-0" aria-hidden="true" />
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
          className="px-2 pb-1 text-[10px]"
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
