import * as React from 'react'
import { useAccounting } from '@/api/accounting'
import { conversationLabel, useProjectConversations } from '@/api/agentChat'
import { useAgents } from '@/api/agents'
import { useProjectLedger } from '@/api/ledger'
import { useAnswerQuestion, useQuestions } from '@/api/questions'
import { useTasks, type Task } from '@/api/tasks'
import { BudgetExhaustionNotice } from '@/components/accounting/BudgetExhaustionNotice'
import { QueryErrorNotice, type QueryFailure } from '@/components/common/QueryErrorNotice'
import { getStatusConfig } from '@/lib/agentStatusConfig'
import { formatAgoLong } from '@/lib/format'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import { AgentPostureChips } from './AgentPostureChips'
import { OverviewView, type AgentStripItem, type FinishedItem, type NeedItem, type RunningItem } from './OverviewView'

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
  const { data: taskPage, error: tasksError } = useTasks()
  const { data: conversationPage, error: conversationsError } = useProjectConversations(projectId || null)
  const { data: ledger, error: ledgerError } = useProjectLedger()
  const { data: accounting, error: accountingError } = useAccounting()
  const failures: QueryFailure[] = [
    ['the agents', agentsError],
    ['the questions', questionsError],
    ['the tasks', tasksError],
    ['the conversations', conversationsError],
    ['the ledger', ledgerError],
    ['the budget', accountingError],
  ]
  const answer = useAnswerQuestion()
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
    ...questions
      .filter((q) => !q.answered && !q.declined)
      .map<NeedItem>((q) => ({
        id: `question-${q.id}`,
        kind: 'question',
        agent: q.from_agent || null,
        colorIndex: colorOf(q.from_agent),
        title: q.question,
        detail: q.asker_waiting === false ? 'The turn that asked has ended; nobody is waiting on this answer any more.' : (q.header ?? null),
        at: q.created_at,
        // A multi-select or open-ended question is answered where it can be composed in full.
        options: q.multi_select ? undefined : q.options,
        primary: q.from_agent
          ? { label: 'Open conversation', onClick: () => onNavigate(`agent:${q.from_agent}`) }
          : { label: 'Answer', onClick: () => onNavigate('questions') },
      })),
    ...tasks
      .filter((t) => t.status === 'approved' && t.latest_integration && t.latest_integration.outcome !== 'merged')
      .map<NeedItem>((t) => ({
        id: `merge-${t.id}`,
        kind: 'merge',
        agent: null,
        title: `“${t.title}” was approved but not merged`,
        detail: t.latest_integration!.reason ? sentence(t.latest_integration!.reason) : null,
        at: t.latest_integration!.created_at,
        primary: { label: 'Open task', onClick: () => openTask(t.id) },
      })),
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

  const usdByAgent = new Map((ledger?.spend.by_agent ?? []).map((a) => [a.agent, a.usd]))
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
      usd: usdByAgent.get(a.name) ?? 0,
      extra: <AgentPostureChips agent={a} onNavigate={onNavigate} />,
      onOpen: () => onNavigate(`agent:${a.name}`),
    }
  })

  return (
    <OverviewView
      loading={agentsLoading}
      needs={needs}
      running={running}
      finished={finished}
      agents={strip}
      spend={{ usd: ledger?.spend.total_usd ?? 0, tokens: ledger?.spend.total_tokens ?? 0, period: 'so far' }}
      taskTotal={taskPage?.total}
      onOpenTasks={() => onNavigate('tasks')}
      onOpenLedger={() => onNavigate('activity')}
      onOpenQuestions={() => onNavigate('questions')}
      onAddAgent={onAddAgent}
      notice={
        failures.some(([, error]) => error) || accounting?.budget.exhausted ? (
          <>
            {/* A failed query would otherwise read as fact here: no questions, nobody working, $0. */}
            <QueryErrorNotice failures={failures} />
            {accounting?.budget.exhausted ? <BudgetExhaustionNotice exhausted /> : null}
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
