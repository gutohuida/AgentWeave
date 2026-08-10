import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useSSEConnectionState } from '@/hooks/useSSE'
import {
  AgentSummary,
  useAgentOutput,
  useAgents,
  useAgentTimeline,
} from '@/api/agents'
import {
  conversationLabel,
  useAgentChatHistory,
  useAgentConversations,
  useAgentRecentChat,
  releaseConversationTask,
  type AgentConversation,
} from '@/api/agentChat'
import { PERMISSION_MODE_CONTROL } from '@/api/modelCatalog'
import { NEW_CONVERSATION_ID } from '@/lib/navigation'
import { useQueueStatus, useQueuedEntries, withdrawQueueEntry } from '@/api/queue'
import { useRunners } from '@/api/runners'
import { useWorkspacePaths } from '@/api/workspace'
import {
  continueConversation,
  cutOver,
  dismissCheckpointWarning,
  takeCheckpoint,
  useCheckpoints,
} from '@/api/checkpoints'
import { ApiError } from '@/api/client'
import { useConfigStore } from '@/store/configStore'
import { AgentTimeline } from './AgentTimeline'
import { BannerStack, type ConversationBanner } from './BannerStack'
import { Composer } from './Composer'
import { PermissionRequestCard } from './PermissionRequestCard'
import { AgentQuestionCard } from './AgentQuestionCard'
import { UnaskedQuestionCard } from './UnaskedQuestionCard'
import { usePendingPermissionRequests } from '@/api/permissions'
import { usePendingUnaskedQuestions } from '@/api/unaskedQuestions'
import { activeQuestionFor } from '@/lib/pendingQuestions'
import { useAnswerQuestion, useQuestions } from '@/api/questions'
import { ConversationControls, type HandoffState } from './ConversationControls'
import { agentColorVars } from '@/lib/agentColors'

interface AgentOutputPanelProps {
  agent: AgentSummary
  onBackToProject?: () => void
  /** The conversation-header entry point to this agent's configuration. The other is the agent's
   *  row menu in navigation; both reach the same destination. */
  onOpenAgentSettings?: () => void
  /** The conversation this panel renders, resolved by the destination. `null` means the agent
   *  has none yet, and the next message starts one. */
  conversationId?: string | null
  /** Move the destination. The panel calls this for the moves it causes itself — the trigger
   *  returning a real conversation id for a first message. It never holds the answer; the
   *  destination does. */
  onSelectConversation?: (conversationId: string | null) => void
  /** The specification document the operator has open, when this panel is the specification
   *  workspace's chat. Sent with the trigger so the Hub can name it in the turn context; never
   *  added to the operator's message. `null` on every other surface, and on the Spec page
   *  before a document resolves. */
  specDocumentPath?: string | null
  /** The open document's display name, and the way to choose another. Both come from the
   *  conversation view, which owns the picker; omitted, the composer renders no Spec pill. */
  specDocumentLabel?: string | null
  onOpenSpecPicker?: () => void
}

/* Both prompts that used to live here are gone, and nothing replaces them.
 *
 * They asked the agent to invoke an `aw-checkpoint` skill AgentWeave never installed and to
 * write beneath `.agentweave/shared/checkpoints/`, a path outside its own worktree — one runtime
 * was sandbox-blocked from it, the other silently created a nested copy nothing reads. The
 * successor was then told to read `.agentweave/shared/context.md`, which nothing has ever
 * written. Both presses reported "Handoff ready", because readiness meant the run had ended.
 *
 * The Hub now generates the checkpoint from the conversation's own record and hands it to the
 * successor as a queued entry, so there is no prompt to send and no file for anyone to find.
 */
interface TriggerResult {
  status: string
  waiting_reason?: string | null
  conversation_id: string
  provider_session_id?: string | null
}

function emptyToUndefined(overrides: Record<string, string>): Record<string, string> | undefined {
  return Object.keys(overrides).length > 0 ? overrides : undefined
}

/** A stable identity for "this agent states no defaults", so the Composer's memoized children do
 *  not re-render on every parent render for want of one. */
const EMPTY_CONTROLS: Record<string, string> = {}

/** Titles are capped at 120 characters; the continuity line is one row of 11px text under the
 *  composer. Shortened here rather than at the source, because the rail wants the whole thing. */
const CONTINUITY_LABEL_MAX = 44
function continuityLabel(conversation: AgentConversation): string {
  const label = conversationLabel(conversation)
  return label.length > CONTINUITY_LABEL_MAX ? `${label.slice(0, CONTINUITY_LABEL_MAX).trimEnd()}…` : label
}

