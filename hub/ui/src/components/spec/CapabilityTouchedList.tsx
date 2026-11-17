import type { SpecDocumentRecord } from '@/api/spec'
import { formatDay } from '@/lib/format'
import { touchedChanges } from './touchedChanges'

/** The changes that touched a capability, waiting and folded (`spec-home-shows-what-is-being-built…`,
 *  FR-7), each a link to the change. */
export function CapabilityTouchedList({ record, onOpenDocument }: { record: SpecDocumentRecord; onOpenDocument?: (path: string) => void }) {
  const rows = touchedChanges(record)
  return (
    <div className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-3)' }}>
      <span>Changes that touched this capability</span>
      <ul data-testid="capability-touched-list" className="flex flex-col gap-0.5">
        {rows.length === 0 ? <li>none</li> : null}
        {rows.map((change) => (
          <li
            key={change.path}
            data-testid="capability-touched-row"
            style={onOpenDocument ? { cursor: 'pointer' } : undefined}
            onClick={onOpenDocument ? () => onOpenDocument(change.path) : undefined}
            data-path={change.path}
            data-state={change.state}
            data-built={change.built === undefined ? undefined : change.built ? 'true' : 'false'}
          >
            {onOpenDocument ? (
              <button data-slot="link-button" type="button" className="aw-inline-link">
                {change.title}
              </button>
            ) : (
              <span>{change.title}</span>
            )}{' '}
            — {change.state === 'folded' ? 'folded' : `waiting${change.built ? ', built' : ''}`}
            {change.at ? <span title={change.at}> {formatDay(change.at)}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
