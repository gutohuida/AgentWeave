import * as React from 'react'
import { useAgents } from '@/api/agents'
import { useProjectConversations } from '@/api/agentChat'
import { useCharters } from '@/api/charters'
import { useProjectLedger } from '@/api/ledger'
import { useModelCatalog } from '@/api/modelCatalog'
import { useQueueStatuses } from '@/api/queue'
import { useSpecDocuments } from '@/api/spec'
import { useTask, useTasks } from '@/api/tasks'
import { AgentSettingsPage } from '@/components/agents/AgentSettingsPage'
import { SetupProfilesDialog } from '@/components/overview/SetupProfilesDialog'
import {
  AGENT_SETTINGS_SECTIONS,
  AGENT_SETTINGS_SECTION_LABELS,
  profileHref,
  resolveAgentSettingsSection,
  type AgentSettingsSection,
} from '@/lib/navigation'
import { ProfilesPage } from './ProfilesPage'
import type { ProfileNow } from './profilesModel'
import { currentRun, profileItem } from './rosterItems'

const SECTIONS = AGENT_SETTINGS_SECTIONS.map((id) => ({ value: id, label: AGENT_SETTINGS_SECTION_LABELS[id] }))

/**
 * The Profiles tab (FR-12, FR-13): the index of every profile, and one profile's page with its
 * settings sections as one row of tabs. `selected` is the profile the address names; null is the
 * index. Mounted once for both, so the index can hand focus back to the row of the profile the
 * operator just left.
 */
