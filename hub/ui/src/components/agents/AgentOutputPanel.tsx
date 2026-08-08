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
  type AgentConversation,
} from '@/api/agentChat'
import { NEW_CONVERSATION_ID } from '@/lib/navigation'
import { useQueueStatus, withdrawQueueEntry } from '@/api/queue'
import { useRunners } from '@/api/runners'
import { useWorkspacePaths } from '@/api/workspace'
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
  /** The conversation this panel renders, resolved by the destination. `null` means there is
   *  nothing to render yet — either the agent has no conversations, or the destination is
   *  deliberately the new-conversation surface, which `isNewConversation` tells apart. */
  conversationId?: string | null
  /** True when the operator asked for a new conversation. Kept separate from a null
   *  `conversationId` so the empty composer survives the conversation list arriving. */
  isNewConversation?: boolean
  /** Move the destination. The panel calls this for the moves it causes itself — the trigger
   *  returning a real conversation id for a first message, or the handoff handing over to a
   *  fresh one. It never holds the answer; the destination does. */
  onSelectConversation?: (conversationId: string | null) => void
}

const HANDOFF_PROMPT = `Prepare a durable AgentWeave handoff before ending this session.

Invoke your aw-checkpoint skill with reason pre_handoff. Save the current intent, files modified,
decisions and rationale, blockers, exact next steps, and verification commands under
.agentweave/shared/checkpoints/. Stop after confirming the checkpoint path.`

const RESUME_HANDOFF_PREFIX = `Resume from the latest durable AgentWeave handoff.

Before doing anything else, find and read the newest checkpoint for your agent under
.agentweave/shared/checkpoints/, then read .agentweave/shared/context.md. Treat the checkpoint
as authoritative and continue from its Next Steps.

User request:`

interface TriggerResult {
  status: string
  waiting_reason?: string | null
  conversation_id: string
  provider_session_id?: string | null
}