export function AgentOutputPanel({
  agent,
  onBackToProject,
  onOpenAgentSettings,
  conversationId = null,
  onSelectConversation,
  specDocumentPath = null,
  specDocumentLabel = null,
  onOpenSpecPicker,
}: AgentOutputPanelProps) {
  // `lines` is no longer read here. Its only consumer was the effect that watched the output
  // stream for a completed run in order to call a handoff "ready" — the exact inference this
  // capability replaces. The hook itself stays: it keeps the output subscription alive and
  // still answers `isLoading`.
  const { isLoading } = useAgentOutput(agent.name)
  const bottomRef    = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoscroll, setAutoscroll] = useState(true)

  const { apiKey, selectedProjectId: projectId } = useConfigStore()
  const [isSending, setIsSending] = useState(false)
  const onSelectConversationRef = useRef(onSelectConversation)
  onSelectConversationRef.current = onSelectConversation
  /** Where the panel itself last sent the destination — the first message of a new conversation
   *  landing on its real id, or the handoff handing over to a fresh one. The reset below exists
   *  for the operator *leaving* a conversation; a move the panel just made is a continuation of
   *  what it was already doing, and resetting it would wipe the state and the notice set in the
   *  same batch. Recorded as the destination rather than a bare flag so it can only ever suppress
   *  the arrival it was set for. */
  const selfDirectedMoveRef = useRef<string | null | undefined>(undefined)
  const moveTo = (next: string | null) => {
    if (!onSelectConversationRef.current) return
    selfDirectedMoveRef.current = next
    onSelectConversationRef.current(next)
  }
  const [handoffState, setHandoffState] = useState<HandoffState>('idle')
  /** Set once a handoff has been prepared: the conversation on screen is finished, and the next
   *  message must start a fresh one carrying the resume prefix. Local rather than a destination,
   *  because no conversation exists to navigate to yet — moving the destination here would send
   *  the operator to the new-conversation surface and lose the prepared handoff with it. */
  const [startingFresh, setStartingFresh] = useState(false)
  const [sessionNotice, setSessionNotice] = useState<string | null>(null)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [isStopping, setIsStopping] = useState(false)
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, string>>({})
  /** Dismissed in this session, before the stored state has been read back. Cleared on arrival
   *  at another conversation by the reset effect, which is where every per-conversation flag
   *  belongs. */
  const [warningDismissed, setWarningDismissed] = useState(false)
  const [releasedBinding, setReleasedBinding] = useState(false)
  const { data: permissionRequests = [] } = usePendingPermissionRequests()
  const { data: unaskedQuestions = [] } = usePendingUnaskedQuestions()
  const { data: openQuestions = [] } = useQuestions(false)
  const answerQuestion = useAnswerQuestion()
  const [questionSelection, setQuestionSelection] = useState<string[]>([])
  const [composerDraft, setComposerDraft] = useState('')
  // The same selector the card renders from. Deriving it separately here was safe while only one
  // question could be outstanding; with a batch the two could order differently, and the operator
  // would read one question while answering another.
  const pendingQuestion = activeQuestionFor(openQuestions, agent.name).question
  const { data: conversations = [] } = useAgentConversations(agent.name)
  // Read inside the effect below rather than as a dependency: useAgentConversations's
  // mocked (and, across a react-query refetch, sometimes genuinely fresh) array
  // reference changes more often than the value it carries — depending on the array
  // itself re-fires the effect on every such change and loops forever when the derived
  // setState result is itself a new object each time.
  const conversationsRef = useRef(conversations)
  conversationsRef.current = conversations

  // Arriving at a different conversation clears everything that described the last one. The
  // auto-select-most-recent effect that used to sit beside this is gone: it is now part of
  // resolving the destination (`resolveConversationSelection`), which is what makes it possible
  // to *not* auto-select onto the new-conversation surface.
  useEffect(() => {
    const sentTo = selfDirectedMoveRef.current
    selfDirectedMoveRef.current = undefined
    if (sentTo !== undefined && sentTo === conversationId) return
    setHandoffState('idle')
    setStartingFresh(false)
    setWarningDismissed(false)
    setReleasedBinding(false)
    setSessionNotice(null)
    setSubmissionError(null)
    setIsStopping(false)
  }, [agent.name, conversationId])

  // The composer's model/effort pills show the open conversation's own persisted overrides
  // (task: "An override survives reload"). Task 8.4: this still fires on conversation change now
  // that the conversation arrives as a prop rather than as local state.
  useEffect(() => {
    const current = conversationsRef.current.find((c) => c.id === conversationId)
    const seeded = current?.runtime_overrides ?? {}
    // Skip the update when the seeded value is already equivalent — without this, a
    // fresh-but-equal object from a react-query refetch would still trigger a render.
    setPendingOverrides((existing) =>
      JSON.stringify(existing) === JSON.stringify(seeded) ? existing : seeded,
    )
    // conversations.length (not the array itself) re-seeds once the list first arrives,
    // without depending on an identity that changes more often than its content does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent.name, conversationId, conversations.length])

  useEffect(() => {
    if (agent.status !== 'running') setIsStopping(false)
  }, [agent.status])

  /* The effect that used to sit here is deleted, not replaced.
   *
   * It watched the output stream for a completed run and, on seeing one, declared "Handoff
   * ready". That is precisely the defect this capability removes: readiness meant the run had
   * ended, so a run that wrote nothing and asked the operator a question was reported ready
   * twice. Readiness is now a property of a checkpoint record that exists and passed its probes,
   * which the Hub decides and `handleCheckpoint` reads from the response.
   */

  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoscroll(atBottom)
  }

  /** Move the viewport to the newest entry.
   *
   * Assigns `scrollTop` rather than calling `scrollIntoView({behavior:'smooth'})` or deferring
   * through `requestAnimationFrame`. Both of those are driven by the browser's frame loop, and a
   * document that is not being painted — an unfocused or offscreen window — starves it: measured
   * live, `rAF` never fired and a smooth scroll left `scrollTop` at 0, while a direct assignment
   * landed immediately. Following a conversation must not depend on whether the window happens to
   * be painting.
   */
  function scrollToNewest() {
    const el = containerRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  const isRunning = agent.status === 'running'
  const handoffUnavailable = agent.runner === 'manual'
  const interactionLocked =
    isRunning || isSending || handoffState === 'preparing'
  // A prepared handoff closes the conversation on screen even though the destination still names
  // it: nothing further belongs in it, so it stops being the open conversation here.
  const currentConversationId = startingFresh ? undefined : conversationId ?? undefined
  // Sending with nothing open starts a conversation whether or not the operator asked for one
  // explicitly — a brand-new agent has none to continue either.
  const startsFresh = !currentConversationId
  const currentConversation = conversations.find((c) => c.id === currentConversationId)

  const { data: roster = [] } = useAgents()
  const { data: runners = [] } = useRunners()
  const targetAgentRow = roster.find((a) => a.name === agent.name)
  const targetRunnerRow = runners.find((r) => r.id === targetAgentRow?.runner_id)
  // What the run will do at rest, from the agent rather than from the catalog. The Composer
  // layers the conversation's own overrides on top of this; it sends only those, so showing the
  // agent's default here states what will happen without silently turning it into a choice the
  // operator made for this one conversation.
  const agentDefaultControls = targetAgentRow?.default_permission_mode
    ? { [PERMISSION_MODE_CONTROL]: targetAgentRow.default_permission_mode }
    : EMPTY_CONTROLS
  const { data: timelineEvents = [] } = useAgentTimeline(agent.name)
  const { data: queueStatus } = useQueueStatus(agent.name)
  /** Undelivered entries addressed to the conversation on screen. A checkpoint handed to a
   *  successor is exactly this, which is why the Continue control keys on it rather than on
   *  "was this conversation created by a handoff". */
  const { data: queuedEntries = [] } = useQueuedEntries(agent.name)
  const hasQueuedWork = queuedEntries.some(
    (entry) => entry.conversation_id === currentConversationId,
  )
  const { data: workspacePaths = [] } = useWorkspacePaths()
  const conversationChat = useAgentChatHistory(agent.name, currentConversationId ?? null)
  const recentChat = useAgentRecentChat(agent.name)
  const chat = currentConversationId ? conversationChat : recentChat
  const timelineEntries = chat.data?.entries ?? []
  const sseConnectionState = useSSEConnectionState()

  // Follow the entries the timeline actually renders. This used to depend on `lines` — the
  // legacy raw output log from `useAgentOutput`, which is not what this view shows — so new
  // conversation content grew the DOM without ever scrolling, and unrelated log lines scrolled
  // for content nobody was looking at (2026-08-06-agent-permissions-tool-schemas-and-base-knowledge).
  useLayoutEffect(() => {
    if (autoscroll) scrollToNewest()
  }, [timelineEntries.length, autoscroll])

  // Opening or switching a conversation lands on its newest entry, and resumes following. Nothing
  // did this before, so a conversation with history opened at its oldest message. A layout effect
  // runs after the entries are in the DOM but before paint, so the jump is never visible as a
  // scroll — and `timelineEntries.length` is a dependency because the entries usually arrive a
  // render after the conversation identity changes.
  useLayoutEffect(() => {
    scrollToNewest()
    setAutoscroll(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent.name, currentConversationId])

  const [foldAllSignal, setFoldAllSignal] = useState(0)

  // Fixed evaluation order so a cleared condition never reshuffles the ones
  // that remain (design.md: "Conditions are reported in a banner stack").
  /**
   * A checkpoint the Hub made on its own, waiting to be acted on.
   *
   * Under `offered` the threshold produces a real, probed checkpoint and broadcasts
   * `checkpoint_ready` — and until now nothing listened, so the offer existed only in the
   * database. Confirmed on a live agent: two checkpoints written, both ready, both probes
   * passed, and the operator reported that checkpointing "did not work". A signal nothing
   * surfaces is the exact defect this capability was built to remove.
   *
   * Only `ready` counts. `unwritten` has nothing to read and `failed` disagreed with the
   * database, and neither is something to offer a successor.
   */
  const { data: checkpoints = [] } = useCheckpoints(currentConversationId ?? null)
  const offeredCheckpoint = checkpoints.find(
    (checkpoint) => checkpoint.status === 'ready' && checkpoint.trigger === 'context_pressure',
  )

  const handleCutOver = async () => {
    if (!projectId || !offeredCheckpoint || isSending) return
    setIsSending(true)
    try {
      const result = await cutOver(projectId, offeredCheckpoint.id)
      moveTo(result.successor_conversation_id)
      setSessionNotice('Continuing in a new conversation')
    } catch (err) {
      console.error('Failed to cut over:', err)
      setSessionNotice(
        err instanceof ApiError && err.status === 409
          ? 'Cannot cut over yet — finish or stop the run, and let queued messages deliver'
          : 'Could not cut over',
      )
    } finally {
      setIsSending(false)
    }
  }

  /**
   * The threshold has been reached and nothing has been spent yet.
   *
   * Under `offered` the Hub no longer generates on its own: generating billed a model call
   * whether or not the operator wanted one, and at a low threshold billed it again every turn.
   * The warning hands the decision over instead, and dismissing it is final for this
   * conversation — re-asking someone who said "not yet" is the same as not letting them say it.
   */
  const checkpointWarning = conversations.find(
    (item) => item.id === currentConversationId,
  )?.checkpoint_warning

  const checkpointDue = !warningDismissed && checkpointWarning === 'due'

  /**
   * The dismissal has run out of room.
   *
   * Deliberately not guarded by `warningDismissed`. That flag exists to hide the *first* warning
   * between the click and the refetch that confirms it — and this state is only reachable because
   * that click happened, so the flag is true by definition every time this matters. Reading it
   * here would hide the one warning that cannot be hidden.
   */
  const checkpointFinal = checkpointWarning === 'final'

  const handleDismissWarning = async () => {
    if (!projectId || !currentConversationId) return
    try {
      // Hidden here and persisted there. The local flag makes the banner go away on the click
      // rather than on the next refetch; the stored state is what keeps it away afterwards.
      setWarningDismissed(true)
      await dismissCheckpointWarning(projectId, currentConversationId)
    } catch (err) {
      console.error('Failed to dismiss the checkpoint warning:', err)
    }
  }

  /**
   * The task every turn in this thread is bound to, and checked against at its end.
   *
   * Shown because the binding is otherwise invisible: it decides whether work is checked, it now
   * survives across turns, and an operator who cannot see it cannot tell why a thread keeps
   * attributing turns to something they have moved on from. Releasing is the one thing nothing
   * infers on their behalf.
   */
  // Hidden here and dropped there, the same shape as the checkpoint dismissal: the banner goes on
  // the click, and the refetch is what keeps it gone.
  const boundTaskId = releasedBinding
    ? null
    : conversations.find((item) => item.id === currentConversationId)?.task_id

  const bannerCandidates: Array<ConversationBanner | null> = [
    boundTaskId
      ? {
          id: 'conversation-task-binding',
          // Neither an offer nor a problem: it is a statement of what this thread is for.
          tone: 'info' as const,
          message: `Every turn here counts towards task ${boundTaskId}, and is checked when it ends.`,
          secondaryAction: {
            label: 'Work on something else',
            onClick: () => {
              if (!projectId || !currentConversationId) return
              setReleasedBinding(true)
              void releaseConversationTask(projectId, agent.name, currentConversationId).catch(
                (err) => {
                  // Put it back. A binding that looks released but is not would leave the operator
                  // believing this thread no longer counts towards the task while it still does.
                  setReleasedBinding(false)
                  console.error('Failed to release the conversation binding:', err)
                },
              )
            },
          },
        }
      : null,
    checkpointDue
      ? {
          id: 'checkpoint-due',
          tone: 'offer' as const,
          message:
            'This conversation has reached its checkpoint threshold. Nothing has been written '
            + 'yet — checkpoint now, or dismiss this and keep working.',
          // Called through a closure: `handleCheckpoint` is declared below, and referencing it
          // directly here would read it before its binding is initialised.
          action: {
            label: 'Checkpoint now',
            onClick: () => void handleCheckpoint(),
            pending: isSending,
          },
          secondaryAction: { label: 'Dismiss', onClick: () => void handleDismissWarning() },
        }
      : null,
    checkpointFinal
      ? {
          id: 'checkpoint-final',
          // A problem, not an offer: what happens next if nothing is done is the loss itself.
          tone: 'problem' as const,
          message:
            'This conversation is nearly out of context. If nothing is written now it will be '
            + 'compacted by the CLI, and what survives will be a summary nobody wrote.',
          action: {
            label: 'Checkpoint now',
            onClick: () => void handleCheckpoint(),
            pending: isSending,
          },
          // No secondary action, deliberately. Dismissal was already spent to get here.
        }
      : null,
    offeredCheckpoint
      ? {
          id: 'checkpoint-offered',
          tone: 'offer' as const,
          message:
            'A checkpoint is ready for this conversation. Cutting over continues in a new one '
            + 'and archives this.',
          action: { label: 'Cut over', onClick: handleCutOver, pending: isSending },
        }
      : null,
    submissionError ? { id: 'run-failure', message: submissionError } : null,
    sseConnectionState === 'reconnecting'
      ? { id: 'stream-loss', message: 'Live updates are disconnected — reconnecting…' }
      : null,
    timelineEntries.some((entry) => entry.hop_budget_exceeded)
      ? { id: 'blocked-queue', message: 'Queued messages are blocked by the hop limit — deliver now to continue.' }
      : null,
  ]
  const banners: ConversationBanner[] = bannerCandidates.filter(
    (banner): banner is ConversationBanner => banner !== null,
  )

  const handleWithdraw = (entryId: string) => {
    if (!projectId) return
    void withdrawQueueEntry(projectId, entryId)
  }

  const postTrigger = async (
    triggerMessage: string,
    conversationId?: string,
    agentName: string = agent.name,
    overrides?: Record<string, string>,
  ): Promise<TriggerResult> => {
    const response = await fetch(`/api/v1/projects/${projectId}/agent/trigger`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        agent: agentName,
        message: triggerMessage,
        conversation_id: conversationId,
        overrides,
        // Where the operator is looking, not what they said. The Hub renders it into the turn
        // context and never into the stored message. Omitted entirely when there is nothing
        // open, so the Hub is told "no document" rather than an empty string to interpret.
        spec_document: specDocumentPath ?? undefined,
      }),
    })
    if (!response.ok) {
      throw new Error(`Trigger failed with status ${response.status}`)
    }
    return (await response.json()) as TriggerResult
  }

  // A 200 response does not mean the agent actually ran — the Hub can accept the input and
  // still leave it queued (no worktree yet, still running, etc). `status` tells the two
  // apart; without checking it here, a queued trigger looked identical to a running one and
  // the operator got no feedback at all (the "sent a message and nothing happened" report).
  const queuedNotice = (result: TriggerResult, fallback: string): string | null =>
    result.status === 'queued' ? (result.waiting_reason ?? fallback) : null

  const handleStop = async () => {
    if (!apiKey || !projectId || !isRunning || isStopping) return
    setIsStopping(true)
    try {
      const response = await fetch(`/api/v1/projects/${projectId}/agent/${agent.name}/stop`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${apiKey}` },
      })
      if (!response.ok) {
        throw new Error(`Stop failed with status ${response.status}`)
      }
      // Left true: the status chip flips away from "running" once the process actually
      // exits (via the run_stopped SSE event's agents-query invalidation), and the effect
      // above clears isStopping at that point. Clearing it here instead would let the
      // button be clicked again mid-shutdown.
    } catch (err) {
      console.error('Failed to stop run:', err)
      setIsStopping(false)
    }
  }

  const handleDeliverNow = async () => {
    // Any operator-origin entry is depth 0, so it unblocks a hop-budget-suspended
    // chain and drains it in the same turn (design.md: "operator input resets
    // the chain") — this reuses that existing behavior rather than adding a
    // dedicated force-deliver endpoint.
    if (!apiKey || !projectId || isRunning || isSending) return
    setIsSending(true)
    try {
      const result = await postTrigger(
        'Continue — deliver the queued messages.',
        currentConversationId,
      )
      if (result.conversation_id !== currentConversationId) moveTo(result.conversation_id)
      const notice = queuedNotice(result, `${agent.name} is still not available to receive it`)
      if (notice) setSessionNotice(`Still queued — ${notice}`)
    } catch (err) {
      console.error('Failed to deliver queued messages:', err)
    } finally {
      setIsSending(false)
    }
  }

  /** Start the queued work without inventing a message to carry it.
   *
   * Shown when a conversation has undelivered queued entries and no run — which is exactly the
   * state a successor is in the moment it is handed its checkpoint. */
  const handleContinue = async () => {
    if (!apiKey || !projectId || !currentConversationId || isRunning || isSending) return
    setIsSending(true)
    try {
      const result = await continueConversation(projectId, currentConversationId)
      setSessionNotice(
        result.started ? 'Continuing…' : `Not started — ${result.waiting_reason ?? 'unknown'}`,
      )
    } catch (err) {
      console.error('Failed to continue:', err)
      setSessionNotice('Could not start the queued work')
    } finally {
      setIsSending(false)
    }
  }

  /** Take a checkpoint and continue in a successor.
   *
   * Two Hub calls, no agent turn. Generation reads the conversation's record, so this works
   * whether or not the agent is cooperative, idle, or has anything left to say — which is the
   * whole point of moving it Hub-side. The successor is handed the checkpoint as a queued
   * entry, so the operator's next message needs no prefix and carries no instructions.
   */
  const handleCheckpoint = async () => {
    if (!apiKey || !projectId || !currentConversationId || isRunning || isSending) return
    setIsSending(true)
    setHandoffState('preparing')
    setSessionNotice('Writing checkpoint…')
    try {
      const checkpoint = await takeCheckpoint(projectId, currentConversationId)
      if (checkpoint.status !== 'ready') {
        // "unwritten" means the envelope is there but generation produced no usable body, and
        // "failed" means its claims disagreed with the database. Neither is something to hand a
        // successor, and saying so beats a green tick over an empty record.
        setHandoffState('idle')
        setSessionNotice(
          checkpoint.status === 'failed'
            ? 'Checkpoint failed its own checks — nothing was cut over'
            : 'Checkpoint has no written summary — nothing was cut over',
        )
        return
      }
      const result = await cutOver(projectId, checkpoint.id)
      setHandoffState('idle')
      moveTo(result.successor_conversation_id)
      setSessionNotice('Checkpoint written — continuing in a new conversation')
    } catch (err) {
      console.error('Failed to checkpoint:', err)
      setHandoffState('idle')
      setSessionNotice(
        err instanceof ApiError && err.status === 409
          ? 'Cannot checkpoint yet — finish or stop the run, and let queued messages deliver'
          : 'Failed to write checkpoint',
      )
    } finally {
      setIsSending(false)
    }
  }

  /** Answer the waiting question, from whichever the operator supplied.
   *
   * Typed text wins over a selection: someone who bothered to write meant it, and the options
   * were only ever an offer. */
  const answerPendingQuestion = async (
    typedMessage: string,
    // Passed explicitly by the single-choice path, which answers in the same click that makes
    // the selection: `setQuestionSelection` has not applied yet at that point, so reading the
    // state here would see the previous (empty) value and send nothing at all.
    chosenLabels?: string[],
  ): Promise<void> => {
    if (!pendingQuestion) return
    const typed = typedMessage.trim()
    const labels = typed ? [] : (chosenLabels ?? questionSelection)
    if (!typed && labels.length === 0) return
    await answerQuestion.mutateAsync({
      id: pendingQuestion.id,
      answer: typed || labels.join(', '),
      labels,
    })
    setQuestionSelection([])
    setComposerDraft('')
  }

  const handleQuestionToggle = (label: string) => {
    if (!pendingQuestion) return
    if (pendingQuestion.multi_select !== true) {
      // Single choice answers outright. The selection is set first so the row paints as chosen
      // in the same frame as the click, rather than after the round-trip.
      setQuestionSelection([label])
      void answerPendingQuestion('', [label])
        .then(() => undefined)
        .catch(() => setQuestionSelection([]))
      return
    }
    setQuestionSelection((current) =>
      current.includes(label) ? current.filter((l) => l !== label) : [...current, label],
    )
  }

  const handleComposerSubmit = async (typedMessage: string): Promise<void> => {
    // A waiting question owns the composer until it is answered — otherwise the operator's
    // reply becomes a new message and the agent keeps waiting for one that never comes.
    if (pendingQuestion) {
      await answerPendingQuestion(typedMessage)
      return
    }
    if (!apiKey || !projectId) throw new Error('Not configured')
    setIsSending(true)
    setSubmissionError(null)
    // A message always goes to the agent whose conversation this is. The composer used to
    // offer a target-agent picker that could redirect a submission elsewhere, leaving no trace
    // in the conversation the operator was looking at (operator: "Let's remove the ability and
    // the buttons that enable the user from one screen to send message to another agent. Is
    // counter intuitive.").
    // No prefix. A successor created by a cutover already has its checkpoint waiting in its
    // queue, so the operator's message is only their message — where it used to be prepended
    // with instructions to go and find two files that were never written.
    const outgoingMessage = typedMessage
    if (startsFresh) setSessionNotice('Starting new conversation…')
    try {
      const result = await postTrigger(
        outgoingMessage,
        currentConversationId,
        agent.name,
        emptyToUndefined(pendingOverrides),
      )
      if (result.conversation_id !== currentConversationId) moveTo(result.conversation_id)
      if (startsFresh) {
        // The fresh conversation exists now, so the panel stops overriding the destination —
        // the reset effect will not do it, having recognised its own move.
        setStartingFresh(false)
        setHandoffState('idle')
      }
      const notice = queuedNotice(result, `${agent.name} is not available to receive it right now`)
      if (notice) {
        setSessionNotice(`Queued — ${notice}`)
      }
    } catch (err) {
      console.error('Failed to send message:', err)
      setSubmissionError('Failed to send message')
      setSessionNotice('Failed to send message')
      throw err
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg)' }}>
      <div
        className="conversation-header-surface flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2.5"
        data-testid="conversation-header"
      >
        {onBackToProject && (
          <Button variant="ghost" size="icon-sm" className="shrink-0" onClick={onBackToProject} aria-label="Back to project" title="Back to project">
            <Icon name="arrow_left" size={16} />
          </Button>
        )}
        {/* The agent's name appears here and nowhere else in this header. It was printed three
            times when the specification workspace wrapped this surface in its own agent selector;
            that selector is gone, and the name truncates rather than pushing the controls past
            the panel's right edge. */}
        <span className="inline-flex min-w-0 items-center gap-1.5 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <span data-testid={`conversation-agent-color-${agent.name}`} className="h-2 w-2 shrink-0 rounded-full" style={{ background: agentColorVars(agent.color_index).accent }} />
          <span className="truncate">{agent.name}</span>
        </span>

        {/* Status chip. Provider session identity is not shown here — see
            "Conversation identity is readable without exposing provider
            identity": normal controls use conversation_id only, and provider
            binding is confined to agent details / diagnostics. */}
        <span
          className="flex shrink-0 items-center gap-1.5"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            borderRadius: 'var(--radius-sm)',
            padding: '2px 8px',
            fontSize: 11,
            fontWeight: 500,
            background: isRunning ? 'color-mix(in srgb, var(--green) 10%, transparent)' : 'var(--surface-3)',
            color: isRunning ? 'var(--green)' : 'var(--text-3)',
          }}
        >
          {isRunning && (
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
          )}
          {agent.status}
        </span>
        <div className="min-w-0 flex-1" />
        {onOpenAgentSettings && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="shrink-0"
            data-testid="conversation-agent-settings"
            onClick={onOpenAgentSettings}
            aria-label={`Settings for ${agent.name}`}
            title={`Settings for ${agent.name}`}
          >
            <Icon name="settings" size={16} />
          </Button>
        )}
        <ConversationControls
          agent={agent}
          isRunning={isRunning}
          isStopping={isStopping}
          onStop={handleStop}
          currentConversationId={currentConversationId}
          handoffState={handoffState}
          handoffUnavailable={handoffUnavailable}
          interactionLocked={interactionLocked}
          onHandoff={handleCheckpoint}
          onFoldAll={() => setFoldAllSignal((s) => s + 1)}
        />
      </div>

      {/* Output body. The return-to-newest control used to float over its lower edge — which put
          an interactive element on top of whatever entry happened to be scrolled under it, and
          landed on the run's completion line often enough to be reported. It is a row of its own
          now: it costs ~28px only while following is suspended, and overlaps nothing. */}
      <div className="flex min-h-0 flex-1 flex-col">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        data-testid="conversation-output"
        className="flex-1 overflow-y-auto py-[22px]"
        style={{ background: 'var(--bg)' }}
      >
        {isLoading || chat.isLoading ? (
          <p className="font-mono text-xs italic px-5" style={{ color: 'var(--text-3)', fontFamily: "'JetBrains Mono', monospace" }}>Loading output…</p>
        ) : (
          <AgentTimeline
            agent={agent}
            entries={timelineEntries}
            roster={roster}
            timelineEvents={timelineEvents}
            queueStatus={queueStatus}
            isRunning={isRunning}
            onDeliverNow={handleDeliverNow}
            onWithdraw={handleWithdraw}
            foldAllSignal={foldAllSignal}
          />
        )}
        <div ref={bottomRef} />
      </div>

        {/* Not a pause/resume toggle — the spec removed that, because scroll position already
            expresses whether to follow. This states a different intent ("take me back"), and so
            appears only while following is suspended. */}
        {!autoscroll && (
          <div className="flex shrink-0 justify-center pb-2">
            <button
              onClick={() => {
                scrollToNewest()
                setAutoscroll(true)
              }}
              aria-label="Jump to newest"
              title="Jump to newest"
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] font-medium"
              style={{
                background: 'var(--surface-3)',
                border: '1px solid var(--border-hi)',
                color: 'var(--text)',
                boxShadow: '0 2px 10px rgba(0,0,0,0.28)',
              }}
            >
              <Icon name="expand_more" size={13} />
              Jump to newest
            </button>
          </div>
        )}
      </div>

      <div className="conversation-composer-fade shrink-0">
        <div className="mx-auto flex w-full max-w-[820px] flex-col gap-2">
          <BannerStack banners={banners} />

          {/* A successor is handed its checkpoint as a queued entry and then waits. Without this
              the only way to start it was to type a message, which is a strange thing to invent
              when the work is already described. Shown only when there is queued work and no run
              — otherwise the composer is the right control. */}
          {hasQueuedWork && !isRunning && (
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                size="xs"
                data-testid="conversation-continue"
                disabled={isSending}
                onClick={handleContinue}
              >
                <Icon name="play_arrow" size={12} />
                Continue
              </Button>
              <span className="text-[11px]" style={{ color: 'var(--text-3)' }}>
                {agent.name} has work waiting — start it without sending a message.
              </span>
            </div>
          )}

          <span
          data-testid="session-continuity"
          className="flex items-center gap-1"
          style={{
            fontSize: 11,
            color: startsFresh ? 'var(--blue)' : 'var(--text-3)',
          }}
        >
          <Icon
            name={
              handoffState === 'preparing' ? 'hourglass_top' : startsFresh ? 'move_up' : 'link'
            }
            size={12}
          />
          {/* A conversation is named by its title here as it is everywhere else — the identifier
              this used to print is not a label (spec: "Conversations are labelled by title"). */}
          {sessionNotice
            || (startsFresh
              ? 'Next message starts a fresh conversation'
              : currentConversation
                ? `Continuing ${continuityLabel(currentConversation)}`
                : 'Continuing this conversation')}
          </span>

          {/* Above the composer, not in the timeline: the agent is blocked right now and the
              operator is answering under its timeout, so this must be where they already are
              rather than somewhere they have to scroll to. */}
          <PermissionRequestCard requests={permissionRequests} agent={agent.name} />
          {/* Nothing is blocked on this one — the turn has already ended — but it belongs in the
              same place for the same reason: it is the operator's move, and the timeline is
              where things go to be scrolled past. */}
          <UnaskedQuestionCard questions={unaskedQuestions} agent={agent.name} />
          <AgentQuestionCard
            questions={openQuestions}
            agent={agent.name}
            selected={questionSelection}
            onToggle={handleQuestionToggle}
            isResponding={answerQuestion.isPending}
            isTyping={composerDraft.trim().length > 0}
          />

          <div className="conversation-composer-surface">
            <Composer
              key={`${agent.name}::${currentConversationId ?? NEW_CONVERSATION_ID}`}
              agent={agent.name}
              projectId={projectId ?? ''}
              conversationId={currentConversationId ?? null}
              isRunning={isRunning}
              onSubmit={handleComposerSubmit}
              canSubmitEmpty={!!pendingQuestion && questionSelection.length > 0}
              onTextChange={setComposerDraft}
              placeholder={
                pendingQuestion ? `Answer ${agent.name}…` : undefined
              }
              workspacePaths={workspacePaths}
              runner={targetRunnerRow?.cli ?? null}
              effectiveModel={targetRunnerRow?.model ?? null}
              // At rest the Permissions pill has to show what the run will actually do. The Hub
              // applies the agent's default when the conversation states none, so without this
              // the pill would sit at the catalog default while the run went elsewhere — the
              // pill appearing to say one thing and the run doing another.
              effectiveControls={agentDefaultControls}
              pendingOverrides={pendingOverrides}
              onPendingOverridesChange={setPendingOverrides}
              onOpenSpecPicker={onOpenSpecPicker}
              specDocumentLabel={specDocumentLabel}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
