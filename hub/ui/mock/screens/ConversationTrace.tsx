import * as React from 'react'
import type { AgentConversation } from '@/api/agentChat'
import type { AgentSummary } from '@/api/agents'
import type { TraceDetail } from '@/api/traces'
import { ConversationBar } from '@/components/conversation/ConversationBar'
import { EmptyState } from '@/components/common/EmptyState'
import { Drawer } from '@/components/layout/Drawer'
import { ConversationTrace as ConversationTraceView } from '@/components/traces/ConversationTrace'
import { numberRuns, type ConversationRun, type RunSelection } from '@/components/traces/conversationTraceModel'
import { Segmented } from '@/components/ui/segmented'
import { hubDate } from '@/lib/hubTime'
import { agents } from '../fixtures'
import recorded from '../fixtures/conversation_traces.json'
import type { ScreenProps } from '../routes'

/** Recorded read-only from the operator's Hub on 2026-11-06 with
 *  `py -3.11 mock/record_conversation_trace.py`: three of this repository's conversations, each
 *  run's whole trace. The first was carried over from the third. */
type Recorded = Record<
  string,
  {
    conversation: { id: string; agent: string; title: string; origin: string; continued_from: { id: string; title: string } | null }
    runs: ConversationRun[]
    details: Record<string, TraceDetail>
  }
>
const CONVERSATIONS = recorded as unknown as Recorded
const IDS = Object.keys(CONVERSATIONS)

const DRAWER_WIDTH = 1120

function agentNamed(name: string): AgentSummary {
  // mock state: the replica's roster has no Architect or QA; the bar borrows its first agent's shape.
  const found = agents.find((a) => a.name === name)
  return found ?? ({ ...agents[0]!, name } as AgentSummary)
}

export default function ConversationTrace({ route, go }: ScreenProps) {
  const id = route.kind === 'conversation-trace' && route.conversationId && CONVERSATIONS[route.conversationId] ? route.conversationId : IDS[0]!
  const rec = CONVERSATIONS[id]!
  const runs = React.useMemo(() => numberRuns(rec.runs), [rec])
  // The mock's clock: five minutes after the conversation's last turn ended.
  const now = React.useMemo(
    () => new Date(Math.max(...rec.runs.map((r) => hubDate(r.end_time ?? r.start_time).getTime())) + 5 * 60_000),
    [rec],
  )
  const [selection, setSelection] = React.useState<RunSelection>({ from: 1, to: runs.length, since: 'all' })
  React.useEffect(() => setSelection({ from: 1, to: runs.length, since: 'all' }), [runs.length, id])
  const [open, setOpen] = React.useState(true)
  const triggerRef = React.useRef<HTMLButtonElement | null>(null)
  const continued = rec.conversation.continued_from
  const continuedRecorded = continued && CONVERSATIONS[continued.id] ? continued : null

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 px-4 py-2" style={{ borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-3)' }}>
        <span>Mock · recorded conversation</span>
        <Segmented
          label="Recorded conversation"
          size="xs"
          value={id}
          onChange={(next) => go({ kind: 'conversation-trace', conversationId: next })}
          options={IDS.map((cid) => ({ value: cid, label: `${CONVERSATIONS[cid]!.conversation.agent} · ${CONVERSATIONS[cid]!.runs.length} turns` }))}
        />
      </div>
      <ConversationBar
        agent={agentNamed(rec.conversation.agent)}
        conversation={{ id, title: rec.conversation.title } as unknown as AgentConversation}
        title={rec.conversation.title}
        isRunning={false}
        elapsedSeconds={null}
        diagnosticsHidden={false}
        onToggleDiagnostics={() => undefined}
        onFoldAll={() => undefined}
        onOpenConversationTrace={() => setOpen(true)}
        onOpenTrace={() => undefined}
      />
      <div className="flex flex-1 items-center justify-center">
        <EmptyState
          icon="monitoring"
          title="The conversation's turns"
          description="Mock: the conversation itself is not recorded. Its menu (⋯ in the bar above) opens “Trace of this conversation”."
        />
      </div>
      <Drawer open={open} onOpenChange={setOpen} title="Trace of this conversation" side="right" width={DRAWER_WIDTH} triggerRef={triggerRef}>
        {open ? (
          <ConversationTraceView
            key={id}
            title={rec.conversation.title}
            agent={rec.conversation.agent}
            runs={runs}
            details={rec.details}
            selection={selection}
            onSelection={setSelection}
            continuedFrom={continued}
            onOpenContinued={continuedRecorded ? () => go({ kind: 'conversation-trace', conversationId: continuedRecorded.id }) : undefined}
            now={now}
          />
        ) : null}
      </Drawer>
    </div>
  )
}