function emptyToUndefined(overrides: Record<string, string>): Record<string, string> | undefined {
  return Object.keys(overrides).length > 0 ? overrides : undefined
}

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
  conversationId = null,
  isNewConversation = false,
  onSelectConversation,
}: AgentOutputPanelProps) {
  const { lines, isLoading } = useAgentOutput(agent.name)
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
  const [sessionNotice, setSessionNotice] = useState<string | null>(null)
  const [submissionError, setSubmissionError] = useState<string | null>(null)
  const [isStopping, setIsStopping] = useState(false)
  const [pendingOverrides, setPendingOverrides] = useState<Record<string, string>>({})
  const handoffOutputStartRef = useRef<number | null>(null)
  const handoffSawRunningRef = useRef(false)
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
    const arrivedWhereItSentItself =
      sentTo !== undefined &&
      (sentTo === NEW_CONVERSATION_ID ? isNewConversation : sentTo === conversationId)
    if (arrivedWhereItSentItself) return
    setHandoffState('idle')
    setSessionNotice(null)
    setSubmissionError(null)
    setIsStopping(false)
    handoffOutputStartRef.current = null
    handoffSawRunningRef.current = false
  }, [agent.name, conversationId, isNewConversation])

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

  useEffect(() => {
    const outputStart = handoffOutputStartRef.current
    if (handoffState !== 'preparing' || outputStart === null) return
    if (agent.status === 'running') {
      handoffSawRunningRef.current = true
      return
    }

    const completed = lines.slice(outputStart).some(
      (line) => line.kind === 'status' && line.payload?.phase === 'completed',
    )
    if (completed || handoffSawRunningRef.current) {
      handoffOutputStartRef.current = null
      handoffSawRunningRef.current = false
      setHandoffState('ready')
      setSessionNotice('Handoff ready — your next message starts fresh and resumes it')
    }
  }, [agent.status, handoffState, lines.length])

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
  const currentConversationId = conversationId ?? undefined
  // Sending with nothing open starts a conversation whether or not the operator asked for one
  // explicitly — a brand-new agent has none to continue.
  const startsFresh = !currentConversationId
  const currentConversation = conversations.find((c) => c.id === currentConversationId)

  const { data: roster = [] } = useAgents()
  const { data: runners = [] } = useRunners()
  const targetAgentRow = roster.find((a) => a.name === agent.name)
  const targetRunnerRow = runners.find((r) => r.id === targetAgentRow?.runner_id)
  const { data: timelineEvents = [] } = useAgentTimeline(agent.name)
  const { data: queueStatus } = useQueueStatus(agent.name)
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
  const banners: ConversationBanner[] = [
    submissionError ? { id: 'run-failure', message: submissionError } : null,
    sseConnectionState === 'reconnecting'
      ? { id: 'stream-loss', message: 'Live updates are disconnected — reconnecting…' }
      : null,
    timelineEntries.some((entry) => entry.hop_budget_exceeded)
      ? { id: 'blocked-queue', message: 'Queued messages are blocked by the hop limit — deliver now to continue.' }
      : null,
  ].filter((banner): banner is ConversationBanner => banner !== null)

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

  const handleHandoff = async () => {
    if (!apiKey || !projectId || !currentConversationId || isRunning || isSending) return
    setIsSending(true)
    setHandoffState('preparing')
    setSessionNotice('Preparing durable handoff…')
    handoffOutputStartRef.current = lines.length
    handoffSawRunningRef.current = false
    try {
      const result = await postTrigger(HANDOFF_PROMPT, currentConversationId)
      const notice = queuedNotice(result, `${agent.name} is not available to receive it`)
      if (notice) {
        handoffOutputStartRef.current = null
        handoffSawRunningRef.current = false
        setHandoffState('idle')
        setSessionNotice(`Could not start handoff — ${notice}`)
        return
      }
      // Self-directed: the handover to a fresh conversation is the handoff continuing, so the
      // reset effect must leave `handoffState` alone or the next message never resumes it.
      moveTo(NEW_CONVERSATION_ID)
    } catch (err) {
      console.error('Failed to prepare handoff:', err)
      handoffOutputStartRef.current = null
      handoffSawRunningRef.current = false
      setHandoffState('idle')
      setSessionNotice('Failed to prepare handoff')
    } finally {
      setIsSending(false)
    }
  }

  /** The operator switching conversations from a control on this surface. Not self-directed:
   *  the reset effect should treat it as leaving the current conversation. */
  const selectConversation = (id: string) => {
    onSelectConversation?.(id)
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
    const outgoingMessage =
      startsFresh && handoffState === 'ready'
        ? `${RESUME_HANDOFF_PREFIX}\n\n${typedMessage}`
        : typedMessage
    if (startsFresh) setSessionNotice('Starting new conversation…')
    try {
      const result = await postTrigger(
        outgoingMessage,
        currentConversationId,
        agent.name,
        emptyToUndefined(pendingOverrides),
      )
      if (result.conversation_id !== currentConversationId) moveTo(result.conversation_id)
      if (startsFresh) setHandoffState('idle')
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
        className="conversation-header-surface flex shrink-0 items-center gap-2 px-4 py-2.5"
        data-testid="conversation-header"
      >
        {onBackToProject && (
          <Button variant="ghost" size="icon-sm" onClick={onBackToProject} aria-label="Back to project" title="Back to project">
            <Icon name="arrow_left" size={16} />
          </Button>
        )}
        <span className="inline-flex items-center gap-1.5 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <span data-testid={`conversation-agent-color-${agent.name}`} className="h-2 w-2 rounded-full" style={{ background: agentColorVars(agent.color_index).accent }} />
          {agent.name}
        </span>

        {/* Status chip. Provider session identity is not shown here — see
            "Conversation identity is readable without exposing provider
            identity": normal controls use conversation_id only, and provider
            binding is confined to agent details / diagnostics. */}
        <span
          className="flex items-center gap-1.5"
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
        <div className="flex-1" />
        <ConversationControls
          agent={agent}
          isRunning={isRunning}
          isStopping={isStopping}
          onStop={handleStop}
          conversations={conversations}
          currentConversationId={currentConversationId}
          onSelectConversation={selectConversation}
          onNewConversation={() => selectConversation(NEW_CONVERSATION_ID)}
          handoffState={handoffState}
          handoffUnavailable={handoffUnavailable}
          interactionLocked={interactionLocked}
          onHandoff={handleHandoff}
          onFoldAll={() => setFoldAllSignal((s) => s + 1)}
        />
      </div>

      {/* Output body. Positioned so the return-to-newest control can float over its lower edge
          without taking layout space or shifting the conversation when it appears. */}
      <div className="relative flex min-h-0 flex-1 flex-col">
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
          <button
            onClick={() => {
              scrollToNewest()
              setAutoscroll(true)
            }}
            aria-label="Jump to newest"
            title="Jump to newest"
            className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] font-medium"
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
        )}
      </div>

      <div className="conversation-composer-fade shrink-0">
        <div className="mx-auto flex w-full max-w-[820px] flex-col gap-2">
          <BannerStack banners={banners} />

          <span
          data-testid="session-continuity"
          className="flex items-center gap-1"
          style={{
            fontSize: 11,
            color: handoffState === 'ready' || startsFresh ? 'var(--blue)' : 'var(--text-3)',
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
              pendingOverrides={pendingOverrides}
              onPendingOverridesChange={setPendingOverrides}
              conversations={conversations}
              onSelectConversation={selectConversation}
              onNewConversation={() => selectConversation(NEW_CONVERSATION_ID)}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
