import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import {
  useCloseExploration,
  useProposeSpecDocument,
  useSetSpecPhase,
  useSetSpecRigor,
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
  const setRigor = useSetSpecRigor()
  const [blocking, setBlocking] = useState<SpecBlockingFinding[]>([])
  const [rigorRefusal, setRigorRefusal] = useState<string[]>([])

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

  async function onRigor(rigor: string) {
    setRigorRefusal([])
    try {
      await setRigor.mutateAsync({
        path,
        rigor,
        // Compare-and-swap: what is being enforced has to be what the operator read.
        expectedDigest: document?.content_digest ?? null,
      })
    } catch (error) {
      // `ApiError.message` is the response body verbatim, so the structured refusal has to be
      // parsed back out of it. Falling through to the raw text is deliberate: an unparseable
      // failure the operator can still read beats a generic sentence that hides it.
      const raw = error instanceof Error ? error.message : String(error)
      let detail: { message?: string; blocking?: string[] } | string | undefined
      try {
        detail = (JSON.parse(raw) as { detail?: typeof detail }).detail
      } catch {
        detail = raw
      }
      if (typeof detail === 'string' || detail === undefined) {
        setRigorRefusal([detail || 'That change was refused.'])
      } else {
        setRigorRefusal(
          detail.blocking?.length
            ? detail.blocking
            : [detail.message ?? 'That change was refused.'],
        )
      }
    }
  }

  return (
    <div className="flex shrink-0 flex-col gap-1.5 px-3 py-2 text-xs">
      <div className="flex items-center gap-2">
        <span
          className="rounded-full px-2 py-0.5"
          style={{
            background: 'var(--surface-2)',
            // Muted for the two phases nobody is actively deciding about — `archived` and
            // `current` — as opposed to `exploring`/`proposed`, where a decision is pending.
            color:
              document.phase === 'archived' || document.phase === 'current'
                ? 'var(--text-3)'
                : 'var(--text-2)',
          }}
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

        {document.phase === 'approved' && (
          <button
            type="button"
            disabled={busy}
            onClick={() => setPhase.mutate({ path, to: 'archived' })}
            className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
          >
            Archive
          </button>
        )}

        {(document.phase === 'proposed' || document.phase === 'approved') && (
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

        <div className="flex-1" />

        {/* Rigor, beside the phase and visibly not the same control. They answer different
            questions — "has the operator agreed to this?" and "what happens to work that ignores
            it?" — and an operator reading one will otherwise assume the other. */}
        <label className="flex items-center gap-1.5" style={{ color: 'var(--text-3)' }}>
          <span>Enforcement</span>
          <select
            data-testid="spec-rigor"
            value={document.rigor}
            disabled={busy || setRigor.isPending}
            onChange={(event) => onRigor(event.target.value)}
            className="rounded-[var(--radius-sm)] px-1.5 py-0.5"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-2)',
              border: '1px solid var(--border)',
              fontSize: 11,
            }}
          >
            <option value="sketch">Sketch — blocks nothing</option>
            <option value="contract">Contract — stated, not enforced</option>
            <option value="gate">Gate — unverified work cannot be approved</option>
          </select>
        </label>
      </div>

      {/* Why a promotion was refused. A document that cannot be read cannot be enforced, and
          saying only "refused" leaves the operator guessing at which of several things is wrong. */}
      {rigorRefusal.length > 0 && (
        <ul
          className="flex flex-col gap-0.5 pl-1"
          data-testid="spec-rigor-refusal"
          style={{ color: 'var(--amber)' }}
        >
          {rigorRefusal.map((reason) => (
            <li key={reason} className="flex items-start gap-1.5">
              <Icon name="warning" size={13} />
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      )}

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
