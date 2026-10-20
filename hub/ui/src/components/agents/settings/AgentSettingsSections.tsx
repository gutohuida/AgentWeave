import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Field, SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import { ReachGrantsChips } from '@/components/settings/ReachGrantsChips'
import { permissionOptions, runnerOptions } from '@/components/settings/settingsOptions'
import type { SelectOption } from '@/components/ui/menu'
import type { AgentSummary } from '@/api/agents'
import type { ReachGrants } from '@/api/projects'
import type { Runner } from '@/api/runners'
import type { ControlValue } from '@/api/modelCatalog'
import { formatDateTime } from '@/lib/format'

/** An agent's settings: Identity, Execution and Access. (The charter binding has its own Charter
 *  section: a setting is editable from one place only.) Same rows, same grid and same
 *  apply-on-change model as Project settings. Fixes the review's Execution bug: each row sized
 *  its own label column, so "Granted reach" was squeezed to one word per line. */

export type AgentPatch = Partial<
  Pick<AgentSummary, 'description' | 'runner_id' | 'charter_id' | 'default_permission_mode' | 'reach_grants' | 'can_read_checkpoints' | 'can_recall' | 'can_accept_evidence'>
>

export function AgentIdentitySettings({
  agent,
  now,
  onChange,
  onRename,
  onArchive,
  onUnarchive,
  archiving,
  archiveRefusal,
  descriptionMax = 256,
  notices,
}: {
  agent: AgentSummary
  now: Date
  onChange: (patch: AgentPatch, said: string) => void
  /** Absent while the Hub has no rename: the name is then shown and not offered for editing. */
  onRename?: (name: string) => void
  onArchive: () => void
  onUnarchive: () => void
  archiving?: boolean
  /** Why the Hub refused the last archive (a run in progress, undelivered messages), with what
   *  the operator can do about it. */
  archiveRefusal?: React.ReactNode
  descriptionMax?: number
  /** A refused save, under the page heading. */
  notices?: React.ReactNode
}) {
  const archived = agent.lifecycle === 'archived'
  const [description, setDescription] = React.useState(agent.description ?? '')
  const [renaming, setRenaming] = React.useState(false)
  const [name, setName] = React.useState(agent.name)
  React.useEffect(() => setDescription(agent.description ?? ''), [agent.description])
  const nameError = /^[a-zA-Z0-9_-]{1,32}$/.test(name) ? null : 'Letters, digits, - and _ only, up to 32.'

  return (
    <SettingsPage icon="badge" title="Identity" description="What this agent is called and what it is for.">
      {notices}
      <SettingsGroup title="Agent">
        <SettingsRow
          label="Name"
          description={onRename ? 'How you and its peers address it. Renaming keeps its history under the new name.' : 'How you and its peers address it, and the attribution on everything it produced.'}
          control={
            renaming ? (
              <form
                className="flex items-start gap-1.5"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (nameError || !onRename) return
                  onRename(name)
                  setRenaming(false)
                }}
              >
                <Field error={nameError ?? undefined}>
                  <Input autoFocus aria-label="New name" value={name} aria-invalid={Boolean(nameError)} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && setRenaming(false)} />
                </Field>
                <Button type="submit" variant="outline" size="sm" disabled={Boolean(nameError) || name === agent.name}>
                  Rename
                </Button>
              </form>
            ) : (
              <span className="flex items-center gap-2">
                <span className="aw-readonly-value">{agent.name}</span>
                {onRename ? (
                  <Button variant="ghost" size="xs" onClick={() => setRenaming(true)}>
                    <Icon name="edit" size={12} /> Rename
                  </Button>
                ) : null}
              </span>
            )
          }
        />
        <SettingsRow
          label="Description"
          htmlFor="a-desc"
          description="For you. Agents never read it; the charter is where behaviour is stated."
          stacked
          control={
            <Textarea
              id="a-desc"
              aria-label={`Description for ${agent.name}`}
              rows={2}
              value={description}
              maxLength={descriptionMax}
              placeholder="What this agent is for."
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => {
                // Blank clears it: the Hub stores no description rather than an empty one.
                const next = description.trim()
                if (next !== (agent.description ?? '')) onChange({ description: next || null }, next ? 'Description saved' : 'Description cleared')
              }}
            />
          }
        />
        <SettingsRow
          label="Last active"
          control={<span className="aw-readonly-value tabular">{agent.last_seen ? formatDateTime(agent.last_seen, now) : 'Never'}</span>}
        />
      </SettingsGroup>

      {archived ? (
        <section className="aw-danger" aria-label="Archived" data-tone="neutral">
          <div className="min-w-0">
            <h2 className="aw-danger-title">{agent.name} is archived</h2>
            <p className="aw-danger-desc">It is not offered anywhere an agent is chosen. Its conversations, runs and messages are unchanged, and you can bring it back at any time.</p>
          </div>
          <Button variant="outline" size="sm" data-testid="agent-archive-toggle" disabled={archiving} onClick={onUnarchive}>
            Unarchive {agent.name}
          </Button>
        </section>
      ) : (
      <section className="aw-danger" aria-label="Archive">
        <div className="min-w-0">
          <h2 className="aw-danger-title">Archive {agent.name}</h2>
          <p className="aw-danger-desc">It leaves the sidebar, task assignment and peer messaging. Everything it did stays, under its name. An agent is never deleted: its name is the attribution on everything it produced.</p>
          {archiveRefusal ? <div className="aw-danger-refusal" role="alert">{archiveRefusal}</div> : null}
        </div>
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="destructive" size="sm" data-testid="agent-archive-toggle" disabled={archiving}>
              Archive…
            </Button>
          </DialogTrigger>
          <DialogContent
            title={`Archive ${agent.name}?`}
            description={`${agent.name} stops receiving work and messages. Its conversations, tasks and evidence stay readable, and you can bring it back from its settings. The Hub refuses while a run is in progress or messages are undelivered, and says which.`}
            footer={
              <>
                <DialogClose asChild>
                  <Button variant="ghost" size="sm">
                    Keep {agent.name}
                  </Button>
                </DialogClose>
                <DialogClose asChild>
                  <Button variant="destructive" size="sm" onClick={onArchive}>
                    Archive {agent.name}
                  </Button>
                </DialogClose>
              </>
            }
          />
        </Dialog>
      </section>
      )}
    </SettingsPage>
  )
}