export function ProfilesScreen({
  projectId,
  selected,
  section,
  setting,
  onOpenIndex,
  onOpenProfile,
  onOpenTask,
  onOpenBuild,
  onOpenConversation,
  onNewThread,
  onAddProfile,
}: {
  projectId: string
  selected: string | null
  section: AgentSettingsSection
  setting?: string | null
  onOpenIndex: () => void
  onOpenProfile: (name: string, section?: AgentSettingsSection) => void
  onOpenTask: (taskId: string) => void
  onOpenBuild: (buildId: string) => void
  onOpenConversation: (agent: string, conversationId: string) => void
  onNewThread: (agent: string) => void
  onAddProfile: () => void
}) {
  const roster = useAgents('all')
  const { data: charters = [], error: chartersError } = useCharters()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const { data: ledger, error: ledgerError } = useProjectLedger()
  const { data: taskPage, error: tasksError } = useTasks()
  const { data: documents, error: documentsError } = useSpecDocuments()
  const { data: conversations, error: conversationsError } = useProjectConversations(projectId)
  const [query, setQuery] = React.useState('')
  const [pairOpen, setPairOpen] = React.useState(false)
  const now = React.useMemo(() => new Date(), [roster.dataUpdatedAt]) // eslint-disable-line react-hooks/exhaustive-deps

  const agents = React.useMemo(() => roster.data ?? [], [roster.data])
  const openNames = React.useMemo(() => agents.filter((a) => a.lifecycle !== 'archived').map((a) => a.name), [agents])
  const queueStatuses = useQueueStatuses(openNames)
  const heldReasonOf = (name: string) => queueStatuses.find((q) => q.agent === name)?.waiting_reason ?? null
  const picked = agents.find((a) => a.name === selected) ?? null
  // The task the open profile is on, read on its own: the board's page may not hold it.
  const pickedRun = picked ? currentRun(picked) : null
  const { data: pickedTask, error: pickedTaskError } = useTask(pickedRun?.task_id ?? null)

  const tasks = taskPage?.tasks ?? []
  const taskOf = (id: string) => (pickedTask?.id === id ? pickedTask : tasks.find((t) => t.id === id))
  const spendOf = (name: string): number | null | undefined => {
    if (!ledger) return ledgerError ? null : undefined
    const row = ledger.spend.by_agent.find((a) => a.agent === name)
    return row ? row.usd : undefined
  }
  const items = agents.map((agent) =>
    profileItem(agent, {
      catalog,
      charterName: charters.find((c) => c.id === agent.charter_id)?.name ?? null,
      spend: spendOf(agent.name),
      taskOf,
      heldReason: heldReasonOf(agent.name),
    }),
  )
  const latestThread = (name: string) =>
    (conversations?.conversations ?? [])
      .filter((c) => c.agent === name)
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0]?.id ?? null

  const nowFor = (name: string): ProfileNow => {
    const agent = agents.find((a) => a.name === name)
    if (!agent) return { kind: 'never' }
    const item = items.find((i) => i.name === name)
    const run = currentRun(agent)
    if (item && (item.status.kind === 'working' || item.status.kind === 'reviewing')) {
      const task = run?.task_id ? taskOf(run.task_id) : undefined
      const build = task?.build_id
        ? (documents?.documents.find((d) => d.id === task.spec_document_id)?.title ?? 'its build')
        : null
      return {
        kind: item.status.kind,
        task: task?.title ?? (run?.task_id ? 'a task' : 'a thread'),
        build,
        since: run?.started_at ?? agent.last_seen ?? now.toISOString(),
        reviewing: item.status.kind === 'reviewing' ? (task?.builder ?? task?.assignee ?? null) : null,
      }
    }
    if (item?.status.kind === 'held') return { kind: 'held', reason: item.status.detail ?? 'waiting' }
    return agent.last_seen ? { kind: 'last-run', at: agent.last_seen } : { kind: 'never' }
  }

  const runTaskOf = (name: string) => {
    const agent = agents.find((a) => a.name === name)
    const run = agent ? currentRun(agent) : null
    return run?.task_id ? taskOf(run.task_id) ?? null : null
  }

  // A read beside the roster that failed leaves part of what the page says unknown: say which,
  // rather than show a charter as missing or a profile as never having had a thread.
  const unread = [
    chartersError ? 'charters' : null,
    catalogError ? 'model names' : null,
    tasksError || pickedTaskError ? 'tasks' : null,
    documentsError ? 'builds' : null,
    conversationsError ? 'threads' : null,
    ledgerError ? 'spend' : null,
  ].filter((what): what is string => what !== null)

  const state = roster.isLoading ? 'loading' : roster.error ? 'error' : 'ready'
  const open = state === 'ready' && picked ? picked.name : null
  const active = resolveAgentSettingsSection(section) ?? 'agent'
  const poolSize = picked?.pool?.length

  return (
    <>
      {state === 'ready' && unread.length > 0 ? (
        <p className="aw-pf-partial" role="status" data-testid="profiles-partial">
          Could not load the {unread.join(', ')}, so some of what this page says may be incomplete.
        </p>
      ) : null}
      <ProfilesPage
        items={items}
        selected={open}
        query={query}
        onQueryChange={setQuery}
        onOpen={(name) => onOpenProfile(name)}
        onClose={onOpenIndex}
        onAdd={onAddProfile}
        onAddPair={() => setPairOpen(true)}
        state={state}
        onRetry={() => void roster.refetch()}
        now={now}
        nowFor={nowFor}
        hasThread={(name) => latestThread(name) !== null}
        profileHref={(name) => profileHref(projectId, name)}
        onNewThread={onNewThread}
        onOpenLatestThread={(name) => {
          const id = latestThread(name)
          if (id) onOpenConversation(name, id)
        }}
        onOpenTask={(name) => {
          const task = runTaskOf(name)
          if (task) onOpenTask(task.id)
        }}
        onOpenBuild={(name) => {
          const task = runTaskOf(name)
          if (task?.build_id) onOpenBuild(task.build_id)
        }}
        sections={SECTIONS.map((s) => (s.value === 'running' && poolSize ? { ...s, count: poolSize } : s))}
        section={active}
        onSection={(id) => open && onOpenProfile(open, id as AgentSettingsSection)}
      >
        {open ? <AgentSettingsPage key={open} agent={open} section={active} setting={setting} /> : null}
      </ProfilesPage>
      <SetupProfilesDialog projectId={projectId} open={pairOpen} onOpenChange={setPairOpen} />
    </>
  )
}
