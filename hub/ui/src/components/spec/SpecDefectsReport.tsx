import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import {
  POST_APPROVAL_STEPS,
  useProjectJourney,
  useRecordDefect,
  useSpecDefects,
} from '@/api/spec'

/**
 * Where each change's defects were caught (`a-change-is-reconciled-with-its-code-before-it-is-
 * folded`, FR-5): one row per change with a count per step, so the journey can be tuned from data.
 * The Hub derives the list from its own records; this only lays it out. Below it, the operator
 * records a defect against the open change (FR-6) — one found after fold, or by hand.
 */
export function SpecDefectsReport({
  currentPath,
  onSelect,
}: {
  currentPath?: string | null
  onSelect: (path: string) => void
}) {
  const { data, error } = useSpecDefects()
  const [open, setOpen] = useState(true)
  const changes = data?.changes ?? []
  const onChange = !!currentPath && currentPath.startsWith('spec/changes/')

  if (error) {
    return (
      <p className="px-2 py-1 text-[11px]" style={{ color: 'var(--amber)' }}>
        Could not load the defects report: {readableApiError(error, 'the Hub did not answer.')}
      </p>
    )
  }
  if (changes.length === 0 && !onChange) return null

  return (
    <section data-testid="spec-defects" className="mt-2 flex flex-col gap-1 px-2 text-[11px]">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1 text-left"
        style={{ color: 'var(--text-2)', fontWeight: 600 }}
      >
        <Icon name={open ? 'expand_more' : 'chevron_right'} size={13} />
        Defects by step
      </button>
      {open && (
        <>
          <ul className="flex flex-col gap-1">
            {changes.map((change) => (
              <li key={change.document_id} data-testid="spec-defects-row">
                <button
                  type="button"
                  onClick={() => onSelect(change.path)}
                  className="flex w-full flex-col items-start rounded-[var(--radius-sm)] px-1.5 py-1 text-left hover:bg-[var(--row-hover)]"
                  title={change.defects
                    .map((defect) => `${defect.caught_by}: ${defect.summary}`)
                    .join('\n')}
                >
                  <span className="truncate" style={{ color: 'var(--text-2)', maxWidth: '100%' }}>
                    {change.title}
                  </span>
                  <span style={{ color: 'var(--text-3)' }}>
                    {Object.entries(change.by_step)
                      .map(([step, count]) => `${step} ${count}`)
                      .join(' · ')}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {onChange && <RecordDefect path={currentPath} />}
        </>
      )}
    </section>
  )
}

function RecordDefect({ path }: { path: string }) {
  const { data: journey, error: journeyError } = useProjectJourney()
  const record = useRecordDefect()
  const [adding, setAdding] = useState(false)
  const [summary, setSummary] = useState('')
  const [step, setStep] = useState('after-fold')
  const [refusal, setRefusal] = useState<string | null>(null)
  // The journey's own steps when they could be read; the post-approval stages are always offered.
  const steps = [
    ...(journey?.steps ?? [])
      .map((entry) => entry.key)
      .filter((key) => !(POST_APPROVAL_STEPS as readonly string[]).includes(key)),
    ...POST_APPROVAL_STEPS,
  ]

  if (!adding) {
    return (
      <button
        type="button"
        data-testid="spec-defect-add"
        onClick={() => setAdding(true)}
        className="self-start rounded-[var(--radius-sm)] px-1.5 py-0.5 hover:bg-[var(--row-hover)]"
        style={{ color: 'var(--text-3)' }}
      >
        Record a defect on this change…
      </button>
    )
  }

  function onSave() {
    setRefusal(null)
    record.mutate(
      { path, summary: summary.trim(), caught_by: step },
      {
        onSuccess: () => {
          setSummary('')
          setAdding(false)
        },
        onError: (error: unknown) =>
          setRefusal(readableApiError(error, 'The Hub refused the defect.')),
      },
    )
  }

  return (
    <div className="flex flex-col gap-1" data-testid="spec-defect-form">
      <textarea
        aria-label="What went wrong"
        value={summary}
        onChange={(event) => setSummary(event.target.value)}
        maxLength={2000}
        rows={2}
        className="rounded-[var(--radius-sm)] px-1.5 py-1"
        style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
      />
      <div className="flex items-center gap-1">
        <select
          aria-label="Caught at"
          value={step}
          onChange={(event) => setStep(event.target.value)}
          className="min-w-0 flex-1 rounded-[var(--radius-sm)] px-1 py-0.5"
          style={{ background: 'var(--surface-2)', color: 'var(--text-2)', border: '1px solid var(--border)' }}
        >
          {steps.map((key) => (
            <option key={key} value={key}>
              {key}
            </option>
          ))}
        </select>
        <Button variant="primary" size="xs" disabled={!summary.trim() || record.isPending} onClick={onSave}>
          Record
        </Button>
        <Button variant="ghost" size="xs" onClick={() => setAdding(false)}>
          Cancel
        </Button>
      </div>
      {journeyError && (
        <span style={{ color: 'var(--text-3)' }}>
          The project&apos;s own steps could not be read; only the stages after approval are offered.
        </span>
      )}
      {refusal && (
        <span role="alert" style={{ color: 'var(--red)' }}>
          {refusal}
        </span>
      )}
    </div>
  )
}