export function AgentExecutionSettings({
  agent,
  runners,
  runnerOptions: runnerChoices,
  permissionModes,
  permissionUnset,
  projectGrants,
  runnerNotes,
  permissionNote,
  notices,
  children,
  onChange,
}: {
  agent: AgentSummary
  runners: Runner[]
  /** The runner menu, when the container names each runner's model (F268). */
  runnerOptions?: SelectOption<string>[]
  permissionModes: ControlValue[]
  /** What clearing the default gives (the project's, or the runner's built-in), for the menu's
   *  first choice. */
  permissionUnset?: { label: string; detail: string }
  /** The project's grants, shown when the agent inherits them. */
  projectGrants: ReachGrants | null
  /** What the Hub says about running this agent (cannot run, cannot collaborate), under the
   *  runner menu. Replaces the plain "no runner" line when given. */
  runnerNotes?: React.ReactNode
  /** A caveat under the permissions menu (Claude's read-only commands under Ask me). */
  permissionNote?: React.ReactNode
  /** A refused save, under the page heading. */
  notices?: React.ReactNode
  /** Groups only some runners have (Copilot's review agents and GitHub server). */
  children?: React.ReactNode
  onChange: (patch: AgentPatch, said: string) => void
}) {
  const ownGrants = agent.reach_grants != null
  return (
    <SettingsPage icon="terminal" title="Execution" description={`What ${agent.name} runs as when you give it a turn.`}>
      {notices}
      <SettingsGroup title="Runs as">
        <SettingsRow
          label="Runner"
          description="The CLI, model and flags this agent launches with."
          control={
            <span className="aw-control-stack">
              <MenuSelect
                label={`Runner for ${agent.name}`}
                value={agent.runner_id ?? ''}
                onChange={(v) => onChange({ runner_id: v || null }, v ? `${agent.name} runs on ${runners.find((r) => r.id === v)?.name}` : `${agent.name} has no runner`)}
                options={runnerChoices ?? runnerOptions(runners, { label: 'No runner', detail: 'The agent cannot run until it has one' })}
              />
              {runnerNotes !== undefined ? (
                runnerNotes
              ) : agent.runner_id ? null : (
                <span className="aw-control-warning" role="status">
                  <Icon name="warning" size={12} /> This agent cannot run until it has one.
                </span>
              )}
            </span>
          }
        />
      </SettingsGroup>

      <SettingsGroup title="Permissions" description="What it may do when a conversation has not said. A conversation's own choice wins for that conversation.">
        <SettingsRow
          label="Default permissions"
          changed={Boolean(agent.default_permission_mode)}
          onReset={() => onChange({ default_permission_mode: null }, 'Default permissions follow the project again')}
          description="Also what scheduled runs and peer messages get, since they have no composer to choose in."
          control={
            <span className="aw-control-stack">
              <MenuSelect
                label={`Default permissions for ${agent.name}`}
                value={agent.default_permission_mode ?? ''}
                onChange={(v) => onChange({ default_permission_mode: v || null }, v ? `${agent.name}: ${permissionModes.find((m) => m.id === v)?.label}` : 'Default permissions follow the project again')}
                options={permissionOptions(permissionModes, permissionUnset?.label ?? 'The project’s default', permissionUnset?.detail ?? 'Whatever Project settings → General says')}
              />
              {permissionNote}
            </span>
          }
        />
        <SettingsRow
          label="Own granted reach"
          description="Folders and hosts beyond its workspace under Workspace only. Off: it has the project's grants."
          changed={ownGrants}
          onReset={() => onChange({ reach_grants: null }, 'Granted reach follows the project again')}
          control={
            <Switch
              aria-label={`Own granted reach for ${agent.name}`}
              checked={ownGrants}
              onCheckedChange={(v) => onChange({ reach_grants: v ? (projectGrants ?? { roots: [], hosts: [] }) : null }, v ? `${agent.name} has its own reach` : 'Granted reach follows the project again')}
            />
          }
        >
          <ReachGrantsChips
            grants={ownGrants ? agent.reach_grants : projectGrants}
            readOnly={!ownGrants}
            emptyLabel={ownGrants ? 'Nothing beyond the workspace' : 'The project grants nothing beyond the workspace'}
            onChange={(g) => onChange({ reach_grants: g ?? { roots: [], hosts: [] } }, 'Granted reach updated')}
          />
        </SettingsRow>
      </SettingsGroup>
      {children}
    </SettingsPage>
  )
}

