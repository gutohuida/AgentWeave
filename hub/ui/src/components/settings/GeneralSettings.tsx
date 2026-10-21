import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { Field, SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import type { ProjectCheck, ProjectSettings } from '@/api/projects'
import type { ControlValue } from '@/api/modelCatalog'
import { describeThreshold } from '@/components/environment/describeThreshold'
import { CommittedInput } from './CommittedInput'
import { PROJECT_DEFAULTS, permissionOptions, wholeNumber } from './settingsOptions'
import { ReachGrantsChips } from './ReachGrantsChips'

/** Project settings → General. Every row applies on change (numbers when you leave the field);
 *  the container saves the patch and confirms with a toast. Rows that differ from the Hub's
 *  defaults offer a reset in the same place on every row. */

/** Token thresholds are stored as a count and entered in thousands, the unit an operator thinks in. */
const TOKENS_PER_UNIT = 1000

type ThresholdMode = 'percent' | 'tokens'

function toEntry(mode: ThresholdMode, value: number | null): string {
  if (value == null) return ''
  return String(mode === 'tokens' ? Math.round(value / TOKENS_PER_UNIT) : value)
}

function toStored(mode: ThresholdMode, entry: string): number | null {
  if (entry === '') return null
  return mode === 'tokens' ? Number(entry) * TOKENS_PER_UNIT : Number(entry)
}

const UNIT_WORD: Record<ThresholdMode, string> = { percent: '%', tokens: 'K tokens' }

const CHECKPOINT_MODE_LABEL: Record<ProjectSettings['checkpoint_mode'], string> = {
  off: 'Off',
  offered: 'Offer me one',
  automatic: 'Automatic',
}

export function GeneralSettings({
  settings,
  runnerOptions,
  modelOptions,
  permissionModes,
  folder,
  folderAvailable,
  mainBranch,
  contextWindow,
  ceilingNotes = [],
  agentsUnreadable,
  notices,
  relocating,
  onChange,
  onRelocate,
  onOpenBudgets,
  onDeleteProject,
}: {
  settings: ProjectSettings
  /** The checkpoint-runner menu (the container names each runner's model from the catalog). */
  runnerOptions: SelectOption<string>[]
  /** The checkpoint runner's provider's models. */
  modelOptions: SelectOption<string>[]
  permissionModes: ControlValue[]
  folder: string
  folderAvailable: boolean
  /** What the Hub detects about the project's git state: whether it is a repository, and the
   *  branch it would suggest. Absent while unknown. */
  mainBranch?: { is_repository: boolean; suggestion: string | null } | null
  /** The checkpoint model's window, so a threshold reads in both units. */
  contextWindow?: number | null
  /** Where an agent's checkpoint fires below the project's threshold (D10). */
  ceilingNotes?: string[]
  /** The project's agents could not be read, so those notes cannot be computed. */
  agentsUnreadable?: boolean
  /** What the last save answered (warnings, a refusal), shown under the page heading. */
  notices?: React.ReactNode
  relocating?: boolean
  onChange: (patch: Partial<ProjectSettings>, said: string) => void
  /** Rebind a project whose folder has moved. */
  onRelocate?: (path: string) => void
  onOpenBudgets?: () => void
  /** Opens the type-to-confirm delete dialog the container owns. */
  onDeleteProject: () => void
}) {
  const checks = settings.checks ?? []
  const [unit, setUnit] = React.useState<ThresholdMode>(settings.checkpoint_threshold_mode ?? 'percent')
  React.useEffect(() => {
    if (settings.checkpoint_threshold_mode) setUnit(settings.checkpoint_threshold_mode)
  }, [settings.checkpoint_threshold_mode])
  const [newPath, setNewPath] = React.useState('')
  const isRepository = mainBranch ? mainBranch.is_repository : true
  const stored = settings.checkpoint_threshold_value
  const storedMode = settings.checkpoint_threshold_mode
  const reading = describeThreshold(storedMode, stored, contextWindow ?? null)
  const setChecks = (next: ProjectCheck[], said: string) => onChange({ checks: next.length ? next : null }, said)
  const moveCheck = (index: number, by: number) => {
    const next = [...checks]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item)
    setChecks(next, `Moved the check ${item.name} ${by < 0 ? 'up' : 'down'}`)
  }
  const clearThreshold = (said: string) =>
    onChange({ checkpoint_threshold_value: null, checkpoint_threshold_mode: null, checkpoint_notes_value: null }, said)

  return (
    <SettingsPage icon="settings" title="General" description="How agents work together in this project, what they may reach, and where approved work lands.">
      {notices}
      <SettingsGroup title="Collaboration">
        <SettingsRow
          label="Agents may start jobs, flows and loops"
          description="Off: an agent asking to start a job, flow or loop is refused, and you are asked instead."
          changed={settings.allow_agent_jobs !== PROJECT_DEFAULTS.allow_agent_jobs}
          onReset={() => onChange({ allow_agent_jobs: PROJECT_DEFAULTS.allow_agent_jobs }, 'Agents may start jobs again')}
          control={
            <Switch
              aria-label="Agents may start jobs, flows and loops"
              checked={settings.allow_agent_jobs}
              onCheckedChange={(v) => onChange({ allow_agent_jobs: v }, v ? 'Agents may start jobs' : 'Agents can no longer start jobs')}
            />
          }
        />
        <SettingsRow
          label="Hop budget"
          htmlFor="s-hops"
          description="How many agent-to-agent hops a chain may take before it pauses for you."
          changed={settings.hop_budget !== PROJECT_DEFAULTS.hop_budget}
          onReset={() => onChange({ hop_budget: PROJECT_DEFAULTS.hop_budget }, `Hop budget reset to ${PROJECT_DEFAULTS.hop_budget}`)}
          control={
            <CommittedInput
              id="s-hops"
              numeric
              width={72}
              suffix="hops"
              value={String(settings.hop_budget)}
              validate={wholeNumber(1, 50, 'hops')}
              onCommit={(v) => onChange({ hop_budget: Number(v) }, `Hop budget set to ${v}`)}
            />
          }
        />
        <SettingsRow
          label="Deliveries per turn"
          htmlFor="s-cap"
          description="The most queued messages one agent turn takes in."
          changed={settings.turn_delivery_cap !== PROJECT_DEFAULTS.turn_delivery_cap}
          onReset={() => onChange({ turn_delivery_cap: PROJECT_DEFAULTS.turn_delivery_cap }, `Deliveries per turn reset to ${PROJECT_DEFAULTS.turn_delivery_cap}`)}
          control={
            <CommittedInput
              id="s-cap"
              numeric
              width={72}
              suffix="per turn"
              value={String(settings.turn_delivery_cap)}
              validate={wholeNumber(1, 100, 'messages')}
              onCommit={(v) => onChange({ turn_delivery_cap: Number(v) }, `Deliveries per turn set to ${v}`)}
            />
          }
        />
        <SettingsRow
          label="Agent budget"
          htmlFor="s-agents"
          description="How many agents the project may hold before an agent asking for another is refused. Adding one yourself is never limited."
          changed={settings.agent_budget !== PROJECT_DEFAULTS.agent_budget}
          onReset={() => onChange({ agent_budget: PROJECT_DEFAULTS.agent_budget }, `Agent budget reset to ${PROJECT_DEFAULTS.agent_budget}`)}
          control={
            <CommittedInput
              id="s-agents"
              numeric
              width={72}
              suffix="agents"
              value={String(settings.agent_budget)}
              validate={wholeNumber(1, 64, 'agents')}
              onCommit={(v) => onChange({ agent_budget: Number(v) }, `Agent budget set to ${v}`)}
            />
          }
        />
        {onOpenBudgets ? (
          <SettingsRow
            label="Token limit"
            description="Set in Budgets, beside the usage it limits."
            control={
              <Button variant="outline" size="sm" onClick={onOpenBudgets}>
                Open Budgets
              </Button>
            }
          />
        ) : null}
      </SettingsGroup>

      <SettingsGroup title="Reach" description="What agents may do when nobody said otherwise. An agent's own settings win over these.">
        <SettingsRow
          label="Default permissions"
          description="For every run whose conversation and agent have not chosen. Full access allows everything, Copilot and specification turns included."
          changed={Boolean(settings.default_permission_mode)}
          onReset={() => onChange({ default_permission_mode: null }, 'Default permissions reset to each runner’s own')}
          control={
            <MenuSelect
              label="Default permissions"
              value={settings.default_permission_mode ?? ''}
              onChange={(v) => {
                const chosen = permissionModes.find((m) => m.id === v)
                onChange({ default_permission_mode: v || null }, chosen ? `Default permissions: ${chosen.label}` : 'Default permissions reset to each runner’s own')
              }}
              options={permissionOptions(permissionModes, 'Each runner’s own', 'Claude and Codex: Workspace only. Copilot: Ask me.')}
            />
          }
        />
        <SettingsRow
          label="Granted reach"
          description="Under Workspace only: folders and hosts an agent may use beyond its workspace (a shell command needs read and write). A guardrail against mistakes, not a sandbox; writes outside are still recorded on the run."
          stacked
          control={<ReachGrantsChips grants={settings.reach_grants} onChange={(g) => onChange({ reach_grants: g }, 'Granted reach updated')} />}
        />
      </SettingsGroup>

      <SettingsGroup title="Integration" description="Where approved work lands, and what must pass first.">
        <SettingsRow
          label="Main branch"
          htmlFor="s-branch"
          description={isRepository ? 'Approving a task merges its work here. Empty: nothing merges.' : 'This folder is not a git repository, so there is nothing to merge into.'}
          control={
            <span className="aw-control-stack">
              <CommittedInput
                id="s-branch"
                value={settings.main_branch ?? ''}
                disabled={!isRepository}
                placeholder={mainBranch?.suggestion ?? 'No branch: nothing merges'}
                onCommit={(v) => onChange({ main_branch: v || null }, v ? `Approved work merges into ${v}` : 'Approved work no longer merges')}
              />
              {isRepository && mainBranch?.suggestion && !settings.main_branch ? (
                <Button variant="ghost" size="xs" className="self-start" onClick={() => onChange({ main_branch: mainBranch.suggestion }, `Approved work merges into ${mainBranch.suggestion}`)}>
                  Use “{mainBranch.suggestion}”
                </Button>
              ) : null}
            </span>
          }
        />
        <SettingsRow
          label="Checks"
          description="Commands run on the main branch plus a task's work before approval merges it, in this order. Approval is refused until they pass."
          stacked
          control={
            <div className="aw-checks" data-testid="project-checks">
              {checks.length === 0 ? <p className="aw-checks-empty">No checks: approval merges without running anything.</p> : null}
              {checks.map((check, i) => (
                <div key={`${check.name}-${i}`} className="aw-check-row aw-reveal-host" data-testid={`project-check-${i}`}>
                  <Icon name="terminal" size={13} className="aw-check-icon" />
                  <span className="aw-check-name">{check.name}</span>
                  <code className="aw-check-command">{check.command}</code>
                  <span className="aw-check-timeout">{check.timeout_seconds}s</span>
                  <span className="aw-reveal">
                    <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Move ${check.name} up`} title="Move up" disabled={i === 0} onClick={() => moveCheck(i, -1)}>
                      <Icon name="arrow_upward" size={13} />
                    </button>
                    <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Move ${check.name} down`} title="Move down" disabled={i === checks.length - 1} onClick={() => moveCheck(i, 1)}>
                      <Icon name="arrow_downward" size={13} />
                    </button>
                    <CheckDialog
                      title={`Edit ${check.name}`}
                      initial={check}
                      submitLabel="Save check"
                      trigger={
                        <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Edit ${check.name}`} title="Edit">
                          <Icon name="edit" size={13} />
                        </button>
                      }
                      onSubmit={(next) => setChecks(checks.map((c, j) => (j === i ? next : c)), `Saved the check ${next.name}`)}
                    />
                    <button
                      type="button"
                      data-slot="icon-button"
                      className="aw-icon-button"
                      aria-label={`Remove ${check.name}`}
                      title="Remove"
                      onClick={() => setChecks(checks.filter((_, j) => j !== i), `Removed the check ${check.name}`)}
                    >
                      <Icon name="delete" size={13} />
                    </button>
                  </span>
                </div>
              ))}
              <CheckDialog
                title="Add a check"
                submitLabel="Add check"
                trigger={
                  <Button variant="ghost" size="xs" className="self-start">
                    <Icon name="add" size={13} /> Add check
                  </Button>
                }
                onSubmit={(check) => setChecks([...checks, check], `Added the check ${check.name}`)}
              />
            </div>
          }
        />
      </SettingsGroup>

      <SettingsGroup title="Checkpointing" description="When a conversation's context fills, the Hub writes a checkpoint so a fresh conversation can continue the work.">
        <SettingsRow
          label="Checkpoints"
          changed={settings.checkpoint_mode !== PROJECT_DEFAULTS.checkpoint_mode}
          onReset={() => onChange({ checkpoint_mode: PROJECT_DEFAULTS.checkpoint_mode }, 'Checkpoints reset to Offer me one')}
          control={
            <MenuSelect
              label="Checkpoints"
              value={settings.checkpoint_mode}
              onChange={(v) => onChange({ checkpoint_mode: v }, `Checkpoints: ${CHECKPOINT_MODE_LABEL[v]}`)}
              options={[
                { value: 'offered', label: 'Offer me one', detail: 'At the threshold the Hub writes one and tells you. Nothing is archived until you cut over.' },
                { value: 'automatic', label: 'Automatic', detail: 'At the threshold the Hub writes one, opens a successor with it, and archives this conversation.' },
                { value: 'off', label: 'Off', detail: 'No checkpoints are written by themselves. You can still write one from a conversation.' },
              ]}
            />
          }
        />
        <SettingsRow
          label="Checkpoint at"
          htmlFor="s-threshold"
          inactive={settings.checkpoint_mode === 'off'}
          description={reading ? `Reached at ${reading}. Empty: the built-in point.` : 'How full the context gets before a checkpoint is written. Empty: the built-in point.'}
          changed={stored != null}
          onReset={() => clearThreshold('Checkpoint point reset to the built-in one')}
          control={
            <span className="flex items-center gap-1.5">
              <CommittedInput
                id="s-threshold"
                numeric
                width={72}
                placeholder={unit === 'percent' ? '70' : '140'}
                value={storedMode === unit ? toEntry(unit, stored) : ''}
                validate={(d) => (d === '' ? null : wholeNumber(1, unit === 'percent' ? 99 : 10000, unit === 'percent' ? 'percent' : 'thousand tokens')(d))}
                onCommit={(v) =>
                  // A threshold is a unit and a value together, or neither — never half.
                  v === ''
                    ? clearThreshold('Checkpoint point reset to the built-in one')
                    : onChange({ checkpoint_threshold_value: toStored(unit, v), checkpoint_threshold_mode: unit }, `Checkpoint at ${v}${UNIT_WORD[unit] === '%' ? '%' : 'K tokens'}`)
                }
              />
              <MenuSelect
                label="Threshold unit"
                maxWidth={130}
                value={unit}
                onChange={(v) => {
                  setUnit(v)
                  // The two units share no value: a threshold stored in the other one is cleared,
                  // and entered again in this one.
                  if (stored != null && storedMode !== v) clearThreshold(`Checkpoint point cleared: enter it in ${v === 'percent' ? 'percent' : 'K tokens'}`)
                }}
                options={[
                  { value: 'percent', label: '% of window' },
                  { value: 'tokens', label: 'K tokens' },
                ]}
              />
            </span>
          }
        >
          {ceilingNotes.map((note) => (
            <p key={note} className="aw-row-note" data-testid="ceiling-note">
              {note}
            </p>
          ))}
          {agentsUnreadable ? <p className="aw-row-note">The project's agents could not be read, so a threshold lowered for their runners is not shown.</p> : null}
        </SettingsRow>
        <SettingsRow
          label="Ask for notes at"
          htmlFor="s-notes"
          inactive={settings.checkpoint_mode === 'off' || stored == null}
          description={stored == null ? 'Set a checkpoint point first: notes are asked for below it.' : 'Before the checkpoint, the agent is asked what the record cannot show. Must sit below the checkpoint point.'}
          control={
            <CommittedInput
              id="s-notes"
              numeric
              width={72}
              disabled={stored == null}
              placeholder={unit === 'percent' ? '60' : '120'}
              suffix={UNIT_WORD[storedMode ?? unit]}
              value={storedMode ? toEntry(storedMode, settings.checkpoint_notes_value) : ''}
              validate={(d) => (d === '' ? null : wholeNumber(1, (storedMode ?? unit) === 'percent' ? 98 : 10000, (storedMode ?? unit) === 'percent' ? 'percent' : 'thousand tokens')(d))}
              onCommit={(v) =>
                onChange(
                  { checkpoint_notes_value: toStored(storedMode ?? unit, v) },
                  v === '' ? 'Notes point reset to the built-in one' : `Notes asked for at ${v}${UNIT_WORD[storedMode ?? unit] === '%' ? '%' : 'K tokens'}`,
                )
              }
            />
          }
        />
        <SettingsRow
          label="Continue automatically"
          inactive={settings.checkpoint_mode === 'off'}
          description="After a cut-over, start the new conversation's first turn without waiting. Off: you get a Continue button, never a message you have to invent."
          control={
            <Switch
              aria-label="Continue automatically"
              checked={settings.checkpoint_auto_continue}
              onCheckedChange={(v) => onChange({ checkpoint_auto_continue: v }, v ? 'New conversations continue on their own' : 'New conversations wait for Continue')}
            />
          }
        />
        <SettingsRow
          label="Checkpoint runner"
          inactive={settings.checkpoint_mode === 'off'}
          description="Who writes checkpoints. A cheap model is usually right; the work itself runs elsewhere."
          control={
            <MenuSelect
              label="Checkpoint runner"
              value={settings.checkpoint_runner_id ?? ''}
              onChange={(v) => onChange({ checkpoint_runner_id: v || null }, v ? `Checkpoints written by ${runnerOptions.find((o) => o.value === v)?.label ?? 'that runner'}` : 'Checkpointing has no runner')}
              options={runnerOptions}
            />
          }
        />
        <SettingsRow
          label="Checkpoint model"
          inactive={settings.checkpoint_mode === 'off' || !settings.checkpoint_runner_id}
          description="Only for writing checkpoints, in place of the runner's own model."
          control={
            <MenuSelect
              label="Checkpoint model"
              value={settings.checkpoint_model ?? ''}
              disabled={!settings.checkpoint_runner_id}
              onChange={(v) => onChange({ checkpoint_model: v || null }, v ? `Checkpoints use ${modelOptions.find((o) => o.value === v)?.label ?? v}` : 'Checkpoints use the runner’s model')}
              options={modelOptions}
            />
          }
        />
      </SettingsGroup>

      <SettingsGroup title="Project">
        <SettingsRow
          label="Name"
          htmlFor="s-name"
          description="How this project is named everywhere in AgentWeave."
          control={<CommittedInput id="s-name" value={settings.name} validate={(d) => (d.trim() ? null : 'A project needs a name.')} onCommit={(v) => onChange({ name: v }, `Project renamed to ${v}`)} />}
        />
        <SettingsRow
          label="Folder"
          description={
            <span className="aw-folder-path" title={folder}>
              {folder || 'No folder bound'}
            </span>
          }
          control={
            folderAvailable ? (
              <span className="flex items-center gap-2">
                <span className="aw-state-chip" data-tone="good">
                  <span className="aw-state-dot" />
                  Available
                </span>
                <Button variant="outline" size="sm" onClick={() => void navigator.clipboard?.writeText(folder)}>
                  <Icon name="content_copy" size={13} /> Copy path
                </Button>
              </span>
            ) : (
              <span className="aw-state-chip" data-tone="bad">
                <span className="aw-state-dot" />
                Missing
              </span>
            )
          }
        >
          {!folderAvailable && onRelocate ? (
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                if (newPath.trim()) onRelocate(newPath.trim())
              }}
            >
              <Input aria-label="New directory path" value={newPath} placeholder="Where the folder is now" onChange={(e) => setNewPath(e.target.value)} style={{ maxWidth: 420 }} />
              <Button type="submit" variant="outline" size="sm" disabled={!newPath.trim() || relocating}>
                Locate project
              </Button>
            </form>
          ) : null}
        </SettingsRow>
      </SettingsGroup>

      <section className="aw-danger" aria-label="Danger zone">
        <div className="min-w-0">
          <h2 className="aw-danger-title">Delete project</h2>
          <p className="aw-danger-desc">Removes {settings.name} from AgentWeave: its agents, conversations, tasks and history. The folder on disk is not touched.</p>
        </div>
        <Button variant="destructive" size="sm" onClick={onDeleteProject}>
          Delete project…
        </Button>
      </section>
    </SettingsPage>
  )
}

function CheckDialog({
  title,
  initial,
  submitLabel,
  trigger,
  onSubmit,
}: {
  title: string
  initial?: ProjectCheck
  submitLabel: string
  trigger: React.ReactNode
  onSubmit: (check: ProjectCheck) => void
}) {
  const [open, setOpen] = React.useState(false)
  const [name, setName] = React.useState(initial?.name ?? '')
  const [command, setCommand] = React.useState(initial?.command ?? '')
  const [timeout, setTimeoutValue] = React.useState(String(initial?.timeout_seconds ?? 900))
  const timeoutError = wholeNumber(10, 3600, 'seconds')(timeout)
  const ready = name.trim() && command.trim() && !timeoutError
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) {
          setName(initial?.name ?? '')
          setCommand(initial?.command ?? '')
          setTimeoutValue(String(initial?.timeout_seconds ?? 900))
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent
        title={title}
        description="It runs in a checkout of the main branch with the task's work merged in. A non-zero exit refuses the approval."
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!ready}
              onClick={() => {
                onSubmit({ name: name.trim(), command: command.trim(), timeout_seconds: Number(timeout) })
                setOpen(false)
              }}
            >
              {submitLabel}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-1">
          <Field label="Name" htmlFor="c-name" hint="Shown on the approval card when it fails.">
            <Input id="c-name" autoFocus value={name} placeholder="Unit tests" onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Command" htmlFor="c-cmd" hint="Run from the repository root.">
            <Input id="c-cmd" className="font-mono" value={command} placeholder="npm test" onChange={(e) => setCommand(e.target.value)} />
          </Field>
          <Field label="Time limit" htmlFor="c-timeout" error={timeout && timeoutError ? timeoutError : undefined} hint="Seconds before the check is stopped and counted as failed.">
            <Input id="c-timeout" inputMode="numeric" className="tabular" style={{ width: 96 }} value={timeout} aria-invalid={Boolean(timeoutError)} onChange={(e) => setTimeoutValue(e.target.value)} />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  )
}
