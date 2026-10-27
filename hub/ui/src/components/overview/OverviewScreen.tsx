import * as React from 'react'
import { useAccounting } from '@/api/accounting'
import { conversationLabel, useProjectConversations } from '@/api/agentChat'
import { useAgents } from '@/api/agents'
import { useProjectLedger } from '@/api/ledger'
import { useQueueStatuses } from '@/api/queue'
import { useAnswerQuestion, useQuestions } from '@/api/questions'
import { useEndStall, useOpenStalls, type Stall } from '@/api/stalls'
import { useFlakyTests, useHandleFlakyTests } from '@/api/flakyTests'
import { isWaitedOn } from '@/lib/pendingQuestions'
import { useTasks, useUpdateTask, type Task } from '@/api/tasks'
import { accountingDisplayLabel, formatAiCredits } from '@/components/accounting/accountingDisplay'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'
import { QueryErrorNotice, type QueryFailure } from '@/components/common/QueryErrorNotice'
import { getStatusConfig } from '@/lib/agentStatusConfig'
import { formatAgoLong } from '@/lib/format'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import { AgentPostureChips } from './AgentPostureChips'
import { OverviewView, type AgentStripItem, type FinishedItem, type NeedItem, type RunningItem } from './OverviewView'

/** The Hub's own agent for stalled work (`hub/hub/stalls.py`, `MENDER`). */
const MENDER = 'mender'

const STALL_TITLE: Record<Stall['cause'], string> = {
  loop_stalled: 'A loop has nothing it can start',
  delivery_refused: 'An agent’s turn was refused',
  integration_skipped: 'Approved work did not merge',
  integration_failed: 'Approved work failed to merge',
  review_unstaffed: 'Nobody can review a task',
  dead_run: 'A run stopped answering',
  stuck_task: 'A task is stuck in progress',
  no_progress: 'A loop has stopped moving',
}

/** `latest_integration` rides on the task list response but is not on the `Task` type yet. */
type TaskWithIntegration = Task & {
  latest_integration?: { outcome: string; reason: string; target_branch: string | null; created_at: string } | null
}

function sentence(text: string): string {
  const t = text.trim()
  if (!t) return t
  return /[.!?]$/.test(t) ? t : `${t}.`
}

/** The Overview, wired: `OverviewView` fed from the project's hooks. Drop-in for `OverviewPage`
 *  (`onNavigate` takes the same strings App's `navigate` understands). */
