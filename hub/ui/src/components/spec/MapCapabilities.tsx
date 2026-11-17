import { useMapDrafts, type ProposedCapabilityState } from '@/api/spec'

const PROPOSED_STATE_LABEL: Record<ProposedCapabilityState, string> = {
  'no-draft': 'no draft yet',
  exploring: 'exploring',
  approved: 'approved',
  current: 'current',
  declined: 'declined',
}

/** The capabilities a system map proposes, each with its draft's state and a link to the draft
 *  where one exists (`a-project-with-no-specs-is-offered-a-start` FR-8). */
export function MapCapabilities({ path, onOpenDocument }: { path: string; onOpenDocument?: (path: string) => void }) {
  const { data, isError } = useMapDrafts(path)
  const rows = data ?? []
  return (
    <div className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-3)' }}>
      <span>Proposed capabilities</span>
      <ul data-testid="map-capabilities" className="flex flex-col gap-0.5">
        {isError ? <li data-testid="map-capabilities-unread">could not be read</li> : null}
        {!isError && data && rows.length === 0 ? <li>none proposed</li> : null}
        {rows.map((row) => {
          const draft = row.draft
          const opens = draft && onOpenDocument ? () => onOpenDocument(draft.path) : undefined
          return (
            <li
              key={row.title}
              data-testid="map-capability-row"
              data-title={row.title}
              data-state={row.state}
              data-draft={draft?.path}
              style={opens ? { cursor: 'pointer' } : undefined}
              onClick={opens}
            >
              {opens ? (
                <button data-slot="link-button" type="button" className="aw-inline-link">
                  {row.title}
                </button>
              ) : (
                <span>{row.title}</span>
              )}{' '}
              — {PROPOSED_STATE_LABEL[row.state] ?? row.state}
              {draft && draft.title !== row.title ? <span> ({draft.title})</span> : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
