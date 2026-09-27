import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { useJob, type JobUpdate } from '@/api/jobs'
import { useUpdateLoopSettings, type LoopSummary } from '@/api/loops'
import { cronDayAmbiguity, describeCron } from '@/lib/cron'
import { hubDate } from '@/lib/hubTime'
import { endingBucket } from './loopCounts'

/** A `datetime-local` input's value for an instant: wall-clock time in the operator's zone, which
 *  is what the input holds and what `JobForm` reads back with `new Date`. */
function toLocalInput(value?: string | null): string {
  if (!value) return ''
  const d = hubDate(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const FLOW_NEEDS_STOP = 'A flow needs a stop condition: keep “when the queue empties”, or set a stop time.'

const inputStyle = {
  fontSize: 11,
  background: 'var(--surface-2)',
  color: 'var(--text)',
  border: '1px solid var(--border)',
} as const

/** What each input opens on: the value that governs the *next* firing, so the staged value where
 *  there is one and the live value otherwise (design D1). A field is sent when it differs from this
 *  — diffing against the live values would send nothing for an operator who put the live agent back
 *  over a staged one, and the staged one would still be applied. */
function openingValues(loop: LoopSummary & { job_id: string }, job: { name: string; message: string; cron: string }) {
  const pending = loop.pending_edit
  return {
    name: job.name,
    agent: pending?.agent ?? loop.agent ?? '',
    message: job.message,
    cron: job.cron,
    purpose: pending?.purpose ?? loop.purpose ?? '',
    stopAt: toLocalInput(pending?.stop_at ?? loop.stop_at),
    stopWhenQueueEmpties: pending?.stop_when_queue_empties ?? loop.stop_when_queue_empties,
  }
}

/**
 * The loop's settings, read and edited from its own tab
 * (`a-flow-is-configured-from-its-own-tab`, design D1/D2). Read-only once the loop has ended or
 * been archived: an edit to a loop that will not fire again would be staged for nothing.
 */
export function LoopSettings({ loop }: { loop: LoopSummary & { job_id: string } }) {
  const { data: job, isError: jobFailed } = useJob(loop.job_id)
  const { data: agents, isError: agentsFailed } = useAgents()
  const update = useUpdateLoopSettings(loop.job_id)
  type Values = ReturnType<typeof openingValues>
  // `opened` is what the inputs opened on, frozen at Edit: a refresh mid-edit must not move the
  // baseline the diff is taken against.
  const [edit, setEdit] = useState<{ opened: Values; form: Values } | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)

  if (!job) {
    return jobFailed ? (
      <p role="alert" style={{ fontSize: 11, color: 'var(--amber)' }}>
        Could not load this loop's settings.
      </p>
    ) : null
  }

  const editing = edit !== null
  const opening = edit?.opened ?? openingValues(loop, job)
  const bucket = endingBucket(loop)
  const readOnly = !!loop.archived_at || bucket === 'completed' || bucket === 'stopped'
  const current = edit?.form ?? opening

  const agentNames = (agents ?? []).map((a) => a.name)
  if (opening.agent && !agentNames.includes(opening.agent)) agentNames.unshift(opening.agent)
  const controlWarning = editing && loop.control === 'creator' && current.agent !== opening.agent
  const cronPlain = describeCron(current.cron)
  const cronAmbiguity = cronDayAmbiguity(current.cron)

  const beginEdit = () => {
    const opened = openingValues(loop, job)
    setEdit({ opened, form: opened })
    setRefusal(null)
    update.reset()
  }

  const set = <K extends keyof Values>(key: K, value: Values[K]) => {
    if (edit) setEdit({ ...edit, form: { ...edit.form, [key]: value } })
    setRefusal(null)
  }

  const save = () => {
    const updates: JobUpdate = {}
    if (current.name !== opening.name) updates.name = current.name
    if (current.agent !== opening.agent) updates.agent = current.agent
    if (current.message !== opening.message) updates.message = current.message
    if (current.cron !== opening.cron) updates.cron = current.cron.trim()
    if (current.purpose !== opening.purpose) updates.purpose = current.purpose
    // An emptied stop-time input is "unchanged", never a clear: the Hub reads a null `stop_at` as
    // "not supplied", so a clear would answer 200 and change nothing.
    if (current.stopAt && current.stopAt !== opening.stopAt) {
      // `new Date`, not `hubDate`: the input holds the operator's wall-clock time, not a Hub timestamp.
      updates.stop_at = new Date(current.stopAt).toISOString()
    }
    if (current.stopWhenQueueEmpties !== opening.stopWhenQueueEmpties) {
      updates.stop_when_queue_empties = current.stopWhenQueueEmpties
    }
    // What the next firing would have, counting what this save sends. A flow with neither stop is
    // refused here, as `create_flow` refuses it at creation.
    if (loop.spec_document_id && !current.stopAt && !current.stopWhenQueueEmpties) {
      setRefusal(FLOW_NEEDS_STOP)
      return
    }
    if (Object.keys(updates).length === 0) {
      setEdit(null)
      return
    }
    update.mutate(updates, { onSuccess: () => setEdit(null) })
  }

  const failure = refusal ?? (update.isError ? readableApiError(update.error, 'Could not save these settings.') : null)

  return (
    <div className="mt-3" data-testid="loop-tab-settings">
      <div className="flex items-center justify-between">
        <p style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-3)' }}>Settings</p>
        {!readOnly && !editing && (
          <Button variant="outline" size="xs" onClick={beginEdit}>
            Edit
          </Button>
        )}
      </div>

      {agentsFailed && (
        <p role="alert" style={{ fontSize: 11, color: 'var(--amber)' }}>
          Could not load the agent list; only the current agent is offered.
        </p>
      )}

      {!editing ? (
        <div className="mt-1 space-y-0.5" style={{ fontSize: 11, color: 'var(--text)' }} data-testid="loop-tab-settings-read">
          <p><span style={{ color: 'var(--text-3)' }}>Default agent: </span>{loop.agent || 'none'}</p>
          <p><span style={{ color: 'var(--text-3)' }}>Message: </span>{job.message}</p>
          <p>
            <span style={{ color: 'var(--text-3)' }}>Cadence: </span>
            {describeCron(job.cron) ?? job.cron}
          </p>
          {loop.spec_document_id && (
            <p><span style={{ color: 'var(--text-3)' }}>Document: </span>{loop.spec_document_id}</p>
          )}
          {loop.work_needs_evidence != null && (
            <p>
              <span style={{ color: 'var(--text-3)' }}>Approval needs evidence: </span>
              {loop.work_needs_evidence ? 'yes' : 'no'}
            </p>
          )}
        </div>
      ) : (
        <div className="mt-1 space-y-2" data-testid="loop-tab-settings-form">
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Name
            <input
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={inputStyle}
              value={current.name}
              onChange={(e) => set('name', e.target.value)}
            />
          </label>
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Default agent
            <select
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={inputStyle}
              value={current.agent}
              onChange={(e) => set('agent', e.target.value)}
            >
              {agentNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <p style={{ fontSize: 10, color: 'var(--text-3)' }}>
            Tasks already assigned stay with their agent; the new default takes the next ones.
          </p>
          {controlWarning && (
            <p role="note" data-testid="loop-tab-settings-control-warning" style={{ fontSize: 11, color: 'var(--amber)' }}>
              This loop’s queue is decided by its creator agent. Changing the agent gives control back to you
              when the change applies.
            </p>
          )}
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Message
            <textarea
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={inputStyle}
              rows={2}
              value={current.message}
              onChange={(e) => set('message', e.target.value)}
            />
          </label>
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Cadence (cron)
            <input
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={inputStyle}
              value={current.cron}
              onChange={(e) => set('cron', e.target.value)}
            />
          </label>
          {cronPlain && <p style={{ fontSize: 10, color: 'var(--text-3)' }}>{cronPlain}</p>}
          {cronAmbiguity && <p style={{ fontSize: 10, color: 'var(--amber)' }}>{cronAmbiguity}</p>}
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Purpose
            <textarea
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={inputStyle}
              rows={2}
              value={current.purpose}
              onChange={(e) => set('purpose', e.target.value)}
            />
          </label>
          <label className="block" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Stop at
            <input
              type="datetime-local"
              className="mt-0.5 block w-full rounded-[var(--radius-sm)] px-2 py-1"
              style={inputStyle}
              value={current.stopAt}
              onChange={(e) => set('stopAt', e.target.value)}
            />
          </label>
          <p style={{ fontSize: 10, color: 'var(--text-3)' }}>
            A stop time can be moved, not removed. To run without one, stop it when the queue empties instead.
          </p>
          <label className="flex items-center gap-1.5" style={{ fontSize: 11, color: 'var(--text-3)' }}>
            <input
              type="checkbox"
              checked={current.stopWhenQueueEmpties}
              onChange={(e) => set('stopWhenQueueEmpties', e.target.checked)}
            />
            Stop when the queue empties
          </label>

          <div className="flex items-center gap-1">
            <Button variant="primary" size="xs" disabled={update.isPending} onClick={save}>
              Save
            </Button>
            <Button variant="outline" size="xs" onClick={() => setEdit(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {failure && (
        <p role="alert" className="mt-1" style={{ fontSize: 11, color: 'var(--red)' }}>
          {failure}
        </p>
      )}
    </div>
  )
}
