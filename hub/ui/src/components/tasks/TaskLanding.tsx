import { useState } from 'react'

import { readableApiError } from '@/api/client'
import { useLandHeldLanding, useTaskChecks, type TaskLanding as Landing } from '@/api/tasks'
import { Button } from '@/components/ui/button'

/**
 * Beside Land, once the work is approved: where it is on its way to the main branch
 * (`approved-work-merges-in-batches`, FR the-landing-is-visible). Queued with its place in the
 * project's queue; checking in a batch, with how long the batch has run and how long the previous
 * one took; held, and on what (a prerequisite, or failures main shares, which one reason lands);
 * landed, with the commit; or sent back, with the failing output. Reads the checks route, which a
 * `task_landing_changed` event refreshes without a reload.
 */

const short = (sha?: string | null) => (sha ? sha.slice(0, 8) : '')
const minutes = (seconds: number) => Math.max(1, Math.round(seconds / 60))
const unit = (seconds: number) =>
  seconds < 90 ? `${Math.max(0, Math.round(seconds))}s` : `${minutes(seconds)} min`

function HeldOnMain({ taskId }: { taskId: string }) {
  const [reason, setReason] = useState('')
  const land = useLandHeldLanding(taskId)
  return (
    <form
      className="flex flex-wrap items-center gap-1.5"
      onSubmit={(event) => {
        event.preventDefault()
        if (reason.trim()) land.mutate(reason.trim())
      }}
    >
      <input
        aria-label="Why land over the failures main shares"
        data-testid={`task-landing-reason-${taskId}`}
        className="text-[11px] px-1.5 py-0.5 rounded border min-w-0 flex-1"
        style={{ borderColor: 'var(--border)', background: 'var(--surface-2)' }}
        placeholder="Reason to land the batch anyway"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
      />
      <Button type="submit" size="sm" variant="outline" disabled={!reason.trim() || land.isPending}>
        {land.isPending ? 'Landing…' : 'Land batch'}
      </Button>
      {land.error && (
        <p role="alert" className="text-[11px] w-full" style={{ color: 'var(--red)' }}>
          {readableApiError(land.error, 'The batch could not be landed.')}
        </p>
      )}
    </form>
  )
}

/** The landing's state in one line; a batch's run time is the Hub's, refetched while it runs. */
function landingSentence(landing: Landing): string {
  const batch = landing.batch
  switch (landing.state) {
    case 'queued':
      return landing.position != null
        ? `Queued to land · ${landing.position === 1 ? 'next' : `#${landing.position} in the queue`}`
        : 'Queued to land'
    case 'checking':
    case 'landing': {
      const ran = batch?.seconds ?? 0
      const tasks = batch ? batch.task_ids.length : 1
      const previous = batch?.previous_seconds
      return (
        `${landing.state === 'landing' ? 'Landing' : 'Checking'} with ${tasks} ${tasks === 1 ? 'task' : 'tasks'}` +
        ` · running ${unit(ran)}` +
        (previous != null ? ` · the previous batch took ${unit(previous)}` : '')
      )
    }
    case 'held':
      return landing.waits_on
        ? `Held: waits for ${landing.waits_on} to land first`
        : 'Held for you: its batch fails only as main does'
    case 'landed':
      return landing.landed_sha ? `Landed on main at ${short(landing.landed_sha)}` : 'Landed on main'
    case 'sent_back':
      return 'Sent back by its landing batch'
    case 'not_landed':
      return 'Not landed'
  }
}

const COLOR: Record<Landing['state'], string> = {
  queued: 'var(--text-2)',
  checking: 'var(--text-2)',
  landing: 'var(--text-2)',
  held: 'var(--amber, var(--text-2))',
  landed: 'var(--green)',
  sent_back: 'var(--red)',
  not_landed: 'var(--red)',
}

export function TaskLanding({ taskId }: { taskId: string }) {
  const { data, error } = useTaskChecks(taskId, true)
  const landing = data?.landing ?? null
  if (error) {
    return (
      <span role="alert" className="text-[11px]" style={{ color: 'var(--red)' }}>
        {readableApiError(error, "This task's landing could not be read.")}
      </span>
    )
  }
  if (!landing) return null
  return (
    <div data-testid={`task-landing-${taskId}`} role="status" className="space-y-1 text-[11px]">
      <p data-testid={`task-landing-state-${taskId}`} style={{ color: COLOR[landing.state] }}>
        {landingSentence(landing)}
      </p>
      {landing.state === 'held' && !landing.waits_on && landing.reason && (
        <p style={{ color: 'var(--text-2)' }}>{landing.reason}</p>
      )}
      {landing.state === 'held' && !landing.waits_on && <HeldOnMain taskId={taskId} />}
      {(landing.state === 'sent_back' || landing.state === 'not_landed') && landing.reason && (
        <pre
          aria-label="Why it did not land"
          className="p-2 rounded overflow-x-auto max-h-48"
          style={{ background: 'var(--surface-3)', color: 'var(--text)', whiteSpace: 'pre-wrap' }}
        >
          {landing.reason.slice(-1500)}
        </pre>
      )}
      {landing.state === 'landed' && (landing.override_reason || landing.batch?.override_reason) && (
        <p style={{ color: 'var(--text-2)' }}>
          Landed over failures main shares: {landing.override_reason || landing.batch?.override_reason}
        </p>
      )}
    </div>
  )
}
