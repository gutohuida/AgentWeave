import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { MenuSelect } from '@/components/ui/menu'
import { agentColorVars } from '@/lib/agentColors'
import '@/styles/panel-tabs.css'

export interface WatchablePeer {
  name: string
  colorIndex: number | null | undefined
  /** "working", "waiting for an answer", "idle" — what the peer is doing, in words. */
  state: string
  working: boolean
}

export interface WatchableConversation {
  id: string
  title: string
  /** "now", "12m ago": when its last message arrived, already in words. */
  when: string
}

export interface WatchTabProps {
  peers: WatchablePeer[]
  peer: string
  onPeerChange: (name: string) => void
  conversations: WatchableConversation[]
  conversationId: string | null
  onConversationChange: (id: string) => void
  /** Switches the main view to this conversation, where the operator can talk to the peer. */
  onOpenConversation: () => void
  /** The peer's conversation, drawn by the app's own timeline, read-only. */
  children?: React.ReactNode
}

/** The side panel's Watch tab: another agent's conversation, live and read-only (operator,
 *  2026-11-12: watch only; talking to the peer is one click away, in the main view). */
export function WatchTab({ peers, peer, onPeerChange, conversations, conversationId, onConversationChange, onOpenConversation, children }: WatchTabProps) {
  const current = peers.find((p) => p.name === peer)
  // A live view opens at the newest message and stays there while output arrives, as the
  // conversation itself does; an operator who scrolled up to read is left where they are.
  const body = React.useRef<HTMLDivElement>(null)
  const pinned = React.useRef(true)
  React.useLayoutEffect(() => {
    const el = body.current
    pinned.current = true
    if (el) el.scrollTop = el.scrollHeight
  }, [peer, conversationId])
  React.useEffect(() => {
    const el = body.current
    if (!el) return undefined
    const follow = () => {
      if (pinned.current) el.scrollTop = el.scrollHeight
    }
    const mutations = new MutationObserver(follow)
    mutations.observe(el, { childList: true, subtree: true, characterData: true })
    const sizes = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(follow)
    sizes?.observe(el)
    return () => {
      mutations.disconnect()
      sizes?.disconnect()
    }
  }, [])
  const onScroll = () => {
    const el = body.current
    if (el) pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
  }
  return (
    <div className="aw-ptab" data-testid="watch-tab">
      <div className="aw-ptab-head">
        <div className="aw-ptab-controls">
          <MenuSelect<string>
            label="Agent to watch"
            value={peer}
            onChange={onPeerChange}
            maxWidth={200}
            options={peers.map((p) => ({
              value: p.name,
              label: p.name,
              detail: p.state,
              icon: <span className="aw-agent-dot" style={{ '--agent-accent': agentColorVars(p.colorIndex).accent } as React.CSSProperties} />,
            }))}
          />
          {conversations.length > 1 ? (
            <MenuSelect<string>
              label="Conversation"
              value={conversationId ?? ''}
              onChange={onConversationChange}
              maxWidth={220}
              options={conversations.map((c) => ({ value: c.id, label: c.title, detail: c.when }))}
            />
          ) : null}
        </div>
        <div className="aw-watch-status">
          {current?.working ? <span className="aw-watch-live" aria-hidden="true" /> : null}
          <span>{current ? `${current.name} is ${current.state}` : ''}</span>
          <span className="aw-watch-readonly">
            <Icon name="visibility" size={12} />
            Watching
          </span>
        </div>
      </div>
      <div className="aw-ptab-scroll aw-watch-body" ref={body} onScroll={onScroll}>
        {children}
      </div>
      <div className="aw-watch-foot">
        <span>You can’t send messages from here.</span>
        <Button size="xs" variant="outline" onClick={onOpenConversation}>
          Talk to {peer}
          <Icon name="arrow_forward" size={13} />
        </Button>
      </div>
    </div>
  )
}
