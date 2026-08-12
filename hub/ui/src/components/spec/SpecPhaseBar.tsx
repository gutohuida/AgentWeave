import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import {
  useCloseExploration,
  useProposeSpecDocument,
  useSetSpecPhase,
  useSpecDocuments,
  type SpecBlockingFinding,
} from '@/api/spec'

/**
 * The phase of the open document, and the decisions only the operator can take.
 *
 * Every control here is deliberately absent from the agent's tool surface. An
 * agent can write the document and can see what is blocking it; it cannot close
 * exploration, propose, approve, or reopen. That asymmetry is the feature — the
 * gate it replaced was a skill instructing the agent to read the document's own
 * status and stop, which is the agent checking its own permission slip.
 */
export function SpecPhaseBar({ path }: { path: string }) {
  const { data } = useSpecDocuments()
  const closeExploration = useCloseExploration()
  const propose = useProposeSpecDocument()
  const setPhase = useSetSpecPhase()
  const [blocking, setBlocking] = useState<SpecBlockingFinding[]>([])

  const document = data?.documents.find((entry) => entry.path === path)
  if (!document) return null

  const busy = closeExploration.isPending || propose.isPending || setPhase.isPending

  async function onPropose() {
    const result = await propose.mutateAsync({ path })
    // A blocked proposal is the normal case while a document is being written,
    // so it reports rather than throws. Showing every finding at once matters:
    // one per attempt turns five problems into five round trips.
    setBlocking(result.blocking ?? [])
  }

  return (
    <div className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs">
      <div className="flex items-center gap-2">
        <span
          className="rounded-full px-2 py-0.5"
          style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
          data-testid="spec-phase"
        >
          {document.phase}
        </span>

        {document.phase === 'exploring' && !document.explore_closed && (
          <button
            type="button"
            disabled={busy}
            onClick={() => closeExploration.mutate({ path })}
            className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
          >
            Exploration is complete
          </button>
        )}

        {document.phase === 'exploring' && document.explore_closed && (
          <button
            type="button"
            disabled={busy}
            onClick={onPropose}
            className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
          >
            Propose
          </button>
        )}

        {document.phase === 'proposed' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setPhase.mutate({ path, to: 'approved' })}
            className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
          >
            Approve
          </button>
        )}

        {document.phase !== 'exploring' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setPhase.mutate({ path, to: 'exploring' })}
            className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
            style={{ color: 'var(--text-3)' }}
          >
            Reopen
          </button>
        )}
      </div>

      {blocking.length > 0 && (
        <ul className="flex flex-col gap-0.5 pl-1" style={{ color: 'var(--text-3)' }}>
          {blocking.map((finding) => (
            <li key={`${finding.code}:${finding.where}`} className="flex items-start gap-1.5">
              <Icon name="warning" size={13} />
              <span>
                <code>{finding.where}</code> — {finding.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
