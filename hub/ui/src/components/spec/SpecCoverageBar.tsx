import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useSpecCoverage, type CoverageEntry } from '@/api/spec'

/** Order and wording, highest precedence first. The labels say what the state *means* rather than
 *  naming the enum: an operator reading "stale" has to be told what went stale, and the reason a
 *  requirement is in its state has to be apparent without reading the code. */
const STATES: Array<{ key: CoverageEntry['state']; label: string; tone: string; why: string }> = [
  {
    key: 'drifting',
    label: 'Drifting',
    tone: 'var(--amber)',
    why: 'The implementation changed after this was verified. Someone needs to say which one was wrong.',
  },
  {
    key: 'stale',
    label: 'Stale',
    tone: 'var(--amber)',
    why: 'The requirement was reworded after its evidence was accepted, so that evidence describes an older wording.',
  },
  {
    key: 'evidence_awaiting_review',
    label: 'Awaiting review',
    tone: 'var(--blue)',
    why: 'Evidence exists for the current wording and nobody has decided about it yet.',
  },
  {
    key: 'verified',
    label: 'Verified',
    tone: 'var(--green)',
    why: 'Accepted evidence for the current wording.',
  },
  {
    key: 'in_progress',
    label: 'In progress',
    tone: 'var(--text-2)',
    why: 'Work is linked and under way, or finished with nothing recorded to show for it.',
  },
  {
    key: 'not_started',
    label: 'Not started',
    tone: 'var(--text-3)',
    why: 'Work is linked and has not begun.',
  },
  {
    key: 'unserved',
    label: 'No work linked',
    tone: 'var(--text-3)',
    why: 'Nothing on the board says it will build this.',
  },
]

const INTEGRATION_LABEL: Record<CoverageEntry['integration'], string> = {
  integrated: 'in the main line',
  not_integrated: 'not in the main line',
  unknown: 'main line unknown',
  not_applicable: '',
}

/**
 * Coverage for the open document.
 *
 * Two things this deliberately does not do. It does not show a percentage — a single number makes
 * seven distinct states look like one axis, and the interesting question is almost always *which*
 * requirements are where. And it never shows a state without its integration answer: approved work
 * in this product routinely sits on a branch nothing merges, so "verified" alone would be true of
 * the branch and false of the product.
 */
export function SpecCoverageBar({ path }: { path: string }) {
  const { data } = useSpecCoverage(path)
  const [open, setOpen] = useState(false)

  if (!data || (data.requirements.length === 0 && data.diagnostics.length === 0)) return null

  const present = STATES.filter((state) => (data.totals[state.key] ?? 0) > 0)
  const unintegrated = data.requirements.filter(
    (entry) => entry.state === 'verified' && entry.integration === 'not_integrated',
  )

  return (
    <div
      className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs"
      data-testid="spec-coverage"
      style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-2)' }}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2"
        aria-expanded={open}
        style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
      >
        <Icon name="fact_check" size={14} />
        {present.map((state) => (
          <span key={state.key} className="flex items-center gap-1" title={state.why}>
            <span
              aria-hidden
              style={{
                width: 7,
                height: 7,
                borderRadius: 99,
                background: state.tone,
                display: 'inline-block',
              }}
            />
            <span data-testid={`coverage-count-${state.key}`}>
              {data.totals[state.key]} {state.label.toLowerCase()}
            </span>
          </span>
        ))}
        {data.diagnostics.length > 0 && (
          <span data-testid="coverage-diagnostics" style={{ color: 'var(--amber)' }}>
            {data.diagnostics.length} broken
          </span>
        )}
        <Icon name={open ? 'expand_less' : 'expand_more'} size={14} />
      </button>

      {/* Surfaced without opening the detail, because it is the one result that reads as good news
          and is not: the work is verified and is not in the product. */}
      {unintegrated.length > 0 && (
        <div
          data-testid="coverage-not-integrated"
          className="flex items-center gap-1.5 pl-5"
          style={{ color: 'var(--amber)' }}
        >
          <Icon name="call_split" size={13} />
          <span>
            {unintegrated.length} verified, not in the main line:{' '}
            {unintegrated.map((entry) => entry.identifier).join(', ')}
          </span>
        </div>
      )}

      {open && (
        <ul className="flex flex-col gap-0.5 pl-5" style={{ color: 'var(--text-3)' }}>
          {data.requirements.map((entry) => {
            const state = STATES.find((candidate) => candidate.key === entry.state)
            const integration = INTEGRATION_LABEL[entry.integration]
            return (
              <li key={entry.requirement_id} data-testid={`coverage-row-${entry.identifier}`}>
                <a href={`#${entry.identifier}`} style={{ color: 'var(--text-2)' }}>
                  {entry.identifier}
                </a>{' '}
                — {state?.label ?? entry.state}
                {integration ? ` · ${integration}` : ''}
                {entry.linked_task_ids.length > 0
                  ? ` · ${entry.linked_task_ids.length} task${
                      entry.linked_task_ids.length === 1 ? '' : 's'
                    }`
                  : ''}
                {state ? <div style={{ paddingLeft: 12 }}>{state.why}</div> : null}
              </li>
            )
          })}
          {data.diagnostics.map((diagnostic) => (
            <li
              key={diagnostic.requirement_id}
              data-testid={`coverage-diagnostic-${diagnostic.requirement_id}`}
              style={{ color: 'var(--amber)' }}
            >
              {diagnostic.identifier || '(no identifier)'} — {diagnostic.problem}. It has no coverage
              state because it cannot be given one.
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
