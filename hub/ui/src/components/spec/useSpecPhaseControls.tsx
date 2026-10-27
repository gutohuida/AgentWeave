import { useSpecDeletionStore } from '@/store/specDeletionStore'
import * as React from 'react'
import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { ArchiveConfirmDialog } from '@/components/spec/ArchiveConfirmDialog'
import { DeleteConfirmDialog } from '@/components/common/DeleteConfirmDialog'
import { FoldIntoCapabilityDialog } from '@/components/spec/FoldIntoCapabilityDialog'
import { RetireCapabilityDialog } from '@/components/spec/RetireCapabilityDialog'
import { StartFlowDialog } from '@/components/spec/StartFlowDialog'
import { BuildDialog } from '@/components/spec/BuildDialog'
import { BuildStatusStrip } from '@/components/spec/BuildStatusStrip'
import { ReconcileSummary } from '@/components/spec/ReconcileSummary'
import { CloseAlreadyBuilt } from '@/components/spec/CloseAlreadyBuilt'
import { useDocumentFlow, type LoopSummary } from '@/api/loops'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MenuItem, MenuSeparator } from '@/components/ui/menu'
import { Segmented } from '@/components/ui/segmented'
import { Switch } from '@/components/ui/switch'
import { formatAgoLong, formatDateTime } from '@/lib/format'
import { toast } from '@/lib/toast'
import type { SpecPrimaryAction } from './SpecDocumentHeader'
import { GapLines, ReviewerLine } from './SpecPhaseParts'
import {
  useApproveAndBuildSpecDocument,
  useBuildSpecDocument,
  useCheckSpecDocument,
  useDeleteSpecDocument,
  useSetSpecJourney,
  useSetSpecPhase,
  useSetSpecRigor,
  useSpec,
  useSpecDocuments,
  useSpecRigorHistory,
  type BuildChoices,
  type SpecBlockingFinding,
  type SpecBuildOutcome,
  type SpecDocumentRecord,
  type SpecNextSliceOutcome,
  type SpecSize,
} from '@/api/spec'

type Rigor = SpecDocumentRecord['rigor']

/** Lowest to highest. A move down this list is a demotion, and a demotion made in the app needs a
 *  reason: the record is what makes lowering a gate legitimate (F429). */
const RIGOR_ORDER: Rigor[] = ['sketch', 'contract', 'gate']
const RIGOR_LABEL: Record<Rigor, string> = { sketch: 'Sketch', contract: 'Contract', gate: 'Gate' }


/** What a Build said: the flow's messages, then each declared builder no open agent answers to
 *  (`a-task-names-its-builder`) and, where a build was already running, that the tasks joined it. */
function buildOutcomeMessages(outcome: SpecBuildOutcome | undefined): string[] {
  const messages = [...(outcome?.flow?.messages ?? [])]
  for (const entry of outcome?.build?.unresolved_builders ?? []) {
    messages.push(
      `${entry.task}'s builder @${entry.builder} is not an open agent here; the task waits for the driver.`,
    )
  }
  if (outcome?.build?.message) messages.push(outcome.build.message)
  return messages
}

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

interface Refusal {
  /** What stops the move outright: Approve anyway does not get past these. */
  blocking: SpecBlockingFinding[]
  /** Gaps the Hub listed beside the refusal. */
  gaps: SpecBlockingFinding[]
  /** `approval_warnings`: the only refusal Approve anyway answers. */
  overridable: boolean
  /** `document_changed`: the document changed since it was loaded (`approve-what-was-seen`). */
  stale?: boolean
}

/** The approval the operator asked for, kept so Approve anyway resends the same one. */
interface PendingApproval {
  build: boolean
  choices?: BuildChoices
}

/**
 * What a refused phase move says. The Hub answers an incomplete document with `detail.blocking`
 * (the same list Check returns with a 200) and the gaps beside it as `detail.warnings`; an
 * approval stopped only by gaps answers `approval_warnings` with `detail.warnings`; any other
 * refusal is one message. `ApiError.message` is the response body verbatim, so the detail is parsed
 * back out of it.
 */
