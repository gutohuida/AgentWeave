import type { CheckState } from '@/lib/checkState'
import type { TaskStatus } from '@/components/spec/page/model'
import { TASK_STATUS_LABEL } from '@/components/spec/page/model'
import type { CostCell } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'

/** The build view (spec `a-build-view-showing-every-task-and-run-of-a-build`): one screen per build,
 *  and the two compact summaries that open it. Everything the three surfaces count, word or order
 *  is derived here, so the side panel, the spec page and the full view cannot disagree (FR-11).
 *
 *  The `*Read` types are the route contract: what the build's read route must return. Nothing
 *  here fetches. */

// ── The route contract ──────────────────────────────────────────────────

/** `GET /projects/{id}/project/builds/{build_id}/tasks` (proposed): one build, its tasks with their
 *  runs and send-backs, and the runs of the build that worked no single task. The run set is
 *  `work_tally`'s for the build, so the totals derived here equal `/figures` (FR-8). */
export interface BuildRead {
  build: BuildHeaderRead
  /** Every task of the build exactly once: the document's declared tasks in declared order, then
   *  the tasks added to the build later (Hub-filed fixes, amendments) in the order they were made. */
  tasks: BuildTaskRead[]
  /** Runs counted to the build but to none of its tasks: a lead's turns, the mender on the build's
   *  loop. Listed so the totals reconcile with the figures; oldest first. */
  build_runs: BuildRunRead[]
  /** When the Hub answered (UTC). "Updated 12s ago" is measured from here. */
  as_of: string
}

export type BuildState = 'running' | 'stopped' | 'finished'

export interface BuildHeaderRead {
  id: string
  document_id: string
  document_title: string
  document_path: string | null
  state: BuildState
  level: string | null
  created_at: string
  stopped_at: string | null
  stop_reason: string | null
  /** What the build needs from the operator (`hub/hub/build_needs.py`, the build list's own):
   *  "stopped" when it stopped before its work was done, otherwise its first task's need. */
  needs_operator: BuildNeedsRead | null
  /** The operator dismissed it from the sidebar and its needs are still the ones dismissed. */
  attention_dismissed: boolean
}

export interface BuildTaskRead {
  id: string
  /** The readable reference ("AW-164"); null for a task from before readable ids. */
  ref: string | null
  title: string | null
  status: TaskStatus
  /** The Hub's stage (`task_stage.py`) and latest check; when present the row words these in place
   *  of the raw status. */
  stage?: string | null
  check_state?: CheckState | null
  /** False for a task added to the build later, not declared by its document. */
  declared: boolean
  builder: string | null
  checker: string | null
  /** The task's last status change. */
  last_change_at: string | null
  /** Why the task waits on the operator, or null. */
  needs_operator: NeedsOperatorRead | null
  /** The requirements the task serves, each with its latest evidence's review state. */
  requirements: RequirementEvidenceRead[]
  /** Every run that worked the task, oldest first by `started_at`. */
  runs: BuildRunRead[]
  /** Every move to `revision_needed` or `rejected`, in `task_transitions.sequence` order. */
  send_backs: SendBackRead[]
}

export interface NeedsOperatorRead {
  /** `stalled`: an open stall; `gave-up`: the mender gave up on it; `question`: a blocking question. */
  kind: 'stalled' | 'gave-up' | 'question'
  /** The stall's reason or the question, in the Hub's words. */
  text: string
}

/** A build's need: a task's, or `stopped`, the build's own when it stopped before its work was done. */
export interface BuildNeedsRead {
  kind: 'stopped' | NeedsOperatorRead['kind']
  text: string
}

/** `missing`: the task serves the requirement and no evidence was recorded for it. */
export type EvidenceReview = 'accepted' | 'awaiting' | 'rejected' | 'held' | 'missing'

export interface RequirementEvidenceRead {
  /** "FR-3". */
  identifier: string
  evidence: EvidenceReview
}

/** What a run was to the task: `work_tally.run_role`, in the view's words. `lead` only appears
 *  among `build_runs`. */
export type RunRole = 'build' | 'review' | 'mender' | 'lead'

