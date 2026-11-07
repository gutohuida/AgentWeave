import { useEffect, useMemo, useRef, useState } from 'react'
import { useConversationRuns, useRunTraces, useTraceTotals, type TraceDetail } from '@/api/traces'
import { useProjectCheckpoints } from '@/api/checkpoints'
import { Drawer } from '@/components/layout/Drawer'
import { LoadingThread } from '@/components/common/LoadingThread'
import { ConversationTrace } from '@/components/traces/ConversationTrace'
import {
  boundsOf,
  numberRuns,
  runFromSummary,
  selectRuns,
  type RunSelection,
} from '@/components/traces/conversationTraceModel'
import { readableApiError } from '@/api/client'

const DRAWER_WIDTH = 1120
const ALL: RunSelection = { from: 1, to: Number.MAX_SAFE_INTEGER, since: 'all' }

interface Viewed {
  id: string
  title: string
}

/**
 * Reads one conversation's trace and hands it to the view: the turn rows (every page of the list
 * route), the Hub's totals over the turns shown (as since/until), and a turn's spans only once the
 * turn is first unfolded. Mounted only while the drawer is open, so a closed one costs no request.
 */
function ConversationTraceBody({ conversationId, title, agent }: { conversationId: string; title: string; agent: string }) {
  const [viewed, setViewed] = useState<Viewed>({ id: conversationId, title })
  // Following 'Continued from' re-keys the whole body: another conversation, its own state.
  return <ConversationTraceOf key={viewed.id} viewed={viewed} agent={agent} onView={setViewed} />
}

function ConversationTraceOf({ viewed, agent, onView }: { viewed: Viewed; agent: string; onView: (next: Viewed) => void }) {
  const { data: summaries, isLoading, error } = useConversationRuns(viewed.id)
  const lineage = useProjectCheckpoints({ conversationId: viewed.id }).data?.lineage ?? null
  const earlier = lineage?.started_from ?? null

  const runs = useMemo(() => numberRuns((summaries ?? []).map(runFromSummary)), [summaries])
  const [selection, setSelection] = useState<RunSelection>(ALL)
  const effective = useMemo<RunSelection>(
    () => ({ ...selection, from: Math.max(1, selection.from), to: Math.min(runs.length, selection.to) }),
    [selection, runs.length],
  )

  const [now, setNow] = useState(() => new Date())
  const running = runs.some((r) => !r.ended)
  useEffect(() => {
    setNow(new Date())
    if (!running) return undefined
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [running, summaries])

  // The totals are the Hub's, over the turns shown: a range of start times that picks exactly them.
  const shown = useMemo(() => selectRuns(runs, effective, now.getTime()), [runs, effective, now])
  const narrowed = shown.length !== runs.length
  const bounds = narrowed ? boundsOf(shown) : null
  const totalsQuery = useTraceTotals(
    { conversation_id: viewed.id, operation: 'invoke_agent', since: bounds?.since, until: bounds?.until },
    null,
    runs.length > 0 && shown.length > 0,
  )

  // A turn's spans are read the first time it is unfolded, and not again.
  const [requested, setRequested] = useState<string[]>([])
  const traces = useRunTraces(requested)
  const details = useMemo(() => {
    const out: Record<string, TraceDetail | null | undefined> = {}
    requested.forEach((id, i) => {
      const q = traces[i]
      if (!q) return
      out[id] = q.data !== undefined ? q.data : q.error ? null : undefined
    })
    return out
  }, [requested, traces])

  if (isLoading) return <LoadingThread label="Loading the conversation’s turns" />
  if (error) {
    return (
      <p role="alert" className="aw-traces-error">
        {readableApiError(error, 'The conversation’s turns could not be listed.')}
      </p>
    )
  }
  return (
    <ConversationTrace
      conversationId={viewed.id}
      title={viewed.title}
      agent={agent}
      runs={runs}
      details={details}
      selection={effective}
      onSelection={setSelection}
      continuedFrom={earlier ? { id: earlier.conversation_id, title: earlier.title || 'an earlier conversation' } : null}
      onOpenContinued={earlier ? () => onView({ id: earlier.conversation_id, title: earlier.title || 'An earlier conversation' }) : undefined}
      onUnfold={(runId) => setRequested((prev) => (prev.includes(runId) ? prev : [...prev, runId]))}
      totals={totalsQuery.error ? undefined : totalsQuery.data?.totals ?? null}
      now={now}
    />
  )
}

/** The drawer a whole conversation's trace opens in, opened and closed by its caller. */
export function ConversationTraceDrawer({
  conversationId,
  title,
  agent,
  open,
  onOpenChange,
}: {
  conversationId: string
  title: string
  agent: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  return (
    <Drawer open={open} onOpenChange={onOpenChange} title="Trace of this conversation" side="right" width={DRAWER_WIDTH} triggerRef={triggerRef}>
      {open ? <ConversationTraceBody conversationId={conversationId} title={title} agent={agent} /> : null}
    </Drawer>
  )
}
