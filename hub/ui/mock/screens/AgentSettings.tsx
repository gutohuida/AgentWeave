import * as React from 'react'
import { SettingsNavLayout } from '@/components/settings/SettingsNavLayout'
import { AgentIdentitySettings, type AgentPatch } from '@/components/agents/settings/AgentSettingsSections'
import {
  AgentCharterGroup,
  AgentCheckpointsSettings,
  AgentPermissionsSettings,
  AgentRunningSettings,
  AgentWorkspaceSettings,
  type ModelChoice,
} from '@/components/agents/settings/AgentSettingsPages'
import { toast } from '@/lib/toast'
import { CheckpointsPanel } from '@/components/checkpoints/CheckpointsPanel'
import { CHECKPOINTS, LABELS, NOTES } from '../checkpointsMock'
import { PoolEditor } from '@/components/agents/pool/PoolEditor'
import { entryLabel } from '@/components/agents/pool/poolModel'
import type { AgentPoolEntry } from '@/api/agentPool'
import { POOL_CATALOG, POOL_RUNNERS, POOLS, poolEntry } from '../poolMock'
import type { AgentSummary } from '@/api/agents'
import type { Charter } from '@/api/charters'
import type { ProjectSettings } from '@/api/projects'
import type { ModelCatalogResponse } from '@/api/modelCatalog'
import { PERMISSION_WAIT_FALLBACK_SECONDS, QUESTION_WAIT_FALLBACK_SECONDS } from '@/lib/agentWaits'
import { agents, project } from '../fixtures'
import type { AgentSettingsSection, ScreenProps } from '../routes'
import settingsJson from '../fixtures/settings.json'
import catalogJson from '../fixtures/model_catalog.json'
import chartersJson from '../fixtures/charters.json'

const projectSettings = settingsJson as unknown as ProjectSettings
const catalog = catalogJson as unknown as ModelCatalogResponse
const charters = chartersJson as unknown as Charter[]
const permissionModes = catalog.providers.find((p) => p.provider === 'claude')?.controls?.find((c) => c.id === 'permission_mode')?.values ?? []

/** Every provider's models, as the Running page's model menu lists them. */
const MODEL_OPTIONS = catalog.providers.flatMap((p) => [
  { value: `${p.provider}:`, label: `${p.label} · its default`, detail: 'Whatever the provider picks' },
  ...(p.models ?? []).map((m) => ({ value: `${p.provider}:${m.id}`, label: `${p.label} · ${m.label}` })),
])

/** Five sections (`settings-in-the-app-s-style-where-you-expect-them`), down from seven:
 *  Identity + Charter → Agent, Execution + Interaction → Running, Execution's permissions +
 *  Access → Permissions, Context → Checkpoints. */
const SECTIONS: Array<{ id: AgentSettingsSection; label: string; icon: string }> = [
  { id: 'agent', label: 'Agent', icon: 'badge' },
  { id: 'running', label: 'Running', icon: 'terminal' },
  { id: 'permissions', label: 'Permissions', icon: 'lock' },
  { id: 'checkpoints', label: 'Checkpoints', icon: 'book_marked' },
  { id: 'workspace', label: 'Workspace', icon: 'folder' },
]

// mock state: the profile's checkpoints are the Checkpoints mock's, those its threads wrote.
const profileCheckpoints = (name: string) => CHECKPOINTS.filter((c) => c.agent === name)

/** The profile's own checkpoints on its Checkpoints section, one openable in place (leaner-navigation). */
function ProfileCheckpoints({ agent, now }: { agent: string; now: Date }) {
  const [opened, setOpened] = React.useState<string | null>(() => new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('open'))
  return (
    <CheckpointsPanel
      checkpoints={profileCheckpoints(agent)}
      openedId={opened}
      onOpen={setOpened}
      conversationLabel={(id) => LABELS.get(id) ?? 'An earlier thread'}
      notes={NOTES.filter((n) => n.consumed_by_checkpoint_id === opened)}
      onOpenConversation={() => toast({ title: 'Opens that thread' })}
      emptyText={` has not taken a checkpoint yet.`}
      now={now}
    />
  )
}

