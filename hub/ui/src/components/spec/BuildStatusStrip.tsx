import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useStopBuild, useUpdateBuild, type SpecBuild } from '@/api/spec'
import { formatDateTime } from '@/lib/format'

const DRIVER_LABEL: Record<SpecBuild['driver'], string> = {
  flow: 'the flow',
  lead: 'a lead',
  hand: 'hand',
}

function dollars(value: number | null): string {
  return value == null ? '$0.00' : `$${value.toFixed(2)}`
}

/**
 * A document's newest build, on its header (`a-build-has-a-driver-a-level-and-its-people`, FR-1,
 * FR-10): who drives it, at which level, what it has spent of its cap, its window, and why it
 * stopped. Stop ends a running build's hand-outs (running turns finish); Raise cap sets a higher
 * cap, which resumes a build its cap stopped. A finished build is shown as finished, with neither.
 */
export function BuildStatusStrip({ build }: { build: SpecBuild }) {
  const stop = useStopBuild()
  const update = useUpdateBuild()
  const [raising, setRaising] = useState(false)
  const [cap, setCap] = useState('')
  const [refusal, setRefusal] = useState<string | null>(null)
  const capValue = Number(cap)
  const capValid = cap.trim() !== '' && Number.isFinite(capValue) && capValue > 0
  const busy = stop.isPending || update.isPending

  const spend =
    build.budget_cap_usd != null
      ? `${dollars(build.spent_usd)} of ${dollars(build.budget_cap_usd)}`
      : `${dollars(build.spent_usd)}, no cap`
  const unpriced = build.unpriced_turns ? ` (${build.unpriced_turns} unpriced turns)` : ''
  const window =
    build.window_start || build.window_end
      ? ` · window ${build.window_start ? formatDateTime(build.window_start) : 'now'} to ${
          build.window_end ? formatDateTime(build.window_end) : 'open-ended'
        }`
      : ''
  const people = [
    build.builders.length ? `builders @${build.builders.join(', @')}` : null,
    build.reviewers.length ? `reviewers @${build.reviewers.join(', @')}` : null,
    build.driver === 'lead' && build.lead ? `lead @${build.lead}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  function onStop() {
    setRefusal(null)
    stop.mutate(
      { id: build.id },
      { onError: (error: unknown) => setRefusal(readableApiError(error, 'The Hub refused to stop it.')) },
    )
  }

  function onRaise() {
    setRefusal(null)
    update.mutate(
      { id: build.id, budget_cap_usd: capValue },
      {
        onSuccess: () => {
          setRaising(false)
          setCap('')
        },
        onError: (error: unknown) =>
          setRefusal(readableApiError(error, 'The Hub refused to change the cap.')),
      },
    )
  }

  return (
    <div className="aw-spec-message" data-testid="spec-build-status" data-state={build.state}>
      <span className="aw-spec-message-text">
        Build {build.state} · driven by {DRIVER_LABEL[build.driver]} · {build.level} · spent{' '}
        <span data-testid="spec-build-spend">{spend}</span>
        {unpriced}
        {window}
        {people ? ` · ${people}` : ''}
        {build.landing === 'nowhere' ? ' · lands nowhere' : ''}
        {build.state === 'stopped' && build.stop_reason ? ` · stopped: ${build.stop_reason}` : ''}
      </span>
      {build.state !== 'finished' ? (
        <span className="flex items-center gap-2">
          {build.state === 'running' ? (
            <Button size="xs" variant="ghost" disabled={busy} onClick={onStop} data-testid="spec-build-stop">
              Stop
            </Button>
          ) : null}
          {raising ? (
            <>
              <input
                className="control-field"
                style={{ padding: '2px 6px', width: 80, fontSize: 12 }}
                inputMode="decimal"
                placeholder="New cap $"
                aria-label="New cap in US dollars"
                data-testid="spec-build-cap"
                value={cap}
                onChange={(event) => setCap(event.target.value)}
              />
              <Button size="xs" disabled={busy || !capValid} onClick={onRaise} data-testid="spec-build-cap-save">
                Set cap
              </Button>
            </>
          ) : (
            <Button
              size="xs"
              variant="ghost"
              disabled={busy}
              onClick={() => setRaising(true)}
              data-testid="spec-build-raise"
            >
              Raise cap
            </Button>
          )}
        </span>
      ) : null}
      {refusal ? (
        <span role="alert" className="aw-spec-message-text" style={{ color: 'var(--amber)' }}>
          {refusal}
        </span>
      ) : null}
    </div>
  )
}
