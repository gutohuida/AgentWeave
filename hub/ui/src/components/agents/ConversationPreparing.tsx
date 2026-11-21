import { useEffect, useState } from 'react'
import type { WorkspacePreparation } from '@/api/workspacePreparation'
import { Icon } from '@/components/common/Icon'
import { formatDateTime, formatDuration } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'

/** The checkout this thread's turn waits on, while the Hub prepares it.
 *
 *  A turn's checkout is written before its run exists, and on a large repository git takes tens
 *  of seconds; before this the thread showed nothing, or a Continue offer for work that was
 *  already starting. The status region is always rendered so the sentence is announced once when
 *  it appears (P16, P25); the line itself fades in after the app's loader delay, so a fast
 *  checkout never flashes (`.aw-delayed`). Word and icon, not colour alone (P21). */
export function ConversationPreparing({
  agent,
  preparation,
}: {
  agent: string
  preparation: WorkspacePreparation | undefined
}) {
  return (
    <div role="status" aria-live="polite" data-testid="conversation-preparing">
      {preparation && <PreparingLine agent={agent} preparation={preparation} />}
    </div>
  )
}

function PreparingLine({ agent, preparation }: { agent: string; preparation: WorkspacePreparation }) {
  const started = hubDate(preparation.started_at)
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.floor((now.getTime() - started.getTime()) / 1000))
  const what = preparation.task_id ? "the task's checkout" : "this thread's checkout"
  return (
    <span
      className="aw-delayed flex items-center gap-1.5 text-[11px]"
      style={{ color: 'var(--text-2)' }}
      title={`Started ${formatDateTime(started, now)}`}
    >
      <Icon name="git_branch_plus" size={14} />
      <span>
        Preparing {what}. {agent} starts once git has written it.
      </span>
      {/* Ticks every second, so it stays out of what the status region announces. */}
      <span aria-hidden="true" className="tabular" style={{ color: 'var(--text-3)' }}>
        {formatDuration(seconds)}
      </span>
    </span>
  )
}