/** `measured`: priced; `unpriced`: usage reported, no price; `unreported`: finished with no usage
 *  row at all; `running`: not finished. */
export type RunCostState = 'measured' | 'unpriced' | 'unreported' | 'running'

export interface BuildRunRead {
  id: string
  role: RunRole
  agent: string
  model: string | null
  conversation_id: string | null
  started_at: string
  ended_at: string | null
  /** The run's own status: running, completed, failed, stopped, cancelled, interrupted. */
  status: string
  cost_state: RunCostState
  /** Set only when `cost_state` is `measured`. Never 0 for an unmeasured cost. */
  cost_usd_micros: number | null
  tokens: { input: number | null; output: number | null; cache_read: number | null; cache_write: number | null } | null
  /** The task moves this run made, in sequence order (empty when it made none). */
  moves: Array<{ from: string | null; to: string }>
  /** For a mender run: the stall it worked and how that ended. */
  mend: { cause: string; outcome: string | null; detail: string | null } | null
}

export interface SendBackRead {
  sequence: number
  at: string
  to: 'revision_needed' | 'rejected'
  /** Who sent it back: a reviewing agent, the landing checks, or the operator. */
  by: { kind: 'agent'; agent: string } | { kind: 'checks' } | { kind: 'operator' }
  run_id: string | null
  /** defect, broken-check, evidence-only, flaky, merge-needed, regression; null when none given. */
  reason_class: string | null
  /** The reviewer's reason. */
  reason: string
  /** The Hub's note beside it (which evidence was rejected, which landing batch). */
  note: string
}

// ── Words, icons ────────────────────────────────────────────────────────

/** A task's state in words and an icon shape, never colour alone (FR-13, P21). The words are the
 *  spec page's (`TASK_STATUS_LABEL`), so the task reads the same on both. */
export const TASK_STATE: Record<TaskStatus, { label: string; icon: string }> = {
  pending: { label: TASK_STATUS_LABEL.pending, icon: 'circle_dashed' },
  assigned: { label: TASK_STATUS_LABEL.assigned, icon: 'circle' },
  in_progress: { label: TASK_STATUS_LABEL.in_progress, icon: 'hammer' },
  completed: { label: TASK_STATUS_LABEL.completed, icon: 'package_check' },
  under_review: { label: TASK_STATUS_LABEL.under_review, icon: 'fact_check' },
  revision_needed: { label: TASK_STATUS_LABEL.revision_needed, icon: 'undo' },
  approved: { label: TASK_STATUS_LABEL.approved, icon: 'check_circle' },
  rejected: { label: TASK_STATUS_LABEL.rejected, icon: 'remove_circle' },
}

export function taskStateOf(status: string): { label: string; icon: string } {
  return TASK_STATE[status as TaskStatus] ?? { label: status.replace(/_/g, ' '), icon: 'circle' }
}

export const BUILD_STATE: Record<BuildState, { label: string; icon: string }> = {
  running: { label: 'Running', icon: 'play_arrow' },
  finished: { label: 'Finished', icon: 'check_circle' },
  stopped: { label: 'Stopped', icon: 'stop_circle' },
}

export const EVIDENCE: Record<EvidenceReview, { label: string; icon: string; meaning: string }> = {
  accepted: { label: 'accepted', icon: 'check_circle', meaning: 'Its evidence was accepted' },
  awaiting: { label: 'awaiting', icon: 'hourglass', meaning: 'Its evidence waits for a reviewer' },
  rejected: { label: 'rejected', icon: 'x', meaning: 'Its evidence was rejected' },
  held: { label: 'held', icon: 'pause', meaning: 'Set aside by a send-back: it needs new evidence' },
  missing: { label: 'no evidence', icon: 'circle_dashed', meaning: 'No evidence was recorded for it' },
}

/** The order evidence states are listed in: what needs a look first. */
const EVIDENCE_RANK: EvidenceReview[] = ['rejected', 'missing', 'held', 'awaiting', 'accepted']

export const ROLE: Record<RunRole, { label: string; icon: string }> = {
  build: { label: 'Build', icon: 'hammer' },
  review: { label: 'Review', icon: 'fact_check' },
  mender: { label: 'Mender', icon: 'build' },
  lead: { label: 'Lead', icon: 'route' },
}