function readRefusal(error: unknown, fallback: string): Refusal {
  try {
    const raw = error instanceof Error ? error.message : String(error)
    const detail = (
      JSON.parse(raw) as {
        detail?: {
          code?: string
          message?: string
          blocking?: SpecBlockingFinding[]
          warnings?: SpecBlockingFinding[]
        }
      }
    ).detail
    if (detail?.code === 'document_changed') {
      return {
        blocking: [{ code: 'document_changed', where: '', message: detail.message ?? 'The document changed since it was loaded.' }],
        gaps: [],
        overridable: false,
        stale: true,
      }
    }
    const gaps = detail?.warnings ?? []
    if (detail?.code === 'approval_warnings' && gaps.length) {
      return { blocking: [], gaps, overridable: true }
    }
    if (detail?.blocking?.length) return { blocking: detail.blocking, gaps, overridable: false }
  } catch {
    // not JSON: fall through to the readable message
  }
  return {
    blocking: [{ code: 'refused', where: '', message: readableApiError(error, fallback) }],
    gaps: [],
    overridable: false,
  }
}

export interface SpecPhaseControls {
  document: SpecDocumentRecord
  /** The one action the document is waiting for, or null when nothing is. */
  primary: SpecPrimaryAction | null
  /** A control that qualifies the primary action (Draft the next slice, beside Approve). */
  beforePrimary: React.ReactNode
  /** Overflow-menu items: every other decision the operator can take on this document. */
  menu: React.ReactNode
  reopen?: () => void
  archive?: () => void
  remove?: () => void
  rigorChoice: { value: Rigor; onChange: (rigor: Rigor) => void; disabled: boolean }
  /** The decisions as plain calls, for a header that draws its own buttons (the redesigned page).
   *  `build` and `approveAndBuild` open the Build dialog in `dialogs`. */
  actions: {
    check: () => void
    approve: () => void
    approveAndBuild: () => void
    build: () => void
    reopen: () => void
    busy: boolean
  }
  /** What the last Check or refused approval found, as the Hub reported it. `checked` is true once
   *  a Check has answered, `clean` when it found nothing to block or warn about. */
  findings: { blocking: SpecBlockingFinding[]; gaps: SpecBlockingFinding[]; checking: boolean; checked: boolean; clean: boolean }
  /** Beside the phase: the flow the document runs. */
  badges: React.ReactNode
  /** What the controls produced: refusals, gaps, the journey, a rigor change waiting for its reason. */
  messages: React.ReactNode
  dialogs: React.ReactNode
}

/**
 * The phase of the open document, and the decisions only the operator can take, as the parts a
 * document header lays out (`SpecDocumentHeader`): one primary action, the rest in the overflow
 * menu, and the messages those actions produce. Null when the Hub tracks no record for the path.
 *
 * Every control here is deliberately absent from the agent's tool surface. An agent can write the
 * document and can see what is blocking it; it cannot approve, build, or reopen. That asymmetry
 * is the feature — the gate it replaced was a skill instructing the agent to read the document's
 * own status and stop, which is the agent checking its own permission slip.
 */
