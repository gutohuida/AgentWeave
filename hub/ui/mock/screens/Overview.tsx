import * as React from 'react'
import type { ProjectLedger } from '@/api/ledger'
import { OverviewView, type AgentStripItem, type FinishedItem, type NeedItem, type RunningItem } from '@/components/overview/OverviewView'
import { toast } from '@/lib/toast'
import { formatAgoLong } from '@/lib/format'
import ledgerJson from '../fixtures/ledger.json'
import { agentAttention, agents, conversations, tasks } from '../fixtures'
import type { ScreenProps } from '../routes'

const ledger = ledgerJson as unknown as ProjectLedger

/** `latest_integration` rides on the task payload but is not on the `Task` type yet. */
interface LatestIntegration {
  outcome: string
  reason: string
  target_branch: string | null
  created_at: string
}

const colorOf = (name: string) => agents.find((a) => a.name === name)?.color_index

export default function Overview({ go, now }: ScreenProps) {
  const [answered, setAnswered] = React.useState<string[]>([])
  const minutesAgo = (m: number) => new Date(now.getTime() - m * 60_000).toISOString()

  const unmerged = tasks.find((t) => {
    const li = (t as unknown as { latest_integration?: LatestIntegration }).latest_integration
    return li && li.outcome !== 'merged' && /uncommitted/.test(li.reason)
  })
  const unmergedIntegration = (unmerged as unknown as { latest_integration?: LatestIntegration } | undefined)?.latest_integration

  const allNeeds: NeedItem[] = [
    // mock state: QA1 waiting on an ask_user question (the replica has none open).
    {
      id: 'q-mock',
      kind: 'question',
      agent: 'QA1',
      colorIndex: colorOf('QA1'),
      title: 'Allow a 30-second cache on search results?',
      detail:
        'Search now answers from a short-lived cache, so a busy page stays fast. The cost: a new item can take up to 30 seconds to appear in results.',
      at: minutesAgo(6),
      options: [
        { label: 'Allow the cache', description: 'Faster pages; results lag by up to 30 seconds.' },
        { label: 'Keep results live', description: 'Always current; slower under load.' },
      ],
      primary: { label: 'Open conversation', onClick: () => go({ kind: 'conversation', agent: 'QA1', conversationId: 'conv-e92920dba933' }) },
    },
    ...(unmerged && unmergedIntegration
      ? [
          {
            id: `merge-${unmerged.id}`,
            kind: 'merge' as const,
            agent: null,
            title: `“${unmerged.title}” was approved but not merged`,
            detail: 'The project folder has uncommitted changes to tracked files. Commit or stash them, then try the merge again.',
            at: unmergedIntegration.created_at,
            primary: { label: 'Try again', onClick: () => toast({ title: 'Merging into master…', description: 'You will see the result here and on the task.' }) },
            secondary: { label: 'Open task', onClick: () => go({ kind: 'tab', tab: 'tasks' }) },
          },
        ]
      : []),
  ]
  const needs = allNeeds.filter((n) => !answered.includes(n.id))

  const builderConversation = conversations.find((c) => c.id === 'conv-e3aba2c5956a')
  const running: RunningItem[] = [
    // mock state: Builder marked as working (see fixtures.ts).
    {
      id: 'run-mock',
      agent: 'Builder',
      colorIndex: colorOf('Builder'),
      conversationTitle: builderConversation?.title ?? 'Conversation',
      taskTitle: tasks.find((t) => t.id === 'task-5fa7e0e0bf66')?.title ?? null,
      startedAt: minutesAgo(4.2),
      tokens: builderConversation?.context_usage?.context_tokens ?? null,
      onOpen: () => go({ kind: 'conversation', agent: 'Builder', conversationId: 'conv-e3aba2c5956a' }),
    },
  ]

  const usdByTask = new Map(ledger.spend.by_task.map((t) => [t.task_id, t.usd]))
  const finished: FinishedItem[] = ledger.merges
    .filter((m) => m.outcome === 'merged' && m.at)
    .slice(0, 5)
    .map((m) => ({
      id: m.id,
      kind: 'merged' as const,
      title: m.task_title ?? m.task_id,
      detail: `Merged into ${m.target_branch ?? 'main'} · approved by ${m.actor_kind === 'operator' ? 'you' : m.actor}`,
      at: m.at!,
      usd: usdByTask.get(m.task_id) ?? null,
      onOpen: () => go({ kind: 'tab', tab: 'tasks' }),
    }))

  const usdByAgent = new Map(ledger.spend.by_agent.map((a) => [a.agent, a.usd]))
  const strip: AgentStripItem[] = agents.map((a) => {
    const state = agentAttention(a.name)
    const latest = conversations.filter((c) => c.agent === a.name).sort((x, y) => y.updated_at.localeCompare(x.updated_at))[0]
    return {
      name: a.name,
      colorIndex: a.color_index,
      state,
      doing:
        state === 'running'
          ? `Working on “${latest?.title ?? 'a conversation'}”`
          : state === 'waiting'
            ? 'Waiting for your answer'
            : `Last active ${a.last_seen ? formatAgoLong(a.last_seen, now) : 'never'}`,
      usd: usdByAgent.get(a.name) ?? 0,
      onOpen: () => (latest ? go({ kind: 'conversation', agent: a.name, conversationId: latest.id }) : go({ kind: 'conversation', agent: a.name, conversationId: null })),
    }
  })

  return (
    <OverviewView
      needs={needs}
      running={running}
      finished={finished}
      agents={strip}
      spend={{ usd: ledger.spend.total_usd, tokens: ledger.spend.total_tokens, period: 'this week' }}
      onOpenLedger={() => go({ kind: 'tab', tab: 'activity' })}
      onAnswer={(need, option) => {
        setAnswered((a) => [...a, need.id])
        toast({ title: `Answered ${need.agent}: “${option.label}”`, tone: 'success', action: { label: 'Undo', onClick: () => setAnswered((a) => a.filter((x) => x !== need.id)) } })
      }}
      now={now}
    />
  )
}
