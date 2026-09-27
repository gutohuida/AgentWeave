import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { ArchiveConfirmDialog } from '@/components/spec/ArchiveConfirmDialog'
import { StartFlowDialog } from '@/components/spec/StartFlowDialog'
import { useDocumentFlow, type LoopSummary } from '@/api/loops'
import { readableApiError } from '@/api/client'
import {
  useCloseExploration,
  useProposeSpecDocument,
  useSetSpecPhase,
  useSetSpecRigor,
  useSpecDocuments,
  type SpecBlockingFinding,
} from '@/api/spec'

/**
 * What a refused phase move says, as findings. The Hub answers an incomplete document with
 * `detail.blocking` (the same list `propose` returns with a 200); any other refusal is one message.
 * `ApiError.message` is the response body verbatim, so the detail is parsed back out of it.
 */
function findingsFromRefusal(error: unknown, fallback: string): SpecBlockingFinding[] {
  try {
    const raw = error instanceof Error ? error.message : String(error)
    const detail = (JSON.parse(raw) as { detail?: { blocking?: SpecBlockingFinding[] } }).detail
    if (detail?.blocking?.length) return detail.blocking
  } catch {
    // not JSON: fall through to the readable message
  }
  return [{ code: 'refused', where: '', message: readableApiError(error, fallback) }]
}

/**
 * The phase of the open document, and the decisions only the operator can take.
 *
 * Every control here is deliberately absent from the agent's tool surface. An
 * agent can write the document and can see what is blocking it; it cannot close
 * exploration, propose, approve, or reopen. That asymmetry is the feature — the
 * gate it replaced was a skill instructing the agent to read the document's own
 * status and stop, which is the agent checking its own permission slip.
 */
export function SpecPhaseBar({
  path,
  onOpenLoop,
}: {
  path: string
  /** Opens a loop's tab. Each host supplies its own: the conversation panel opens the tab beside
   *  the document; the Spec destination has no panel shell and must navigate to one. Without it
   *  the flow's label is text rather than a link that does nothing. */
  onOpenLoop?: (loop: LoopSummary) => void
}) {
  const { data } = useSpecDocuments()
  const closeExploration = useCloseExploration()
  const propose = useProposeSpecDocument()
  const setPhase = useSetSpecPhase()
  const setRigor = useSetSpecRigor()
  const [blocking, setBlocking] = useState<SpecBlockingFinding[]>([])
  const [rigorRefusal, setRigorRefusal] = useState<string[]>([])
  const [confirmingArchive, setConfirmingArchive] = useState(false)
  const [archiveRefusal, setArchiveRefusal] = useState<string | null>(null)
  const [startingFlow, setStartingFlow] = useState(false)

  const document = data?.documents.find((entry) => entry.path === path)
  const flow = useDocumentFlow(document?.id)
  if (!document) return null

  const busy = closeExploration.isPending || propose.isPending || setPhase.isPending

  async function onPropose() {
    setBlocking([])
    try {
      const result = await propose.mutateAsync({ path })
      // A blocked proposal is the normal case while a document is being written,
      // so it reports rather than throws. Showing every finding at once matters:
      // one per attempt turns five problems into five round trips.
      setBlocking(result.blocking ?? [])
    } catch (error) {
      // 422 (no payload / payload invalid) used to reject unhandled and show nothing.
      setBlocking(findingsFromRefusal(error, 'The Hub refused to propose this document.'))
    }
  }

  function onApprove() {
    setBlocking([])
    setPhase.mutate(
      { path, to: 'approved' },
      {
        // F207: approval runs the completeness checks again and answers 409 with the findings.
        onError: (error: unknown) =>
          setBlocking(findingsFromRefusal(error, 'The Hub refused to approve this document.')),
      },
    )
  }

  function onConfirmArchive() {
    setArchiveRefusal(null)
    setPhase.mutate(
      { path, to: 'archived' },
      {
        onSuccess: () => setConfirmingArchive(false),
        // It used to drop this, and the dialog simply stayed open. Archiving from `exploring` or
        // `proposed` is refused once the document has produced work, and the refusal says what to
        // do instead.
        onError: (error: unknown) =>
          setArchiveRefusal(readableApiError(error, 'The Hub refused to archive this document.')),
      },
    )
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
            onClick={onApprove}
            className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
          >
            Approve
          </button>
        )}

        {/* F205: `spec_lifecycle` has archive edges from `exploring` and `proposed` too, added for
            F37 (a mistaken, empty document nothing could retire) and offered by no screen. The Hub
            refuses them once the document has produced requirements or tasks, and the dialog shows
            that refusal. */}
        {(document.phase === 'approved' || document.phase === 'exploring' || document.phase === 'proposed') && (
          <button
            type="button"
            disabled={busy}
            onClick={() => { setArchiveRefusal(null); setConfirmingArchive(true) }}
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

        {/* A flow is offered on an approved change-spec only: earlier there are no tasks to work,
            other kinds are not decomposed into flows, and an archived document is finished. */}
        {document.kind === 'change-spec' && document.phase === 'approved' && (
          flow ? (
            onOpenLoop && flow.agent ? (
              <button
                type="button"
                onClick={() => onOpenLoop(flow)}
                data-testid="spec-flow-link"
                className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
              >
                Flow: {flow.label}
              </button>
            ) : (
              <span data-testid="spec-flow-link" style={{ color: 'var(--text-3)' }}>
                Flow: {flow.label}
              </span>
            )
          ) : (
            <button
              type="button"
              onClick={() => setStartingFlow(true)}
              data-testid="spec-start-flow"
              className="rounded-[var(--radius-sm)] px-2 py-1 hover:bg-[var(--row-hover)]"
            >
              Start a flow…
            </button>
          )
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
                {finding.where && <code>{finding.where}</code>}
                {finding.where ? ' — ' : ''}
                {finding.message}
              </span>
            </li>
          ))}
        </ul>
      )}

      {startingFlow && (
        <StartFlowDialog
          document={{ id: document.id, title: document.title }}
          onClose={() => setStartingFlow(false)}
        />
      )}

      {confirmingArchive && (
        <ArchiveConfirmDialog
          title={document.title}
          isPending={setPhase.isPending}
          error={archiveRefusal}
          onCancel={() => setConfirmingArchive(false)}
          onConfirm={onConfirmArchive}
        />
      )}
    </div>
  )
}