export const NEEDS: Record<NeedsOperatorRead['kind'], string> = {
  stalled: 'Stalled',
  'gave-up': 'The mender gave up',
  question: 'A question for you',
}

const REASON_CLASS: Record<string, string> = {
  defect: 'Defect',
  'broken-check': 'Broken check',
  'evidence-only': 'Evidence only',
  flaky: 'Flaky',
  'merge-needed': 'Needs a merge',
  regression: 'Regression',
}

export function reasonClassLabel(value: string | null): string | null {
  if (!value) return null
  return REASON_CLASS[value] ?? value.charAt(0).toUpperCase() + value.slice(1).replace(/-/g, ' ')
}

export function sentBackBy(by: SendBackRead['by']): string {
  if (by.kind === 'agent') return by.agent
  if (by.kind === 'checks') return 'the landing checks'
  return 'you'
}

/** The reviewer's words, without the Hub's "Sent back as <class>:" prefix the class chip already says. */
export function sendBackText(sendBack: SendBackRead): string {
  const reason = sendBack.reason.replace(/^Sent back( as [\w-]+)?:\s*/i, '').trim()
  // The landing checks name their check run by id ("…failed on check run chk-63a5…"); the id
  // means nothing on screen, and differs between otherwise identical send-backs (P17).
  const text = (reason || sendBack.note.trim()).replace(/\s+on check run chk-[0-9a-f]+/gi, '')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** What a run did to its task, in words, and how it reads: `good` moved the task on, `bad` failed
 *  or sent it back, `live` is still running, `quiet` made no decision. */
export type MoveTone = 'good' | 'bad' | 'live' | 'quiet'
export interface MoveWords {
  text: string
  tone: MoveTone
}

const FAILED_STATUSES = new Set(['failed', 'error'])
const STOPPED_STATUSES = new Set(['stopped', 'cancelled', 'interrupted'])

export function moveOf(run: BuildRunRead): MoveWords {
  if (run.status === 'running') return { text: 'Working now', tone: 'live' }
  if (run.mend) {
    if (run.mend.outcome === 'fixed') return { text: 'Fixed the stall', tone: 'good' }
    if (run.mend.outcome === 'gave_up') return { text: 'Gave up on the stall', tone: 'bad' }
    if (run.mend.outcome === 'resolved') return { text: 'Stall cleared itself', tone: 'quiet' }
    return { text: 'Looked at a stall', tone: 'quiet' }
  }
  if (FAILED_STATUSES.has(run.status)) return { text: 'Failed', tone: 'bad' }
  if (STOPPED_STATUSES.has(run.status)) return { text: 'Stopped', tone: 'bad' }
  const last = run.moves[run.moves.length - 1]
  if (!last) return { text: run.role === 'review' ? 'Made no decision' : 'Made no move', tone: 'quiet' }
  switch (last.to) {
    case 'completed':
      return { text: 'Handed in for review', tone: 'good' }
    case 'approved':
      return { text: 'Approved', tone: 'good' }
    case 'revision_needed':
      return { text: 'Sent it back', tone: 'bad' }
    case 'rejected':
      return { text: 'Rejected it', tone: 'bad' }
    case 'in_progress':
      return { text: 'Started, not handed in', tone: 'quiet' }
    case 'under_review':
      return { text: 'Took it for review', tone: 'quiet' }
    case 'assigned':
    case 'pending':
      return { text: 'Let it go unfinished', tone: 'quiet' }
    default:
      return { text: `Moved it to ${taskStateOf(last.to).label.toLowerCase()}`, tone: 'quiet' }
  }
}

const TONE_RANK: Record<MoveTone, number> = { bad: 3, live: 2, quiet: 1, good: 0 }

/** The worst of several moves: a group shows its worst outcome, never its best (P12). */
export function worstMove(moves: MoveWords[]): MoveWords {
  return moves.reduce((worst, m) => (TONE_RANK[m.tone] > TONE_RANK[worst.tone] ? m : worst), moves[0] ?? { text: '', tone: 'quiet' })
}

// ── Time and cost ───────────────────────────────────────────────────────

/** A run's working time in seconds; a running run counts up to `now`. */
export function runSeconds(run: BuildRunRead, now: Date): number {
  const start = hubDate(run.started_at).getTime()
  const end = run.ended_at ? hubDate(run.ended_at).getTime() : run.status === 'running' ? now.getTime() : start
  return Math.max(0, Math.round((end - start) / 1000))
}

/** A run's own cost cell. Unpriced is never zero; a run still going, or one that reported no
 *  usage, has no figure. */
export function runCost(run: BuildRunRead): CostCell {
  if (run.cost_state === 'measured' && run.cost_usd_micros != null) return { kind: 'cost', usd: run.cost_usd_micros / 1_000_000 }
  if (run.cost_state === 'unpriced') return { kind: 'unpriced' }
  return { kind: 'none' }
}

/** A total over runs: what was priced, and how many runs it leaves out and why. */
export interface CostTotal {
  usd: number
  priced: number
  unpriced: number
  /** Finished runs with no usage reported: also left out of `usd`. */
  unreported: number
  running: number
}

export function costTotal(runs: BuildRunRead[]): CostTotal {
  const t: CostTotal = { usd: 0, priced: 0, unpriced: 0, unreported: 0, running: 0 }
  for (const run of runs) {
    if (run.cost_state === 'measured' && run.cost_usd_micros != null) {
      t.usd += run.cost_usd_micros / 1_000_000
      t.priced += 1
    } else if (run.cost_state === 'unpriced') t.unpriced += 1
    else if (run.cost_state === 'running') t.running += 1
    else t.unreported += 1
  }
  return t
}

/** A total as a cell: a figure when anything was priced; `unpriced` when the only finished runs
 *  went unmeasured (FR-4); nothing when no run has finished. */
export function totalCell(t: CostTotal): CostCell {
  if (t.priced > 0) return { kind: 'cost', usd: t.usd }
  if (t.unpriced > 0) return { kind: 'unpriced' }
  return { kind: 'none' }
}

/** What a total leaves out, said in full ("Leaves out 2 unpriced runs and 1 still running"), or null. */
export function leftOut(t: CostTotal): string | null {
  const parts: string[] = []
  if (t.priced > 0 && t.unpriced > 0) parts.push(`${t.unpriced} unpriced run${t.unpriced === 1 ? '' : 's'}`)
  if (t.unreported > 0) parts.push(`${t.unreported} run${t.unreported === 1 ? '' : 's'} that reported no usage`)
  if (t.priced > 0 && t.running > 0) parts.push(`${t.running} still running`)
  if (!parts.length) return null
  return `Leaves out ${parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts[0]}`
}

/** The short form beside a figure: "+2 unpriced". Null when nothing priced is left out. */
export function leftOutShort(t: CostTotal): string | null {
  if (t.priced > 0 && t.unpriced > 0) return `+${t.unpriced} unpriced`
  return null
}

// ── Timeline ────────────────────────────────────────────────────────────

export interface TimelineRun {
  kind: 'run'
  key: string
  run: BuildRunRead
  /** "Build 2": the role and its ordinal within the task. Also the run button's name. */
  label: string
  latest: boolean
  move: MoveWords
  cost: CostCell
  seconds: number
}

export interface TimelineSendBack {
  kind: 'send-back'
  key: string
  sendBack: SendBackRead
  /** "Send-back 2". */
  label: string
  by: string
  reasonClass: string | null
  text: string
}

/** A stretch of the timeline that repeats, shown as one counted row that expands (P12): mender
 *  turns back to back, one agent building again and again, or a build and the same send-back in
 *  turn (a build bounced by failing checks forty times reads as one row, not eighty). */
export interface TimelineGroup {
  kind: 'group'
  key: string
  /** "Mender ×3", "Build ×44". */
  label: string
  /** What repeated, in words: "Build 3 to Build 45, each sent back by the landing checks". */
  detail: string
  /** The send-backs' reason, when every one in the group gave the same. */
  reason: string | null
  items: Array<TimelineRun | TimelineSendBack>
  runs: TimelineRun[]
  sendBacks: number
  move: MoveWords
  cost: CostTotal
  seconds: number
}

export type TimelineItem = TimelineRun | TimelineSendBack | TimelineGroup

/** Runs and send-backs merged on one clock, oldest first: a run at its start, a send-back at the
 *  moment it was made, so a reviewer's send-back sits after the review that made it and before the
 *  build it caused. Repeated mender runs with nothing between them collapse into a group. */
export function timelineOf(runs: BuildRunRead[], sendBacks: SendBackRead[], now: Date): TimelineItem[] {
  type Event = { at: number; order: number; run?: BuildRunRead; sendBack?: SendBackRead }
  const events: Event[] = [
    ...runs.map((run, i) => ({ at: hubDate(run.started_at).getTime(), order: i, run })),
    ...sendBacks.map((sendBack, i) => ({ at: hubDate(sendBack.at).getTime(), order: runs.length + i, sendBack })),
  ]
  events.sort((a, b) => a.at - b.at || a.order - b.order)

  const counts: Record<string, number> = {}
  const latestId = runs.length ? [...runs].sort((a, b) => hubDate(b.started_at).getTime() - hubDate(a.started_at).getTime())[0]!.id : null
  const flat: Array<TimelineRun | TimelineSendBack> = events.map((e) => {
    if (e.run) {
      const role = ROLE[e.run.role]
      counts[e.run.role] = (counts[e.run.role] ?? 0) + 1
      return {
        kind: 'run',
        key: e.run.id,
        run: e.run,
        label: `${role.label} ${counts[e.run.role]}`,
        latest: e.run.id === latestId,
        move: moveOf(e.run),
        cost: runCost(e.run),
        seconds: runSeconds(e.run, now),
      }
    }
    const sb = e.sendBack!
    counts['send-back'] = (counts['send-back'] ?? 0) + 1
    return {
      kind: 'send-back',
      key: `sb-${sb.sequence}`,
      sendBack: sb,
      label: `Send-back ${counts['send-back']}`,
      by: sentBackBy(sb.by),
      reasonClass: reasonClassLabel(sb.reason_class),
      text: sendBackText(sb),
    }
  })

  const out: TimelineItem[] = []
  for (let i = 0; i < flat.length; ) {
    const found = repeatAt(flat, i)
    if (found) {
      out.push(groupOf(flat.slice(i, i + found.period * found.times), found.times))
      i += found.period * found.times
      continue
    }
    out.push(flat[i]!)
    i++
  }
  return out
}

/** What makes two timeline lines "the same" for grouping: a run's role and agent; a send-back's
 *  sender, class and reason. */
function signatureOf(item: TimelineRun | TimelineSendBack): string {
  if (item.kind === 'run') return `run:${item.run.role}:${item.run.agent}`
  const by = item.sendBack.by
  return `send-back:${by.kind}:${by.kind === 'agent' ? by.agent : ''}:${item.sendBack.reason_class ?? ''}:${item.text}`
}

/** The repeat starting at `i`, if any: a pattern of one line (a run) or two (a run and a
 *  send-back, either way round) seen at least three times in a row; mender turns group from two. */
function repeatAt(flat: Array<TimelineRun | TimelineSendBack>, i: number): { period: number; times: number } | null {
  const sig = flat.map(signatureOf)
  const timesOf = (period: number): number => {
    let times = 1
    while (i + (times + 1) * period <= flat.length && sig.slice(i + times * period, i + (times + 1) * period).every((s, k) => s === sig[i + k])) times++
    return times
  }
  let best: { period: number; times: number } | null = null
  for (const period of [1, 2]) {
    const pattern = flat.slice(i, i + period)
    if (pattern.length < period || !pattern.some((p) => p.kind === 'run')) continue
    if (period === 2 && sig[i] === sig[i + 1]) continue
    const times = timesOf(period)
    const mender = period === 1 && pattern[0]!.kind === 'run' && pattern[0]!.run.role === 'mender'
    if (times < (mender ? 2 : 3)) continue
    if (!best || period * times > best.period * best.times) best = { period, times }
  }
  return best
}

function groupOf(items: Array<TimelineRun | TimelineSendBack>, times: number): TimelineGroup {
  const runs = items.filter((i): i is TimelineRun => i.kind === 'run')
  const sendBacks = items.filter((i): i is TimelineSendBack => i.kind === 'send-back')
  const role = ROLE[runs[0]!.run.role].label
  const range = runs.length > 1 ? `${runs[0]!.label} to ${runs[runs.length - 1]!.label}` : runs[0]!.label
  const reasons = new Set(sendBacks.map((s) => s.text))
  const first = sendBacks[0]
  // The label stays short ("Build ×44") to fit the label column; `detail` says what repeated.
  const label = `${role} ×${times}`
  let detail: string
  let move: MoveWords
  if (!first) {
    detail = runs[0]!.run.role === 'mender' ? 'repeated mender turns, shown as one' : `${range}, each by ${runs[0]!.run.agent}`
    move = worstMove(runs.map((r) => r.move))
  } else {
    detail = `${range}, each sent back by ${first.by}`
    move = { text: `Sent back ${sendBacks.length} times`, tone: 'bad' }
  }
  return {
    kind: 'group',
    key: `group-${items[0]!.key}`,
    label,
    detail,
    reason: first && reasons.size === 1 ? first.text : null,
    items,
    runs,
    sendBacks: sendBacks.length,
    move,
    cost: costTotal(runs.map((r) => r.run)),
    seconds: runs.reduce((n, r) => n + r.seconds, 0),
  }
}

// ── Figures ─────────────────────────────────────────────────────────────

export interface TaskFigures {
  runs: number
  cost: CostTotal
  seconds: number
  sendBacks: number
  /** Counts of the task's requirements by evidence state, worst first. */
  evidence: Array<{ state: EvidenceReview; count: number }>
}

export function taskFigures(task: BuildTaskRead, now: Date): TaskFigures {
  return {
    runs: task.runs.length,
    cost: costTotal(task.runs),
    seconds: task.runs.reduce((n, r) => n + runSeconds(r, now), 0),
    sendBacks: task.send_backs.length,
    evidence: evidenceCounts(task.requirements),
  }
}

export function evidenceCounts(requirements: RequirementEvidenceRead[]): Array<{ state: EvidenceReview; count: number }> {
  return EVIDENCE_RANK.map((state) => ({ state, count: requirements.filter((r) => r.evidence === state).length })).filter((c) => c.count > 0)
}

/** "6 accepted", or the states that need a look: "1 rejected · 1 awaiting". */
export function evidenceSummary(requirements: RequirementEvidenceRead[]): string {
  if (!requirements.length) return 'none named'
  const counts = evidenceCounts(requirements)
  if (counts.length === 1) return `${counts[0]!.count} ${EVIDENCE[counts[0]!.state].label}`
  return counts
    .filter((c) => c.state !== 'accepted')
    .map((c) => `${c.count} ${EVIDENCE[c.state].label}`)
    .join(' · ')
}

export interface BuildTotals {
  tasks: number
  approved: number
  runs: number
  cost: CostTotal
  /** Seconds of agent work: every run's duration added up (not the build's wall time). */
  seconds: number
  sendBacks: number
  /** Tasks that wait on the operator. */
  needsOperator: number
  /** Runs working now. */
  live: number
}

/** The build's totals over every run of the build (its tasks' and its own), the numbers the
 *  figures route reports for it (FR-8). */
export function buildTotals(read: BuildRead, now: Date): BuildTotals {
  const runs = [...read.tasks.flatMap((t) => t.runs), ...read.build_runs]
  return {
    tasks: read.tasks.length,
    approved: read.tasks.filter((t) => t.status === 'approved').length,
    runs: runs.length,
    cost: costTotal(runs),
    seconds: runs.reduce((n, r) => n + runSeconds(r, now), 0),
    sendBacks: read.tasks.reduce((n, t) => n + t.send_backs.length, 0),
    needsOperator: read.tasks.filter((t) => t.needs_operator).length,
    live: runs.filter((r) => r.status === 'running').length,
  }
}

export interface SummaryTask {
  id: string
  /** What the address names the task by: its reference, or its id when it has none. */
  key: string
  ref: string | null
  title: string
  status: TaskStatus
  needsOperator: boolean
}

/** What a compact summary shows, derived from the same totals as the full view (FR-10, FR-11). */
export interface BuildSummaryModel {
  id: string
  title: string
  state: BuildState
  totals: BuildTotals
  tasks: SummaryTask[]
}

export function summaryOf(read: BuildRead, now: Date): BuildSummaryModel {
  return {
    id: read.build.id,
    title: read.build.document_title,
    state: read.build.state,
    totals: buildTotals(read, now),
    tasks: read.tasks.map((t) => ({
      id: t.id,
      key: taskKey(t),
      ref: t.ref,
      title: t.title ?? 'A task with no title',
      status: t.status,
      needsOperator: Boolean(t.needs_operator),
    })),
  }
}

/** Who checks the task: the one named, else whoever reviewed it last (`named` false). */
export function checkerOf(task: BuildTaskRead): { name: string | null; named: boolean } {
  if (task.checker) return { name: task.checker, named: true }
  const reviewer = [...task.runs].reverse().find((r) => r.role === 'review')?.agent ?? null
  return { name: reviewer, named: false }
}

/** One sentence on what of the build waits on the operator ("PNSOS-3 is stalled"), or null. */
export function needsLine(read: BuildRead): string | null {
  const waiting = read.tasks.filter((t) => t.needs_operator)
  if (read.build.needs_operator?.kind === 'stopped') return stoppedLine(read)
  if (!waiting.length) return null
  const first = waiting[0]!
  const what = { stalled: 'is stalled', 'gave-up': 'was given up on by the mender', question: 'has a question for you' }[first.needs_operator!.kind]
  return waiting.length === 1 ? `${taskName(first)} ${what}` : `${waiting.length} tasks need you, ${taskName(first)} first`
}

/** The build stopped before its work was done: what it says ("Stopped with 2 tasks not done"). */
export function stoppedLine(read: BuildRead): string {
  const open = read.tasks.filter((t) => t.status !== 'approved' && t.status !== 'rejected').length
  return open ? `Stopped with ${open} ${open === 1 ? 'task' : 'tasks'} not done` : 'Stopped before its work was done'
}

export function taskKey(task: Pick<BuildTaskRead, 'id' | 'ref'>): string {
  return task.ref ?? task.id
}

/** What a task is called on screen and in its row button's name. */
export function taskName(task: Pick<BuildTaskRead, 'ref' | 'title'>): string {
  return task.ref ?? task.title ?? 'a task with no reference'
}

// ── Filter and address ──────────────────────────────────────────────────

export type TaskFilter = 'all' | 'needs-you'

export function filterTasks(tasks: BuildTaskRead[], filter: TaskFilter): BuildTaskRead[] {
  return filter === 'needs-you' ? tasks.filter((t) => t.needs_operator) : tasks
}

/** The view's address beyond the build: the task expanded, the run whose trace is open, the filter. */
export interface BuildAddress {
  task: string | null
  run: string | null
  filter: TaskFilter
}

export const NO_ADDRESS: BuildAddress = { task: null, run: null, filter: 'all' }

/** `task=<ref>&run=<id>&filter=needs-you`, empty parts left out. */
export function addressQuery(address: BuildAddress): string {
  const q = new URLSearchParams()
  if (address.task) q.set('task', address.task)
  if (address.run) q.set('run', address.run)
  if (address.filter !== 'all') q.set('filter', address.filter)
  return q.toString()
}

export function parseAddress(query: string): BuildAddress {
  const q = new URLSearchParams(query)
  return { task: q.get('task') || null, run: q.get('run') || null, filter: q.get('filter') === 'needs-you' ? 'needs-you' : 'all' }
}

/** The task a run belongs to, so an address naming only a run still opens at its task. */
export function taskOfRun(read: BuildRead, runId: string): BuildTaskRead | null {
  return read.tasks.find((t) => t.runs.some((r) => r.id === runId)) ?? null
}
