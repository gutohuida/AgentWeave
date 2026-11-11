import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTrigger } from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { MenuSelect, type SelectOption } from '@/components/ui/menu'
import { Field, SettingsGroup, SettingsPage, SettingsRow } from '@/components/ui/settings'
import { Switch } from '@/components/ui/switch'
import type { CheckPhase, GeneratedFiles, CheckUsualDuration, CheckUsualDurations, ProjectCheck, ProjectSettings } from '@/api/projects'
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

/** The longest time limit a fast check may have (`project_checks.FAST_CHECK_MAX_SECONDS`). */
const FAST_CHECK_MAX_SECONDS = 120

/** When a check runs (`checks-know-their-phase-and-give-way-to-the-user`, FR-1). */
const PHASE_OPTIONS: ReadonlyArray<SelectOption<CheckPhase>> = [
  { value: 'both', label: 'Before review and at landing', detail: 'Checks the task before anyone reviews it, and again on the merged result before it lands.' },
  { value: 'review', label: 'Before review only', detail: 'Not run again when approved work lands.' },
  { value: 'landing', label: 'At landing only', detail: 'For a slow suite: review and approval do not wait for it, and it checks the merged result before it lands.' },
]

/** What the Hub answers to a fast check marked landing-only (FR-4), said before the save. */
const FAST_NOT_LANDING_ONLY =
  "A fast check gates an agent's completion before review, so it cannot be landing-only."

/** Where the Hub puts the ids of the tests to re-run (`project_checks.TESTS_PLACEHOLDER`). */
const TESTS_PLACEHOLDER = '{tests}'

/** Where the Hub puts the path of the file listing what a task changed (`project_checks.CHANGED_FILES_PLACEHOLDER`). */
const CHANGED_FILES_PLACEHOLDER = '{changed_files}'

/** A working report path and re-run command per runner (`checks-report-which-tests-failed-in-any-language`,
 *  FR-8). Each re-run goes through a small script in the project that turns the ids back into its
 *  runner's selectors: the Hub keeps no knowledge of any runner. */
const REPORT_EXAMPLES: ReadonlyArray<{ runner: string; command: string; report: string; rerun: string; wrapper: string }> = [
  {
    runner: 'pytest',
    command: 'pytest --junitxml=report.xml -o junit_family=xunit1',
    report: 'report.xml',
    rerun: 'python rerun_pytest.py {tests}',
    wrapper: 'turns tests.test_api.TestLogin::test_ok into tests/test_api.py::TestLogin::test_ok and runs pytest with the same --junitxml.',
  },
  {
    runner: 'Vitest or Jest',
    command: 'npx vitest run --reporter=junit --outputFile=report.xml',
    report: 'report.xml',
    rerun: 'node rerun-vitest.mjs {tests}',
    wrapper: 'runs each id’s file (its classname) with -t matching its name; for Jest, jest-junit and --testNamePattern.',
  },
  {
    runner: 'Node’s test runner',
    command: 'node --test --test-reporter=junit --test-reporter-destination=report.xml',
    report: 'report.xml',
    rerun: 'node rerun.mjs {tests}',
    wrapper: 'runs node --test with the same reporter and a --test-name-pattern for each name.',
  },
  {
    runner: 'Go (gotestsum)',
    command: 'gotestsum --junitfile report.xml -- ./...',
    report: 'report.xml',
    rerun: 'sh rerun-go.sh {tests}',
    wrapper: "runs gotestsum --junitfile report.xml -- -run '^(TestA|TestB)$' on each id’s package (its classname).",
  },
  {
    runner: 'cargo-nextest',
    command: 'cargo nextest run --profile ci',
    report: 'target/nextest/ci/junit.xml',
    rerun: 'sh rerun-nextest.sh {tests}',
    wrapper: `drops each id’s binary (its classname) and runs cargo nextest run --profile ci -E 'test(=name)'; the ci profile sets [profile.ci.junit] path = "junit.xml".`,
  },
]

