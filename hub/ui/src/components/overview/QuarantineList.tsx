import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatAgoLong, formatDateTime } from '@/lib/format'
import type { NeverQuarantineMark, QuarantinedTest } from '@/api/quarantine'

/**
 * The project's quarantined tests on the Overview, beside the known-failing list (`the-slow-checks-
 * run-once-per-landing-not-once-per-task-and-flaky-tests-are-quarantined`, FR-11): each test the
 * gates excuse because it flakes, with its check, flake rate on entry, time of entry, passes toward
 * leaving and fix task; and the tests the operator marked never to be quarantined (FR-8).
 */
export function QuarantineList({
  quarantined,
  marks,
  onSetMark,
  onRemoveMark,
  busy = false,
  error,
  onOpenTask,
  now,
}: {
  /** As the route returns them: newest entry first. */
  quarantined: QuarantinedTest[]
  /** As the route returns them: newest mark first. */
  marks: NeverQuarantineMark[]
  onSetMark: (check: string, test: string) => void
  onRemoveMark: (check: string, test: string) => void
  busy?: boolean
  error?: string | null
  onOpenTask: (taskId: string) => void
  now: Date
}) {
  const [check, setCheck] = React.useState('')
  const [test, setTest] = React.useState('')
  return (
    <section className="aw-ov-section aw-ov-q" aria-labelledby="ov-quarantine" data-testid="quarantine-list">
      <h2 id="ov-quarantine" className="aw-ov-heading">
        Quarantined tests {quarantined.length ? <span className="aw-ov-count" data-tone="amber">{quarantined.length}</span> : null}
      </h2>
      {quarantined.length === 0 ? (
        <div className="aw-ov-calm">
          <Icon name="check_circle" size={15} /> No test is quarantined.
        </div>
      ) : (
        <ul className="aw-ov-list">
          {quarantined.map((entry) => (
            <li key={entry.id} data-testid={`quarantined-${entry.id}`} className="aw-ov-row aw-ov-kf-row aw-ov-q-row">
              <span className="aw-ov-row-icon" data-kind="flaky" aria-hidden="true">
                <Icon name="block" size={13} />
              </span>
              <span className="aw-ov-row-text">
                <span className="aw-ov-row-title" title={entry.test}>{entry.test}</span>
                <span className="aw-ov-row-detail">
                  <span data-slot="q-check">{entry.check}</span> ·{' '}
                  <span data-slot="q-rate">
                    {entry.flake_rate != null ? `flake rate ${entry.flake_rate.toFixed(2)} on entry` : 'flake rate unknown'}
                  </span>{' '}
                  ·{' '}
                  {entry.entered_at ? (
                    <time data-slot="q-entered" dateTime={entry.entered_at} title={formatDateTime(entry.entered_at, now)}>
                      entered {formatAgoLong(entry.entered_at, now)}
                    </time>
                  ) : (
                    <span>entry time unknown</span>
                  )}{' '}
                  · <span data-slot="q-passes">{entry.passes} of {entry.passes_to_exit} passes to leave</span>
                </span>
              </span>
              <span className="aw-ov-row-end">
                <button
                  type="button"
                  className="aw-overview-link"
                  disabled={busy}
                  title="Never quarantine this test: it leaves quarantine now and its failures count"
                  onClick={() => onSetMark(entry.check, entry.test)}
                >
                  Never quarantine
                </button>
                {entry.fix_task ? (
                  <button
                    data-slot="q-fix-task"
                    type="button"
                    className="aw-overview-link"
                    title={entry.fix_task.title}
                    onClick={() => onOpenTask(entry.fix_task!.id)}
                  >
                    {entry.fix_task.display_id ?? entry.fix_task.id}
                    {entry.fix_task.status ? ` · ${entry.fix_task.status.replace(/_/g, ' ')}` : ''}
                  </button>
                ) : (
                  <span data-slot="q-fix-task">No fix task</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div data-testid="never-quarantine-marks" className="aw-ov-q-marks">
        <h3 className="aw-ov-q-sub">Never quarantined</h3>
        {marks.length === 0 ? (
          <p className="aw-ov-q-empty">No test is marked. Name one below and its failures always count.</p>
        ) : (
          <ul className="aw-ov-list">
            {marks.map((mark) => (
              <li key={mark.id} data-testid={`never-quarantine-${mark.id}`} className="aw-ov-row aw-ov-kf-row aw-ov-q-row">
                <span className="aw-ov-row-icon" aria-hidden="true">
                  <Icon name="lock" size={13} />
                </span>
                <span className="aw-ov-row-text">
                  <span className="aw-ov-row-title" title={mark.test}>{mark.test}</span>
                  <span className="aw-ov-row-detail">{mark.check}</span>
                </span>
                <span className="aw-ov-row-end">
                  <button type="button" className="aw-overview-link" disabled={busy} onClick={() => onRemoveMark(mark.check, mark.test)}>
                    Remove mark
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <form
          className="aw-ov-q-form"
          onSubmit={(event) => {
            event.preventDefault()
            if (!check.trim() || !test.trim()) return
            onSetMark(check.trim(), test.trim())
            setTest('')
          }}
        >
          <label className="aw-ov-q-field">
            <span>Check</span>
            <Input aria-label="Check name" placeholder="e.g. hub-tests" value={check} onChange={(e) => setCheck(e.target.value)} />
          </label>
          <label className="aw-ov-q-field" data-grow="true">
            <span>Test id</span>
            <Input aria-label="Test id" placeholder="e.g. tests/test_x.py::test_name" value={test} onChange={(e) => setTest(e.target.value)} />
          </label>
          <Button type="submit" variant="outline" size="sm" disabled={busy || !check.trim() || !test.trim()}>
            Never quarantine a test
          </Button>
        </form>
        {error ? <p role="alert" className="aw-ov-q-error">{error}</p> : null}
      </div>
    </section>
  )
}
