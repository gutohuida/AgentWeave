import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { ArchiveConfirmDialog } from '@/components/spec/ArchiveConfirmDialog'
import { FoldIntoCapabilityDialog } from '@/components/spec/FoldIntoCapabilityDialog'
import { StartFlowDialog } from '@/components/spec/StartFlowDialog'
import { useDocumentFlow, type LoopSummary } from '@/api/loops'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { Button } from '@/components/ui/button'
import { hubDate } from '@/lib/hubTime'
import {
  useCloseExploration,
  useProposeSpecDocument,
  useSetSpecPhase,
  useSetSpecRigor,
  useSpec,
  useSpecDocuments,
  useSpecRigorHistory,
  type SpecBlockingFinding,
  type SpecDeliveryStatus,
  type SpecDocumentRecord,
  type SpecNextSliceOutcome,
} from '@/api/spec'

type Rigor = SpecDocumentRecord['rigor']

/** Lowest to highest. A move down this list is a demotion, and a demotion made in the app needs a
 *  reason: the record is what makes lowering a gate legitimate (F429). */
const RIGOR_ORDER: Rigor[] = ['sketch', 'contract', 'gate']
const RIGOR_LABEL: Record<Rigor, string> = { sketch: 'Sketch', contract: 'Contract', gate: 'Gate' }

/** No choice made yet — distinct from `''`, which is a real choice ("No flow", design D5b). */
const NO_CHOICE = '__unset__'

