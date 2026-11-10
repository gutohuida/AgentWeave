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

/** The container an agent's settings route would be: the agent from the roster, a patch applied
 *  (here locally, in the app through the agent mutation) and confirmed in a toast. */
export default function AgentSettings({ route, go, now }: ScreenProps) {
  const name = route.kind === 'agent-settings' ? route.agent : 'Builder'
  const section: AgentSettingsSection = route.kind === 'agent-settings' && SECTIONS.some((s) => s.id === route.section) ? route.section : 'running'
  const initial = agents.find((a) => a.name === name) ?? agents[0]!
  const [agent, setAgent] = React.useState<AgentSummary>(initial)
  React.useEffect(() => setAgent(initial), [initial])
  // mock state: the recorded roster carries no runner; Builder runs on Sonnet here.
  const [model, setModel] = React.useState<ModelChoice | null>({ provider: 'claude', model: 'claude-sonnet-5-5' })

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
          title="Agent"
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
          taken={7}
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

  return (
    <SettingsNavLayout
      title={`${agent.name} settings`}
      subtitle={model ? MODEL_OPTIONS.find((o) => o.value === `${model.provider}:${model.model ?? ''}`)?.label : 'No model'}
      back={{ label: `Back to ${agent.name}`, onClick: () => go({ kind: 'conversation', agent: agent.name, conversationId: null }) }}
      items={SECTIONS}
      active={section}
      onSelect={(id) => go({ kind: 'agent-settings', agent: agent.name, section: id })}
      footer={{ label: 'Project settings', icon: 'settings', onClick: () => go({ kind: 'settings', section: 'general' }) }}
    >
      {body}
    </SettingsNavLayout>
  )
}