export function OverviewScreen({
  onNavigate,
  onOpenConversation,
  onAddAgent,
}: {
  onNavigate: (page: string) => void
  /** Opens the Add-agent dialog for this project (F808). */
  onAddAgent?: () => void
  /** Opens one conversation; without it a row opens its agent's latest conversation. */
  onOpenConversation?: (agent: string, conversationId: string) => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: agents = [], isLoading: agentsLoading, error: agentsError } = useAgents()
  const { data: questions = [], error: questionsError } = useQuestions(false)
  const { data: openStalls = [], error: stallsError } = useOpenStalls()
  const endStall = useEndStall()
  const { data: flakyReport, error: flakyError } = useFlakyTests()
  const handleFlaky = useHandleFlakyTests()
  const flaky = flakyReport?.flaky ?? []
  const { data: taskPage, error: tasksError } = useTasks()
  const { data: conversationPage, error: conversationsError } = useProjectConversations(projectId || null)
  const { data: ledger, error: ledgerError } = useProjectLedger()
  const { data: accounting, error: accountingError } = useAccounting()
  const failures: QueryFailure[] = [
    ['the agents', agentsError],
    ['the questions', questionsError],
    ['the stalls', stallsError],
    ['the flaky tests', flakyError],
    ['the tasks', tasksError],
    ['the conversations', conversationsError],
    ['the ledger', ledgerError],
    ['the budget', accountingError],
  ]
  // Turns the budget is holding: the queue's own reason, per agent, never inferred from the total.
  const queueStatuses = useQueueStatuses(agents.map((a) => a.name))
  const heldByBudget = accounting?.budget.exhausted
    ? queueStatuses.reduce((n, s) => n + (/budget/i.test(s.waiting_reason ?? '') ? s.waiting_count : 0), 0)
    : 0
  const answer = useAnswerQuestion()
  const updateTask = useUpdateTask()
  const now = new Date()

  const tasks = React.useMemo(() => (taskPage?.tasks ?? []) as TaskWithIntegration[], [taskPage])
  const conversations = React.useMemo(() => conversationPage?.conversations ?? [], [conversationPage])
  const openTask = (taskId: string) => {
    useTaskFilterStore.getState().setPendingOpenTaskId(taskId)
    onNavigate('tasks')
  }
  const openConversation = (agent: string, conversationId: string) =>
    onOpenConversation ? onOpenConversation(agent, conversationId) : onNavigate(`agent:${agent}`)
  const colorOf = (name: string) => agents.find((a) => a.name === name)?.color_index

  const needs: NeedItem[] = [
    // A question an agent is blocked on comes first (F904): the route is oldest first, and a
    // non-blocking record would otherwise sit in front of every later ask someone waits on.
    // `sort` is stable, so within each group the route's order stands.
    ...questions
      .filter((q) => !q.answered && !q.declined)
      .sort((a, b) => Number(isWaitedOn(b)) - Number(isWaitedOn(a)))
      .map<NeedItem>((q) => ({
        id: `question-${q.id}`,
        kind: 'question',
        agent: q.from_agent || null,
        colorIndex: colorOf(q.from_agent),
        title: q.question,
        waiting: isWaitedOn(q),
        // Only a blocking question whose asking turn ended has lost its waiter. A non-blocking one
        // is a note — the mender's always are — and nobody ever waited: its answer is delivered as
        // a later message, so saying nobody is waiting would be false.
        detail: q.blocking && q.asker_waiting === false ? 'The turn that asked has ended; nobody is waiting on this answer any more.' : (q.header ?? null),
        at: q.created_at,
        // A multi-select or open-ended question is answered where it can be composed in full.
        options: q.multi_select ? undefined : q.options,
        // The thread it was asked in when the Hub says which: the answer is delivered there.
        primary: q.from_agent
          ? {
              label: 'Open conversation',
              onClick: () => (q.conversation_id ? openConversation(q.from_agent, q.conversation_id) : onNavigate(`agent:${q.from_agent}`)),
            }
          : { label: 'Answer', onClick: () => onNavigate('questions') },
      })),
    // A task whose only mover is the operator (`blocked`, `every-task-can-always-be-moved-on`): it
    // waits on them whether or not a question sits beside it, so it is listed with its reason and
    // the move that releases it.
    ...tasks
      .filter((t) => t.status === 'blocked')
      .map<NeedItem>((t) => ({
        id: `blocked-${t.id}`,
        kind: 'blocked',
        agent: t.assignee || null,
        colorIndex: t.assignee ? colorOf(t.assignee) : null,
        title: `“${t.title}” is waiting on you`,
        detail: t.blocked_reason ? sentence(t.blocked_reason) : null,
        at: t.updated,
        primary: { label: 'Resume work', onClick: () => updateTask.mutate({ id: t.id, status: 'in_progress' }) },
        secondary: { label: 'Open task', onClick: () => openTask(t.id) },
      })),
    ...tasks
      .filter((t) => t.status === 'approved' && t.latest_integration && t.latest_integration.outcome !== 'merged')
      .map<NeedItem>((t) => {
        const mending = openStalls.find((st) => st.task_id === t.id && st.conversation_id)
        return {
          id: `merge-${t.id}`,
          kind: 'merge',
          agent: null,
          title: `“${t.title}” was approved but not merged`,
          detail: t.latest_integration!.reason ? sentence(t.latest_integration!.reason) : null,
          at: t.latest_integration!.created_at,
          primary: { label: 'Open task', onClick: () => openTask(t.id) },
          secondary: mending ? { label: 'The mender is on it', onClick: () => openConversation(MENDER, mending.conversation_id!) } : undefined,
        }
      }),
    // Every other stall (`hub/hub/stalls.py`); a merge stall is the merge row above.
    ...openStalls
      .filter((st) => !(st.cause.startsWith('integration_') && tasks.some((t) => t.id === st.task_id)))
      .map<NeedItem>((st) => ({
        id: `stall-${st.id}`,
        kind: 'stall',
        agent: st.conversation_id ? MENDER : null,
        colorIndex: st.conversation_id ? colorOf(MENDER) : null,
        title: STALL_TITLE[st.cause],
        detail: sentence(st.reason) + (st.conversation_id ? ' The mender is on it.' : ''),
        at: st.last_seen_at,
        primary: st.conversation_id
          ? { label: 'Open the mender’s thread', onClick: () => openConversation(MENDER, st.conversation_id!) }
          : st.task_id
            ? { label: 'Open task', onClick: () => openTask(st.task_id!) }
            : { label: 'Open tasks', onClick: () => onNavigate('tasks') },
        // Ended by hand: what the operator says when they have dealt with it themselves.
        secondary: { label: 'Dismiss', onClick: () => endStall.mutate(st.id) },
      })),
    // Tests the approval checks saw fail and then pass when re-run (`hub/hub/flaky_tests.py`):
    // approval went on, so nothing else asks anyone to fix them. One row for the whole list,
    // handed to a task as a round of fixing.
    ...(flaky.length
      ? [
          {
            id: 'flaky-tests',
            kind: 'flaky' as const,
            agent: null,
            title: `${flaky.length} flaky test${flaky.length === 1 ? '' : 's'} in the approval checks`,
            detail: sentence(
              flaky
                .slice(0, 3)
                .map((f) => `${f.test ?? `the ${f.check} check`} (${f.occurrences}×)`)
                .join(', ') + (flaky.length > 3 ? `, and ${flaky.length - 3} more` : ''),
            ),
            at: flaky[0].last_seen ?? new Date().toISOString(),
            primary: {
              label: 'Create a fix task',
              onClick: () =>
                handleFlaky.mutate(true, {
                  onSuccess: (r) => {
                    toast({ title: 'Made a task to fix the flaky tests', tone: 'success' })
                    if (r.task_id) openTask(r.task_id)
                  },
                }),
            },
            secondary: { label: 'Dismiss', onClick: () => handleFlaky.mutate(false) },
          } satisfies NeedItem,
        ]
      : []),
  ]

  const running: RunningItem[] = conversations
    .filter((c) => c.attention === 'running')
    .map((c) => ({
      id: c.id,
      agent: c.agent,
      colorIndex: colorOf(c.agent),
      conversationTitle: conversationLabel(c),
      taskTitle: c.task_id ? (tasks.find((t) => t.id === c.task_id)?.title ?? null) : null,
      startedAt: c.updated_at,
      tokens: c.context_usage?.context_tokens ?? null,
      onOpen: () => openConversation(c.agent, c.id),
    }))

  const usdByTask = new Map((ledger?.spend.by_task ?? []).map((t) => [t.task_id, t.usd]))
  const finished: FinishedItem[] = (ledger?.merges ?? [])
    .filter((m) => m.outcome === 'merged' && m.at)
    .slice(0, 5)
    .map((m) => ({
      id: m.id,
      kind: 'merged' as const,
      title: m.task_title ?? 'A task',
      detail: `Merged into ${m.target_branch ?? 'the main branch'} · approved by ${m.actor_kind === 'operator' ? 'you' : (m.actor ?? 'an agent')}`,
      at: m.at!,
      usd: usdByTask.get(m.task_id) ?? null,
      onOpen: () => openTask(m.task_id),
    }))

  // The ledger counts a turn with no reported cost as $0; the accounting snapshot knows which
  // were unpriced, so it answers per agent when it has loaded (F952).
  const usdByAgent = new Map<string, number | null>(
    accounting?.agents
      ? accounting.agents.map((a) => [a.agent, a.api_equivalent_usd_micros != null ? a.api_equivalent_usd_micros / 1_000_000 : null])
      : (ledger?.spend.by_agent ?? []).map((a) => [a.agent, a.usd]),
  )
  const strip: AgentStripItem[] = agents.map((a) => {
    const mine = conversations.filter((c) => c.agent === a.name).sort((x, y) => y.updated_at.localeCompare(x.updated_at))
    const live = mine.find((c) => c.attention === 'running')
    const waiting = mine.some((c) => c.attention === 'waiting')
    const state: AgentStripItem['state'] =
      a.status === 'running' || live
        ? 'running'
        : waiting
          ? 'waiting'
          : a.status === 'stalled'
            ? 'stalled'
            : !a.runner_id && (!a.runner || a.runner === 'native')
              ? 'no-runner'
              : 'idle'
    const latest = live ?? mine[0]
    return {
      name: a.name,
      colorIndex: a.color_index,
      state,
      statusLabel: state === 'waiting' ? 'Waiting' : getStatusConfig(a.status).label || a.status,
      doing:
        state === 'running'
          ? `Working on “${latest ? conversationLabel(latest) : 'a conversation'}”`
          : state === 'waiting'
            ? 'Waiting for your answer'
            : state === 'stalled'
              ? 'Stalled: its turn stopped making progress'
              : state === 'no-runner'
                ? 'No runner yet, so it cannot start a turn'
                : `Last active ${a.last_seen ? formatAgoLong(a.last_seen, now) : 'never'}`,
      usd: usdByAgent.get(a.name) ?? (accounting?.agents ? null : 0),
      extra: <AgentPostureChips agent={a} onNavigate={onNavigate} />,
      onOpen: () => onNavigate(`agent:${a.name}`),
    }
  })

  // The same facts the Budgets page states: what the dollar figure leaves out, the credits a
  // Copilot project spends, and the allowance a subscription is measured by (F952).
  const project = accounting?.project
  const unpriced = project?.unpriced_turns ?? 0
  const display = accounting?.preferred_display
  const spend = {
    usd: project ? (project.api_equivalent_usd_micros != null ? project.api_equivalent_usd_micros / 1_000_000 : null) : (ledger?.spend.total_usd ?? 0),
    tokens: ledger?.spend.total_tokens ?? 0,
    period: project && project.api_equivalent_usd_micros != null ? 'API-equivalent so far' : 'so far',
    credits: formatAiCredits(project?.ai_nano_aiu ?? null),
    notes: [
      unpriced > 0 && project?.api_equivalent_usd_micros != null ? `${unpriced} ${unpriced === 1 ? 'turn' : 'turns'} unpriced` : null,
      display?.kind === 'allowance' ? accountingDisplayLabel(display) : null,
    ].filter((note): note is string => !!note),
  }

  return (
    <OverviewView
      loading={agentsLoading}
      needs={needs}
      running={running}
      finished={finished}
      agents={strip}
      spend={spend}
      taskTotal={taskPage?.total}
      heldByBudget={heldByBudget}
      onOpenTasks={() => onNavigate('tasks')}
      onOpenLedger={() => onNavigate('activity')}
      onOpenQuestions={() => onNavigate('questions')}
      onAddAgent={onAddAgent}
      notice={
        failures.some(([, error]) => error) || accounting?.budget.exhausted ? (
          <>
            {/* A failed query would otherwise read as fact here: no questions, nobody working, $0. */}
            <QueryErrorNotice failures={failures} />
            {accounting?.budget.exhausted ? (
              <BudgetExhaustionNotice
                exhausted
                embedded
                limitTokens={accounting.budget.limit_tokens}
                usedTokens={accounting.budget.used_tokens}
                heldCount={heldByBudget}
                onOpenBudgets={() => onNavigate('budgets')}
              />
            ) : null}
          </>
        ) : null
      }
      onAnswer={(need, option) => {
        const id = need.id.replace(/^question-/, '')
        answer.mutate(
          { id, answer: option.label, labels: [option.label] },
          {
            onSuccess: () => toast({ title: `Answered ${need.agent ?? 'the question'}: “${option.label}”`, tone: 'success' }),
            onError: (error: unknown) =>
              toast({ title: 'The answer was not sent', description: error instanceof Error ? error.message : undefined, tone: 'error' }),
          },
        )
      }}
      now={now}
    />
  )
}
