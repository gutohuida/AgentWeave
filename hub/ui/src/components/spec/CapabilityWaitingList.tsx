import type { SpecDocumentRecord } from '@/api/spec'

/** The open changes naming a capability, in the order the Hub returns them
 *  (`a-change-names-the-capabilities-it-changes` FR-5). Never re-sorted here. */
export function CapabilityWaitingList({ record }: { record: SpecDocumentRecord }) {
  const waiting = record.waiting_changes ?? []
  return (
    <div className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-3)' }}>
      <span>Changes waiting to be folded in</span>
      <ul data-testid="capability-waiting-list" className="flex flex-col gap-0.5">
        {waiting.length === 0 ? <li>none</li> : null}
        {waiting.map((change) => (
          <li
            key={change.path}
            data-testid="capability-waiting-row"
            data-path={change.path}
            data-built={change.built ? 'true' : 'false'}
          >
            <span>{change.title}</span>{' '}
            — {change.phase}
            {change.built ? ', built' : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}
