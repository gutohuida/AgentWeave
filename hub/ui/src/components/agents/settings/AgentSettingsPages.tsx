import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Segmented } from '@/components/ui/segmented'
import type { AgentSummary } from '@/api/agents'
import type { ControlValue } from '@/api/modelCatalog'
import type { ReachGrants } from '@/api/projects'
import { CommittedInput } from '@/components/settings/CommittedInput'
import { wholeNumber } from '@/components/settings/settingsOptions'
import { formatAgo } from '@/lib/format'
import { AgentAccessGroups, AgentPermissionGroup, type AgentPatch } from './AgentSettingsSections'

/**
 * An agent's settings in five sections (`settings-in-the-app-s-style-where-you-expect-them`):
 * Agent (identity and charter: `AgentIdentitySettings` with `AgentCharterGroup`), Running,
 * Permissions, Checkpoints and Workspace. Permissions and Checkpoints carry the names of the
 * project sections they override. Presentational: values in, a patch and a toast sentence out.
 */

/** The charter this agent works under, on the Agent page. */
export function AgentCharterGroup({
  agent,
  charters,
  onChange,
  onOpenCharters,
}: {
  agent: AgentSummary
  charters: SelectOption<string>[]
  onChange: (patch: AgentPatch, said: string) => void
  onOpenCharters?: () => void
}) {
  return (
    <SettingsGroup title="Charter">
      <SettingsRow
        label="Charter"
        description="The behaviour contract read at the start of each of its turns."
        control={
          <span className="aw-control-stack">
            <MenuSelect
              label={`Charter for ${agent.name}`}
              value={agent.charter_id ?? ''}
              onChange={(v) => onChange({ charter_id: v || null }, v ? `${agent.name} works under ${charters.find((c) => c.value === v)?.label}` : `${agent.name} has no charter`)}
              options={[{ value: '', label: 'No charter', detail: 'Only the project’s instructions and its roster' }, ...charters]}
            />
            {onOpenCharters ? (
              <Button variant="ghost" size="xs" className="self-end" onClick={onOpenCharters}>
                Edit charters <Icon name="arrow_forward" size={12} />
              </Button>
            ) : null}
          </span>
        }
      />
    </SettingsGroup>
  )
}

/** A model to run on: what agent creation offers, so no runner needs making first. The value is
 *  `<provider>:<model>`; an empty model is the provider's own default. */
export type ModelChoice = { provider: string; model: string | null }

function modelChoiceValue(choice: ModelChoice | null): string {
  return choice ? `${choice.provider}:${choice.model ?? ''}` : ''
}

function seconds(value: number | null | undefined, fallback: number): string {
  return String(value ?? fallback)
}

export function AgentRunningSettings({
  agent,
  model,
  modelOptions,
  runNotes,
  permissionFallback,
  questionFallback,
  notices,
  children,
  onModelChange,
  onChange,
}: {
  agent: AgentSummary
  /** The model it runs on now; null with nothing bound. */
  model: ModelChoice | null
  /** Every installed provider's models, `<provider>:<model>` valued, grouped by provider name in each label. */
  modelOptions: SelectOption<string>[]
  /** What the Hub says about running it (cannot run, cannot collaborate). */
  runNotes?: React.ReactNode
  permissionFallback: number
  questionFallback: number
  notices?: React.ReactNode
  /** Groups only some providers have (Copilot's review agents and GitHub server). */
  children?: React.ReactNode
  onModelChange: (choice: ModelChoice, said: string) => void
  onChange: (patch: Partial<Pick<AgentSummary, 'permission_timeout_seconds' | 'question_timeout_seconds'>>, said: string) => void
}) {
  return (
    <SettingsPage icon="terminal" title="Running" description={`What ${agent.name} runs on, and how long it holds a turn open for you.`}>
      {notices}
      <SettingsGroup title="Model">
        <SettingsRow
          label="Model"
          description="The coding agent and model each of its turns launches with. A conversation can still pick another for itself."
          control={
            <span className="aw-control-stack">
              <MenuSelect
                label={`Model for ${agent.name}`}
                maxWidth={320}
                value={modelChoiceValue(model)}
                placeholder="Choose a model"
                onChange={(v) => {
                  const [provider, ...rest] = v.split(':')
                  const id = rest.join(':')
                  onModelChange({ provider: provider!, model: id || null }, `${agent.name} runs on ${modelOptions.find((o) => o.value === v)?.label ?? v}`)
                }}
                options={modelOptions}
              />
              {runNotes ?? (model ? null : (
                <span className="aw-control-warning" role="status">
                  <Icon name="warning" size={12} /> It cannot run until it has a model.
                </span>
              ))}
            </span>
          }
        />
      </SettingsGroup>
      {children}
      <SettingsGroup title="Waiting for you" description="How long a run holds its turn open before it gives up and carries on.">
        <SettingsRow
          label="A permission decision"
          htmlFor="a-perm-wait"
          description="Under “Ask me”, how long it waits for you to allow or refuse an action. Running out refuses it."
          changed={agent.permission_timeout_seconds != null}
          onReset={() => onChange({ permission_timeout_seconds: null }, `Permission wait back to ${permissionFallback}s`)}
          control={
            <CommittedInput
              id="a-perm-wait"
              numeric
              width={72}
              suffix="seconds"
              value={seconds(agent.permission_timeout_seconds, permissionFallback)}
              validate={wholeNumber(10, 3600, 'seconds')}
              onCommit={(v) => onChange({ permission_timeout_seconds: Number(v) }, `Waits ${v}s for a permission decision`)}
            />
          }
        />
        <SettingsRow
          label="An answer to a question"
          htmlFor="a-question-wait"
          description="How long it waits for you to answer a question it asked. Longer than a permission decision: you have to read it and choose."
          changed={agent.question_timeout_seconds != null}
          onReset={() => onChange({ question_timeout_seconds: null }, `Question wait back to ${questionFallback}s`)}
          control={
            <CommittedInput
              id="a-question-wait"
              numeric
              width={72}
              suffix="seconds"
              value={seconds(agent.question_timeout_seconds, questionFallback)}
              validate={wholeNumber(10, 3600, 'seconds')}
              onCommit={(v) => onChange({ question_timeout_seconds: Number(v) }, `Waits ${v}s for an answer`)}
            />
          }
        />
      </SettingsGroup>
    </SettingsPage>
  )
}