/** What an approval asked to draft the next slice did (`a-spec-is-written-one-slice-at-a-time` D4, D4a). */
function nextSliceMessage(outcome: SpecNextSliceOutcome): string {
  switch (outcome.state) {
    case 'waiting': {
      const open = outcome.open_tasks ?? 0
      return `@${outcome.agent} will be asked to draft slice ${outcome.slice} once this slice's ${open} open task${open === 1 ? '' : 's'} ${open === 1 ? 'is' : 'are'} approved or rejected.`
    }
    case 'queued':
      return `Asked @${outcome.agent} to draft slice ${outcome.slice}.`
    case 'last_slice':
      return 'This was the roadmap’s last slice; there is no next one to draft.'
    case 'no_author':
      return 'No agent created this document, so nobody was asked to draft the next slice.'
    case 'no_conversation':
      return `@${outcome.agent} created this document outside a conversation, so the next slice was not queued.`
    case 'not_queued':
      return `The approval stands, but the Hub could not queue slice ${outcome.slice} to @${outcome.agent}.`
    default:
      return 'This document names no roadmap slice, so nothing was queued.'
  }
}

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
  // `delivery_status` (design D5) rides the same `spec/<path>` query `SpecDocumentPanel` and
  // `SpecApprovalReport` already hold — one cache entry, not a second fetch.
  const { data: specDoc, isError: specDocError } = useSpec(path)
  const { data: openAgentsData, isError: agentsError } = useAgents()
  const closeExploration = useCloseExploration()
  const propose = useProposeSpecDocument()
  const setPhase = useSetSpecPhase()
  const setRigor = useSetSpecRigor()
  const [blocking, setBlocking] = useState<SpecBlockingFinding[]>([])
  const [rigorRefusal, setRigorRefusal] = useState<string[]>([])
  const [confirmingArchive, setConfirmingArchive] = useState(false)
  const [archiveRefusal, setArchiveRefusal] = useState<string | null>(null)
  const [startingFlow, setStartingFlow] = useState(false)
  const [folding, setFolding] = useState(false)
  const [deliveryAgentChoice, setDeliveryAgentChoice] = useState(NO_CHOICE)
  // On by default (C1a D4): approving a slice usually means "and now the next one".
  const [draftNextSlice, setDraftNextSlice] = useState(true)
  const [nextSliceOutcome, setNextSliceOutcome] = useState<SpecNextSliceOutcome | null>(null)
  // A rigor chosen in the select and not yet confirmed. The select no longer posts on change: the
  // change waits here for its reason (design D2).
  const [pendingRigor, setPendingRigor] = useState<Rigor | null>(null)
  const [rigorReason, setRigorReason] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const { data: historyData, error: historyError } = useSpecRigorHistory(path)

  const document = data?.documents.find((entry) => entry.path === path)
  const flow = useDocumentFlow(document?.id)
  if (!document) return null

  // On a failed fetch there is nothing to flag as stale, and nothing to offer as a replacement —
  // the strip simply does not appear, the same "say nothing false" rule the rest of the bar
  // follows for a document the Hub does not track.
  const deliveryStatus = specDocError ? undefined : specDoc?.delivery_status
  const roadmapSlice = specDocError ? undefined : specDoc?.roadmap_slice
  const foldState = specDocError ? undefined : specDoc?.fold_state
  // An approved change that no merge names archives only with a reason saying it changes no
  // capability (the Hub's archive guard). A Hub without `fold_state` never asks.
  const archiveNeedsReason =
    document.kind === 'change-spec' &&
    document.phase === 'approved' &&
    foldState !== undefined &&
    foldState.state !== 'folded'
  const openAgents = agentsError ? [] : (openAgentsData ?? [])

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
    setNextSliceOutcome(null)
    setPhase.mutate(
      {
        path,
        to: 'approved',
        // Sent only when the operator picked something in the stale-delivery strip (design D5b);
        // otherwise omitted, so an un-restarted `:8000` (which has no `delivery_status` to show a
        // strip from in the first place) never receives a field it would 422.
        ...(deliveryAgentChoice !== NO_CHOICE ? { delivery_agent: deliveryAgentChoice } : {}),
        // Only for a slice document: the Hub that named `roadmap_slice` is the one that accepts it.
        ...(roadmapSlice ? { draft_next_slice: draftNextSlice } : {}),
      },
      {
        onSuccess: (result) => setNextSliceOutcome(result.next_slice ?? null),
        // F207: approval runs the completeness checks again and answers 409 with the findings.
        onError: (error: unknown) =>
          setBlocking(findingsFromRefusal(error, 'The Hub refused to approve this document.')),
      },
    )
  }

  function onConfirmArchive(reason: string) {
    setArchiveRefusal(null)
    setPhase.mutate(
      archiveNeedsReason
        ? { path, to: 'archived', reason, no_capability_change: true }
        : { path, to: 'archived' },
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

  // The route answers oldest first; the history reads newest first, reversed here and only here.
  const history = [...(historyData?.events ?? [])].reverse()
  const demoting =
    pendingRigor !== null && RIGOR_ORDER.indexOf(pendingRigor) < RIGOR_ORDER.indexOf(document.rigor)
  const reasonMissing = demoting && rigorReason.trim() === ''

  function onChooseRigor(rigor: Rigor) {
    setRigorRefusal([])
    setRigorReason('')
    setPendingRigor(rigor === document?.rigor ? null : rigor)
  }

  function onCancelRigor() {
    setPendingRigor(null)
    setRigorReason('')
  }

  async function onConfirmRigor() {
    if (pendingRigor === null || reasonMissing) return
    setRigorRefusal([])
    try {
      await setRigor.mutateAsync({
        path,
        rigor: pendingRigor,
        reason: rigorReason.trim(),
        // Compare-and-swap: what is being enforced has to be what the operator read.
        expectedDigest: document?.content_digest ?? null,
      })
      setPendingRigor(null)
      setRigorReason('')
    } catch (error) {
      // The row stays open with its reason, so a refusal the operator can fix is one retry away.
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
      {nextSliceOutcome && (
        <p data-testid="next-slice-outcome" style={{ color: 'var(--text-2)' }}>
          {nextSliceMessage(nextSliceOutcome)}
        </p>
      )}

      {/* A stale delivery, above Approve (design D5/D5b): the declared agent is archived or
          unknown, so approving as written would not start a flow. The choice made here — another
          open agent, or "No flow" — travels with Approve; it is used for this flow only and never
          rewrites the document. */}
      {deliveryStatus?.state === 'stale' && (
        <div
          data-testid="delivery-stale-strip"
          className="flex flex-wrap items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5"
          style={{ background: 'color-mix(in srgb, var(--amber) 10%, transparent)', color: 'var(--text-2)' }}
        >
          <Icon name="warning" size={13} />
          <span className="flex-1">
            Delivery names {deliveryStatus.agent}, which is{' '}
            {deliveryStatus.reason === 'archived' ? 'archived' : 'not an agent on this project'}.
            {' '}Approving will not start a flow unless you choose another agent.
          </span>
          <select
            data-testid="delivery-agent-choice"
            value={deliveryAgentChoice}
            onChange={(event) => setDeliveryAgentChoice(event.target.value)}
            disabled={busy}
            className="rounded-[var(--radius-sm)] px-1.5 py-0.5"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-2)',
              border: '1px solid var(--border)',
              fontSize: 11,
            }}
          >
            <option value={NO_CHOICE} disabled>
              Choose…
            </option>
            {openAgents.map((agent) => (
              <option key={agent.name} value={agent.name}>
                @{agent.name}
              </option>
            ))}
            <option value="">No flow</option>
          </select>
        </div>
      )}

      {/* A finished change on its way into the corpus (`a-finished-change-is-folded-into-its-
          capability`): every task decided and no merge names it yet. Folding is the close-out;
          the archive control beside the phase asks why when a change changes no capability. */}
      {document.phase === 'approved' && foldState?.state === 'ready' && (
        <div
          data-testid="fold-state"
          data-state="ready"
          className="flex flex-wrap items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5"
          style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
        >
          <Icon name="task_alt" size={13} />
          <span className="flex-1">
            Shipped, not yet in a capability: every task is decided. Fold its requirements into the
            capability they change.
          </span>
          <Button variant="primary" size="xs" data-testid="fold-open" onClick={() => setFolding(true)}>
            Fold into capability…
          </Button>
        </div>
      )}
      {foldState?.state === 'folded' && (
        <p data-testid="fold-state" data-state="folded" style={{ color: 'var(--text-3)' }}>
          Folded into {foldState.capabilities.join(', ')}.
        </p>
      )}

      {/* Who reviews (F508): always said for a flow-delivered document, so the operator approves
          the staffing they were told about rather than learning it from a task's assignee. */}
      {(deliveryStatus?.state === 'ok' || deliveryStatus?.state === 'stale') && (
        <ReviewerLine status={deliveryStatus} />
      )}

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

        {document.phase === 'proposed' && roadmapSlice && (
          <label
            className="flex items-center gap-1"
            style={{ color: 'var(--text-2)' }}
            title={`This document specifies slice ${roadmapSlice.slice} of a roadmap. Approving it asks the agent that wrote it to draft the next slice once this one's tasks are approved or rejected.`}
          >
            <input
              type="checkbox"
              checked={draftNextSlice}
              disabled={busy}
              onChange={(event) => setDraftNextSlice(event.target.checked)}
            />
            Draft the next slice
          </label>
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
            value={pendingRigor ?? document.rigor}
            disabled={busy || setRigor.isPending}
            onChange={(event) => onChooseRigor(event.target.value as Rigor)}
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

        {/* The audit trail that makes demotion legitimate, beside the control that demotes. Absent
            until there is something in it. */}
        {history.length > 0 && (
          <button
            type="button"
            data-testid="spec-rigor-history-toggle"
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen((open) => !open)}
            className="flex items-center gap-1 rounded-[var(--radius-sm)] px-1.5 py-0.5 hover:bg-[var(--row-hover)]"
            style={{ color: 'var(--text-3)' }}
          >
            <Icon name="schedule" size={13} />
            History ({history.length})
          </button>
        )}
        {/* A failed read is said, not shown as "no changes yet" — the absent toggle means exactly
            that, so an error must not reach it (F197's shape). */}
        {historyError && (
          <span data-testid="spec-rigor-history-error" style={{ color: 'var(--amber)' }}>
            Could not load the rigor history: {readableApiError(historyError, 'the Hub did not answer.')}
          </span>
        )}
      </div>

      {/* A rigor change, waiting for its reason (design D2). A promotion may go without one; a
          demotion may not, because the reason is the record. */}
      {pendingRigor !== null && (
        <div
          data-testid="spec-rigor-confirm"
          className="flex flex-col gap-1.5 rounded-[var(--radius-sm)] px-2 py-1.5"
          style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
        >
          <span>
            Change enforcement from {RIGOR_LABEL[document.rigor]} to {RIGOR_LABEL[pendingRigor]}?
          </span>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              aria-label="Reason for the change"
              value={rigorReason}
              onChange={(event) => setRigorReason(event.target.value)}
              placeholder={demoting ? 'Why lower it?' : 'Why? (optional)'}
              maxLength={2000}
              className="min-w-0 flex-1 rounded-[var(--radius-sm)] px-1.5 py-0.5"
              style={{
                background: 'var(--bg)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
                fontSize: 11,
              }}
            />
            <Button
              variant="primary"
              size="xs"
              disabled={reasonMissing || setRigor.isPending}
              onClick={onConfirmRigor}
            >
              Confirm
            </Button>
            <Button variant="ghost" size="xs" disabled={setRigor.isPending} onClick={onCancelRigor}>
              Cancel
            </Button>
          </div>
          {reasonMissing && (
            <span style={{ color: 'var(--text-3)' }}>
              Say why — this is the record that makes lowering a gate legitimate.
            </span>
          )}
        </div>
      )}

      {historyOpen && history.length > 0 && (
        <ul
          data-testid="spec-rigor-history"
          className="flex flex-col gap-0.5 pl-1"
          style={{ color: 'var(--text-3)' }}
        >
          {history.map((event) => {
            const at = hubDate(event.created_at)
            return (
              <li key={event.id} className="flex flex-wrap items-baseline gap-x-1.5">
                <span style={{ color: 'var(--text-2)' }}>
                  {event.from} → {event.to}
                </span>
                <span>· {event.actor}</span>
                <span>· {event.reason ? event.reason : <em>no reason given</em>}</span>
                <span title={at.toLocaleString()}>
                  · {formatDistanceToNow(at, { addSuffix: true })}
                </span>
              </li>
            )
          })}
        </ul>
      )}

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

      {folding && (
        <FoldIntoCapabilityDialog
          path={document.path}
          title={document.title}
          onClose={() => setFolding(false)}
        />
      )}

      {confirmingArchive && (
        <ArchiveConfirmDialog
          title={document.title}
          isPending={setPhase.isPending}
          error={archiveRefusal}
          reasonPrompt={
            archiveNeedsReason
              ? 'This change is in no capability. Why does it change none? (Fold it instead if it does.)'
              : null
          }
          onCancel={() => setConfirmingArchive(false)}
          onConfirm={onConfirmArchive}
        />
      )}
    </div>
  )
}

function ReviewerLine({ status }: { status: SpecDeliveryStatus }) {
  const stale = Boolean(status.reviewer) && status.reviewer_state !== 'ok'
  return (
    <p
      data-testid="delivery-reviewer"
      data-stale={stale ? 'true' : 'false'}
      className="flex items-center gap-1.5"
      style={{ color: stale ? 'var(--amber)' : 'var(--text-3)' }}
    >
      {stale && <Icon name="warning" size={13} />}
      {!status.reviewer
        ? 'Reviewed by any free agent: the document names no reviewer.'
        : stale
          ? `Reviewed by @${status.reviewer}, ${
              status.reviewer_state === 'archived'
                ? 'which is archived'
                : 'which is not an agent on this project'
            }: its reviews will come to you.`
          : `Reviewed by @${status.reviewer}.`}
    </p>
  )
}
