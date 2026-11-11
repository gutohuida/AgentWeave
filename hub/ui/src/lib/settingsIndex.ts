import {
  agentSettingsDestination,
  appSettingsDestination,
  environmentDestination,
  type AgentSettingsSection,
  type AppSettingsSection,
  type EnvironmentSection,
  type WorkspaceDestination,
} from '@/lib/navigation'

/** Every settings row the operator can search for, and the one rule that matches a search to them.
 *
 *  The index sits beside the screens, so it can drift; `scripts/checks/settings_search_check.py
 *  --findable` renders every row of every section and searches its own label, and fails naming any
 *  row this list does not return. A row's `label` here is the text the row shows. */

export type SettingScope = 'app' | 'project' | 'agent'

export interface SettingEntry {
  scope: SettingScope
  /** The section id the scope's screen takes (`AppSettingsSection`, `EnvironmentSection` or `AgentSettingsSection`). */
  section: string
  /** The section as the operator reads it. */
  sectionLabel: string
  /** The row's label, as the row shows it. */
  label: string
  /** What the row does, in words a search can match. */
  description: string
}

const APP: Record<AppSettingsSection, string> = {
  notifications: 'Sound and notifications',
  appearance: 'Appearance',
  connection: 'Hub connection',
}

const PROJECT: Record<EnvironmentSection, string> = {
  general: 'Project',
  collaboration: 'Collaboration',
  permissions: 'Permissions',
  budgets: 'Budgets',
  instructions: 'Instructions',
  charters: 'Charters',
  checkpoints: 'Checkpoints',
  manager: 'Manager',
  checks: 'Checks',
  landing: 'Landing',
  worktrees: 'Worktrees',
  'spec-steps': 'Spec steps',
  traces: 'Traces',
  diagnostics: 'Diagnostics',
}

const AGENT: Record<AgentSettingsSection, string> = {
  agent: 'Agent',
  running: 'Running',
  permissions: 'Permissions',
  checkpoints: 'Checkpoints',
  workspace: 'Workspace',
}

const app = (section: AppSettingsSection, label: string, description: string): SettingEntry => ({
  scope: 'app',
  section,
  sectionLabel: APP[section],
  label,
  description,
})
const project = (section: EnvironmentSection, label: string, description: string): SettingEntry => ({
  scope: 'project',
  section,
  sectionLabel: PROJECT[section],
  label,
  description,
})
const agent = (section: AgentSettingsSection, label: string, description: string): SettingEntry => ({
  scope: 'agent',
  section,
  sectionLabel: AGENT[section],
  label,
  description,
})