/** The container an agent's settings route would be: the agent from the roster, a patch applied
 *  (here locally, in the app through the agent mutation) and confirmed in a toast. */
export default function AgentSettings({ route, go, now }: ScreenProps) {
  const name = route.kind === 'agent-settings' ? route.agent : 'Builder'
  const section: AgentSettingsSection = route.kind === 'agent-settings' && SECTIONS.some((s) => s.id === route.section) ? route.section : 'running'
  return <AgentSettingsBody name={name} section={section} onSelectSection={(id) => go({ kind: 'agent-settings', agent: name, section: id })} go={go} now={now} />
}

/** The same sections inside a profile's page (`embedded`): just the open section, with no section
 *  list, back link or search (the page's own tabs choose the section). Key it by profile so each keeps its own edits. `summary` and `initialPool`
 *  give the profile; the Agent screen falls back to the recorded agent and Developer's pool. */
export function AgentSettingsBody({
  name,
  section,
  onSelectSection,
  go,
  now,
  embedded = false,
  summary,
  initialPool,
  onPoolCount,
}: {
  name: string
  section: AgentSettingsSection
  onSelectSection: (id: AgentSettingsSection) => void
  go: ScreenProps['go']
  now: Date
  embedded?: boolean
  summary?: AgentSummary
  initialPool?: AgentPoolEntry[]
  /** Told the pool's size whenever it changes, for the page's Models tab. */
  onPoolCount?: (count: number) => void
}) {
  const initial = summary ?? agents.find((a) => a.name === name) ?? agents[0]!
  const [agent, setAgent] = React.useState<AgentSummary>(initial)
  React.useEffect(() => setAgent(initial), [initial])
  // mock state: the recorded roster carries no runner; Builder runs on Sonnet here.
  const [model, setModel] = React.useState<ModelChoice | null>({ provider: 'claude', model: 'claude-sonnet-5-5' })

  // mock state: the pool (spec a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool).
  // `?pool=empty|one|refused` presets the states the data lacks; Builder holds Developer's five.
  const poolState = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('pool')
  const [pool, setPool] = React.useState<AgentPoolEntry[]>(() =>
    initialPool ?? (poolState === 'empty' ? [] : poolState === 'one' ? [POOLS.Developer![0]!] : POOLS.Developer!),
  )
  const [poolError, setPoolError] = React.useState<string | null>(
    poolState === 'refused' ? 'Refused: Opus 5.5 is not offered max effort by this runner’s Claude Code version. Nothing was changed.' : null,
  )
  const label = (e: AgentPoolEntry) => entryLabel(POOL_CATALOG, e)
  React.useEffect(() => onPoolCount?.(pool.length), [pool.length, onPoolCount])

  const say = (said: string) => toast({ title: said, tone: 'success' })
  const apply = (patch: Partial<AgentSummary> | AgentPatch, said: string) => {
    setAgent((a) => ({ ...a, ...patch }))
    say(said)
  }

  let body: React.ReactNode
  switch (section) {
    case 'agent':
      body = (
        <AgentIdentitySettings
          title={embedded ? 'Profile' : 'Agent'}
          agent={agent}
          now={now}
          onChange={apply}
          onArchive={() => say(`${agent.name} archived`)}
          onUnarchive={() => say(`${agent.name} is back`)}
        >
          <AgentCharterGroup
            agent={agent}
            charters={charters.map((c) => ({ value: c.id, label: c.name }))}
            onChange={apply}
            onOpenCharters={() => go({ kind: 'settings', section: 'charters' })}
          />
        </AgentIdentitySettings>
      )
      break
    case 'running':
      body = (
        <AgentRunningSettings
          agent={agent}
          pool={
            <PoolEditor
              agentName={agent.name}
              pool={pool}
              catalog={POOL_CATALOG}
              error={poolError}
              onAdd={(choice) => {
                const runner = POOL_RUNNERS.find((r) => r.cli === choice.provider && r.model === choice.model)
                const entry = runner
                  ? poolEntry(runner.id, choice.effort, pool.length === 0)
                  : { id: `pool-${choice.provider}-${choice.model}-${choice.effort ?? ''}`, runner_id: `runner-${choice.model}`, runner_name: choice.model, cli: choice.provider, model: choice.model, effort: choice.effort, default: pool.length === 0 }
                setPool((p) => [...p, entry])
                setPoolError(null)
                say(`${agent.name} may run on ${label(entry)}`)
              }}
              onRemove={(entry) => {
                setPool((p) => p.filter((e) => e.id !== entry.id))
                setPoolError(null)
                say(`${agent.name} no longer runs on ${label(entry)}`)
              }}
              onMakeDefault={(entry) => {
                setPool((p) => p.map((e) => ({ ...e, default: e.id === entry.id })))
                setPoolError(null)
                say(`${agent.name} runs on ${label(entry)} unless a task chooses another`)
              }}
            />
          }
          model={model}
          modelOptions={MODEL_OPTIONS}
          permissionFallback={PERMISSION_WAIT_FALLBACK_SECONDS}
          questionFallback={QUESTION_WAIT_FALLBACK_SECONDS}
          onModelChange={(choice, said) => {
            setModel(choice)
            say(said)
          }}
          onChange={apply}
        />
      )
      break
    case 'permissions':
      body = <AgentPermissionsSettings agent={agent} permissionModes={permissionModes} projectGrants={projectSettings.reach_grants ?? null} onChange={apply} />
      break
    case 'checkpoints':
      body = (
        <AgentCheckpointsSettings
          agent={agent}
          project={{ mode: projectSettings.checkpoint_mode, at: projectSettings.checkpoint_threshold_value != null ? `${projectSettings.checkpoint_threshold_value}${projectSettings.checkpoint_threshold_mode === 'tokens' ? ' tokens' : '%'}` : null }}
          taken={profileCheckpoints(agent.name).length}
          list={<ProfileCheckpoints agent={agent.name} now={now} />}
          onChange={apply}
          onShowCheckpoints={() => go({ kind: 'tab', tab: 'checkpoints' })}
        />
      )
      break
    case 'workspace':
      body = (
        <AgentWorkspaceSettings
          agent={agent}
          workingDir={`${project.working_directory}\\.agentweave\\worktrees\\${agent.name}`}
          isolated
          branch={`agentweave/${agent.name}`}
          provisioned
          // mock state: shaped like GET /agents/{name}/sessions
          sessions={[
            { id: '7f3c2a91-5be0-4d11-9a0c-2e81d4f0b6aa', type: 'claude', path: `${project.working_directory}\\.agentweave\\worktrees\\${agent.name}`, last_active: '2026-10-17T15:20:00Z' },
            { id: 'c19e44d0-2f7b-4a8e-8d35-61b0a9e7f2c3', type: 'claude', path: `${project.working_directory}\\.agentweave\\worktrees\\task-3f79a0133d22`, last_active: '2026-10-16T09:02:00Z' },
          ]}
          now={now}
          onCopy={(text, said) => {
            void navigator.clipboard?.writeText(text)
            say(said)
          }}
        />
      )
      break
  }

  if (embedded) return <div className="aw-pf-section-body">{body}</div>

  return (
    <SettingsNavLayout
      title={`${agent.name} settings`}
      subtitle={(() => {
        const d = pool.find((e) => e.default)
        return d ? (pool.length > 1 ? `${label(d)} and ${pool.length - 1} more` : label(d)) : 'No model'
      })()}
      back={{ label: `Back to ${agent.name}`, onClick: () => go({ kind: 'conversation', agent: agent.name, conversationId: null }) }}
      items={SECTIONS}
      active={section}
      onSelect={onSelectSection}
      footer={{ label: 'Project settings', icon: 'settings', onClick: () => go({ kind: 'settings', section: 'general' }) }}
    >
      {body}
    </SettingsNavLayout>
  )
}