export function AgentPermissionsSettings({
  agent,
  permissionModes,
  permissionUnset,
  projectGrants,
  permissionNote,
  notices,
  onChange,
}: {
  agent: AgentSummary
  permissionModes: ControlValue[]
  permissionUnset?: { label: string; detail: string }
  projectGrants: ReachGrants | null
  permissionNote?: React.ReactNode
  notices?: React.ReactNode
  onChange: (patch: AgentPatch, said: string) => void
}) {
  return (
    <SettingsPage icon="lock" title="Permissions" description={`What ${agent.name} may do, read and decide. Where it has no setting of its own, the project's applies.`}>
      {notices}
      <AgentPermissionGroup agent={agent} permissionModes={permissionModes} permissionUnset={permissionUnset} projectGrants={projectGrants} permissionNote={permissionNote} onChange={onChange} />
      <AgentAccessGroups agent={agent} onChange={onChange} />
    </SettingsPage>
  )
}

type CheckpointMode = NonNullable<AgentSummary['checkpoint_mode']>
const MODE_WORDS: Record<CheckpointMode, string> = { off: 'Off', offered: 'Offer me one', automatic: 'Automatic' }

export function AgentCheckpointsSettings({
  agent,
  project,
  taken,
  notices,
  onChange,
  onShowCheckpoints,
}: {
  agent: AgentSummary
  /** What the project's Checkpoints section says, so "the project's" reads as a value. */
  project: { mode: CheckpointMode; at: string | null }
  /** How many checkpoints its conversations have produced. */
  taken?: number
  notices?: React.ReactNode
  onChange: (patch: Partial<Pick<AgentSummary, 'checkpoint_mode' | 'checkpoint_threshold_mode' | 'checkpoint_threshold_value'>>, said: string) => void
  onShowCheckpoints: () => void
}) {
  const unit = agent.checkpoint_threshold_mode ?? 'percent'
  const own = agent.checkpoint_threshold_value != null
  const entry = own ? String(unit === 'tokens' ? Math.round(agent.checkpoint_threshold_value! / 1000) : agent.checkpoint_threshold_value) : ''
  return (
    <SettingsPage icon="book_marked" title="Checkpoints" description={`When ${agent.name}'s conversations are checkpointed. Unset, it follows the project's Checkpoints.`}>
      {notices}
      <SettingsGroup title="When">
        <SettingsRow
          label="Checkpoints"
          description="Whether its conversations are checkpointed at all."
          changed={agent.checkpoint_mode != null}
          onReset={() => onChange({ checkpoint_mode: null }, 'Checkpoints follow the project again')}
          control={
            <MenuSelect
              label={`Checkpoints for ${agent.name}`}
              value={agent.checkpoint_mode ?? ''}
              onChange={(v) => onChange({ checkpoint_mode: (v || null) as CheckpointMode | null }, v ? `Checkpoints: ${MODE_WORDS[v as CheckpointMode]}` : 'Checkpoints follow the project again')}
              options={[
                { value: '', label: `The project’s (${MODE_WORDS[project.mode]})` },
                { value: 'offered', label: 'Offer me one', detail: 'At the threshold the Hub writes one and tells you.' },
                { value: 'automatic', label: 'Automatic', detail: 'At the threshold the Hub writes one and continues in a new conversation.' },
                { value: 'off', label: 'Off', detail: 'None are written by themselves for this agent.' },
              ]}
            />
          }
        />
        <SettingsRow
          label="Checkpoint at"
          htmlFor="a-threshold"
          inactive={agent.checkpoint_mode === 'off'}
          description={own ? 'Its own point, in place of the project’s.' : `The project’s: ${project.at ?? 'the built-in point'}. Empty follows it.`}
          changed={own}
          onReset={() => onChange({ checkpoint_threshold_mode: null, checkpoint_threshold_value: null }, 'Checkpoint point follows the project again')}
          control={
            <span className="flex items-center gap-1.5">
              <CommittedInput
                id="a-threshold"
                numeric
                width={72}
                placeholder="—"
                value={entry}
                validate={(d) => (d === '' ? null : wholeNumber(1, unit === 'percent' ? 99 : 10000, unit === 'percent' ? 'percent' : 'thousand tokens')(d))}
                onCommit={(v) =>
                  onChange(
                    v === '' ? { checkpoint_threshold_mode: null, checkpoint_threshold_value: null } : { checkpoint_threshold_mode: unit, checkpoint_threshold_value: unit === 'tokens' ? Number(v) * 1000 : Number(v) },
                    v === '' ? 'Checkpoint point follows the project again' : `Checkpoint at ${v}${unit === 'percent' ? '%' : 'K tokens'}`,
                  )
                }
              />
              <Segmented
                label="Threshold unit"
                size="xs"
                value={unit}
                onChange={(next) => onChange({ checkpoint_threshold_mode: next, checkpoint_threshold_value: null }, `Checkpoint point cleared: enter it in ${next === 'percent' ? 'percent' : 'K tokens'}`)}
                options={[
                  { value: 'percent', label: '%' },
                  { value: 'tokens', label: 'K tokens' },
                ]}
              />
            </span>
          }
        />
      </SettingsGroup>
      <SettingsGroup title="Taken">
        <SettingsRow
          label="Its checkpoints"
          description="Every checkpoint written from its conversations."
          control={
            <Button variant="outline" size="sm" data-testid="agent-checkpoints-link" onClick={onShowCheckpoints}>
              {taken != null ? `Show ${taken}` : 'Show them'} <Icon name="arrow_forward" size={12} />
            </Button>
          }
        />
      </SettingsGroup>
    </SettingsPage>
  )
}