/** In listing order: App, then Project, then agent settings, each in section order, then row order. */
export const SETTINGS_INDEX: ReadonlyArray<SettingEntry> = [
  app('notifications', 'Sound', 'Also the sound AgentWeave makes when it opens. Turn sound on or off.'),
  app('notifications', 'Volume', 'How loud notification sounds are, with a play button to hear it.'),
  app('notifications', 'An agent needs you', 'Notify when an agent asked a question or needs a permission decided.'),
  app('notifications', 'Work stalled or failed', 'Notify when work stalled or failed.'),
  app('notifications', 'An agent replied to you', 'Notify when an agent replied to a turn you started in a conversation.'),
  app('notifications', 'Work finished', 'Notify when something finished, such as a loop that emptied its queue.'),
  app('notifications', 'Question', 'Windows notification when an agent asked you something, or needs a permission decided.'),
  app('notifications', 'Failure', 'Windows notification when work stalled or failed.'),
  app('notifications', 'Done', 'Windows notification when something finished, such as a loop that emptied its queue.'),
  app('notifications', 'Reply', 'Windows notification when an agent replied to a turn you started in a conversation.'),
  app('appearance', 'Theme', 'Light or dark, for this window. Colour mode.'),
  app('connection', 'Hub address', 'The Hub this window reads and writes. Connected with a saved key; change the address or key.'),
  app('connection', 'Closing the window leaves AgentWeave running', 'The window closes and the Hub and its agents carry on, as before. Kept by this app, for this Hub.'),

  project('general', 'Name', 'How this project is named everywhere in AgentWeave. Rename the project.'),
  project('general', 'Folder', 'The project folder on this machine. Move it, relocate it, or delete the project.'),
  project('collaboration', 'Agents may start jobs, flows and loops', 'Off: an agent asking to start a job, flow or loop is refused, and you are asked instead.'),
  project('collaboration', 'Hop budget', 'How many agent-to-agent hops a chain may take before it pauses for you.'),
  project('collaboration', 'Deliveries per turn', 'The most queued messages one agent turn takes in.'),
  project('permissions', 'Default permissions', 'For every run whose conversation and agent have not chosen. Full access allows everything, Copilot and specification turns included.'),
  project('permissions', 'Granted reach', 'Under Workspace only: folders and hosts an agent may use beyond its workspace. A guardrail against mistakes, not a sandbox.'),
  project('budgets', 'Pause agents working on their own', 'Once the project has used this many tokens, turns you did not ask for wait. Token budget.'),
  project('budgets', 'After', 'How many tokens the project may use before agents working on their own pause.'),
  project('budgets', 'Agent budget', 'How many agents the project may hold before an agent asking for another is refused.'),
  project('checkpoints', 'Checkpoints', 'Checkpoint mode: whether conversations are checkpointed at all. Off, offered or automatic.'),
  project('checkpoints', 'Checkpoint at', 'How full the context gets before a checkpoint is written. Empty: the built-in point.'),
  project('checkpoints', 'Ask for notes at', 'Before the checkpoint, the agent is asked what the record cannot show. Must sit below the checkpoint point.'),
  project('checkpoints', 'Continue automatically', 'After a cut-over, start the new conversation first turn without waiting.'),
  project('checkpoints', 'Checkpoint runner', 'Who writes checkpoints. A cheap model is usually right.'),
  project('checkpoints', 'Checkpoint model', 'Only for writing checkpoints, in place of the runner own model.'),
  project('manager', 'Runner', 'The runner a manager job uses. None: each conversation own agent runner.'),
  project('manager', 'Model', 'The model a manager job uses, so it need not cost what the runner turns cost.'),
  project('manager', 'Fires', 'When a manager job fires: automatically, or only when you press its button.'),
  project('manager', 'Cost so far', 'Everything this manager job has spent in this project.'),
  project('checks', 'Checks', 'Commands run on the main branch plus a task work before approval merges it. Approval is refused until they pass.'),
  project('checks', 'Checks give way to me', 'Every process a check starts runs below normal priority, so your own work on this machine comes first.'),
  project('checks', 'Generated files', 'Files a command rebuilds from other files, such as a lockfile or a bundle. Rebuilt when only these conflict on landing.'),
  project('landing', 'Main branch', 'Approving a task merges its work here. Empty: nothing merges.'),
  project('landing', 'Land builds as pull requests', 'A build may put its approved work on one GitHub pull request instead of merging into the main branch.'),
  project('landing', 'One commit per build', 'With pull request landing on, the build branch carries a single commit holding the whole build.'),
  project('landing', "The PR's CI is the full check", 'A pull request build pushes approved work without running the landing checks here; the checks on GitHub decide.'),
  project('landing', 'CI check names', 'Comma-separated check names. Used only where GitHub marks no check required on the base branch.'),
  project('landing', 'CI asked every', 'While a counted check is pending, the Hub asks GitHub this often. Whole minutes, 1 to 60.'),
  project('landing', 'CI asking stops after', 'The CI cutoff: after a push, asking on the interval stops this long with a counted check still unconcluded.'),
  project('traces', 'Recorded', 'How many traces are recorded, and the oldest.'),
  project('traces', 'Keep traces for', 'Older spans are deleted on their own. Retention in days.'),
  project('traces', 'Send traces', 'Send traces to an OpenTelemetry collector. Needs an endpoint first.'),
  project('traces', 'Endpoint', 'The collector address traces are sent to. For example http://localhost:4318/v1/traces.'),
  project('traces', 'Headers', 'Sent with each trace, such as an API key. Values are never shown again.'),
  project('traces', 'Last sent', 'When traces were last sent to the collector.'),
  project('traces', 'Traces', 'The traces recorded in a range of time.'),
  project('traces', 'Download', 'One OTLP JSON file any OpenTelemetry tool can read. Export traces.'),
  project('traces', 'Clear', 'Deletes the traces from this Hub. Nothing already sent to a collector is touched.'),

  agent('agent', 'Name', 'How you and its peers address the agent. Renaming keeps its history under the new name.'),
  agent('agent', 'Description', 'For you. Agents never read it; the charter is where behaviour is stated.'),
  agent('agent', 'Last active', 'When the agent last did something.'),
  agent('agent', 'Charter', 'The behaviour contract read at the start of each of its turns.'),
  agent('agent', 'Review agents', "Copilot's own built-in agents this agent may consult before recording a review verdict."),
  agent('agent', 'GitHub server', "Gives this agent Copilot's built-in GitHub tools, read-only."),
  agent('running', 'Model', 'The coding agent and model each of its turns launches with. A conversation can still pick another for itself.'),
  agent('running', 'A permission decision', 'Under Ask me, how long it waits for you to allow or refuse an action. Running out refuses it.'),
  agent('running', 'An answer to a question', 'How long it waits for you to answer a question it asked.'),
  agent('permissions', 'Default permissions', 'Also what scheduled runs and peer messages get, since they have no composer to choose in.'),
  agent('permissions', 'Own granted reach', "Folders and hosts beyond its workspace under Workspace only. Off: it has the project's grants."),
  agent('permissions', "Read other agents' checkpoints", 'Summaries of where their conversations got to, from every conversation in this project.'),
  agent('permissions', 'Recall what a checkpoint cites', 'The original recorded output a checkpoint cites, word for word.'),
  agent('permissions', 'Accept or reject evidence', 'Accepted evidence is what lets approving a task merge its work.'),
  agent('permissions', 'Keep the specs true', 'Fold built changes into capabilities, edit capabilities, mark documents superseded and fix roadmap links.'),
  agent('checkpoints', 'Checkpoints', 'Checkpoint mode: whether its conversations are checkpointed at all.'),
  agent('checkpoints', 'Checkpoint at', 'The point its own context reaches before a checkpoint is written, in place of the project one.'),
  agent('checkpoints', 'Its checkpoints', 'Every checkpoint written from its conversations.'),
  agent('workspace', 'Working directory', 'The folder the agent works in.'),
  agent('workspace', 'Its own checkout', 'Whether the agent works in a checkout of its own.'),
]