export function useSpecPhaseControls(
  path: string,
  onOpenLoop?: (loop: LoopSummary) => void,
  /** Called once the Hub has deleted this document (F829): the host leaves it. */
  onDeleted?: () => void,
  options: {
    /** The page draws Check's findings beside what they concern: leave them out of `messages`
     *  (a gap list Approve anyway answers stays). */
    inlineFindings?: boolean
  } = {},
): SpecPhaseControls | null {
  const { data } = useSpecDocuments()
  // `delivery_status` (design D5) rides the same `spec/<path>` query `SpecDocumentPanel` and
  // `SpecApprovalReport` already hold — one cache entry, not a second fetch.
  const { data: specDoc, isError: specDocError, refetch: reloadSpec } = useSpec(path)
  const { data: openAgentsData, isError: agentsError } = useAgents()
  const setJourney = useSetSpecJourney()
  const [journeyRefusal, setJourneyRefusal] = useState<string | null>(null)
  const check = useCheckSpecDocument()
  const build = useBuildSpecDocument()
  const approveAndBuild = useApproveAndBuildSpecDocument()
  const setPhase = useSetSpecPhase()
  const setRigor = useSetSpecRigor()
  const [blocking, setBlocking] = useState<SpecBlockingFinding[]>([])
  // Gaps the Hub listed at Check or approve (`approve-lists-what-is-missing-and-can-approve-
  // anyway`). Only an `approval_warnings` refusal makes them overridable: the one Approve anyway answers.
  const [gaps, setGaps] = useState<SpecBlockingFinding[]>([])
  const [gapsOverridable, setGapsOverridable] = useState(false)
  // What an approval told and did not gate on (F704: an unclaimed roadmap slice).
  const [approvalNotes, setApprovalNotes] = useState<SpecBlockingFinding[]>([])
  const [rigorRefusal, setRigorRefusal] = useState<string[]>([])
  const [confirmingArchive, setConfirmingArchive] = useState(false)
  const [archiveRefusal, setArchiveRefusal] = useState<string | null>(null)
  const [startingFlow, setStartingFlow] = useState(false)
  const [folding, setFolding] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [retiring, setRetiring] = useState(false)
  const [retireRefusal, setRetireRefusal] = useState<string | null>(null)
  const [deleteRefusal, setDeleteRefusal] = useState<string | null>(null)
  const deleteDocument = useDeleteSpecDocument()
  // Check's answer when nothing blocks (FR-1): said, so a clean check is not silence.
  const [checkedClean, setCheckedClean] = useState(false)
  const [checkedOnce, setCheckedOnce] = useState(false)
  // The Build dialog, for Build (an approved document) or Approve and build (FR-6, FR-7).
  const [building, setBuilding] = useState<null | 'build' | 'approve'>(null)
  const [buildRefusal, setBuildRefusal] = useState<string | null>(null)
  const [buildMessages, setBuildMessages] = useState<string[]>([])
  const [pendingApproval, setPendingApproval] = useState<PendingApproval>({ build: false })
  // On by default (C1a D4): approving a slice usually means "and now the next one".
  const [draftNextSlice, setDraftNextSlice] = useState(true)
  const [nextSliceOutcome, setNextSliceOutcome] = useState<SpecNextSliceOutcome | null>(null)
  // A rigor chosen and not yet confirmed. Choosing no longer posts: the change waits here for its
  // reason (design D2).
  const [pendingRigor, setPendingRigor] = useState<Rigor | null>(null)
  const [rigorReason, setRigorReason] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const { data: historyData, error: historyError } = useSpecRigorHistory(path)

  const inline = options.inlineFindings === true
  const document = data?.documents.find((entry) => entry.path === path)
  const flow = useDocumentFlow(document?.id)
  if (!document) return null

  // On a failed fetch there is nothing to flag as stale, and nothing to offer as a replacement —
  // the strip simply does not appear, the same "say nothing false" rule the rest of the bar
  // follows for a document the Hub does not track.
  const deliveryStatus = specDocError ? undefined : specDoc?.delivery_status
  const roadmapSlice = specDocError ? undefined : specDoc?.roadmap_slice
  const foldState = specDocError ? undefined : specDoc?.fold_state
  // F532: what the corpus or its history depends on is never offered for deletion. The Hub refuses
  // the rest when a run or a flow is working on it, and the confirm shows that refusal.
  const deletable =
    document.kind !== 'capability' &&
    document.phase !== 'archived' &&
    foldState?.state !== 'folded'
  // An approved change that no merge names archives only with a reason saying it changes no
  // capability (the Hub's archive guard). A Hub without `fold_state` never asks.
  const archiveNeedsReason =
    document.kind === 'change-spec' &&
    document.phase === 'approved' &&
    foldState !== undefined &&
    foldState.state !== 'folded'
  const openAgents = agentsError ? [] : (openAgentsData ?? [])

  const busy =
    setJourney.isPending ||
    check.isPending ||
    setPhase.isPending ||
    build.isPending ||
    approveAndBuild.isPending

  // A change being explored is written one step at a time; the operator can move it to any step and
  // change its size, each taking effect from the next turn (FR-10).
  const onJourney =
    document.kind === 'change-spec' && document.phase === 'exploring' && !!document.step
  function moveJourney(change: { step?: string; size?: SpecSize }) {
    setJourneyRefusal(null)
    setJourney.mutate(
      { path, ...change },
      {
        onError: (error: unknown) =>
          setJourneyRefusal(readableApiError(error, 'The Hub refused to change the journey.')),
      },
    )
  }

  function showRefusal(refusal: Refusal) {
    setBlocking(refusal.blocking)
    setGaps(refusal.gaps)
    setGapsOverridable(refusal.overridable)
    // The page then shows what the document holds now; the operator reads it and approves again.
    if (refusal.stale) void reloadSpec()
  }

  function clearFindings() {
    setBlocking([])
    setGaps([])
    setGapsOverridable(false)
    setApprovalNotes([])
    setCheckedClean(false)
    setCheckedOnce(false)
    setBuildMessages([])
  }

  async function onCheck() {
    clearFindings()
    try {
      const result = await check.mutateAsync({ path })
      // Exactly what the agent's own save reported, and nothing moved: the agent keeps writing
      // while the operator looks (`check-never-moves`). Every finding at once: one per attempt
      // turns five problems into five round trips.
      setCheckedOnce(true)
      setBlocking(result.blocking ?? [])
      setGaps(result.warnings ?? [])
      setCheckedClean((result.blocking ?? []).length === 0 && (result.warnings ?? []).length === 0)
    } catch (error) {
      // 422 (no payload / payload invalid) is said, not swallowed.
      showRefusal(readRefusal(error, 'The Hub could not check this document.'))
    }
  }

  /** The version of what the page shows: an approval names it (`approve-what-was-seen`). */
  const loadedVersion = specDoc?.content_version ?? ''

  function onApprove(anyway = false) {
    clearFindings()
    setNextSliceOutcome(null)
    setPendingApproval({ build: false })
    setPhase.mutate(
      {
        path,
        to: 'approved',
        content_version: loadedVersion,
        // Only for a slice document: the Hub that named `roadmap_slice` is the one that accepts it.
        ...(roadmapSlice ? { draft_next_slice: draftNextSlice } : {}),
        // Only on the resend from the gap list, never on a plain Approve (FR-1).
        ...(anyway ? { approve_anyway: true } : {}),
      },
      {
        onSuccess: (result) => {
          setNextSliceOutcome(result.next_slice ?? null)
          setApprovalNotes(result.approval_notes ?? [])
        },
        // F207: approval runs the completeness checks again. Gaps alone answer `approval_warnings`,
        // which Approve anyway gets past; a refusal answers `document_incomplete`; a document that
        // changed since it was loaded answers `document_changed`.
        onError: (error: unknown) =>
          showRefusal(readRefusal(error, 'The Hub refused to approve this document.')),
      },
    )
  }

  function onApproveAndBuild(choices: BuildChoices, anyway = false) {
    clearFindings()
    setNextSliceOutcome(null)
    setBuildRefusal(null)
    setPendingApproval({ build: true, choices })
    approveAndBuild.mutate(
      {
        path,
        content_version: loadedVersion,
        ...choices,
        ...(roadmapSlice ? { draft_next_slice: draftNextSlice } : {}),
        ...(anyway ? { approve_anyway: true } : {}),
      },
      {
        onSuccess: (result) => {
          setBuilding(null)
          setNextSliceOutcome(result.next_slice ?? null)
          setApprovalNotes(result.approval_notes ?? [])
          setBuildMessages(buildOutcomeMessages(result.build_outcome))
        },
        // Refused exactly as Approve is (FR-7): the gaps and Approve anyway show in the header.
        onError: (error: unknown) => {
          setBuilding(null)
          showRefusal(readRefusal(error, 'The Hub refused to approve this document.'))
        },
      },
    )
  }

  function onBuild(choices: BuildChoices) {
    setBuildRefusal(null)
    build.mutate(
      { path, ...choices },
      {
        onSuccess: (result) => {
          setBuilding(null)
          setBuildMessages(buildOutcomeMessages(result.build_outcome))
        },
        onError: (error: unknown) =>
          setBuildRefusal(readableApiError(error, 'The Hub refused to build this document.')),
      },
    )
  }

  function onApproveAnyway() {
    if (pendingApproval.build) onApproveAndBuild(pendingApproval.choices ?? {}, true)
    else onApprove(true)
  }

  function onReopen() {
    setPhase.mutate(
      { path, to: 'exploring' },
      {
        onSuccess: () => toast({ title: 'Reopened for changes', description: 'Its tasks are kept.' }),
        onError: (error: unknown) =>
          toast({ title: 'Could not reopen it', description: readableApiError(error, 'The Hub refused.'), tone: 'error' }),
      },
    )
  }

  async function onConfirmDelete() {
    setDeleteRefusal(null)
    try {
      const result = await deleteDocument.mutateAsync({ path })
      // F829: the page the operator lands on says what went; this panel is gone by then.
      useSpecDeletionStore.getState().set({ path, title: document?.title ?? path, tasks: result.tasks?.length ?? 0, kept: result.kept_work ?? [] })
      setConfirmingDelete(false)
      onDeleted?.()
    } catch (error) {
      setDeleteRefusal(readableApiError(error, 'The Hub refused to delete this document.'))
    }
  }

  function onConfirmArchive(reason: string) {
    setArchiveRefusal(null)
    setPhase.mutate(
      archiveNeedsReason
        ? { path, to: 'archived', reason, no_capability_change: true }
        : { path, to: 'archived' },
      {
        onSuccess: () => setConfirmingArchive(false),
        // It used to drop this, and the dialog simply stayed open. Archiving from `exploring` is
        // refused once the document has produced work, and the refusal says what to do instead.
        onError: (error: unknown) =>
          setArchiveRefusal(readableApiError(error, 'The Hub refused to archive this document.')),
      },
    )
  }

  function onConfirmRetire(reason: string, absorbedBy: string | null) {
    setRetireRefusal(null)
    setPhase.mutate(
      { path, to: 'archived', reason, ...(absorbedBy ? { absorbed_by: absorbedBy } : {}) },
      {
        onSuccess: () => setRetiring(false),
        // Open work on its requirements, or an absorber that is not a current capability.
        onError: (error: unknown) =>
          setRetireRefusal(readableApiError(error, 'The Hub refused to retire this capability.')),
      },
    )
  }

  const retirement = specDocError ? undefined : specDoc?.retired
  const otherCapabilities = (data?.documents ?? [])
    .filter((entry) => entry.kind === 'capability' && entry.phase === 'current' && entry.path !== path)
    .map((entry) => ({ path: entry.path, title: entry.title }))
  const absorberTitle = retirement?.absorbed_by
    ? (data?.documents.find((entry) => entry.path === retirement.absorbed_by)?.title ?? retirement.absorbed_by)
    : null

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

  // ── The one primary action ─────────────────────────────────────────────────────────────────
  // A finished change on its way into the corpus (`a-finished-change-is-folded-into-its-
  // capability`): every task decided and no merge names it yet. Folding is the close-out.
  const foldReady = document.phase === 'approved' && foldState?.state === 'ready'
  // A flow is offered on an approved change-spec only: earlier there are no tasks to work, other
  // kinds are not decomposed into flows, and an archived document is finished.
  const canStartFlow = document.kind === 'change-spec' && document.phase === 'approved' && !flow
  // Building is a separate action, possibly taken later than approval (`build-is-separate`).
  const canBuild = canStartFlow
  const isChange = document.kind === 'change-spec'
  let primary: SpecPrimaryAction | null = null
  if (document.phase === 'exploring') {
    primary = {
      label: 'Approve',
      reason: 'Approving lays its tasks out as a plan; nothing starts until you build it.',
      onClick: () => onApprove(),
      disabled: busy || !specDoc,
      testId: 'spec-approve',
    }
  } else if (foldReady) {
    primary = {
      label: 'Fold into capability…',
      reason: 'Shipped, not yet in a capability: every task is decided. Fold its requirements into the capability they change.',
      onClick: () => setFolding(true),
      testId: 'fold-open',
      reasonTestId: 'fold-state',
      reasonState: 'ready',
    }
  } else if (canBuild) {
    primary = {
      label: 'Build…',
      reason: 'Approved: its tasks are on the board. Build starts them as the document recommends.',
      onClick: () => {
        setBuildRefusal(null)
        setBuilding('build')
      },
      disabled: busy,
      testId: 'spec-build',
    }
  }

  // Check and Approve and build beside Approve while the document is written (FR-1, FR-7).
  const beforePrimary =
    document.phase === 'exploring' ? (
      <>
        {roadmapSlice ? (
          <label
            className="aw-spec-inline-switch"
            title={`This document specifies slice ${roadmapSlice.slice} of a roadmap. Approving it asks the agent that wrote it to draft the next slice once this one's tasks are approved or rejected.`}
          >
            <Switch
              size="sm"
              checked={draftNextSlice}
              disabled={busy}
              aria-label="Draft the next slice"
              onCheckedChange={setDraftNextSlice}
            />
            Draft the next slice
          </label>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          data-testid="spec-check"
          disabled={busy}
          title="Show what still blocks approval, as the agent's save reports it. Nothing moves."
          onClick={() => void onCheck()}
        >
          Check
        </Button>
        {isChange ? (
          <Button
            variant="outline"
            size="sm"
            data-testid="spec-approve-and-build"
            disabled={busy || !specDoc}
            title="Approve the version you read and start building it, in one action"
            onClick={() => {
              setBuildRefusal(null)
              setBuilding('approve')
            }}
          >
            Approve and build…
          </Button>
        ) : null}
      </>
    ) : null

  // ── The overflow menu ──────────────────────────────────────────────────────────────────────
  const menu = (
    <>
      {canStartFlow && primary?.testId !== 'spec-start-flow' ? (
        <MenuItem icon="play_arrow" data-testid="spec-start-flow" onSelect={() => setStartingFlow(true)}>
          Start a flow…
        </MenuItem>
      ) : null}
      {history.length > 0 ? (
        <MenuItem icon="schedule" data-testid="spec-rigor-history-toggle" onSelect={() => setHistoryOpen((open) => !open)}>
          {historyOpen ? 'Hide rigor history' : `Rigor history (${history.length})`}
        </MenuItem>
      ) : null}
      {document.kind === 'capability' && document.phase === 'current' ? (
        <>
          <MenuSeparator />
          <MenuItem
            icon="archive"
            data-testid="spec-retire-capability"
            disabled={busy}
            onSelect={() => {
              setRetireRefusal(null)
              setRetiring(true)
            }}
          >
            Retire…
          </MenuItem>
        </>
      ) : null}
    </>
  )

  // F205: `spec_lifecycle` has an archive edge from `exploring` too, added for F37 (a mistaken,
  // empty document nothing could retire). The Hub refuses it once the document has produced
  // requirements or tasks, and the dialog shows that refusal.
  const archive =
    document.phase === 'approved' || document.phase === 'exploring'
      ? () => {
          setArchiveRefusal(null)
          setConfirmingArchive(true)
        }
      : undefined
  const reopen = document.phase === 'approved' ? onReopen : undefined
  const remove = deletable
    ? () => {
        setDeleteRefusal(null)
        setConfirmingDelete(true)
      }
    : undefined

  const badges =
    document.kind === 'change-spec' && document.phase === 'approved' && flow ? (
      onOpenLoop && flow.agent ? (
        <button
          type="button"
          data-slot="spec-chip"
          className="aw-spec-chip aw-spec-flow-chip"
          data-testid="spec-flow-link"
          onClick={() => onOpenLoop(flow)}
          title="Open the flow working this document's tasks"
        >
          <Icon name="sync" size={11} />
          Flow: {flow.label}
        </button>
      ) : (
        <span className="aw-spec-chip aw-spec-flow-chip" data-static="true" data-testid="spec-flow-link">
          <Icon name="sync" size={11} />
          Flow: {flow.label}
        </span>
      )
    ) : null

  // ── Messages ───────────────────────────────────────────────────────────────────────────────
  const messages = (
    <>
      {nextSliceOutcome && (
        <p className="aw-spec-message" data-testid="next-slice-outcome">
          <span className="aw-spec-message-text">{nextSliceMessage(nextSliceOutcome)}</span>
        </p>
      )}

      {/* A stale recommendation (design D5/D5b): the recommended agent is archived or unknown,
          so building as written would start no flow. The Build dialog chooses another agent, for
          that build only; the document is never rewritten. */}
      {deliveryStatus?.state === 'stale' && (
        <div className="aw-spec-message" data-tone="warn" data-testid="delivery-stale-strip">
          <Icon name="warning" size={13} />
          <span className="aw-spec-message-text">
            The recommended build names {deliveryStatus.agent || 'no agent'}, which is{' '}
            {deliveryStatus.reason === 'archived' ? 'archived' : 'not an agent on this project'}.
            {' '}Building will not start a flow unless you choose another agent in the Build dialog.
          </span>
        </div>
      )}

      {checkedClean && !inline && (
        <p className="aw-spec-message" data-testid="spec-check-clean">
          <span className="aw-spec-message-text">Checked: nothing blocks approval, and nothing moved.</span>
        </p>
      )}

      {buildMessages.length > 0 && (
        <div className="aw-spec-message" data-testid="spec-build-outcome">
          {buildMessages.map((message, i) => (
            <span key={i} className="aw-spec-message-text">
              {message}
            </span>
          ))}
        </div>
      )}

      {/* The build running now (or the last one stopped): driver, level, spend of cap, window,
          with Stop and Raise cap (`a-build-has-a-driver-a-level-and-its-people`). */}
      {!specDocError && specDoc?.builds?.length ? <BuildStatusStrip build={specDoc.builds[0]!} /> : null}

      {/* reconcile-and-measure: what reconciling the change with its code found, while it is
          approved. Its full form, and the ask, are in the fold dialog. */}
      {document.phase === 'approved' && (
        <ReconcileSummary path={document.path} result={foldState?.reconcile} compact />
      )}
      {/* every-task-can-always-be-moved-on FR-5: an approved change whose work already shipped
          closes its open tasks in one step, checked through its evidence rather than rebuilt. */}
      {document.kind === 'change-spec' && document.phase === 'approved' && (
        <CloseAlreadyBuilt
          path={document.path}
          documentId={document.id}
          offer={specDocError ? undefined : specDoc?.approval_outcome?.already_built}
        />
      )}
      {foldState?.state === 'folded' && (
        <p className="aw-spec-message" data-testid="fold-state" data-state="folded">
          <span className="aw-spec-message-text">Folded into {foldState.capabilities.join(', ')}.</span>
        </p>
      )}

      {/* Who reviews (F508): always said for a flow-delivered document, so the operator approves
          the staffing they were told about rather than learning it from a task's assignee. */}
      {(deliveryStatus?.state === 'ok' || deliveryStatus?.state === 'stale') && (
        <ReviewerLine status={deliveryStatus} />
      )}

      {onJourney && (
        <div className="aw-spec-message">
          <nav aria-label="Journey" data-testid="spec-journey" className="aw-spec-journey">
            {(document.journey ?? []).map((step, index) => {
              const current = step === document.step
              return (
                <span key={step} className="flex items-center gap-1">
                  {index > 0 && <Icon name="chevron_right" size={11} />}
                  <button
                    type="button"
                    data-slot="journey-step"
                    className="aw-spec-journey-step"
                    data-testid={`spec-journey-step-${step}`}
                    aria-current={current ? 'step' : undefined}
                    disabled={busy || current}
                    title={current ? 'The step the next turn is briefed with' : `Move to ${step}`}
                    onClick={() => moveJourney({ step })}
                  >
                    {step}
                  </button>
                </span>
              )
            })}
          </nav>
          <span className="ml-auto" data-testid="spec-journey-size" data-value={document.size ?? ''}>
            <Segmented
              label="Size"
              size="xs"
              value={(document.size ?? '') as SpecSize}
              onChange={(size) => {
                if (!busy) moveJourney({ size })
              }}
              options={[
                { value: 'fix', label: 'Fix' },
                { value: 'small', label: 'Small' },
                { value: 'large', label: 'Large' },
              ]}
            />
          </span>
        </div>
      )}
      {journeyRefusal && (
        <p className="aw-spec-message" data-tone="error" data-testid="spec-journey-refusal" role="alert">
          <span className="aw-spec-message-text">{journeyRefusal}</span>
        </p>
      )}

      {/* A rigor change, waiting for its reason (design D2). A promotion may go without one; a
          demotion may not, because the reason is the record. */}
      {pendingRigor !== null && (
        <div className="aw-spec-message" data-testid="spec-rigor-confirm">
          <span className="aw-spec-message-text">
            Change enforcement from {RIGOR_LABEL[document.rigor]} to {RIGOR_LABEL[pendingRigor]}?
          </span>
          <Input
            type="text"
            aria-label="Reason for the change"
            value={rigorReason}
            onChange={(event) => setRigorReason(event.target.value)}
            placeholder={demoting ? 'Why lower it?' : 'Why? (optional)'}
            maxLength={2000}
            className="min-w-0 flex-1"
          />
          <Button variant="primary" size="xs" disabled={reasonMissing || setRigor.isPending} onClick={onConfirmRigor}>
            Confirm
          </Button>
          <Button variant="ghost" size="xs" disabled={setRigor.isPending} onClick={onCancelRigor}>
            Cancel
          </Button>
          {reasonMissing && (
            <span className="w-full" style={{ color: 'var(--text-3)' }}>
              Say why — this is the record that makes lowering a gate legitimate.
            </span>
          )}
        </div>
      )}

      {historyOpen && history.length > 0 && (
        <ul className="aw-spec-message" data-testid="spec-rigor-history">
          {history.map((event) => (
            <li key={event.id} className="flex w-full flex-wrap items-baseline gap-x-1.5">
              <span style={{ color: 'var(--text)' }}>
                {RIGOR_LABEL[event.from as Rigor] ?? event.from} → {RIGOR_LABEL[event.to as Rigor] ?? event.to}
              </span>
              <span>· {event.actor}</span>
              <span>· {event.reason ? event.reason : <em>no reason given</em>}</span>
              <span title={formatDateTime(event.created_at)}>· {formatAgoLong(event.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
      {/* A failed read is said, not shown as "no changes yet" — the absent menu item means exactly
          that, so an error must not reach it (F197's shape). */}
      {historyError && (
        <p className="aw-spec-message" data-tone="warn" data-testid="spec-rigor-history-error">
          <span className="aw-spec-message-text">
            Could not load the rigor history: {readableApiError(historyError, 'the Hub did not answer.')}
          </span>
        </p>
      )}

      {/* Why a promotion was refused. A document that cannot be read cannot be enforced, and
          saying only "refused" leaves the operator guessing at which of several things is wrong. */}
      {rigorRefusal.length > 0 && (
        <ul className="aw-spec-message" data-tone="warn" data-testid="spec-rigor-refusal">
          {rigorRefusal.map((reason) => (
            <li key={reason} className="flex items-start gap-1.5">
              <Icon name="warning" size={13} />
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      )}

      {gaps.length > 0 && (!inline || gapsOverridable) && (
        <div className="aw-spec-message" data-tone="warn" data-testid="approval-warnings">
          <span className="aw-spec-message-text">
            {gapsOverridable
              ? 'Not approved: the Hub found these gaps. Approve anyway records them on the document.'
              : 'Gaps approval will list:'}
          </span>
          {gapsOverridable && document.phase === 'exploring' && (
            <Button
              variant="primary"
              size="xs"
              data-testid="spec-approve-anyway"
              disabled={busy}
              onClick={onApproveAnyway}
            >
              {pendingApproval.build ? 'Approve and build anyway' : 'Approve anyway'}
            </Button>
          )}
          <GapLines gaps={gaps} />
        </div>
      )}

      {approvalNotes.length > 0 && (
        <div className="aw-spec-message" data-testid="approval-notes">
          <span className="aw-spec-message-text">Approved. For your information:</span>
          <GapLines gaps={approvalNotes} />
        </div>
      )}

      {/* What the approval overrode stays beside the phase while the document is approved (FR-5,
          FR-7): the record of the operator's judgement, not a to-do. */}
      {document.phase === 'approved' && (document.approval_warnings_overridden?.length ?? 0) > 0 && (
        <div className="aw-spec-message" data-testid="approval-overridden">
          <span className="aw-spec-message-text">Approved over these gaps:</span>
          <GapLines gaps={document.approval_warnings_overridden ?? []} />
        </div>
      )}

      {blocking.length > 0 && !inline && (
        <ul className="aw-spec-message" data-tone="warn" data-testid="spec-blocking">
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

      {document.kind === 'capability' && document.phase === 'archived' && retirement && (
        <p className="aw-spec-message" data-testid="spec-retired-note">
          <span className="aw-spec-message-text">
            Retired{retirement.at ? ` ${formatAgoLong(retirement.at)}` : ''}: {retirement.reason}
            {absorberTitle ? ` Absorbed by ${absorberTitle}.` : ''}
          </span>
        </p>
      )}
    </>
  )

  const dialogs = (
    <>
      {startingFlow && (
        <StartFlowDialog document={{ id: document.id, title: document.title }} onClose={() => setStartingFlow(false)} />
      )}

      {building && (
        <BuildDialog
          title={document.title}
          approve={building === 'approve'}
          recommended={specDocError ? undefined : specDoc?.recommended_build}
          openAgents={openAgents.map((agent) => agent.name)}
          isPending={build.isPending || approveAndBuild.isPending}
          error={buildRefusal}
          onCancel={() => setBuilding(null)}
          onConfirm={(choices) =>
            building === 'approve' ? onApproveAndBuild(choices) : onBuild(choices)
          }
        />
      )}

      {confirmingDelete && (
        <DeleteConfirmDialog
          heading={`Delete “${document.title}”?`}
          body="Its file, its requirements and their evidence, and every task it put on the board go with it."
          confirmLabel="Delete document"
          isPending={deleteDocument.isPending}
          error={deleteRefusal}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={onConfirmDelete}
        />
      )}

      {retiring && (
        <RetireCapabilityDialog
          title={document.title}
          capabilities={otherCapabilities}
          isPending={setPhase.isPending}
          error={retireRefusal}
          onCancel={() => setRetiring(false)}
          onConfirm={onConfirmRetire}
        />
      )}

      {folding && <FoldIntoCapabilityDialog path={document.path} title={document.title} onClose={() => setFolding(false)} />}

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
    </>
  )

  return {
    document,
    primary,
    beforePrimary,
    menu,
    reopen,
    archive,
    remove,
    rigorChoice: { value: pendingRigor ?? document.rigor, onChange: onChooseRigor, disabled: busy || setRigor.isPending },
    actions: {
      check: () => void onCheck(),
      approve: () => onApprove(),
      approveAndBuild: () => {
        setBuildRefusal(null)
        setBuilding('approve')
      },
      build: () => {
        setBuildRefusal(null)
        setBuilding('build')
      },
      reopen: onReopen,
      busy,
    },
    findings: { blocking, gaps, checking: check.isPending, checked: checkedOnce, clean: checkedClean },
    badges,
    messages,
    dialogs,
  }
}