export interface AgentSessionRow {
  id: string
  type: string
  path: string
  last_active?: string
}

export function AgentWorkspaceSettings({
  agent,
  workingDir,
  isolated,
  branch,
  provisioned,
  note,
  sessions,
  now,
  onCopy,
}: {
  agent: AgentSummary
  workingDir: string
  isolated: boolean
  branch?: string | null
  provisioned?: boolean
  /** Why it has no worktree of its own, when it has none. */
  note?: string | null
  sessions: AgentSessionRow[]
  now: Date
  onCopy: (text: string, said: string) => void
}) {
  return (
    <SettingsPage icon="folder" title="Workspace" description={`Where ${agent.name} does its work on disk. Read only: the Hub decides it.`}>
      <SettingsGroup title="Where it works">
        <SettingsRow
          label="Working directory"
          description={<span className="aw-path">{workingDir}</span>}
          control={
            <Button variant="outline" size="sm" onClick={() => onCopy(workingDir, 'Path copied')}>
              <Icon name="content_copy" size={13} /> Copy path
            </Button>
          }
        />
        <SettingsRow
          label="Its own checkout"
          description={
            isolated
              ? `On ${branch ?? 'its own branch'}, ${provisioned ? 'checked out and ready' : 'created the first time it runs'}. Its changes are merged deliberately.`
              : (note ?? 'It shares the project checkout, so a second writer overwrites rather than conflicts.')
          }
          control={
            <span className="aw-state-chip" data-tone={isolated ? 'good' : undefined}>
              <span className="aw-state-dot" />
              {isolated ? 'Own worktree' : 'Shared'}
            </span>
          }
        />
      </SettingsGroup>
      <SettingsGroup title="Provider sessions" description="Diagnostic: the sessions each coding agent recorded, and where they ran. AgentWeave addresses conversations by its own id.">
        {sessions.length === 0 ? <p className="aw-row-note">No sessions yet.</p> : null}
        {sessions.map((s) => (
          <SettingsRow
            key={s.id}
            label={<span className="font-mono text-[12px]" title={s.id}>{s.id.length > 18 ? `${s.id.slice(0, 8)}…${s.id.slice(-6)}` : s.id}</span>}
            description={<span className="aw-path">{s.path}</span>}
            control={
              <span className="flex items-center gap-2">
                <span className="aw-row-value">{s.type}{s.last_active ? ` · ${formatAgo(s.last_active, now)}` : ''}</span>
                <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label="Copy session id" title="Copy session id" onClick={() => onCopy(s.id, 'Session id copied')}>
                  <Icon name="content_copy" size={13} />
                </button>
              </span>
            }
          />
        ))}
      </SettingsGroup>
    </SettingsPage>
  )
}