/** A search result: the setting, and for an agent setting the project's agents it applies to. */
export interface SettingMatch {
  entry: SettingEntry
  /** Every typed word starts a word of the label (these are listed first). */
  inLabel: boolean
}

const wordsOf = (text: string): string[] => text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)

/** The matching rule: split what was typed into words; fewer than two characters lists nothing; a
 *  setting matches when every typed word starts some word of its label, description, section name
 *  or scope name. Label matches first; within each group, App, Project, agent, then section order,
 *  then row order (the index order). */
export function searchSettings(query: string): SettingMatch[] {
  const typed = wordsOf(query)
  if (typed.join('').length < 2) return []
  const matches: SettingMatch[] = []
  for (const entry of SETTINGS_INDEX) {
    const label = wordsOf(entry.label)
    const rest = wordsOf(`${entry.description} ${entry.sectionLabel} ${SCOPE_WORDS[entry.scope]}`)
    const starts = (words: string[], word: string) => words.some((w) => w.startsWith(word))
    if (!typed.every((word) => starts(label, word) || starts(rest, word))) continue
    matches.push({ entry, inLabel: typed.every((word) => starts(label, word)) })
  }
  return [...matches.filter((m) => m.inLabel), ...matches.filter((m) => !m.inLabel)]
}

/** The scope's own names, matched like any other word ('agent' finds the agent settings). */
const SCOPE_WORDS: Record<SettingScope, string> = { app: 'app', project: 'project', agent: 'agent' }

export const SCOPE_LABEL: Record<SettingScope, string> = { app: 'App', project: 'Project', agent: 'Agent' }

/** Where choosing a setting lands. `agent` is the agent an agent setting opens for. */
export function settingDestination(
  entry: SettingEntry,
  projectId: string | null,
  agentName?: string | null,
): WorkspaceDestination | null {
  if (entry.scope === 'app') return appSettingsDestination(projectId, entry.section as AppSettingsSection, entry.label)
  if (!projectId) return null
  if (entry.scope === 'project') return environmentDestination(projectId, entry.section as EnvironmentSection, entry.label)
  if (!agentName) return null
  return agentSettingsDestination(projectId, agentName, entry.section as AgentSettingsSection, entry.label)
}