export function AgentAccessSettings({
  agent,
  onChange,
  notices,
}: {
  agent: AgentSummary
  onChange: (patch: AgentPatch, said: string) => void
  /** A refused save, under the page heading. */
  notices?: React.ReactNode
}) {
  const readCheckpoints = Boolean(agent.can_read_checkpoints)
  return (
    <SettingsPage icon="lock" title="Access" description={`What ${agent.name} may read of other agents' work, and what it may decide.`}>
      {notices}
      <SettingsGroup title="Other agents' work" description="Both closed by default. A summary of a peer's work and the raw output behind it are granted separately.">
        <SettingsRow
          label="Read other agents' checkpoints"
          description="Summaries of where their conversations got to, from every conversation in this project."
          control={
            <Switch
              aria-label={`Read other agents’ checkpoints for ${agent.name}`}
              checked={readCheckpoints}
              onCheckedChange={(v) =>
                onChange(v ? { can_read_checkpoints: true } : { can_read_checkpoints: false, can_recall: false }, v ? `${agent.name} may read checkpoints` : `${agent.name} may no longer read checkpoints`)
              }
            />
          }
        />
        <SettingsRow
          label="Recall what a checkpoint cites"
          inactive={!readCheckpoints}
          description={readCheckpoints ? 'The original recorded output a checkpoint cites, word for word.' : 'Needs “Read other agents’ checkpoints” first: recall only reaches what a checkpoint it can read cites.'}
          control={
            <Switch
              aria-label={`Recall what a checkpoint cites for ${agent.name}`}
              disabled={!readCheckpoints}
              checked={Boolean(agent.can_recall)}
              onCheckedChange={(v) => onChange({ can_recall: v }, v ? `${agent.name} may recall cited output` : `${agent.name} may no longer recall`)}
            />
          }
        />
      </SettingsGroup>
      <SettingsGroup title="Authority">
        <SettingsRow
          label="Accept or reject evidence"
          description="Accepted evidence is what lets approving a task merge its work. It cannot accept its own: another agent, or you, decides that."
          control={
            <Switch
              aria-label={`Accept evidence for ${agent.name}`}
              checked={Boolean(agent.can_accept_evidence)}
              onCheckedChange={(v) => onChange({ can_accept_evidence: v }, v ? `${agent.name} may decide on evidence` : `${agent.name} may no longer decide on evidence`)}
            />
          }
        />
      </SettingsGroup>
    </SettingsPage>
  )
}
