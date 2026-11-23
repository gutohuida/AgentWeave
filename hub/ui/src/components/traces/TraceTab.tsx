import { ConversationTraceBody } from '@/components/traces/ConversationTraceDrawer'
import { TraceDrawerBody } from '@/components/traces/TraceDrawer'
import type { TraceTarget } from '@/store/panelTabsStore'
import '@/styles/traces.css'

/**
 * The thread side panel's Trace tab (leaner-navigation FR-4): the thread's whole trace, or one run's,
 * read in the panel rather than a drawer so the operator stays in the thread. The bodies are the
 * drawers' own, so what the trace says is the same wherever it is opened.
 */
export function TraceTab({
  target,
  conversationId,
  title,
  agent,
}: {
  target: TraceTarget
  conversationId: string | null
  title: string
  agent: string
}) {
  if (target.scope === 'run') {
    return (
      <div className="flex h-full min-h-0 flex-col" data-testid="trace-tab" data-scope="run" data-run-id={target.runId}>
        <TraceDrawerBody key={target.runId} runId={target.runId} />
      </div>
    )
  }
  if (!conversationId) {
    return (
      <p className="p-4 text-xs" data-testid="trace-tab-empty" style={{ color: 'var(--text-3)' }}>
        This thread has no runs yet, so there is no trace to show.
      </p>
    )
  }
  return (
    <div className="h-full min-h-0 overflow-auto" data-testid="trace-tab" data-scope="thread" data-conversation-id={conversationId}>
      <ConversationTraceBody key={conversationId} conversationId={conversationId} title={title} agent={agent} />
    </div>
  )
}