/** Why a re-run command cannot be saved, said before the Hub refuses it (FR-1). */
function rerunCommandError(value: string): string | undefined {
  if (!value.trim() || value.includes(TESTS_PLACEHOLDER)) return undefined
  return `A re-run command needs ${TESTS_PLACEHOLDER}, where the Hub puts the ids of the tests to re-run.`
}

function changeCommandError(value: string): string | undefined {
  if (!value.trim() || value.includes(CHANGED_FILES_PLACEHOLDER)) return undefined
  return `A command for a change needs ${CHANGED_FILES_PLACEHOLDER}, where the Hub puts the path of the file listing the files the task changed.`
}

/** Seconds as an operator reads a check's duration: `42s`, `4m 12s`. */
function formatSeconds(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds * 10) / 10}s`
  const whole = Math.round(seconds)
  const rest = whole % 60
  return rest ? `${Math.floor(whole / 60)}m ${rest}s` : `${whole / 60}m`
}

/** How long a check usually takes, beside its time limit (FR-11). Nothing while unknown. */
function UsualDuration({ usual, index }: { usual: CheckUsualDuration | null | undefined; index: number }) {
  if (usual === undefined) return null
  return (
    <span
      data-testid={`project-check-usual-${index}`}
      title={usual ? `The median and longest of its last ${usual.passes} passing runs in this project` : undefined}
    >
      {' · '}
      {usual ? `usually ${formatSeconds(usual.median_seconds)}, at most ${formatSeconds(usual.longest_seconds)}` : 'no passing runs yet'}
    </span>
  )
}

const CHECKPOINT_MODE_LABEL: Record<ProjectSettings['checkpoint_mode'], string> = {
  off: 'Off',
  offered: 'Offer me one',
  automatic: 'Automatic',
}


/** Everything the project settings pages read. Each page takes what it needs from it, so a
 *  container can hand the same object to whichever section is open. */
export interface GeneralSettingsProps {
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
  /** How long each check usually takes, by name. Absent while unknown. */
  usualDurations?: CheckUsualDurations
  /** Why they could not be read, if they could not. */
  usualDurationsUnreadable?: string | null
  /** The checkpoint model's window, so a threshold reads in both units. */
  contextWindow?: number | null
  /** Where an agent's checkpoint fires below the project's threshold (D10). */
  ceilingNotes?: string[]
  /** The project's agents could not be read, so those notes cannot be computed. */
  agentsUnreadable?: boolean
  /** What the last save answered (warnings, a refusal), shown under the page heading. */
  notices?: React.ReactNode
  relocating?: boolean
  /** 'Make this a git repository', shown under the folder when it is not one. The container
   *  owns its reads and writes. */
  repositoryOffer?: React.ReactNode
  onChange: (patch: Partial<ProjectSettings>, said: string) => void
  /** Rebind a project whose folder has moved. */
  onRelocate?: (path: string) => void
  /** Opens the type-to-confirm delete dialog the container owns. */
  onDeleteProject: () => void
}

type RowsProps = Pick<GeneralSettingsProps, 'settings' | 'onChange'>

function CollaborationRows({ settings, onChange }: RowsProps) {
  return (
    <>
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
    </>
  )
}

/** How many agents the project may hold: a budget, so it sits in Budgets beside the token limit. */
export function AgentBudgetRow({ settings, onChange }: RowsProps) {
  return (
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
  )
}

function PermissionRows({ settings, permissionModes, onChange }: RowsProps & Pick<GeneralSettingsProps, 'permissionModes'>) {
  return (
    <>
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
    </>
  )
}

function MainBranchRow({ settings, mainBranch, onChange }: RowsProps & Pick<GeneralSettingsProps, 'mainBranch'>) {
  const isRepository = mainBranch ? mainBranch.is_repository : true
  return (
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
  )
}

function ChecksRows({
  settings,
  usualDurations,
  usualDurationsUnreadable,
  onChange,
}: RowsProps & Pick<GeneralSettingsProps, 'usualDurations' | 'usualDurationsUnreadable'>) {
  const checks = settings.checks ?? []
  const setChecks = (next: ProjectCheck[], said: string) => onChange({ checks: next.length ? next : null }, said)
  const moveCheck = (index: number, by: number) => {
    const next = [...checks]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item)
    setChecks(next, `Moved the check ${item.name} ${by < 0 ? 'up' : 'down'}`)
  }
  return (
    <>
        <SettingsRow
          label="Checks"
          description="Commands run on the main branch plus a task's work before approval merges it, in this order. Approval is refused until they pass."
          stacked
          control={
            <div className="aw-checks" data-testid="project-checks">
              {checks.length === 0 ? <p className="aw-checks-empty">No checks: approval merges without running anything.</p> : null}
              {checks.length > 0 && usualDurationsUnreadable ? (
                <p className="aw-checks-empty" data-testid="project-checks-usual-unreadable">
                  How long each check usually takes could not be read. {usualDurationsUnreadable}
                </p>
              ) : null}
              {checks.map((check, i) => (
                <div key={`${check.name}-${i}`} className="aw-check-row aw-reveal-host" data-testid={`project-check-${i}`}>
                  <Icon name="terminal" size={13} className="aw-check-icon" />
                  <div className="aw-check-body">
                  <span className="aw-check-name">{check.name}</span>
                  <code className="aw-check-command" title={check.command}>{check.command}</code>
                  <span className="aw-check-timeout" title={check.paths?.length ? `Runs only when the work changes ${check.paths.join(', ')}` : undefined}>
                    {check.paths?.length ? (
                      <span data-testid={`project-check-paths-${i}`}>
                        {check.paths[0]}
                        {check.paths.length > 1 ? ` +${check.paths.length - 1}` : ''} ·{' '}
                      </span>
                    ) : null}
                    {check.fast ? <span data-testid={`project-check-fast-${i}`}>fast · </span> : null}
                    {check.change_command ? (
                      <span data-testid={`project-check-change-${i}`} title={`Before review, runs ${check.change_command}`}>
                        sized to the change ·{' '}
                      </span>
                    ) : null}
                    {check.report_path ? (
                      <span data-testid={`project-check-report-${i}`} title={check.rerun_command ? `Re-runs failing tests with ${check.rerun_command}` : 'Re-runs failing tests by running the whole check'}>
                        report {check.report_path}
                        {check.rerun_command ? ', re-runs by test' : ''}
                        {check.rerun_command ? `, disturbed at ${check.disturbed_threshold ?? 3}` : ''} ·{' '}
                      </span>
                    ) : null}
                    {check.phase === 'review' || check.phase === 'landing' ? (
                      <span data-testid={`project-check-phase-${i}`}>{check.phase === 'review' ? 'before review only' : 'at landing only'} · </span>
                    ) : null}
                    {check.timeout_seconds}s limit
                    <UsualDuration usual={usualDurations ? (usualDurations[check.name] ?? null) : undefined} index={i} />
                  </span>
                  </div>
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
        <SettingsRow
          label="Checks give way to me"
          description="Every process a check starts runs below normal priority, so your own work on this machine comes first. Checks marked fast keep normal priority; only the other checks give way. On an idle machine the checks still get all of it."
          changed={(settings.checks_give_way ?? false) !== PROJECT_DEFAULTS.checks_give_way}
          onReset={() => onChange({ checks_give_way: false }, 'Checks run at normal priority again')}
          control={
            <Switch
              aria-label="Checks give way to me"
              data-testid="project-checks-give-way"
              checked={settings.checks_give_way ?? false}
              onCheckedChange={(v) =>
                onChange({ checks_give_way: v }, v ? 'Checks give way to your own work' : 'Checks run at normal priority')
              }
            />
          }
        />
    </>
  )
}

function GeneratedFilesRow({ settings, onChange }: RowsProps) {
  return (
        <SettingsRow
          label="Generated files"
          description="Files a command rebuilds from other files (a lockfile, a bundle). When work lands and only these files conflict, the Hub rebuilds them instead of sending the task back. Paths are comma-separated globs; the timeout is 1 to 3600 seconds. Empty the paths to turn it off."
          changed={Boolean(settings.generated_files)}
          onReset={() => onChange({ generated_files: null }, 'Generated files cleared')}
          control={<GeneratedFilesEditor value={settings.generated_files ?? null} onSave={(v) => onChange({ generated_files: v }, v ? 'Generated files saved' : 'Generated files cleared')} />}
        />
  )
}

function PullRequestRows({ settings, onChange }: RowsProps) {
  return (
    <>
        <SettingsRow
          label="Land builds as pull requests"
          description="A build may put its approved work on one GitHub pull request instead of merging into the main branch. Pushing publishes the work, so this is off until you turn it on. It needs a GitHub remote and a logged-in GitHub CLI."
          changed={(settings.pr_landing ?? false) !== PROJECT_DEFAULTS.pr_landing}
          onReset={() => onChange({ pr_landing: false }, 'Builds no longer land as pull requests')}
          control={
            <Switch
              aria-label="Land builds as pull requests"
              data-testid="project-pr-landing"
              checked={settings.pr_landing ?? false}
              onCheckedChange={(v) =>
                onChange({ pr_landing: v }, v ? 'Builds may land as pull requests' : 'Builds no longer land as pull requests')
              }
            />
          }
        />
        <SettingsRow
          label="One commit per build"
          description="With pull request landing on, the build branch carries a single commit holding the whole build instead of one commit per task. A push replaces it only if nobody else has pushed to the branch."
          changed={(settings.pr_single_commit ?? false) !== PROJECT_DEFAULTS.pr_single_commit}
          onReset={() => onChange({ pr_single_commit: false }, 'One commit per task again')}
          control={
            <Switch
              aria-label="One commit per build"
              data-testid="project-pr-single-commit"
              checked={settings.pr_single_commit ?? false}
              disabled={!settings.pr_landing}
              onCheckedChange={(v) =>
                onChange({ pr_single_commit: v }, v ? 'The build branch carries one commit' : 'One commit per task')
              }
            />
          }
        />
        <SettingsRow
          label="The PR's CI is the full check"
          description="A pull request build pushes approved work without running the landing checks here; the checks that count on GitHub decide whether the PR is ready or the latest task goes back. It needs pull request landing on, and turns off with it. It also needs required checks on GitHub or a list of check names below."
          changed={(settings.pr_ci_full_check ?? false) !== PROJECT_DEFAULTS.pr_ci_full_check}
          onReset={() => onChange({ pr_ci_full_check: false }, 'Landing checks run here again')}
          control={
            <Switch
              aria-label="The PR's CI is the full check"
              data-testid="project-pr-ci-full-check"
              checked={settings.pr_ci_full_check ?? false}
              onCheckedChange={(v) =>
                onChange({ pr_ci_full_check: v }, v ? 'The PR’s CI is the full check' : 'Landing checks run here again')
              }
            />
          }
        />
        <SettingsRow
          label="CI check names"
          htmlFor="s-pr-ci-names"
          description="Comma-separated. Used only where GitHub marks no check required on the base branch."
          changed={(settings.pr_ci_check_names ?? []).length > 0}
          onReset={() => onChange({ pr_ci_check_names: [] }, 'CI check names cleared')}
          control={
            <CommittedInput
              id="s-pr-ci-names"
              ariaLabel="CI check names"
              value={(settings.pr_ci_check_names ?? []).join(', ')}
              onCommit={(v) =>
                onChange(
                  { pr_ci_check_names: v.split(',').map((n) => n.trim()).filter(Boolean) },
                  'CI check names saved',
                )
              }
            />
          }
        />
        <SettingsRow
          label="CI asked every"
          htmlFor="s-pr-ci-interval"
          description="While a counted check is pending, the Hub asks GitHub this often. Whole minutes, 1 to 60."
          changed={(settings.pr_ci_interval_minutes ?? 2) !== PROJECT_DEFAULTS.pr_ci_interval_minutes}
          onReset={() => onChange({ pr_ci_interval_minutes: PROJECT_DEFAULTS.pr_ci_interval_minutes }, 'CI interval reset to 2 minutes')}
          control={
            <CommittedInput
              id="s-pr-ci-interval"
              ariaLabel="CI interval"
              numeric
              width={72}
              suffix="min"
              value={String(settings.pr_ci_interval_minutes ?? 2)}
              validate={(d) => (/^\d+$/.test(d.trim()) ? null : 'A whole number of minutes.')}
              onCommit={(v) => onChange({ pr_ci_interval_minutes: Number(v) }, `CI asked every ${v} minutes`)}
            />
          }
        />
        <SettingsRow
          label="CI asking stops after"
          htmlFor="s-pr-ci-cutoff"
          description="After a push, asking on the interval stops this long with a counted check still unconcluded, and the build shows that CI has not finished. Whole minutes, 5 to 1440, and not shorter than the interval."
          changed={(settings.pr_ci_cutoff_minutes ?? 60) !== PROJECT_DEFAULTS.pr_ci_cutoff_minutes}
          onReset={() => onChange({ pr_ci_cutoff_minutes: PROJECT_DEFAULTS.pr_ci_cutoff_minutes }, 'CI cutoff reset to 60 minutes')}
          control={
            <CommittedInput
              id="s-pr-ci-cutoff"
              ariaLabel="CI cutoff"
              numeric
              width={72}
              suffix="min"
              value={String(settings.pr_ci_cutoff_minutes ?? 60)}
              validate={(d) => (/^\d+$/.test(d.trim()) ? null : 'A whole number of minutes.')}
              onCommit={(v) => onChange({ pr_ci_cutoff_minutes: Number(v) }, `CI asking stops after ${v} minutes`)}
            />
          }
        />
    </>
  )
}

function CheckpointRows({
  settings,
  runnerOptions,
  modelOptions,
  contextWindow,
  ceilingNotes = [],
  agentsUnreadable,
  onChange,
}: RowsProps & Pick<GeneralSettingsProps, 'runnerOptions' | 'modelOptions' | 'contextWindow' | 'ceilingNotes' | 'agentsUnreadable'>) {
  const [unit, setUnit] = React.useState<ThresholdMode>(settings.checkpoint_threshold_mode ?? 'percent')
  React.useEffect(() => {
    if (settings.checkpoint_threshold_mode) setUnit(settings.checkpoint_threshold_mode)
  }, [settings.checkpoint_threshold_mode])
  const stored = settings.checkpoint_threshold_value
  const storedMode = settings.checkpoint_threshold_mode
  const reading = describeThreshold(storedMode, stored, contextWindow ?? null)
  const clearThreshold = (said: string) =>
    onChange({ checkpoint_threshold_value: null, checkpoint_threshold_mode: null, checkpoint_notes_value: null }, said)
  return (
    <>
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
    </>
  )
}

function ProjectRows({
  settings,
  folder,
  folderAvailable,
  mainBranch,
  relocating,
  repositoryOffer,
  onChange,
  onRelocate,
}: RowsProps & Pick<GeneralSettingsProps, 'folder' | 'folderAvailable' | 'mainBranch' | 'relocating' | 'repositoryOffer' | 'onRelocate'>) {
  const [newPath, setNewPath] = React.useState('')
  const isRepository = mainBranch ? mainBranch.is_repository : true
  return (
    <>
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
              id="locate-project"
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
          {folderAvailable && !isRepository ? repositoryOffer : null}
        </SettingsRow>
    </>
  )
}

function DangerZone({ settings, onDeleteProject }: Pick<GeneralSettingsProps, 'settings' | 'onDeleteProject'>) {
  return (
      <section className="aw-danger" aria-label="Danger zone">
        <div className="min-w-0">
          <h2 className="aw-danger-title">Delete project</h2>
          <p className="aw-danger-desc">Removes {settings.name} from AgentWeave: its agents, conversations, tasks and history. The folder on disk is not touched.</p>
        </div>
        <Button variant="destructive" size="sm" onClick={onDeleteProject}>
          Delete project…
        </Button>
      </section>
  )
}

/* The sections General splits into (`settings-in-the-app-s-style-where-you-expect-them`). Each is
 * a page of its own in Project settings; together they hold every row General held, except the
 * agent budget, which moves to Budgets. */

export function ProjectBasicsSettings(props: GeneralSettingsProps) {
  return (
    <SettingsPage icon="folder" title="Project" description="What this project is called and where it lives on this machine.">
      {props.notices}
      <SettingsGroup title="Name and folder">
        <ProjectRows {...props} />
      </SettingsGroup>
      <DangerZone {...props} />
    </SettingsPage>
  )
}

export function CollaborationSettings(props: GeneralSettingsProps) {
  return (
    <SettingsPage icon="forum" title="Collaboration" description="How far agents may pass work between themselves before you are asked.">
      {props.notices}
      <SettingsGroup title="Agents working together">
        <CollaborationRows {...props} />
      </SettingsGroup>
    </SettingsPage>
  )
}

export function PermissionsSettings(props: GeneralSettingsProps) {
  return (
    <SettingsPage icon="lock" title="Permissions" description="What agents may do when nobody said otherwise. An agent's own settings win over these.">
      {props.notices}
      <SettingsGroup title="Defaults for every agent">
        <PermissionRows {...props} />
      </SettingsGroup>
    </SettingsPage>
  )
}

export function ChecksSettings(props: GeneralSettingsProps) {
  return (
    <SettingsPage icon="verified_user" title="Checks" description="What must pass before approved work lands.">
      {props.notices}
      <SettingsGroup title="Before work lands">
        <ChecksRows {...props} />
      </SettingsGroup>
      <SettingsGroup title="When work conflicts">
        <GeneratedFilesRow {...props} />
      </SettingsGroup>
    </SettingsPage>
  )
}

export function LandingSettings(props: GeneralSettingsProps) {
  return (
    <SettingsPage icon="git_merge" title="Landing" description="Where approved work goes: merged into the main branch, or onto a pull request.">
      {props.notices}
      <SettingsGroup title="Merging">
        <MainBranchRow {...props} />
      </SettingsGroup>
      <SettingsGroup title="Pull requests" description="Off until you turn it on: pushing publishes the work.">
        <PullRequestRows {...props} />
      </SettingsGroup>
    </SettingsPage>
  )
}

export function CheckpointsSettings(props: GeneralSettingsProps) {
  return (
    <SettingsPage icon="book_marked" title="Checkpoints" description="When a conversation's context fills, the Hub writes a checkpoint so a fresh conversation can continue the work.">
      {props.notices}
      <SettingsGroup title="When and who">
        <CheckpointRows {...props} />
      </SettingsGroup>
    </SettingsPage>
  )
}


function GeneratedFilesEditor({
  value,
  onSave,
}: {
  value: GeneratedFiles | null
  onSave: (value: GeneratedFiles | null) => void
}) {
  const stored = {
    paths: (value?.paths ?? []).join(', '),
    command: value?.command ?? '',
    timeout: String(value?.timeout_seconds ?? 600),
  }
  const [paths, setPaths] = React.useState(stored.paths)
  const [command, setCommand] = React.useState(stored.command)
  const [timeout, setTimeoutValue] = React.useState(stored.timeout)
  React.useEffect(() => {
    setPaths(stored.paths)
    setCommand(stored.command)
    setTimeoutValue(stored.timeout)
  }, [stored.paths, stored.command, stored.timeout])
  const list = paths.split(',').map((p) => p.trim()).filter(Boolean)
  const seconds = Number(timeout)
  const error = !list.length
    ? null
    : !command.trim()
      ? 'A rebuild command is needed.'
      : !/^\d+$/.test(timeout.trim()) || seconds < 1 || seconds > 3600
        ? 'The timeout is a whole number from 1 to 3600.'
        : null
  const dirty = paths !== stored.paths || command !== stored.command || timeout !== stored.timeout
  // Applies when focus leaves the three fields together, once they make a whole value: saved on
  // change, like every other row, without saving a half-typed command.
  const commit = (event: React.FocusEvent<HTMLDivElement>) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
    if (!dirty || error) return
    onSave(list.length ? { paths: list, command: command.trim(), timeout_seconds: seconds } : null)
  }
  return (
    <div className="flex flex-col gap-2" data-testid="generated-files-editor" onBlur={commit}>
      <Textarea rows={1} aria-label="Generated file paths" className="font-mono aw-textarea-grow" value={paths} placeholder="package-lock.json, dist/**" onChange={(e) => setPaths(e.target.value)} />
      <Textarea rows={1} aria-label="Generated files command" className="font-mono aw-textarea-grow" value={command} placeholder="npm install --package-lock-only" aria-invalid={Boolean(error && !command.trim())} onChange={(e) => setCommand(e.target.value)} />
      <span className="aw-committed">
        <Input aria-label="Generated files timeout" inputMode="numeric" className="tabular text-right" style={{ width: 72 }} value={timeout} onChange={(e) => setTimeoutValue(e.target.value)} />
        <span className="aw-committed-suffix">seconds</span>
      </span>
      {error ? <span role="alert" className="aw-committed-error">{error}</span> : null}
    </div>
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
  const [paths, setPaths] = React.useState((initial?.paths ?? []).join('\n'))
  const [fast, setFast] = React.useState(Boolean(initial?.fast))
  const [phase, setPhase] = React.useState<CheckPhase>(initial?.phase ?? 'both')
  const [reportPath, setReportPath] = React.useState(initial?.report_path ?? '')
  const [rerun, setRerun] = React.useState(initial?.rerun_command ?? '')
  const [changeCommand, setChangeCommand] = React.useState(initial?.change_command ?? '')
  const [threshold, setThreshold] = React.useState(initial?.disturbed_threshold ? String(initial.disturbed_threshold) : '')
  const thresholdError = threshold.trim() ? wholeNumber(2, 10000, 'tests')(threshold) : undefined
  const rerunError = rerunCommandError(rerun)
  const changeError = changeCommandError(changeCommand)
  const phaseError = fast && phase === 'landing' ? FAST_NOT_LANDING_ONLY : undefined
  // A completion waits for the fast checks, so none may run longer than that wait (FR-1); the Hub
  // refuses it too, and this says so before the save.
  const timeoutError = wholeNumber(10, fast ? FAST_CHECK_MAX_SECONDS : 3600, 'seconds')(timeout)
  const patterns = [...new Set(paths.split(/[\n,]/).map((p) => p.trim()).filter(Boolean))]
  const ready = name.trim() && command.trim() && !timeoutError && !phaseError && !rerunError && !changeError && !thresholdError
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) {
          setName(initial?.name ?? '')
          setCommand(initial?.command ?? '')
          setTimeoutValue(String(initial?.timeout_seconds ?? 900))
          setPaths((initial?.paths ?? []).join('\n'))
          setFast(Boolean(initial?.fast))
          setPhase(initial?.phase ?? 'both')
          setReportPath(initial?.report_path ?? '')
          setRerun(initial?.rerun_command ?? '')
          setChangeCommand(initial?.change_command ?? '')
          setThreshold(initial?.disturbed_threshold ? String(initial.disturbed_threshold) : '')
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
                onSubmit({
                  name: name.trim(),
                  command: command.trim(),
                  timeout_seconds: Number(timeout),
                  ...(patterns.length ? { paths: patterns } : {}),
                  ...(fast ? { fast: true } : {}),
                  // Both is the default, and a check saved without a phase reads as both.
                  ...(phase !== 'both' ? { phase } : {}),
                  // Neither is sent when empty: a check without a report reads as having neither.
                  ...(reportPath.trim() ? { report_path: reportPath.trim() } : {}),
                  ...(rerun.trim() ? { rerun_command: rerun.trim() } : {}),
                  // Only a check with a report and a rerun command has one; empty reads as 3.
                  ...(rerun.trim() && reportPath.trim() && threshold.trim() ? { disturbed_threshold: Number(threshold) } : {}),
                  ...(changeCommand.trim() ? { change_command: changeCommand.trim() } : {}),
                })
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
          <Field
            label="Paths"
            htmlFor="c-paths"
            hint="Optional, one per line, like hub/** or constraints-dev.txt. When the work changes none of them, the check is skipped and counts as passed. Leave empty to run it for every task."
          >
            <Textarea
              id="c-paths"
              rows={3}
              className="font-mono"
              style={{ resize: 'vertical', fontSize: 12 }}
              value={paths}
              placeholder="hub/**"
              onChange={(e) => setPaths(e.target.value)}
            />
          </Field>
          <Field
            label="Fast"
            htmlFor="c-fast"
            hint={`Run when an agent completes its task, before anyone reviews it: a failure refuses the completion with the check's output, so the agent fixes it in the same turn. For quick checks like lint and format, at most ${FAST_CHECK_MAX_SECONDS} seconds.`}
          >
            <Switch id="c-fast" aria-label="Fast" checked={fast} onCheckedChange={setFast} />
          </Field>
          <Field label="Runs" htmlFor="c-phase" error={phaseError} hint="Before review, at landing, or both.">
            <MenuSelect id="c-phase" label="Runs" testId="check-phase" value={phase} onChange={setPhase} options={PHASE_OPTIONS} />
          </Field>
          <Field
            label="Report path"
            htmlFor="c-report"
            hint="Optional. The JUnit XML file the command writes, relative to the directory the check runs in (the repository root), read after every run to name the tests that failed."
          >
            <Input id="c-report" className="font-mono" value={reportPath} placeholder="report.xml" onChange={(e) => setReportPath(e.target.value)} />
          </Field>
          <Field
            label="Re-run command"
            htmlFor="c-rerun"
            error={rerunError}
            hint={`Optional. Runs only the named tests, writing the same report: ${TESTS_PLACEHOLDER} is replaced by their ids, each a separate argument.`}
          >
            <Input id="c-rerun" className="font-mono" value={rerun} placeholder="python rerun_pytest.py {tests}" aria-invalid={Boolean(rerunError)} onChange={(e) => setRerun(e.target.value)} />
          </Field>
          {reportPath.trim() && rerun.trim() ? (
            <Field
              label="Disturbed threshold"
              htmlFor="c-disturbed"
              error={thresholdError}
              hint="Optional, at least 2, 3 when empty. When this many tests fail in one run and every one passes when re-run, the run is recorded as disturbed: no test is listed as flaky and no fix task is filed."
            >
              <Input id="c-disturbed" inputMode="numeric" className="tabular" style={{ width: 96 }} value={threshold} placeholder="3" aria-invalid={Boolean(thresholdError)} onChange={(e) => setThreshold(e.target.value)} />
            </Field>
          ) : null}
          <Field
            label="Command for a change"
            htmlFor="c-change"
            error={changeError}
            hint={`Optional. Runs in a task's check before review, in place of the command, where the files the task changed are known: ${CHANGED_FILES_PLACEHOLDER} is replaced by the path of a file listing them, one per line. Landings and the main branch still run the whole command.`}
          >
            <Input id="c-change" className="font-mono" value={changeCommand} placeholder="python run_related_tests.py {changed_files}" aria-invalid={Boolean(changeError)} onChange={(e) => setChangeCommand(e.target.value)} />
          </Field>
          <div className="aw-field-note flex flex-col gap-1" data-tone="hint" data-testid="check-report-explained">
            <p data-testid="check-report-id-form">
              A test&rsquo;s id is its report&rsquo;s classname and name joined by <code>::</code>, like{' '}
              <code>tests.test_api.TestLogin::test_ok</code>. The re-run command receives the ids as separate arguments, so a small script in the project
              turns them into its runner&rsquo;s selectors.
            </p>
            <p data-testid="check-report-whole-note">
              A check without a report is judged as a whole: a failure names no test, and nothing is re-run or narrowed test by test.
            </p>
            <ul className="flex flex-col gap-1" data-testid="check-report-examples">
              {REPORT_EXAMPLES.map((example) => (
                <li key={example.runner} data-testid="check-report-example">
                  <strong>{example.runner}</strong>: command <code>{example.command}</code>, report path <code>{example.report}</code>, re-run{' '}
                  <code>{example.rerun}</code>, which {example.wrapper}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
